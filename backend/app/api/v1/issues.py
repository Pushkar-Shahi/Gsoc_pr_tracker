import re
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, desc, asc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.models import Issue, Repository, Task, PlatformSettings
from app.schemas.schemas import IssueRead, IssueListResponse, IssueImportRequest, IssueImportResponse
from app.services.github_client import GitHubClient
from app.services.ranking_service import RankingService
from app.services.policy_inspector import PolicyInspector
from app.core.config import settings
from app.core.gsoc_orgs import ALL_GSOC_OWNERS, FOCUS_GSOC_OWNERS, FOCUS_GSOC_ORGS, get_gsoc_info, is_gsoc_org, is_focus_gsoc_org
from app.core.tenant import TenantContext, get_current_tenant

router = APIRouter(prefix="/issues", tags=["Issues"])

@router.get("", response_model=IssueListResponse)
async def list_issues(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    query: Optional[str] = None,
    language: Optional[str] = None,
    repository: Optional[str] = None,
    difficulty: Optional[str] = None,
    license_status: Optional[str] = None,
    state: str = Query("open", pattern="^(open|closed|all)$"),
    eligible_only: bool = Query(True),
    unassigned_only: bool = Query(True),
    gsoc_only: bool = Query(True),
    gsoc_org: Optional[str] = None,
    sort_by: str = Query("created", pattern="^(rank|created|stars|effort)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    ctx: Optional[TenantContext] = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Issue).options(
        selectinload(Issue.repository),
        selectinload(Issue.tasks)
    )

    # Join repository if filtering by language, stars, or repo name
    stmt = stmt.join(Repository)

    filters = []

    # Filter by issue state (default "open")
    if state != "all":
        filters.append(Issue.state == state)

    # Exclude ineligible or already-assigned issues when unassigned_only / eligible_only is requested
    if eligible_only or unassigned_only:
        filters.append(Issue.is_eligible.is_(True))

    # Target organizations constraint: NumFOCUS, PSF, DeepChem, Kornia OR issues linked to user tasks/PRs
    focus_owners = list(FOCUS_GSOC_OWNERS)
    if gsoc_org and gsoc_org.strip() and gsoc_org.strip().lower() != "all":
        org_filter = gsoc_org.strip().lower()
        if org_filter == "numfocus":
            target_owners = [
                "numfocus", "numpy", "scipy", "pandas-dev", "matplotlib",
                "scikit-learn", "scikit-image", "sympy", "networkx", "astropy",
                "jupyter", "jupyterlab", "dask", "xarray", "zarr-developers", "statsmodels"
            ]
        elif org_filter in ("psf", "python"):
            target_owners = ["psf", "python", "pallets", "pypa", "celery", "pylint-dev"]
        elif org_filter == "deepchem":
            target_owners = ["deepchem"]
        elif org_filter == "kornia":
            target_owners = ["kornia"]
        else:
            target_owners = [org_filter]
        filters.append(func.lower(Repository.owner).in_(target_owners))
    else:
        # Default: Show the 4 focus orgs OR issues that have user tasks/PRs
        filters.append(
            or_(
                func.lower(Repository.owner).in_(focus_owners),
                Issue.id.in_(select(Task.issue_id))
            )
        )

    if query and query.strip():
        q_term = f"%{query.strip()}%"
        filters.append(
            or_(
                Issue.title.ilike(q_term),
                Issue.body.ilike(q_term),
                Repository.full_name.ilike(q_term)
            )
        )

    if language and language.strip():
        filters.append(Repository.primary_language.ilike(language.strip()))

    if repository and repository.strip():
        filters.append(Repository.full_name.ilike(f"%{repository.strip()}%"))

    if difficulty and difficulty.strip():
        filters.append(Issue.difficulty_estimate == difficulty.strip().lower())

    if license_status and license_status.strip():
        filters.append(Issue.license_status == license_status.strip())

    if filters:
        stmt = stmt.where(*filters)

    # Sorting
    if sort_by == "rank":
        order_col = Issue.ranking_score
    elif sort_by == "created":
        order_col = Issue.github_created_at
    elif sort_by == "stars":
        order_col = Repository.stars_count
    elif sort_by == "effort":
        order_col = Issue.estimated_effort_hours
    else:
        order_col = Issue.ranking_score

    stmt = stmt.order_by(desc(order_col).nulls_last() if sort_order == "desc" else asc(order_col).nulls_last())

    # Count total
    count_stmt = select(func.count(Issue.id)).join(Repository)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    result = await db.execute(stmt)
    issues = result.scalars().all()

    # Enrich active task data if present
    items = []
    org_id = ctx.organization.id if (ctx and getattr(ctx, "organization", None)) else None
    for issue in issues:
        active_task = None
        if issue.tasks:
            tenant_tasks = [t for t in issue.tasks if t.tenant_id == org_id] if org_id else []
            if tenant_tasks:
                latest_task = sorted(tenant_tasks, key=lambda t: t.created_at, reverse=True)[0]
                active_task = {
                    "id": latest_task.id,
                    "workflow_state": latest_task.workflow_state,
                    "worktree_path": latest_task.worktree_path,
                    "branch_name": latest_task.branch_name,
                    "assignment_required": latest_task.assignment_required,
                    "pr_number": latest_task.pr_number,
                    "pr_url": latest_task.pr_url
                }

        issue_dict = IssueRead.model_validate(issue)
        issue_dict.active_task = active_task
        if issue_dict.repository:
            gsoc_org = get_gsoc_info(issue.repository.owner, issue.repository.name)
            if gsoc_org or issue.repository.is_gsoc:
                issue_dict.repository.is_gsoc = True
                issue_dict.repository.gsoc_org_name = issue.repository.gsoc_org_name or gsoc_org or "GSoC Org"
        items.append(issue_dict)

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return IssueListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        coverage_status={
            "mode": "Global Public GitHub Discovery",
            "open_unassigned_only": True,
            "hidden_count": 0
        }
    )

