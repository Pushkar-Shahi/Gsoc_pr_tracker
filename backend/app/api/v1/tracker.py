import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import httpx

from app.db.database import get_db
from app.models.models import Task, Issue, Repository, PlatformSettings, AuditLog
from app.schemas.schemas import TaskRead
from app.services.github_client import GitHubClient
from app.services.background_worker import sync_task_pr_status

router = APIRouter(prefix="/tracker", tags=["Contribution Tracker"])
logger = logging.getLogger(__name__)

async def get_github_client(db: AsyncSession) -> GitHubClient:
    stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    res = await db.execute(stmt)
    settings_obj = res.scalar_one_or_none()
    token = settings_obj.github_token if settings_obj else None
    return GitHubClient(token=token)

class TrackItemRequest(BaseModel):
    url: str = Field(..., description="GitHub Issue or PR URL (e.g. https://github.com/owner/repo/pull/123 or https://github.com/owner/repo/issues/456)")

@router.post("/track", response_model=TaskRead)
async def track_item(payload: TrackItemRequest, db: AsyncSession = Depends(get_db)):
    """
    Accepts any GitHub Pull Request or Issue URL (or owner/repo#number),
    fetches live status from GitHub, and adds it to the active tracker.
    """
    raw_url = payload.url.strip()
    gh = await get_github_client(db)

    # 1. Parse URL patterns
    # Pattern A: Pull Request
    pr_match = re.search(r'github\.com/([^/]+)/([^/]+)/pull/(\d+)', raw_url, re.IGNORECASE)
    # Pattern B: Issue
    issue_match = re.search(r'github\.com/([^/]+)/([^/]+)/issues/(\d+)', raw_url, re.IGNORECASE)
    # Pattern C: owner/repo#number
    shorthand_match = re.search(r'^([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)#(\d+)$', raw_url)

    owner = None
    repo_name = None
    item_number = None
    is_pr = False

    if pr_match:
        owner = pr_match.group(1)
        repo_name = pr_match.group(2)
        item_number = int(pr_match.group(3))
        is_pr = True
    elif issue_match:
        owner = issue_match.group(1)
        repo_name = issue_match.group(2)
        item_number = int(issue_match.group(3))
        is_pr = False
    elif shorthand_match:
        owner = shorthand_match.group(1)
        repo_name = shorthand_match.group(2)
        item_number = int(shorthand_match.group(3))
        # Probe PR first, then issue
        pr_probe = await gh.get_pull_request(owner, repo_name, item_number)
        if pr_probe:
            is_pr = True
        else:
            is_pr = False
    else:
        raise HTTPException(
            status_code=400,
            detail="Could not parse GitHub URL. Expected format: 'https://github.com/owner/repo/pull/123' or 'https://github.com/owner/repo/issues/456'"
        )

    # 2. Ensure Repository exists in DB
    full_name = f"{owner}/{repo_name}"
    repo_stmt = select(Repository).where(Repository.full_name.ilike(full_name))
    repo_res = await db.execute(repo_stmt)
    repository = repo_res.scalar_one_or_none()

    if not repository:
        repo_data = await gh.get_repository(owner, repo_name)
        if not repo_data:
            raise HTTPException(status_code=404, detail=f"GitHub repository '{full_name}' not found or unreachable.")
        
        repository = Repository(
            owner=repo_data["owner"]["login"],
            name=repo_data["name"],
            full_name=repo_data["full_name"],
            html_url=repo_data["html_url"],
            default_branch=repo_data.get("default_branch", "main"),
            primary_language=repo_data.get("language"),
            license_spdx=repo_data.get("license", {}).get("spdx_id") if repo_data.get("license") else None,
            license_name=repo_data.get("license", {}).get("name") if repo_data.get("license") else None,
            stars_count=repo_data.get("stargazers_count", 0),
            open_issues_count=repo_data.get("open_issues_count", 0),
            is_fork=repo_data.get("fork", False),
            is_archived=repo_data.get("archived", False)
        )
        db.add(repository)
        await db.commit()
        await db.refresh(repository)

    # 3. Handle Pull Request Tracking
    if is_pr:
        pr_data = await gh.get_pull_request(owner, repo_name, item_number)
        if not pr_data:
            raise HTTPException(status_code=404, detail=f"Pull request #{item_number} not found in {full_name}")

        # PRs in GitHub are also issues with same number
        issue_stmt = select(Issue).where(
            Issue.repository_id == repository.id,
            Issue.issue_number == item_number
        )
        issue_res = await db.execute(issue_stmt)
        issue = issue_res.scalar_one_or_none()

        title = pr_data.get("title", f"Pull Request #{item_number}")
        body = pr_data.get("body", "")
        author = pr_data.get("user", {}).get("login", "unknown")
        html_url = pr_data.get("html_url")
        pr_state = pr_data.get("state", "open")
        is_merged = pr_data.get("merged", False)

        if not issue:
            issue = Issue(
                repository_id=repository.id,
                github_id=pr_data.get("id", item_number),
                issue_number=item_number,
                title=title,
                body=body,
                author=author,
                html_url=html_url,
                state="closed" if (is_merged or pr_state == "closed") else "open",
                labels=pr_data.get("labels", []),
                assignees=pr_data.get("assignees", []),
                comments_count=pr_data.get("comments", 0)
            )
            db.add(issue)
            await db.commit()
            await db.refresh(issue)
        else:
            issue.title = title
            issue.state = "closed" if (is_merged or pr_state == "closed") else "open"

        # Check existing task
        task_stmt = select(Task).options(
            selectinload(Task.issue).selectinload(Issue.repository)
        ).where(
            Task.issue_id == issue.id
        )
        t_res = await db.execute(task_stmt)
        task = t_res.scalar_one_or_none()

        workflow_state = "MERGED_OR_CLOSED" if (is_merged or pr_state == "closed") else "PR_CREATED"

        branch_name = pr_data.get("head", {}).get("ref") or f"pr-{item_number}"

        if not task:
            task = Task(
                issue_id=issue.id,
                pr_number=item_number,
                pr_url=html_url,
                pr_state=pr_state,
                pr_merged=is_merged,
                branch_name=branch_name,
                workflow_state=workflow_state
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
        else:
            task.pr_number = item_number
            task.pr_url = html_url
            task.pr_state = pr_state
            task.pr_merged = is_merged
            task.branch_name = branch_name
            task.workflow_state = workflow_state

        # Perform live status sync (CI runs + reviews)
        try:
            await sync_task_pr_status(task, db, gh)
        except Exception as e:
            logger.warning(f"Initial PR sync warning for {full_name}#{item_number}: {e}")

        audit = AuditLog(
            task_id=task.id,
            issue_id=issue.id,
            action="TRACKER_PR_ADDED",
            actor="USER",
            details={"repo": full_name, "pr_number": item_number, "url": html_url}
        )
        db.add(audit)
        await db.commit()

        # Re-fetch task with relationships
        res_stmt = select(Task).options(
            selectinload(Task.issue).selectinload(Issue.repository)
        ).where(Task.id == task.id)
        final_res = await db.execute(res_stmt)
        return final_res.scalar_one()

    # 4. Handle Issue Tracking
    else:
        issue_data = await gh.get_issue(owner, repo_name, item_number)
        if not issue_data:
            raise HTTPException(status_code=404, detail=f"Issue #{item_number} not found in {full_name}")

        issue_stmt = select(Issue).where(
            Issue.repository_id == repository.id,
            Issue.issue_number == item_number
        )
        issue_res = await db.execute(issue_stmt)
        issue = issue_res.scalar_one_or_none()

        title = issue_data.get("title", f"Issue #{item_number}")
        body = issue_data.get("body", "")
        author = issue_data.get("user", {}).get("login", "unknown")
        html_url = issue_data.get("html_url")
        state = issue_data.get("state", "open")

        if not issue:
            issue = Issue(
                repository_id=repository.id,
                github_id=issue_data.get("id", item_number),
                issue_number=item_number,
                title=title,
                body=body,
                author=author,
                html_url=html_url,
                state=state,
                labels=issue_data.get("labels", []),
                assignees=issue_data.get("assignees", []),
                comments_count=issue_data.get("comments", 0)
            )
            db.add(issue)
            await db.commit()
            await db.refresh(issue)
        else:
            issue.title = title
            issue.state = state
            issue.labels = issue_data.get("labels", issue.labels)
            issue.assignees = issue_data.get("assignees", issue.assignees)
            issue.comments_count = issue_data.get("comments", issue.comments_count)

        # Check existing task
        task_stmt = select(Task).options(
            selectinload(Task.issue).selectinload(Issue.repository)
        ).where(
            Task.issue_id == issue.id
        )
        t_res = await db.execute(task_stmt)
        task = t_res.scalar_one_or_none()

        if not task:
            task = Task(
                issue_id=issue.id,
                workflow_state="TRACKING" if state == "open" else "MERGED_OR_CLOSED"
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
        else:
            if state != "open":
                task.workflow_state = "MERGED_OR_CLOSED"

        audit = AuditLog(
            task_id=task.id,
            issue_id=issue.id,
            action="TRACKER_ISSUE_ADDED",
            actor="USER",
            details={"repo": full_name, "issue_number": item_number, "url": html_url}
        )
        db.add(audit)
        await db.commit()

        res_stmt = select(Task).options(
            selectinload(Task.issue).selectinload(Issue.repository)
        ).where(Task.id == task.id)
        final_res = await db.execute(res_stmt)
        return final_res.scalar_one()

@router.post("/sync-all")
async def sync_all_tracked_items(db: AsyncSession = Depends(get_db)):
    """
    Synchronizes all tracked PRs and issues with real-time GitHub status.
    """
    gh = await get_github_client(db)

    # 1. Sync PRs
    pr_tasks_stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.pr_number.isnot(None))
    res = await db.execute(pr_tasks_stmt)
    pr_tasks = res.scalars().all()

    synced_prs = 0
    for task in pr_tasks:
        try:
            await sync_task_pr_status(task, db, gh)
            synced_prs += 1
        except Exception as e:
            logger.error(f"Error syncing tracked PR {task.id}: {e}")

    # 2. Sync Tracked Issues (tasks without pr_number)
    issue_tasks_stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.pr_number.is_(None))
    i_res = await db.execute(issue_tasks_stmt)
    tracked_issue_tasks = i_res.scalars().all()

    synced_issues = 0
    for itask in tracked_issue_tasks:
        if itask.issue:
            iss = itask.issue
            try:
                live = await gh.get_issue(iss.repository.owner, iss.repository.name, iss.issue_number)
                if live:
                    iss.state = live.get("state", iss.state)
                    iss.assignees = live.get("assignees", iss.assignees)
                    iss.comments_count = live.get("comments", iss.comments_count)
                    iss.labels = live.get("labels", iss.labels)
                    if iss.state != "open":
                        itask.workflow_state = "MERGED_OR_CLOSED"
                    synced_issues += 1
            except Exception as e:
                logger.error(f"Error syncing tracked issue {iss.id}: {e}")

    await db.commit()
    return {
        "status": "success",
        "synced_prs": synced_prs,
        "synced_issues": synced_issues,
        "total_active": synced_prs + synced_issues
    }

