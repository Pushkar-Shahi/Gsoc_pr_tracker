import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Task, Issue, Repository, PlatformSettings, AuditLog
from app.services.github_client import GitHubClient
from app.services.discovery_service import DiscoveryService

logger = logging.getLogger(__name__)


async def sync_task_pr_status(
    task: Task,
    db: AsyncSession,
    gh: GitHubClient
) -> Dict[str, Any]:
    """
    Synchronizes pull request status, merge outcome, CI check runs, and maintainer reviews from GitHub.
    If maintainers requested changes, moves the task back into COLLABORATIVE_WORK.
    Never auto-merges or deploys.
    """
    if not task.pr_number or not task.issue or not task.issue.repository:
        return {"synced": False, "reason": "No PR number or repository associated."}

    owner = task.issue.repository.owner
    repo = task.issue.repository.name
    pr_number = task.pr_number

    # 1. Fetch Pull Request details from GitHub
    pr_data = await gh.get_pull_request(owner, repo, pr_number)
    if not pr_data:
        return {"synced": False, "reason": f"Could not fetch PR #{pr_number} from GitHub."}

    state = pr_data.get("state", "open")
    merged = pr_data.get("merged", False)
    head_sha = pr_data.get("head", {}).get("sha")

    task.pr_state = "merged" if merged else state
    task.pr_merged = merged

    # If merged or closed, update workflow state
    if merged:
        task.workflow_state = "MERGED_OR_CLOSED"
        audit = AuditLog(
            task_id=task.id,
            issue_id=task.issue_id,
            action="PR_MERGED_UPSTREAM",
            actor="MAINTAINER",
            details={"pr_number": pr_number, "merged_at": pr_data.get("merged_at")}
        )
        db.add(audit)
    elif state == "closed":
        task.workflow_state = "MERGED_OR_CLOSED"
        audit = AuditLog(
            task_id=task.id,
            issue_id=task.issue_id,
            action="PR_CLOSED_UPSTREAM",
            actor="MAINTAINER",
            details={"pr_number": pr_number, "closed_at": pr_data.get("closed_at")}
        )
        db.add(audit)

    # 2. Fetch CI Check Runs if commit SHA is present
    if head_sha:
        ci_report = await gh.get_commit_check_runs(owner, repo, head_sha)
        task.pr_ci_status = ci_report.get("status", "unknown")

    # 3. Fetch Reviews from Maintainers
    reviews = await gh.get_pull_request_reviews(owner, repo, pr_number)
    formatted_reviews = []
    has_changes_requested = False
    has_approved = False

    for r in reviews:
        r_state = r.get("state", "").upper()
        author = r.get("user", {}).get("login", "unknown")
        body = r.get("body", "")
        submitted_at = r.get("submitted_at")
        
        formatted_reviews.append({
            "id": r.get("id"),
            "author": author,
            "body": body,
            "state": r_state,
            "submitted_at": submitted_at
        })

        if r_state == "CHANGES_REQUESTED":
            has_changes_requested = True
        elif r_state == "APPROVED":
            has_approved = True

    task.pr_review_comments = formatted_reviews

    if has_changes_requested:
        task.pr_review_status = "CHANGES_REQUESTED"
        # If PR was in PR_CREATED or IN_REVIEW, transition back to COLLABORATIVE_WORK
        if task.workflow_state in ("PR_CREATED", "IN_REVIEW"):
            task.workflow_state = "COLLABORATIVE_WORK"
            task.blocked_reason = "Maintainer requested changes. Workspace ready for collaborative iteration in Antigravity."
            audit = AuditLog(
                task_id=task.id,
                issue_id=task.issue_id,
                action="MAINTAINER_REQUESTED_CHANGES",
                actor="MAINTAINER",
                details={
                    "pr_number": pr_number,
                    "review_count": len(formatted_reviews),
                    "transition": "COLLABORATIVE_WORK"
                }
            )
            db.add(audit)
    elif has_approved:
        task.pr_review_status = "APPROVED"
        task.blocked_reason = None
    elif reviews:
        task.pr_review_status = "COMMENTED"
    else:
        task.pr_review_status = "PENDING"

    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)

    return {
        "synced": True,
        "pr_number": pr_number,
        "pr_state": task.pr_state,
        "pr_merged": task.pr_merged,
        "pr_ci_status": task.pr_ci_status,
        "pr_review_status": task.pr_review_status,
        "workflow_state": task.workflow_state
    }