@router.get("/{issue_id}", response_model=IssueRead)
async def get_issue(
    issue_id: str,
    ctx: Optional[TenantContext] = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Issue).options(
        selectinload(Issue.repository),
        selectinload(Issue.tasks)
    ).where(Issue.id == issue_id)
    
    result = await db.execute(stmt)
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    active_task = None
    if issue.tasks:
        org_id = ctx.organization.id if (ctx and getattr(ctx, "organization", None)) else None
        tenant_tasks = [t for t in issue.tasks if t.tenant_id == org_id] if org_id else []
        if tenant_tasks:
            latest = sorted(tenant_tasks, key=lambda t: t.created_at, reverse=True)[0]
            active_task = {
                "id": latest.id,
                "workflow_state": latest.workflow_state,
                "worktree_path": latest.worktree_path,
                "branch_name": latest.branch_name,
                "assignment_required": latest.assignment_required,
                "pr_number": latest.pr_number,
                "pr_url": latest.pr_url
            }
    
    res = IssueRead.model_validate(issue)
    res.active_task = active_task
    if res.repository:
        gsoc_org = get_gsoc_info(issue.repository.owner, issue.repository.name)
        if gsoc_org or issue.repository.is_gsoc:
            res.repository.is_gsoc = True
            res.repository.gsoc_org_name = issue.repository.gsoc_org_name or gsoc_org or "GSoC Org"
    return res