@router.delete("/all")
async def untrack_all_items(
    scope: str = Query("all", description="'all', 'merged', 'issues', or 'prs'"),
    db: AsyncSession = Depends(get_db)
):
    """
    Removes tracked items based on scope ('all', 'merged', 'issues', 'prs').
    """
    stmt = select(Task)
    if scope == "merged":
        stmt = stmt.where(or_(Task.pr_merged == True, Task.workflow_state == "MERGED_OR_CLOSED"))
    elif scope == "issues":
        stmt = stmt.where(Task.pr_number.is_(None))
    elif scope == "prs":
        stmt = stmt.where(Task.pr_number.isnot(None))

    res = await db.execute(stmt)
    tasks_to_delete = res.scalars().all()
    count = len(tasks_to_delete)
    for t in tasks_to_delete:
        audit = AuditLog(
            task_id=t.id,
            issue_id=t.issue_id,
            action="TRACKER_ITEM_REMOVED",
            actor="USER",
            details={"scope": scope, "task_id": t.id, "pr_number": t.pr_number}
        )
        db.add(audit)
        await db.delete(t)
    await db.commit()
    return {"status": "success", "removed": count, "scope": scope}

@router.post("/import-author")
async def import_author_prs(
    username: Optional[str] = Query(None, description="GitHub username to search PRs for"),
    db: AsyncSession = Depends(get_db)
):
    """
    Searches GitHub for all pull requests authored by the specified user
    and tracks them in the platform.
    """
    if not username:
        s_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
        s_res = await db.execute(s_stmt)
        sett = s_res.scalar_one_or_none()
        username = sett.github_username if (sett and sett.github_username) else "Pushkar-Shahi"

    gh = await get_github_client(db)
    search_query = f"author:{username} type:pr"
    url = f"https://api.github.com/search/issues?q={search_query}&per_page=50"

    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "IssueToPR-Platform"}
    s_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    s_res = await db.execute(s_stmt)
    sett = s_res.scalar_one_or_none()
    if sett and sett.github_token:
        headers["Authorization"] = f"token {sett.github_token}"

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"GitHub search failed: {resp.text}")
        data = resp.json()

    items = data.get("items", [])
    imported_tasks = []

    for item in items:
        pr_html_url = item.get("html_url")
        if not pr_html_url:
            continue
        try:
            pr_match = re.search(r'github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_html_url, re.IGNORECASE)
            if not pr_match:
                continue
            owner = pr_match.group(1)
            repo_name = pr_match.group(2)
            item_number = int(pr_match.group(3))

            full_name = f"{owner}/{repo_name}"
            repo_stmt = select(Repository).where(Repository.full_name.ilike(full_name))
            repo_res = await db.execute(repo_stmt)
            repository = repo_res.scalar_one_or_none()
            if not repository:
                repo_data = await gh.get_repository(owner, repo_name)
                if not repo_data:
                    continue
                repository = Repository(
                    owner=repo_data["owner"]["login"],
                    name=repo_data["name"],
                    full_name=repo_data["full_name"],
                    html_url=repo_data["html_url"],
                    default_branch=repo_data.get("default_branch", "main"),
                    primary_language=repo_data.get("language"),
                    stars_count=repo_data.get("stargazers_count", 0),
                    open_issues_count=repo_data.get("open_issues_count", 0)
                )
                db.add(repository)
                await db.commit()
                await db.refresh(repository)

            pr_data = await gh.get_pull_request(owner, repo_name, item_number)
            if not pr_data:
                continue

            issue_stmt = select(Issue).where(
                Issue.repository_id == repository.id,
                Issue.issue_number == item_number
            )
            i_res = await db.execute(issue_stmt)
            issue = i_res.scalar_one_or_none()

            title = pr_data.get("title", f"Pull Request #{item_number}")
            body = pr_data.get("body", "")
            author = pr_data.get("user", {}).get("login", username)
            pr_state = pr_data.get("state", "open")
            is_merged = pr_data.get("merged", False)
            branch_name = pr_data.get("head", {}).get("ref") or f"pr-{item_number}"

            if not issue:
                issue = Issue(
                    repository_id=repository.id,
                    github_id=pr_data.get("id", item_number),
                    issue_number=item_number,
                    title=title,
                    body=body,
                    author=author,
                    html_url=pr_html_url,
                    state="closed" if (is_merged or pr_state == "closed") else "open",
                    labels=pr_data.get("labels", []),
                    assignees=pr_data.get("assignees", []),
                    comments_count=pr_data.get("comments", 0)
                )
                db.add(issue)
                await db.commit()
                await db.refresh(issue)
            else:
                issue.title = title
                issue.state = "closed" if (is_merged or pr_state == "closed") else "open"

            task_stmt = select(Task).where(Task.issue_id == issue.id)
            t_res = await db.execute(task_stmt)
            task = t_res.scalar_one_or_none()

            workflow_state = "MERGED_OR_CLOSED" if (is_merged or pr_state == "closed") else "PR_CREATED"
            if not task:
                task = Task(
                    issue_id=issue.id,
                    pr_number=item_number,
                    pr_url=pr_html_url,
                    pr_state=pr_state,
                    pr_merged=is_merged,
                    branch_name=branch_name,
                    workflow_state=workflow_state
                )
                db.add(task)
                await db.commit()
                await db.refresh(task)
            else:
                task.pr_number = item_number
                task.pr_url = pr_html_url
                task.pr_state = pr_state
                task.pr_merged = is_merged
                task.branch_name = branch_name
                task.workflow_state = workflow_state

            try:
                await sync_task_pr_status(task, db, gh)
            except Exception:
                pass

            imported_tasks.append(task.id)
        except Exception as e:
            logger.error(f"Error importing PR {pr_html_url}: {e}")

    await db.commit()
    return {
        "status": "success",
        "username": username,
        "found_on_github": len(items),
        "imported": len(imported_tasks)
    }

@router.delete("/{task_id}")
async def untrack_item(task_id: str, db: AsyncSession = Depends(get_db)):
    """
    Removes a tracked item from the tracker dashboard.
    """
    stmt = select(Task).where(Task.id == task_id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Tracked item not found.")

    audit = AuditLog(
        task_id=task.id,
        issue_id=task.issue_id,
        action="TRACKER_ITEM_REMOVED",
        actor="USER",
        details={"task_id": task_id, "pr_number": task.pr_number}
    )
    db.add(audit)
    await db.delete(task)
    await db.commit()
    return {"status": "success", "message": "Item removed from tracker."}

@router.get("/stats")
async def get_tracker_stats(db: AsyncSession = Depends(get_db)):
    """
    Returns high-level statistics for the tracker dashboard.
    """
    tasks_res = await db.execute(select(Task))
    all_tasks = tasks_res.scalars().all()

    total_tracked = len(all_tasks)
    prs_open = len([t for t in all_tasks if t.pr_number and t.pr_state == "open" and not t.pr_merged])
    prs_merged = len([t for t in all_tasks if t.pr_merged])
    prs_changes_requested = len([t for t in all_tasks if t.pr_review_status == "CHANGES_REQUESTED"])
    issues_tracked = len([t for t in all_tasks if not t.pr_number])

    return {
        "total_tracked": total_tracked,
        "prs_open": prs_open,
        "prs_merged": prs_merged,
        "prs_changes_requested": prs_changes_requested,
        "issues_tracked": issues_tracked
    }