async def reconcile_tasks_on_startup(session_factory: async_sessionmaker):
    """
    Recovers interrupted tasks from persisted state and reconciles them
    against GitHub and local Git repositories on server startup.
    """
    logger.info("Starting startup task reconciliation and integrity check...")
    async with session_factory() as db:
        # Find all tasks that are active or in-progress
        stmt = select(Task).options(
            selectinload(Task.issue).selectinload(Issue.repository)
        ).where(
            Task.workflow_state.notin_(["CANCELLED", "MERGED_OR_CLOSED"])
        )
        res = await db.execute(stmt)
        active_tasks = res.scalars().all()

        settings_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
        s_res = await db.execute(settings_stmt)
        sett = s_res.scalar_one_or_none()
        gh = GitHubClient(token=sett.github_token if sett else None)

        reconciled_count = 0
        for task in active_tasks:
            try:
                # Case 1: Interrupted during VALIDATING
                if task.workflow_state == "VALIDATING":
                    logger.info(f"Reconciling task {task.id}: Resetting interrupted VALIDATING to READY_FOR_VALIDATION.")
                    task.workflow_state = "READY_FOR_VALIDATION"
                    task.blocked_reason = "Task validation was interrupted by system shutdown. Ready to re-run validation."
                    reconciled_count += 1

                # Case 2: Interrupted during PUBLISHING
                elif task.workflow_state == "PUBLISHING":
                    logger.info(f"Reconciling task {task.id}: Checking interrupted PUBLISHING state against GitHub.")
                    if task.pr_number:
                        task.workflow_state = "PR_CREATED"
                    else:
                        task.workflow_state = "READY_TO_PUBLISH"
                        task.blocked_reason = "PR publication was interrupted. Validation cleared; ready to publish."
                    reconciled_count += 1

                # Case 3: Reconcile local worktree directory
                if task.worktree_path:
                    p = Path(task.worktree_path)
                    if not p.exists() and task.workflow_state in ("WORKSPACE_PREPARED", "COLLABORATIVE_WORK"):
                        logger.warning(f"Task {task.id}: Worktree {task.worktree_path} missing on filesystem.")
                        task.blocked_reason = "Worktree folder missing on disk. Click 'Re-prepare Workspace' to recreate."

                # Case 4: Reconcile PR status if PR already created
                if task.pr_number and task.workflow_state in ("PR_CREATED", "IN_REVIEW"):
                    await sync_task_pr_status(task, db, gh)
                    reconciled_count += 1

                # Case 5: Verify upstream issue is still open
                if task.issue and task.issue.repository:
                    owner = task.issue.repository.owner
                    repo = task.issue.repository.name
                    fresh_issue = await gh.get_issue(owner, repo, task.issue.issue_number)
                    if fresh_issue:
                        if fresh_issue.get("state") != "open" and task.workflow_state not in ("PR_CREATED", "MERGED_OR_CLOSED"):
                            task.workflow_state = "BLOCKED"
                            task.blocked_reason = f"Upstream issue #{task.issue.issue_number} was closed on GitHub."
                            task.issue.state = fresh_issue.get("state", "closed")
                            task.issue.is_eligible = False
                            task.issue.ineligibility_reason = f"Closed upstream on GitHub (state: {task.issue.state})."
                            task.issue.last_verified_at = datetime.utcnow()
                            logger.info(f"Task {task.id} marked BLOCKED because upstream issue was closed.")
                            reconciled_count += 1

                await db.commit()
            except Exception as e:
                logger.error(f"Error reconciling task {task.id}: {e}")

        logger.info(f"Task reconciliation complete. Checked {len(active_tasks)} active tasks, reconciled {reconciled_count}.")

    # Also reconcile open inbox issues in background
    try:
        asyncio.create_task(reconcile_inbox_issues_upstream(session_factory, max_issues=None, purge=False))
    except Exception as e:
        logger.error(f"Error launching inbox issue reconciliation: {e}")


