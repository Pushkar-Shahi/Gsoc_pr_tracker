import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Task, Issue, Repository, PlatformSettings, AuditLog
from app.services.github_client import GitHubClient
from app.services.discovery_service import DiscoveryService
from app.services.queue_service import queue_service
from app.services.availability_inspector import AvailabilityInspector

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
            Issue.is_eligible == True,
            or_(Issue.bounty_amount == None, Issue.bounty_amount == 0)
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

                # 1. Check if closed upstream or is itself a PR
                if upstream_state != "open" or is_pr:
                    await db.delete(issue)
                    reconciled_closed += 1
                    logger.info(f"Issue {owner}/{repo}#{issue.issue_number} hard-deleted (closed/PR upstream).")
                    continue

                # 2. Check if assigned upstream
                if len(upstream_assignees) > 0:
                    await db.delete(issue)
                    reconciled_closed += 1
                    logger.info(f"Issue {owner}/{repo}#{issue.issue_number} hard-deleted (assigned upstream).")
                    continue

                # 3. Check maintainer reservation
                is_reserved, res_reason = AvailabilityInspector.detect_maintainer_reservation(
                    fresh.get("title", ""),
                    fresh.get("body", "")
                )
                if is_reserved:
                    await db.delete(issue)
                    reconciled_closed += 1
                    logger.info(f"Issue {owner}/{repo}#{issue.issue_number} hard-deleted (maintainer reserved).")
                    continue

                # 4. Check explicit PR closure or submission intent in issue text
                full_text = f"{fresh.get('title', '')}\n{fresh.get('body', '')}"
                has_pr_pattern, pr_reason = AvailabilityInspector.detect_pr_intent_or_closure(full_text)
                if has_pr_pattern:
                    await db.delete(issue)
                    reconciled_closed += 1
                    logger.info(f"Issue {owner}/{repo}#{issue.issue_number} hard-deleted ({pr_reason}).")
                    continue

                # 5. Check live linked PRs that will close this issue
                linked_prs = await gh.get_issue_linked_prs(owner, repo, issue.issue_number)
                if linked_prs and len(linked_prs) > 0:
                    await db.delete(issue)
                    reconciled_closed += 1
                    logger.info(f"Issue {owner}/{repo}#{issue.issue_number} hard-deleted (has active PR #{linked_prs[0]['number']}).")
                    continue

                # Issue is pristine: 0 assignees, 0 open PRs, not reserved
                issue.has_open_pr = False
                issue.linked_pr_count = 0
                issue.linked_prs = []
                issue.is_reserved = False
                issue.reservation_reason = None
                issue.availability_status = "AVAILABLE"
                issue.assignees = []
                issue.last_verified_at = datetime.utcnow()
            except Exception as e:
                logger.debug(f"Failed to check upstream status for {issue.id}: {e}")

        await db.commit()

        # Optional Purge: Delete unattached closed/ineligible issues from DB
        if purge:
            tasks_subquery = select(Task.issue_id).distinct()
            stale_issues_stmt = select(Issue).where(
                or_(
                    Issue.state != "open",
                    Issue.is_eligible == False,
                    Issue.has_open_pr == True,
                    Issue.is_reserved == True,
                    Issue.availability_status != "AVAILABLE"
                ),
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
        self.last_cron_discovered: int = 0
        self.last_cron_pruned: int = 0
        self._active_cron_task: Optional[asyncio.Task] = None
        self._last_login_scan_triggered_at: Optional[datetime] = None
        self.cron_target_orgs: List[str] = ["NumFOCUS", "Python Software Foundation", "DeepChem", "Kornia"]

    def start(self):
        if self._running:
            return
        self._running = True
        self._tasks.append(asyncio.create_task(self._pr_tracker_loop(), name="pr_tracker_worker"))
        self._tasks.append(asyncio.create_task(self._discovery_loop(), name="discovery_cron_worker"))
        self._tasks.append(asyncio.create_task(self._issue_reconciler_loop(), name="issue_reconciler_worker"))
        self._tasks.append(asyncio.create_task(self._startup_empty_inbox_check(), name="startup_empty_inbox_check"))
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        cycle_start_epoch = (now_epoch // self.discovery_interval_sec) * self.discovery_interval_sec
        cycle_end_epoch = cycle_start_epoch + self.discovery_interval_sec
        self.last_cron_run_at = datetime.fromtimestamp(cycle_start_epoch, tz=timezone.utc)
        self.next_cron_run_at = datetime.fromtimestamp(cycle_end_epoch, tz=timezone.utc)
        logger.info(f"Background workers started (PR tracker, 2-hour discovery cron [{self.discovery_interval_sec}s], issue reconciler).")

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Background workers stopped gracefully.")

    async def enqueue_job(self, queue_name: str, payload: Dict[str, Any]) -> str:
        """Enqueues a background job payload via the configured queue service."""
        return await queue_service.enqueue(queue_name, payload)

    async def dequeue_job(self, queue_name: str, timeout: float = 0.0) -> Optional[Dict[str, Any]]:
        """Dequeues a background job payload via the configured queue service."""
        return await queue_service.dequeue(queue_name, timeout)

    async def _pr_tracker_loop(self):
        """Periodically syncs all tracked tasks (pull requests and issues) with GitHub."""
        while self._running:
            try:
                await asyncio.sleep(self.pr_poll_interval_sec)
                async with self.session_factory() as db:
                    sett_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
                    res = await db.execute(sett_stmt)
                    sett = res.scalar_one_or_none()
                    
                    # Conserve rate limits: if no personal GitHub token is configured, poll every 5 minutes
                    if not sett or not sett.github_token:
                        await asyncio.sleep(240)

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

    async def _startup_empty_inbox_check(self):
        """Triggers an immediate 2h scan on server startup if the inbox has no eligible open issues."""
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("ENVIRONMENT") == "testing":
            return
        try:
            await asyncio.sleep(2.0)
            async with self.session_factory() as db:
                open_cnt = (
                    await db.execute(
                        select(func.count(Issue.id)).where(
                            Issue.state == "open",
                            Issue.is_eligible.is_(True),
                            Issue.has_open_pr.is_(False),
                            Issue.is_reserved.is_(False),
                        )
                    )
                ).scalar() or 0
            if open_cnt == 0:
                logger.info("Inbox empty on startup; launching initial 2-hour discovery scan...")
                await self.trigger_cron_scan()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Startup empty-inbox discovery check warning: {e}")

    async def _has_empty_eligible_inbox(self) -> bool:
        try:
            async with self.session_factory() as db:
                open_cnt = (
                    await db.execute(
                        select(func.count(Issue.id)).where(
                            Issue.state == "open",
                            Issue.is_eligible.is_(True),
                            Issue.has_open_pr.is_(False),
                            Issue.is_reserved.is_(False),
                        )
                    )
                ).scalar() or 0
                return open_cnt == 0
        except Exception:
            return False

    async def trigger_login_scan_if_needed(self) -> None:
        """
        Triggers the 2-hour scan asynchronously upon login when the inbox is empty
        or no scan has been triggered in the last 10 minutes.
        """
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("ENVIRONMENT") == "testing":
            return
        if self.is_cron_running and self._active_cron_task and not self._active_cron_task.done():
            return
        now_utc = datetime.now(timezone.utc)
        cooldown_elapsed = (
            self._last_login_scan_triggered_at is None
            or (now_utc - self._last_login_scan_triggered_at).total_seconds() >= 600
        )
        if not cooldown_elapsed and not await self._has_empty_eligible_inbox():
            return
        self._last_login_scan_triggered_at = now_utc
        await self.trigger_cron_scan()

    async def _execute_cron_scan(self) -> Dict[str, Any]:
        """Internal runner for a single coalesced 2-hour discovery + reconciliation pass."""
        self.is_cron_running = True
        logger.info("2-Hour Auto-Scan Cron starting across NumFOCUS, PSF, DeepChem, and Kornia...")
        try:
            async with self.session_factory() as db:
                sett_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
                res = await db.execute(sett_stmt)
                sett = res.scalar_one_or_none()
                gh = GitHubClient(token=sett.github_token if sett else None)

                discovery = DiscoveryService(db=db, github_client=gh)
                result = await discovery.run_discovery_sync(force_refresh=True, page_limit=1)
                discovered_count = int(result.get("total_discovered") or result.get("items_synced") or 0)
                errors = result.get("errors") or []

                # Run bounded stale-issue cleanup asynchronously so HTTP cron triggers return within seconds
                try:
                    asyncio.create_task(
                        reconcile_inbox_issues_upstream(self.session_factory, max_issues=35, purge=True),
                        name="cron_post_reconcile",
                    )
                except Exception as rec_exc:
                    logger.debug(f"Could not schedule post-cron reconcile: {rec_exc}")
                pruned_count = 0

                # Record an audit log for the UI notifications panel
                audit = AuditLog(
                    action="CRON_DISCOVERY_COMPLETED",
                    actor="CRON_WORKER",
                    details={
                        "discovered": discovered_count,
                        "pruned": pruned_count,
                        "errors": errors,
                        "timestamp": datetime.utcnow().isoformat(),
                        "orgs": self.cron_target_orgs,
                        "message": f"Auto-Scan Cron completed. Discovered {discovered_count} fresh unassigned issues from NumFOCUS, PSF, DeepChem, and Kornia."
                    }
                )
                db.add(audit)
                await db.commit()

                now_utc = datetime.now(timezone.utc)
                now_epoch = int(now_utc.timestamp())
                next_cycle_epoch = ((now_epoch // self.discovery_interval_sec) + 1) * self.discovery_interval_sec
                self.last_cron_discovered = discovered_count
                self.last_cron_pruned = pruned_count
                self.last_cron_run_at = now_utc
                self.next_cron_run_at = datetime.fromtimestamp(next_cycle_epoch, tz=timezone.utc)
                logger.info(f"2-Hour Auto-Scan Cron completed. Ingested {discovered_count} issues.")
                return {
                    "success": True,
                    "status": "success",
                    "discovered": discovered_count,
                    "last_issues_synced": discovered_count,
                    "last_issues_pruned": pruned_count,
                    "errors": errors,
                    "last_run_at": self.last_cron_run_at.isoformat(),
                    "next_run_at": self.next_cron_run_at.isoformat(),
                }
        except Exception as e:
            logger.error(f"Error executing auto-scan cron: {e}")
            return {
                "success": False,
                "status": "error",
                "discovered": 0,
                "last_issues_synced": 0,
                "last_issues_pruned": 0,
                "error": str(e),
            }
        finally:
            self.is_cron_running = False

    async def trigger_cron_scan(self) -> Dict[str, Any]:
        """
        Executes a 2-hour cron discovery scan across the target organizations,
        coalescing concurrent callers onto the single active task cleanly.
        """
        if self._active_cron_task and not self._active_cron_task.done():
            return await asyncio.shield(self._active_cron_task)

        self._active_cron_task = asyncio.create_task(self._execute_cron_scan(), name="cron_scan_run")
        try:
            return await asyncio.shield(self._active_cron_task)
        finally:
            if self._active_cron_task and self._active_cron_task.done():
                self._active_cron_task = None

    async def _discovery_loop(self):
        """Synchronizes background 2-hour discovery scans with the exact wall-clock 2h countdown."""
        while self._running:
            try:
                now_epoch = int(datetime.now(timezone.utc).timestamp())
                next_cycle_epoch = ((now_epoch // self.discovery_interval_sec) + 1) * self.discovery_interval_sec
                sleep_sec = max(5, next_cycle_epoch - now_epoch)
                await asyncio.sleep(sleep_sec)
                if not self._running:
                    break
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


def trigger_login_discovery_scan() -> None:
    """Schedules the 2-hour GSoC discovery scan non-blockingly when a user signs in."""
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("ENVIRONMENT") == "testing":
        return
    worker = get_background_worker()
    if worker:
        try:
            asyncio.create_task(worker.trigger_login_scan_if_needed(), name="login_discovery_scan")
        except Exception as exc:
            logger.debug(f"Could not schedule login discovery scan: {exc}")