@router.post("/import", response_model=IssueImportResponse)
async def import_issue(
    payload: IssueImportRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Imports a specific GitHub issue by URL or owner/repo#number,
    performs a comprehensive 7-point condition and eligibility preflight check,
    and saves/updates it in the system.
    """
    raw_url = payload.url.strip()
    # Match patterns like:
    # https://github.com/owner/repo/issues/123
    # github.com/owner/repo/issues/123
    # owner/repo#123
    # owner/repo/issues/123
    pattern = r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+)/issues/(\d+)|([^/]+)/([^/#]+)#(\d+)|([^/]+)/([^/]+)/issues/(\d+)"
    match = re.search(pattern, raw_url)
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub issue reference. Expected format: https://github.com/owner/repo/issues/123 or owner/repo#123"
        )
    
    groups = match.groups()
    if groups[0]:
        owner, repo_name, issue_number = groups[0], groups[1], int(groups[2])
    elif groups[3]:
        owner, repo_name, issue_number = groups[3], groups[4], int(groups[5])
    else:
        owner, repo_name, issue_number = groups[6], groups[7], int(groups[8])

    # Fetch token from settings if saved in DB
    sett_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    sett_res = await db.execute(sett_stmt)
    saved_settings = sett_res.scalar_one_or_none()
    token = saved_settings.github_token if saved_settings else None
    user_skills = saved_settings.skills_profile if saved_settings else settings.DEFAULT_SKILLS

    gh = GitHubClient(token=token)
    repo_data = await gh.get_repository(owner, repo_name)
    if not repo_data:
        raise HTTPException(status_code=404, detail=f"GitHub repository '{owner}/{repo_name}' not found or inaccessible.")

    issue_data = await gh.get_issue(owner, repo_name, issue_number)
    if not issue_data or "id" not in issue_data:
        raise HTTPException(status_code=404, detail=f"GitHub issue #{issue_number} not found in '{owner}/{repo_name}'.")

    if "pull_request" in issue_data:
        raise HTTPException(status_code=400, detail="The provided reference is a Pull Request, not an issue.")

    # 1. Condition Checks
    conditions_checked = {}
    is_eligible = True
    reasons = []

    # Condition: State (Open)
    issue_state = issue_data.get("state", "open")
    is_open = (issue_state == "open")
    conditions_checked["is_open"] = is_open
    if not is_open:
        is_eligible = False
        reasons.append(f"Issue is closed (state: {issue_state}). Only open issues are eligible.")

    # Condition: Unassigned (no assignees)
    assignees = issue_data.get("assignees", [])
    is_unassigned = (len(assignees) == 0)
    conditions_checked["is_unassigned"] = is_unassigned
    if not is_unassigned:
        is_eligible = False
        assigned_names = [a.get("login") for a in assignees if isinstance(a, dict)]
        reasons.append(f"Issue already has assigned contributors: {', '.join(assigned_names)}.")

    # Condition: Repository active & not archived
    is_archived = repo_data.get("archived", False)
    conditions_checked["repo_not_archived"] = not is_archived
    if is_archived:
        is_eligible = False
        reasons.append("Repository is archived; new contributions and pull requests are disabled.")

    # Condition: Author is not automated bot
    author_login = issue_data.get("user", {}).get("login", "")
    is_bot = "bot" in author_login.lower()
    conditions_checked["author_not_bot"] = not is_bot
    if is_bot:
        is_eligible = False
        reasons.append(f"Issue was submitted by automated bot '{author_login}'.")

    # Condition: Blocked labels check
    raw_labels = issue_data.get("labels", [])
    label_names = [l.get("name", "").lower() for l in raw_labels if isinstance(l, dict)]
    has_blocked_label = False
    blocked_label_found = None
    for bl in settings.BLOCKED_LABELS:
        if bl in label_names:
            has_blocked_label = True
            blocked_label_found = bl
            break
    conditions_checked["no_blocker_labels"] = not has_blocked_label
    if has_blocked_label:
        is_eligible = False
        reasons.append(f"Issue has blocker label: '{blocked_label_found}'.")

    # Condition: Open-Source License check
    lic_data = repo_data.get("license") or {}
    spdx = lic_data.get("spdx_id")
    license_status = "UNKNOWN"
    if spdx and spdx not in ("NOASSERTION", None):
        license_status = "VERIFIED_OSI"
    elif lic_data.get("name"):
        license_status = "UNKNOWN"
    else:
        license_status = "NO_LICENSE"
    conditions_checked["license_status"] = license_status
    conditions_checked["license_spdx"] = spdx
    conditions_checked["license_name"] = lic_data.get("name")
    if license_status == "NO_LICENSE":
        reasons.append("Caution: Repository does not contain a standard OSI open-source license.")

    # 2. Ranking & Skill Match Condition
    ranking_service = RankingService(user_skills=user_skills)
    ranking_eval = ranking_service.evaluate_issue(
        title=issue_data.get("title", ""),
        body=issue_data.get("body", ""),
        labels=raw_labels,
        repo_language=repo_data.get("language") or "",
        repo_stars=repo_data.get("stargazers_count", 0),
        license_spdx=spdx
    )
    conditions_checked["skill_match"] = ranking_eval["ranking_breakdown"]["matched_skills"]
    conditions_checked["difficulty_estimate"] = ranking_eval["difficulty_estimate"]
    conditions_checked["ranking_score"] = ranking_eval["ranking_score"]

    # 3. Policy & Assignment Preflight Check
    policy_inspector = PolicyInspector(github_client=gh)
    policy_eval = await policy_inspector.inspect_repository_policy(
        owner=owner,
        repo=repo_name,
        issue_number=issue_number,
        issue_body=issue_data.get("body", ""),
        issue_labels=raw_labels,
        issue_assignees=assignees
    )
    conditions_checked["policy_status"] = policy_eval["workflow_state"]
    conditions_checked["assignment_required"] = policy_eval["assignment_required"]
    conditions_checked["policy_evidence"] = policy_eval["evidence"]

    # 4. Upsert into database
    repo_full_name = f"{owner}/{repo_name}"
    repo_stmt = select(Repository).where(Repository.full_name == repo_full_name)
    repo_res = await db.execute(repo_stmt)
    repository = repo_res.scalar_one_or_none()

    gsoc_org = get_gsoc_info(owner, repo_name)
    if not repository:
        repository = Repository(
            owner=owner,
            name=repo_name,
            full_name=repo_full_name,
            html_url=repo_data.get("html_url", f"https://github.com/{repo_full_name}"),
            default_branch=repo_data.get("default_branch", "main"),
            primary_language=repo_data.get("language"),
            license_spdx=spdx,
            license_name=lic_data.get("name"),
            stars_count=repo_data.get("stargazers_count", 0),
            open_issues_count=repo_data.get("open_issues_count", 0),
            is_archived=is_archived,
            is_gsoc=(gsoc_org is not None),
            gsoc_org_name=gsoc_org,
            last_inspected_at=datetime.utcnow()
        )
        db.add(repository)
        await db.flush()
    elif not repository.is_gsoc and gsoc_org:
        repository.is_gsoc = True
        repository.gsoc_org_name = gsoc_org

    issue_stmt = select(Issue).options(
        selectinload(Issue.repository),
        selectinload(Issue.tasks)
    ).where(
        Issue.repository_id == repository.id,
        Issue.issue_number == issue_number
    )
    issue_res = await db.execute(issue_stmt)
    existing_issue = issue_res.scalar_one_or_none()

    github_created_at = None
    if issue_data.get("created_at"):
        try:
            github_created_at = datetime.fromisoformat(issue_data["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass

    ineligibility_reason = "; ".join(reasons) if not is_eligible else None

    if existing_issue:
        existing_issue.title = issue_data.get("title", existing_issue.title)
        existing_issue.body = issue_data.get("body", existing_issue.body)
        existing_issue.state = issue_state
        existing_issue.labels = raw_labels
        existing_issue.assignees = assignees
        existing_issue.comments_count = issue_data.get("comments", 0)
        existing_issue.is_eligible = is_eligible
        existing_issue.ineligibility_reason = ineligibility_reason
        existing_issue.license_status = license_status
        existing_issue.policy_status = policy_eval["workflow_state"]
        existing_issue.ranking_score = ranking_eval["ranking_score"]
        existing_issue.difficulty_estimate = ranking_eval["difficulty_estimate"]
        existing_issue.estimated_effort_hours = ranking_eval["estimated_effort_hours"]
        existing_issue.ranking_breakdown = ranking_eval["ranking_breakdown"]
        existing_issue.ai_summary = ranking_eval["ai_summary"]
        existing_issue.last_verified_at = datetime.utcnow()
        target_issue = existing_issue
    else:
        target_issue = Issue(
            repository_id=repository.id,
            github_id=issue_data["id"],
            issue_number=issue_number,
            title=issue_data.get("title", ""),
            body=issue_data.get("body", ""),
            author=author_login,
            html_url=issue_data.get("html_url", f"https://github.com/{repo_full_name}/issues/{issue_number}"),
            state=issue_state,
            labels=raw_labels,
            assignees=assignees,
            comments_count=issue_data.get("comments", 0),
            github_created_at=github_created_at,
            is_eligible=is_eligible,
            ineligibility_reason=ineligibility_reason,
            license_status=license_status,
            policy_status=policy_eval["workflow_state"],
            ranking_score=ranking_eval["ranking_score"],
            difficulty_estimate=ranking_eval["difficulty_estimate"],
            estimated_effort_hours=ranking_eval["estimated_effort_hours"],
            ranking_breakdown=ranking_eval["ranking_breakdown"],
            ai_summary=ranking_eval["ai_summary"],
            last_verified_at=datetime.utcnow()
        )
        db.add(target_issue)

    await db.commit()
    await db.refresh(target_issue)

    # Re-fetch with relationships loaded
    final_stmt = select(Issue).options(
        selectinload(Issue.repository),
        selectinload(Issue.tasks)
    ).where(Issue.id == target_issue.id)
    final_res = await db.execute(final_stmt)
    full_issue = final_res.scalar_one()

    conditions_checked["reasons"] = reasons
    return IssueImportResponse(
        issue=IssueRead.model_validate(full_issue),
        conditions_checked=conditions_checked,
        meets_all_conditions=is_eligible
    )


@router.post("/reconcile")
async def reconcile_issues_endpoint(
    purge: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """
    On-demand endpoint to scan and reconcile open issues against GitHub API,
    instantly pruning any that have closed or been assigned upstream,
    with optional purging of unattached closed issues.
    """
    from app.db.database import get_session_factory
    from app.services.background_worker import reconcile_inbox_issues_upstream
    session_factory = await get_session_factory()
    result = await reconcile_inbox_issues_upstream(session_factory, max_issues=None, purge=purge)

    count_stmt = select(func.count(Issue.id)).where(Issue.state == "open", Issue.is_eligible.is_(True))
    count_res = await db.execute(count_stmt)
    remaining_open = count_res.scalar() or 0

    return {
        "status": "success",
        "checked": result["checked"],
        "reconciled_closed": result["reconciled_closed"],
        "purged": result.get("purged", 0),
        "remaining_open": remaining_open
    }


@router.post("/{issue_id}/complete")
async def complete_issue(issue_id: str, db: AsyncSession = Depends(get_db)):
    """
    Mark an issue as completed, removing it from the open eligible inbox.
    """
    stmt = select(Issue).options(
        selectinload(Issue.repository),
        selectinload(Issue.tasks)
    ).where(Issue.id == issue_id)
    result = await db.execute(stmt)
    issue = result.scalar_one_or_none()

    if not issue and str(issue_id).startswith("gh-"):
        try:
            gh_id = int(str(issue_id).replace("gh-", ""))
            stmt2 = select(Issue).options(
                selectinload(Issue.repository),
                selectinload(Issue.tasks)
            ).where(Issue.github_id == gh_id)
            res2 = await db.execute(stmt2)
            issue = res2.scalar_one_or_none()
        except ValueError:
            pass

    if not issue:
        return {
            "status": "success",
            "message": f"Issue {issue_id} marked as completed and removed from inbox.",
            "issue_id": issue_id,
            "issue_number": 0
        }

    issue.state = "closed"
    issue.is_eligible = False
    issue.ineligibility_reason = "Completed by contributor"
    issue.github_closed_at = datetime.utcnow()

    # Update any associated task state to COMPLETED if not already submitted/resolved
    for task in (issue.tasks or []):
        if task.workflow_state not in ["PR_SUBMITTED", "COMPLETED", "RESOLVED"]:
            task.workflow_state = "COMPLETED"

    await db.commit()
    await db.refresh(issue)

    repo_name = issue.repository.full_name if issue.repository else "repository"
    return {
        "status": "success",
        "message": f"Issue #{issue.issue_number} in {repo_name} marked as completed and removed from inbox.",
        "issue_id": issue.id,
        "issue_number": issue.issue_number
    }


@router.delete("/{issue_id}")
async def delete_issue(issue_id: str, db: AsyncSession = Depends(get_db)):
    """
    Delete or dismiss an issue entirely from the platform database.
    """
    stmt = select(Issue).where(Issue.id == issue_id)
    result = await db.execute(stmt)
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    await db.delete(issue)
    await db.commit()
    return {
        "status": "success",
        "message": f"Issue #{issue.issue_number} removed from platform.",
        "issue_id": issue_id
    }


@router.post("/clear-inbox")
async def clear_inbox_issues(db: AsyncSession = Depends(get_db)):
    """
    Purges all issues that are not currently attached to an active task.
    Allows the user to clear all existing issues from the inbox.
    """
    tasks_subquery = select(Task.issue_id).where(Task.issue_id.isnot(None)).distinct()
    stmt = select(Issue).where(Issue.id.not_in(tasks_subquery))
    res = await db.execute(stmt)
    unattached_issues = res.scalars().all()
    cleared_count = len(unattached_issues)
    for iss in unattached_issues:
        await db.delete(iss)
    await db.commit()
    return {
        "status": "success",
        "cleared_count": cleared_count,
        "message": f"Successfully cleared {cleared_count} issues from inbox."
    }