async def reconcile_inbox_issues_upstream(
    session_factory: async_sessionmaker,
    max_issues: Optional[int] = None,
    purge: bool = False
) -> Dict[str, int]:
    """
    Scans open, eligible issues in the local database against GitHub API,
    updates any that have been closed or assigned upstream, and optionally
    purges unattached closed/ineligible issues from the database.
    """
    logger.info("Scanning local open issues against live GitHub state...")
    checked_count = 0
    reconciled_closed = 0
    purged_count = 0

    async with session_factory() as db:
        sett_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
        res = await db.execute(sett_stmt)
        sett = res.scalar_one_or_none()
        gh = GitHubClient(token=sett.github_token if sett else None)

        issues_stmt = select(Issue).options(
            selectinload(Issue.repository)
        ).where(
            Issue.state == "open",
            Issue.is_eligible == True
        )
        if max_issues:
            issues_stmt = issues_stmt.limit(max_issues)

        r = await db.execute(issues_stmt)
        open_issues = r.scalars().all()

        for issue in open_issues:
            if not issue.repository:
                continue
            checked_count += 1
            try:
                owner = issue.repository.owner
                repo = issue.repository.name
                fresh = await gh.get_issue(owner, repo, issue.issue_number)
                if not fresh:
                    continue
                
                upstream_state = fresh.get("state", "open")
                upstream_assignees = fresh.get("assignees", [])
                is_pr = "pull_request" in fresh

                if upstream_state != "open" or is_pr:
                    issue.state = upstream_state
                    issue.is_eligible = False
                    issue.ineligibility_reason = "Issue is a pull request." if is_pr else f"Closed upstream on GitHub (state: {upstream_state})."
                    issue.last_verified_at = datetime.utcnow()
                    reconciled_closed += 1
                    logger.info(f"Issue {owner}/{repo}#{issue.issue_number} pruned from inbox (closed/pr upstream).")
                elif len(upstream_assignees) > 0:
                    issue.assignees = upstream_assignees
                    issue.is_eligible = False
                    assigned_logins = [a.get("login") for a in upstream_assignees if isinstance(a, dict)]
                    issue.ineligibility_reason = f"Assigned to {', '.join(assigned_logins)} upstream on GitHub."
                    issue.last_verified_at = datetime.utcnow()
                    reconciled_closed += 1
                    logger.info(f"Issue {owner}/{repo}#{issue.issue_number} pruned from inbox (assigned upstream).")
                else:
                    issue.last_verified_at = datetime.utcnow()
            except Exception as e:
                logger.debug(f"Failed to check upstream status for {issue.id}: {e}")

        await db.commit()

        # Optional Purge: Delete unattached closed/ineligible issues from DB
        if purge:
            tasks_subquery = select(Task.issue_id).distinct()
            stale_issues_stmt = select(Issue).where(
                or_(Issue.state != "open", Issue.is_eligible == False),
                Issue.id.not_in(tasks_subquery)
            )
            stale_res = await db.execute(stale_issues_stmt)
            stale_issues = stale_res.scalars().all()
            for s_issue in stale_issues:
                await db.delete(s_issue)
                purged_count += 1
            await db.commit()
            logger.info(f"Purged {purged_count} unattached stale/closed issues from database.")

    logger.info(f"Inbox issue reconciliation complete: {checked_count} checked, {reconciled_closed} closed/assigned upstream pruned, {purged_count} purged.")
    return {
        "checked": checked_count,
        "reconciled_closed": reconciled_closed,
        "purged": purged_count
    }


