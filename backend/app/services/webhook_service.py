import logging
import uuid
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Repository, Issue, Task, AuditLog

logger = logging.getLogger(__name__)

class WebhookService:
    @staticmethod
    async def process_github_webhook_event(
        db: AsyncSession,
        event_type: str,
        payload: Dict[str, Any],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processes ingested GitHub App webhook events and synchronizes platform state.
        Supported events: ping, issues, pull_request, pull_request_review, repository.
        """
        event_type = (event_type or "").lower().strip()
        action = payload.get("action", "")

        # 1. Ping event
        if event_type == "ping":
            return {"status": "ok", "message": "pong"}

        # 2. Issues event
        elif event_type == "issues":
            issue_data = payload.get("issue", {})
            repo_data = payload.get("repository", {})
            gh_issue_id = issue_data.get("id")
            issue_num = issue_data.get("number")

            if not issue_num or not gh_issue_id:
                return {"status": "ok", "message": "Incomplete issue data ignored"}

            repo_full_name = repo_data.get("full_name", "")
            owner = repo_data.get("owner", {}).get("login") or (repo_full_name.split("/")[0] if "/" in repo_full_name else "unknown")
            repo_name = repo_data.get("name") or (repo_full_name.split("/")[1] if "/" in repo_full_name else "repo")

            # Look up or create repository
            repo_stmt = select(Repository).where(Repository.full_name == repo_full_name) if repo_full_name else select(Repository).where(Repository.id == "none")
            repo = (await db.execute(repo_stmt)).scalar_one_or_none()
            if not repo and repo_full_name:
                is_priv = bool(repo_data.get("private", False))
                repo = Repository(
                    id=f"repo-{uuid.uuid4().hex[:8]}",
                    tenant_id=tenant_id,
                    owner=owner,
                    name=repo_name,
                    full_name=repo_full_name,
                    html_url=repo_data.get("html_url") or f"https://github.com/{repo_full_name}",
                    default_branch=repo_data.get("default_branch", "main"),
                    primary_language=repo_data.get("language"),
                    is_private=is_priv,
                    is_gsoc=not is_priv,
                )
                db.add(repo)
                await db.flush()

            # Look up or create Issue
            iss_stmt = select(Issue).where(Issue.github_id == gh_issue_id)
            issue = (await db.execute(iss_stmt)).scalar_one_or_none()

            if action in ("opened", "edited", "created"):
                if not issue and repo:
                    issue = Issue(
                        id=f"iss-{uuid.uuid4().hex[:8]}",
                        tenant_id=tenant_id or repo.tenant_id,
                        repository_id=repo.id,
                        github_id=gh_issue_id,
                        issue_number=issue_num,
                        title=issue_data.get("title", "Untitled Issue"),
                        body=issue_data.get("body", ""),
                        html_url=issue_data.get("html_url") or f"https://github.com/{repo_full_name}/issues/{issue_num}",
                        state=issue_data.get("state", "open"),
                        labels=issue_data.get("labels", []),
                        assignees=issue_data.get("assignees", []),
                        comments_count=issue_data.get("comments", 0),
                        is_eligible=True
                    )
                    db.add(issue)
                    await db.flush()
                elif issue:
                    issue.title = issue_data.get("title", issue.title)
                    issue.body = issue_data.get("body", issue.body)
                    issue.state = issue_data.get("state", issue.state)
                    issue.labels = issue_data.get("labels", issue.labels)
                    issue.assignees = issue_data.get("assignees", issue.assignees)
                await db.commit()
                return {"status": "ok", "action": action, "issue_id": issue.id if issue else None}

            elif action == "closed":
                if issue:
                    issue.state = "closed"
                    issue.is_eligible = False
                    # Block active tasks on this issue
                    task_stmt = select(Task).where(
                        Task.issue_id == issue.id,
                        Task.workflow_state.notin_(["CANCELLED", "MERGED_OR_CLOSED"])
                    )
                    tasks = (await db.execute(task_stmt)).scalars().all()
                    for t in tasks:
                        t.workflow_state = "BLOCKED"
                        t.blocked_reason = "Issue closed on GitHub"
                        audit = AuditLog(
                            task_id=t.id,
                            issue_id=issue.id,
                            tenant_id=t.tenant_id,
                            user_id=t.user_id,
                            action="TASK_BLOCKED_UPSTREAM_CLOSED",
                            actor="GITHUB_WEBHOOK",
                            details={"issue_number": issue_num, "reason": "Issue closed upstream"}
                        )
                        db.add(audit)
                    await db.commit()
                return {"status": "ok", "action": "closed"}

            elif action == "reopened":
                if issue:
                    issue.state = "open"
                    issue.is_eligible = True
                    await db.commit()
                return {"status": "ok", "action": "reopened"}

        # 3. Pull Request event
        elif event_type == "pull_request":
            pr_data = payload.get("pull_request", {})
            repo_data = payload.get("repository", {})
            repo_full_name = repo_data.get("full_name")
            pr_number = pr_data.get("number")
            is_merged = pr_data.get("merged", False)

            if action == "closed" and is_merged and pr_number:
                if repo_full_name:
                    task_stmt = (
                        select(Task)
                        .join(Issue, Task.issue_id == Issue.id)
                        .join(Repository, Issue.repository_id == Repository.id)
                        .where(Task.pr_number == pr_number, Repository.full_name == repo_full_name)
                    )
                else:
                    task_stmt = select(Task).where(Task.pr_number == pr_number)
                tasks = (await db.execute(task_stmt)).scalars().all()
                for t in tasks:
                    t.workflow_state = "MERGED_OR_CLOSED"
                    t.pr_merged = True
                    t.pr_state = "closed"
                    audit = AuditLog(
                        task_id=t.id,
                        issue_id=t.issue_id,
                        tenant_id=t.tenant_id,
                        user_id=t.user_id,
                        action="PR_MERGED",
                        actor="GITHUB_WEBHOOK",
                        details={"pr_number": pr_number, "merged": True}
                    )
                    db.add(audit)
                await db.commit()
                return {"status": "ok", "action": "closed", "merged": True}

            elif action == "closed" and pr_number:
                if repo_full_name:
                    task_stmt = (
                        select(Task)
                        .join(Issue, Task.issue_id == Issue.id)
                        .join(Repository, Issue.repository_id == Repository.id)
                        .where(Task.pr_number == pr_number, Repository.full_name == repo_full_name)
                    )
                else:
                    task_stmt = select(Task).where(Task.pr_number == pr_number)
                tasks = (await db.execute(task_stmt)).scalars().all()
                for t in tasks:
                    t.pr_state = "closed"
                await db.commit()
                return {"status": "ok", "action": "closed", "merged": False}

        # 4. Pull Request Review event
        elif event_type == "pull_request_review":
            review_data = payload.get("review", {})
            pr_data = payload.get("pull_request", {})
            repo_data = payload.get("repository", {})
            repo_full_name = repo_data.get("full_name")
            pr_number = pr_data.get("number")
            review_state = review_data.get("state", "").lower()

            if action == "submitted" and pr_number:
                if repo_full_name:
                    task_stmt = (
                        select(Task)
                        .join(Issue, Task.issue_id == Issue.id)
                        .join(Repository, Issue.repository_id == Repository.id)
                        .where(Task.pr_number == pr_number, Repository.full_name == repo_full_name)
                    )
                else:
                    task_stmt = select(Task).where(Task.pr_number == pr_number)
                tasks = (await db.execute(task_stmt)).scalars().all()
                for t in tasks:
                    if review_state == "changes_requested":
                        t.workflow_state = "COLLABORATIVE_WORK"
                        t.pr_review_status = "CHANGES_REQUESTED"
                        audit = AuditLog(
                            task_id=t.id,
                            issue_id=t.issue_id,
                            tenant_id=t.tenant_id,
                            user_id=t.user_id,
                            action="PR_CHANGES_REQUESTED",
                            actor="GITHUB_WEBHOOK",
                            details={"pr_number": pr_number, "body": review_data.get("body")}
                        )
                        db.add(audit)
                    elif review_state == "approved":
                        t.pr_review_status = "APPROVED"
                await db.commit()
                return {"status": "ok", "action": "submitted", "review_state": review_state}

        # 5. Repository event
        elif event_type == "repository":
            repo_data = payload.get("repository", {})
            repo_full_name = repo_data.get("full_name")

            if action == "archived" and repo_full_name:
                repo_stmt = select(Repository).where(Repository.full_name == repo_full_name)
                repo = (await db.execute(repo_stmt)).scalar_one_or_none()
                if repo:
                    repo.is_archived = True
                    iss_stmt = select(Issue).where(Issue.repository_id == repo.id)
                    issues = (await db.execute(iss_stmt)).scalars().all()
                    for iss in issues:
                        iss.is_eligible = False
                        iss.ineligibility_reason = "Repository archived"
                    await db.commit()
                return {"status": "ok", "action": "archived"}

        # Fallback for unrecognized/ignored events
        return {"status": "ok", "event": event_type, "message": "Event ignored"}

process_github_webhook_event = WebhookService.process_github_webhook_event