class BackgroundWorkerService:
    """
    Manages background periodic workers for scheduled discovery polling,
    pull request tracking / review updates, and issue upstream state reconciliation.
    """
    def __init__(
        self,
        session_factory: async_sessionmaker,
        discovery_interval_sec: int = 7200,  # 2 hours default cron interval
        pr_poll_interval_sec: int = 60,
        issue_reconcile_interval_sec: int = 180
    ):
        self.session_factory = session_factory
        self.discovery_interval_sec = discovery_interval_sec
        self.pr_poll_interval_sec = pr_poll_interval_sec
        self.issue_reconcile_interval_sec = issue_reconcile_interval_sec
        self._tasks: List[asyncio.Task] = []
        self._running = False
        self.last_cron_run_at: Optional[datetime] = None
        self.next_cron_run_at: Optional[datetime] = None
        self.is_cron_running: bool = False
        self.cron_target_orgs: List[str] = ["NumFOCUS", "Python Software Foundation", "DeepChem", "Kornia"]

    def start(self):
        if self._running:
            return
        self._running = True
        self._tasks.append(asyncio.create_task(self._pr_tracker_loop(), name="pr_tracker_worker"))
        self._tasks.append(asyncio.create_task(self._discovery_loop(), name="discovery_cron_worker"))
        self._tasks.append(asyncio.create_task(self._issue_reconciler_loop(), name="issue_reconciler_worker"))
        self.next_cron_run_at = datetime.utcnow() + timedelta(seconds=self.discovery_interval_sec)
        logger.info(f"Background workers started (PR tracker, 2-hour discovery cron [{self.discovery_interval_sec}s], issue reconciler).")

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Background workers stopped gracefully.")

    async def _pr_tracker_loop(self):
        """Periodically syncs all tracked tasks (pull requests and issues) with GitHub."""
        while self._running:
            try:
                await asyncio.sleep(self.pr_poll_interval_sec)
                async with self.session_factory() as db:
                    sett_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
                    res = await db.execute(sett_stmt)
                    sett = res.scalar_one_or_none()
                    gh = GitHubClient(token=sett.github_token if sett else None)

                    # Query all active tracked tasks
                    stmt = select(Task).options(
                        selectinload(Task.issue).selectinload(Issue.repository)
                    ).where(
                        Task.workflow_state.notin_(["CANCELLED", "MERGED_OR_CLOSED"])
                    )
                    r = await db.execute(stmt)
                    active_tasks = r.scalars().all()

                    for task in active_tasks:
                        try:
                            if task.pr_number:
                                await sync_task_pr_status(task, db, gh)
                            elif task.issue:
                                owner = task.issue.repository.owner
                                repo = task.issue.repository.name
                                fresh = await gh.get_issue(owner, repo, task.issue.issue_number)
                                if fresh:
                                    task.issue.state = fresh.get("state", task.issue.state)
                                    task.issue.comments_count = fresh.get("comments", task.issue.comments_count)
                                    task.issue.assignees = fresh.get("assignees", task.issue.assignees)
                                    await db.commit()
                        except Exception as e:
                            logger.error(f"Error syncing tracked task {task.id}: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in PR tracker loop: {e}")
                await asyncio.sleep(10)

    async def trigger_cron_scan(self) -> Dict[str, Any]:
        """
        Executes a 2-hour cron discovery scan across the target organizations (NumFOCUS, PSF, DeepChem, Kornia),
        prunes closed/assigned issues, logs an in-app audit notification, and updates status timestamps.
        """
        self.is_cron_running = True
        logger.info("2-Hour Auto-Scan Cron starting across NumFOCUS, PSF, DeepChem, and Kornia...")
        try:
            async with self.session_factory() as db:
                sett_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
                res = await db.execute(sett_stmt)
                sett = res.scalar_one_or_none()
                gh = GitHubClient(token=sett.github_token if sett else None)

                discovery = DiscoveryService(db=db, github_client=gh)
                result = await discovery.run_discovery_sync(force_refresh=True, page_limit=2)
                discovered_count = result.get("total_discovered", 0)

                # Reconcile and purge closed/assigned issues upstream
                await reconcile_inbox_issues_upstream(self.session_factory, max_issues=None, purge=True)

                # Record an audit log for the UI notifications panel
                audit = AuditLog(
                    action="CRON_DISCOVERY_COMPLETED",
                    actor="CRON_WORKER",
                    details={
                        "discovered": discovered_count,
                        "timestamp": datetime.utcnow().isoformat(),
                        "orgs": self.cron_target_orgs,
                        "message": f"Auto-Scan Cron completed. Discovered {discovered_count} fresh unassigned issues from NumFOCUS, PSF, DeepChem, and Kornia."
                    }
                )
                db.add(audit)
                await db.commit()

                self.last_cron_run_at = datetime.utcnow()
                self.next_cron_run_at = datetime.utcnow() + timedelta(seconds=self.discovery_interval_sec)
                logger.info(f"2-Hour Auto-Scan Cron completed. Ingested {discovered_count} issues.")
                return {
                    "success": True,
                    "discovered": discovered_count,
                    "last_run_at": self.last_cron_run_at.isoformat(),
                    "next_run_at": self.next_cron_run_at.isoformat()
                }
        except Exception as e:
            logger.error(f"Error executing auto-scan cron: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.is_cron_running = False

    async def _discovery_loop(self):
        """Periodically polls GitHub discovery every 2 hours."""
        while self._running:
            try:
                await asyncio.sleep(self.discovery_interval_sec)
                logger.info("2-Hour Scheduled discovery background cron triggering...")
                await self.trigger_cron_scan()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in discovery cron worker loop: {e}")
                await asyncio.sleep(60)

    async def _issue_reconciler_loop(self):
        """Periodically scans open database issues and prunes any that have closed upstream."""
        while self._running:
            try:
                await asyncio.sleep(self.issue_reconcile_interval_sec)
                logger.info("Periodic issue upstream reconciliation triggering...")
                await reconcile_inbox_issues_upstream(self.session_factory, max_issues=None, purge=False)
                logger.info("Periodic issue upstream reconciliation completed.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in issue reconciler loop: {e}")
                await asyncio.sleep(60)


_global_worker: Optional[BackgroundWorkerService] = None


def set_background_worker(worker: BackgroundWorkerService):
    global _global_worker
    _global_worker = worker


def get_background_worker() -> Optional[BackgroundWorkerService]:
    global _global_worker
    return _global_worker

