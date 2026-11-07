import logging
from datetime import datetime
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.models import Task, Issue, Repository, PlatformSettings, AuditLog
from app.schemas.schemas import (
    TaskRead, TaskCreate, PreflightResult, AssignmentApprovalRequest,
    AutonomousApproveRequest, ValidationRunRequest, ValidationResult, PublishRequest, PublishResult
)
from app.core.tenant import TenantContext, get_current_tenant
from app.services.policy_inspector import PolicyInspector
from app.services.issue_analyzer import IssueAnalyzer
from app.services.workspace_manager import WorkspaceManager
from app.services.antigravity_handoff import AntigravityHandoffService
from app.services.validation_service import ValidationService
from app.services.pr_publisher import PRPublisher
from app.services.github_client import GitHubClient
from app.core.entitlements import enforce_task_creation_quota
from app.services.billing_service import BillingService

router = APIRouter(prefix="/tasks", tags=["Tasks"])
logger = logging.getLogger(__name__)

class _FallbackEntity:
    def __init__(self, id_val: str, name_val: str = "default"):
        self.id = id_val
        self.name = name_val
        self.github_username = name_val

class _FallbackTenantContext:
    def __init__(self):
        self.organization = _FallbackEntity("default-org")
        self.user = _FallbackEntity("default-user")
        self.membership = None
        self.role = "owner"

def _resolve_tenant_ctx(ctx: Any) -> Any:
    if isinstance(ctx, TenantContext) and ctx.organization and ctx.user:
        return ctx
    if ctx is not None and hasattr(ctx, "organization") and ctx.organization is not None and not isinstance(getattr(ctx, "organization"), Depends):
        return ctx
    return _FallbackTenantContext()

async def get_github_client(db: AsyncSession) -> GitHubClient:
    stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    res = await db.execute(stmt)
    settings_obj = res.scalar_one_or_none()
    token = settings_obj.github_token if settings_obj else None
    return GitHubClient(token=token)

@router.get("", response_model=List[TaskRead])
async def list_tasks(
    state: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    ctx = _resolve_tenant_ctx(ctx)
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(
        or_(
            Task.tenant_id == ctx.organization.id,
            Task.tenant_id.is_(None)
        )
    ).order_by(desc(Task.updated_at))

    if state:
        stmt = stmt.where(Task.workflow_state == state)

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return tasks

@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    ctx = _resolve_tenant_ctx(ctx)
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(
        Task.id == task_id,
        or_(
            Task.tenant_id == ctx.organization.id,
            Task.tenant_id.is_(None)
        )
    )
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.post("/select", response_model=TaskRead)
async def select_issue(
    payload: TaskCreate,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    ctx = _resolve_tenant_ctx(ctx)
    # 1. Fetch issue
    issue_stmt = select(Issue).options(selectinload(Issue.repository)).where(Issue.id == payload.issue_id)
    res = await db.execute(issue_stmt)
    issue = res.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    # 2. Check for active task
    existing_task_stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(
        Task.issue_id == issue.id,
        Task.tenant_id == ctx.organization.id,
        Task.workflow_state.notin_(["CANCELLED", "MERGED_OR_CLOSED"])
    )
    existing_res = await db.execute(existing_task_stmt)
    existing_task = existing_res.scalar_one_or_none()
    gh = await get_github_client(db)

    if existing_task:
        if not existing_task.implementation_brief or "executive_summary" not in existing_task.implementation_brief:
            analyzer = IssueAnalyzer(github_client=gh)
            brief = await analyzer.analyze_issue(
                owner=issue.repository.owner,
                repo=issue.repository.name,
                issue_number=issue.issue_number,
                title=issue.title,
                body=issue.body or "",
                labels=issue.labels or [],
                language=issue.repository.primary_language,
                assignees=issue.assignees or []
            )
            existing_task.implementation_brief = brief
            await db.commit()
            await db.refresh(existing_task)
        return existing_task

    # 3. Live Upstream Pre-Flight: Verify issue is still open and unassigned on GitHub
    fresh_issue = await gh.get_issue(issue.repository.owner, issue.repository.name, issue.issue_number)
    if fresh_issue:
        live_state = fresh_issue.get("state", "open")
        live_assignees = fresh_issue.get("assignees", [])
        is_pr = "pull_request" in fresh_issue
        if live_state != "open" or len(live_assignees) > 0 or is_pr:
            issue.state = live_state
            issue.assignees = live_assignees
            issue.is_eligible = False
            if live_state != "open":
                issue.ineligibility_reason = f"Issue was closed upstream on GitHub (state: {live_state})."
            elif is_pr:
                issue.ineligibility_reason = "Issue is a pull request."
            else:
                assigned_names = [a.get("login") for a in live_assignees if isinstance(a, dict)]
                issue.ineligibility_reason = f"Issue is assigned to {', '.join(assigned_names)} on GitHub."
            issue.last_verified_at = datetime.utcnow()
            await db.commit()
            raise HTTPException(
                status_code=409,
                detail=f"Issue #{issue.issue_number} is no longer available (it was closed or assigned upstream on GitHub). Your inbox has been updated."
            )

    # 3.5 Entitlement Check: Enforce monthly task quota
    await enforce_task_creation_quota(ctx, db)

    # 4. Create Task in SELECTED
    task = Task(
        issue_id=issue.id,
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        workflow_state="SELECTED"
    )
    db.add(task)
    await db.flush()
    await BillingService.record_task_created(ctx.organization.id, db)

    # 5. Run automated deep intelligence & policy inspection
    analyzer = IssueAnalyzer(github_client=gh)
    brief = await analyzer.analyze_issue(
        owner=issue.repository.owner,
        repo=issue.repository.name,
        issue_number=issue.issue_number,
        title=issue.title,
        body=(fresh_issue.get("body") if fresh_issue else issue.body) or "",
        labels=(fresh_issue.get("labels") if fresh_issue else issue.labels) or [],
        language=issue.repository.primary_language,
        assignees=(fresh_issue.get("assignees") if fresh_issue else issue.assignees) or []
    )

    task.implementation_brief = brief
    task.workflow_state = brief["rule_check"]["workflow_state"]
    task.assignment_required = brief["rule_check"]["assignment_required"]
    task.draft_assignment_comment = brief["rule_check"]["draft_comment"]
    if brief["rule_check"]["workflow_state"] in ("BLOCKED", "POLICY_REVIEW_REQUIRED"):
        task.blocked_reason = brief["rule_check"].get("rule_explanation")
    else:
        task.blocked_reason = None
    issue.policy_status = brief["rule_check"]["workflow_state"]

    # Audit log
    audit = AuditLog(
        task_id=task.id,
        issue_id=issue.id,
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="ISSUE_SELECTED_AND_ANALYZED",
        actor="USER",
        details={
            "preflight_state": brief["rule_check"]["workflow_state"],
            "assignment_required": brief["rule_check"]["assignment_required"],
            "category": brief.get("category"),
            "affected_files": brief.get("affected_files", [])
        }
    )
    db.add(audit)
    await db.commit()
    await db.refresh(task)

    # Re-fetch with relationships
    task_stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task.id, Task.tenant_id == ctx.organization.id)
    r = await db.execute(task_stmt)
    return r.scalar_one()

@router.post("/{task_id}/preflight", response_model=PreflightResult)
async def rerun_preflight(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    gh = await get_github_client(db)
    inspector = PolicyInspector(github_client=gh)
    preflight = await inspector.inspect_repository_policy(
        owner=task.issue.repository.owner,
        repo=task.issue.repository.name,
        issue_number=task.issue.issue_number,
        issue_body=task.issue.body or "",
        issue_labels=task.issue.labels or [],
        issue_assignees=task.issue.assignees or []
    )

    task.workflow_state = preflight["workflow_state"]
    task.assignment_required = preflight["assignment_required"]
    task.draft_assignment_comment = preflight["draft_comment"]
    if preflight["workflow_state"] in ("BLOCKED", "POLICY_REVIEW_REQUIRED"):
        task.blocked_reason = preflight.get("recommendation")
    else:
        task.blocked_reason = None
    task.issue.policy_status = preflight["workflow_state"]

    audit = AuditLog(
        task_id=task.id,
        issue_id=task.issue_id,
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="PREFLIGHT_RERUN",
        actor="USER",
        details=preflight
    )
    db.add(audit)
    await db.commit()

    return PreflightResult(
        task_id=task.id,
        workflow_state=task.workflow_state,
        assignment_required=task.assignment_required,
        draft_comment=task.draft_assignment_comment,
        evidence=preflight["evidence"],
        license_status=preflight["license_status"],
        recommendation=preflight["recommendation"]
    )

@router.post("/{task_id}/assignment/approve", response_model=TaskRead)
async def approve_and_post_assignment(
    task_id: str,
    payload: AssignmentApprovalRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    gh = await get_github_client(db)
    if not gh.token:
        raise HTTPException(
            status_code=400,
            detail="GitHub token is required in Settings to post comments to GitHub."
        )

    # Post comment
    comment_res = await gh.post_issue_comment(
        owner=task.issue.repository.owner,
        repo=task.issue.repository.name,
        issue_number=task.issue.issue_number,
        comment_body=payload.approved_comment
    )

    if not comment_res.get("success"):
        raise HTTPException(
            status_code=400,
            detail=f"Failed to post comment to GitHub: {comment_res.get('error')}"
        )

    task.user_approved_assignment = True
    task.assignment_posted_at = datetime.utcnow()
    task.assignment_comment_id = comment_res.get("comment_id")
    task.workflow_state = "WAITING_FOR_MAINTAINER"

    audit = AuditLog(
        task_id=task.id,
        issue_id=task.issue_id,
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="ASSIGNMENT_COMMENT_POSTED",
        actor="USER",
        details={
            "comment_id": comment_res.get("comment_id"),
            "comment_url": comment_res.get("html_url"),
            "comment_text": payload.approved_comment
        }
    )
    db.add(audit)
    await db.commit()
    await db.refresh(task)
    return task

@router.post("/{task_id}/approve", response_model=TaskRead)
async def approve_task(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    ctx = _resolve_tenant_ctx(ctx)
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.user_approved_assignment = True
    await db.commit()
    await db.refresh(task)
    return task

@router.post("/{task_id}/autonomous-approve", response_model=TaskRead)
async def autonomous_approve(
    task_id: str,
    payload: Optional[AutonomousApproveRequest] = None,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Unified Autonomous Approval:
    - If repository rule requires assignment: posts/submits assignment comment to GitHub and transitions to WAITING_FOR_MAINTAINER.
    - If direct PR is permitted (READY_TO_WORK): automatically prepares isolated workspace, branch, briefs, and launches handoff.
    """
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    gh = await get_github_client(db)

    # Branch 1: Assignment Required Rule
    if task.assignment_required:
        comment_text = (payload.custom_comment if payload and payload.custom_comment else None) or task.draft_assignment_comment or (
            f"Hi @{task.issue.repository.owner} team! I analyzed issue #{task.issue.issue_number} and would love to work on this. "
            f"Could you please assign this to me if available? Thank you!"
        )

        comment_id = None
        comment_url = None
        if gh.token:
            comment_res = await gh.post_issue_comment(
                owner=task.issue.repository.owner,
                repo=task.issue.repository.name,
                issue_number=task.issue.issue_number,
                comment_body=comment_text
            )
            if comment_res.get("success"):
                comment_id = str(comment_res.get("comment_id"))
                comment_url = comment_res.get("html_url")
            else:
                logger.warning(f"Could not post comment to GitHub: {comment_res.get('error')}. Proceeding with queued assignment state.")
        else:
            logger.info("GitHub token not configured; queuing assignment request locally.")

        task.user_approved_assignment = True
        task.assignment_posted_at = datetime.utcnow()
        task.assignment_comment_id = comment_id
        task.draft_assignment_comment = comment_text
        task.workflow_state = "WAITING_FOR_MAINTAINER"

        audit = AuditLog(
            task_id=task.id,
            issue_id=task.issue_id,
            tenant_id=ctx.organization.id,
            user_id=ctx.user.id,
            action="AUTONOMOUS_ASSIGNMENT_SUBMITTED",
            actor="USER",
            details={
                "rule": "ASSIGNMENT_REQUIRED",
                "comment_id": comment_id,
                "comment_url": comment_url,
                "comment_text": comment_text
            }
        )
        db.add(audit)
        await db.commit()
        await db.refresh(task)
        return task

    # Branch 2: Direct Contribution Permitted (No Pre-Assignment Needed)
    wm = WorkspaceManager()
    prep_res = await wm.prepare_workspace(
        task_id=task.id,
        owner=task.issue.repository.owner,
        repo=task.issue.repository.name,
        clone_url=task.issue.repository.html_url,
        issue_number=task.issue.issue_number,
        issue_title=task.issue.title,
        issue_body=task.issue.body or "",
        default_branch=task.issue.repository.default_branch or "main"
    )

    task.worktree_path = prep_res["worktree_path"]
    task.branch_name = prep_res["branch_name"]
    
    # Preserve full implementation brief from analyzer, adding worktree paths
    current_brief = task.implementation_brief or {}
    current_brief.update({
        "brief_path": prep_res["brief_path"],
        "prompt_text": current_brief.get("prompt_text") or prep_res["prompt_text"],
        "default_branch": prep_res["default_branch"]
    })
    task.implementation_brief = current_brief
    task.workflow_state = "WORKSPACE_PREPARED"

    # Autonomous Antigravity desktop launch / handoff
    adapter = AntigravityHandoffService()
    handoff_result = await adapter.open_project_in_antigravity(task.worktree_path)
    if handoff_result.get("success"):
        task.workflow_state = "COLLABORATIVE_WORK"

    audit = AuditLog(
        task_id=task.id,
        issue_id=task.issue_id,
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="AUTONOMOUS_WORKSPACE_PREPARED",
        actor="USER",
        details={
            "rule": "DIRECT_CONTRIBUTION_PERMITTED",
            "worktree_path": prep_res["worktree_path"],
            "branch_name": prep_res["branch_name"],
            "handoff": handoff_result
        }
    )
    db.add(audit)
    await db.commit()
    await db.refresh(task)
    return task

@router.post("/{task_id}/briefing/generate", response_model=TaskRead)
async def generate_task_briefing(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Generates or refreshes the comprehensive autonomous issue briefing for a task.
    """
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    gh = await get_github_client(db)
    analyzer = IssueAnalyzer(github_client=gh)
    brief = await analyzer.analyze_issue(
        owner=task.issue.repository.owner,
        repo=task.issue.repository.name,
        issue_number=task.issue.issue_number,
        title=task.issue.title,
        body=task.issue.body or "",
        labels=task.issue.labels or [],
        language=task.issue.repository.primary_language,
        assignees=task.issue.assignees or []
    )

    task.implementation_brief = brief
    task.assignment_required = brief["rule_check"]["assignment_required"]
    task.draft_assignment_comment = brief["rule_check"]["draft_comment"]
    if task.workflow_state in ("SELECTED", "READY_TO_WORK", "ASSIGNMENT_REQUEST_REQUIRED"):
        task.workflow_state = brief["rule_check"]["workflow_state"]

    await db.commit()
    await db.refresh(task)
    return task

@router.post("/{task_id}/assignment/recheck", response_model=TaskRead)
async def recheck_assignment_status(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    gh = await get_github_client(db)
    fresh_issue = await gh.get_issue(
        owner=task.issue.repository.owner,
        repo=task.issue.repository.name,
        issue_number=task.issue.issue_number
    )

    if fresh_issue:
        assignees = fresh_issue.get("assignees", [])
        task.issue.assignees = assignees
        if assignees and len(assignees) > 0:
            # Check if assigned to current user
            settings_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
            s_res = await db.execute(settings_stmt)
            platform_settings = s_res.scalar_one_or_none()
            user_login = (platform_settings.github_username or "").lower() if platform_settings else ""

            assigned_logins = [a.get("login", "").lower() for a in assignees]
            if user_login and user_login in assigned_logins:
                task.maintainer_approved = True
                task.workflow_state = "READY_TO_WORK"
                task.maintainer_notes = "Issue successfully assigned to your GitHub account!"
            else:
                task.workflow_state = "READY_TO_WORK"
                task.maintainer_approved = True
                task.maintainer_notes = f"Assignment detected ({', '.join(assigned_logins)}). Ready to begin coding."

    await db.commit()
    await db.refresh(task)
    return task

@router.post("/{task_id}/workspace/prepare", response_model=TaskRead)
async def prepare_workspace(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.workflow_state in ("CANCELLED", "MERGED_OR_CLOSED", "WAITING_FOR_MAINTAINER"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot prepare workspace while task is in '{task.workflow_state}' state."
        )

    wm = WorkspaceManager()
    prep_res = await wm.prepare_workspace(
        task_id=task.id,
        owner=task.issue.repository.owner,
        repo=task.issue.repository.name,
        clone_url=task.issue.repository.html_url,
        issue_number=task.issue.issue_number,
        issue_title=task.issue.title,
        issue_body=task.issue.body or "",
        default_branch=task.issue.repository.default_branch or "main"
    )

    task.worktree_path = prep_res["worktree_path"]
    task.branch_name = prep_res["branch_name"]
    task.implementation_brief = {
        "brief_path": prep_res["brief_path"],
        "prompt_text": prep_res["prompt_text"],
        "default_branch": prep_res["default_branch"]
    }
    task.workflow_state = "WORKSPACE_PREPARED"

    audit = AuditLog(
        task_id=task.id,
        issue_id=task.issue_id,
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="WORKSPACE_PREPARED",
        actor="USER",
        details={
            "worktree_path": prep_res["worktree_path"],
            "branch_name": prep_res["branch_name"]
        }
    )
    db.add(audit)
    await db.commit()
    await db.refresh(task)
    return task

@router.post("/{task_id}/antigravity/open")
async def open_in_antigravity(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # If workspace not prepared yet or missing on disk, automatically prepare it
    from pathlib import Path
    if not task.worktree_path or not Path(task.worktree_path).exists() or not (Path(task.worktree_path) / ".git").exists():
        logger.info(f"Workspace not prepared, missing, or broken for task {task_id}. Auto-preparing workspace now...")
        wm = WorkspaceManager()
        prep_res = await wm.prepare_workspace(
            task_id=task.id,
            owner=task.issue.repository.owner,
            repo=task.issue.repository.name,
            clone_url=task.issue.repository.html_url,
            issue_number=task.issue.issue_number,
            issue_title=task.issue.title,
            issue_body=task.issue.body or "",
            default_branch=task.issue.repository.default_branch or "main"
        )
        task.worktree_path = prep_res["worktree_path"]
        task.branch_name = prep_res["branch_name"]
        task.implementation_brief = {
            "brief_path": prep_res["brief_path"],
            "prompt_text": prep_res["prompt_text"],
            "default_branch": prep_res["default_branch"]
        }
        task.workflow_state = "WORKSPACE_PREPARED"
        await db.commit()
        await db.refresh(task)

    adapter = AntigravityHandoffService()
    handoff_result = await adapter.open_project_in_antigravity(task.worktree_path)

    if task.workflow_state == "WORKSPACE_PREPARED":
        task.workflow_state = "COLLABORATIVE_WORK"
        await db.commit()

    handoff_result["worktree_path"] = task.worktree_path
    handoff_result["branch_name"] = task.branch_name
    return handoff_result

@router.post("/{task_id}/ready-for-validation", response_model=TaskRead)
async def mark_ready_for_validation(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.workflow_state = "READY_FOR_VALIDATION"
    await db.commit()
    await db.refresh(task)
    return task

@router.post("/{task_id}/validation/run", response_model=ValidationResult)
async def run_validation(
    task_id: str,
    payload: Optional[ValidationRunRequest] = None,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from pathlib import Path
    # If workspace not prepared yet, missing on disk, or missing .git metadata, auto-prepare it!
    if not task.worktree_path or not Path(task.worktree_path).exists() or not (Path(task.worktree_path) / ".git").exists():
        logger.info(f"Workspace not prepared or broken for task {task_id}. Auto-preparing workspace now before validation...")
        wm = WorkspaceManager()
        prep_res = await wm.prepare_workspace(
            task_id=task.id,
            owner=task.issue.repository.owner,
            repo=task.issue.repository.name,
            clone_url=task.issue.repository.html_url,
            issue_number=task.issue.issue_number,
            issue_title=task.issue.title,
            issue_body=task.issue.body or "",
            default_branch=task.issue.repository.default_branch or "main"
        )
        task.worktree_path = prep_res["worktree_path"]
        task.branch_name = prep_res["branch_name"]
        await db.commit()
        await db.refresh(task)

    task.workflow_state = "VALIDATING"
    await db.commit()

    val_service = ValidationService()
    diff_report = await val_service.scan_git_diff(task.worktree_path)

    # Check custom command or implementation brief test command
    custom_cmd = payload.custom_test_command if payload else None
    if not custom_cmd and task.implementation_brief and isinstance(task.implementation_brief, dict):
        brief_cmd = task.implementation_brief.get("test_strategy", {}).get("command")
        if brief_cmd:
            custom_cmd = brief_cmd

    test_report = await val_service.execute_validation_tests(
        task.worktree_path,
        custom_command=custom_cmd
    )

    passed = diff_report["passed"] and test_report["passed"]
    task.validation_results = test_report
    task.diff_security_report = diff_report

    if passed:
        task.workflow_state = "READY_TO_PUBLISH"
        task.blocked_reason = None
        message = "All validation tests passed and Git diff security checks cleared."
    else:
        task.workflow_state = "VALIDATION_FAILED"
        reasons = []
        if not diff_report["passed"]:
            reasons.append("Diff failed security scan (secrets or prohibited files detected).")
        if not test_report["passed"]:
            reasons.append("Automated test suite returned a non-zero exit code.")
        message = "Validation failed: " + " ".join(reasons)
        task.blocked_reason = message

    audit = AuditLog(
        task_id=task.id,
        issue_id=task.issue_id,
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="VALIDATION_RUN",
        actor="USER",
        details={
            "passed": passed,
            "secrets_detected": diff_report.get("secrets_detected", []),
            "unrelated_files": diff_report.get("unrelated_files", []),
            "commands": test_report.get("commands", [])
        }
    )
    db.add(audit)
    await db.commit()

    # Check if auto-publish is explicitly enabled in Settings
    settings_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    s_res = await db.execute(settings_stmt)
    platform_settings = s_res.scalar_one_or_none()

    if passed and platform_settings and platform_settings.auto_publish_pr:
        logger.info(f"Auto-publish policy enabled. Automatically triggering PR publication for task {task.id}.")
        gh = await get_github_client(db)
        publisher = PRPublisher(github_client=gh)
        pub_res = await publisher.publish_pull_request(
            worktree_path=task.worktree_path,
            owner=task.issue.repository.owner,
            repo=task.issue.repository.name,
            issue_number=task.issue.issue_number,
            issue_title=task.issue.title,
            branch_name=task.branch_name,
            default_branch=task.issue.repository.default_branch or "main"
        )
        if pub_res.get("success"):
            task.pr_number = pub_res.get("pr_number")
            task.pr_url = pub_res.get("pr_url")
            task.pr_state = pub_res.get("state", "open")
            task.workflow_state = "PR_CREATED"
            message += f" Pull request published automatically: {task.pr_url}"
            audit_pub = AuditLog(
                task_id=task.id,
                issue_id=task.issue_id,
                tenant_id=ctx.organization.id,
                user_id=ctx.user.id,
                action="PR_PUBLISHED_AUTOMATIC",
                actor="SYSTEM",
                details=pub_res
            )
            db.add(audit_pub)
            await db.commit()

    return ValidationResult(
        task_id=task.id,
        workflow_state=task.workflow_state,
        passed=passed,
        diff_security_passed=diff_report["passed"],
        secrets_detected=diff_report.get("secrets_detected", []),
        unrelated_files=diff_report.get("unrelated_files", []),
        command_outputs=test_report.get("commands", []),
        message=message
    )


@router.post("/{task_id}/validation/override", response_model=TaskRead)
async def override_validation(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually overrides validation check results and marks task as READY_TO_PUBLISH.
    """
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.workflow_state = "READY_TO_PUBLISH"
    task.blocked_reason = None
    audit = AuditLog(
        task_id=task.id,
        issue_id=task.issue_id,
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="VALIDATION_OVERRIDE",
        actor="USER",
        details={"note": "Manual validation override applied by user"}
    )
    db.add(audit)
    await db.commit()
    await db.refresh(task)
    return task


@router.post("/{task_id}/publish", response_model=PublishResult)
async def publish_pr(
    task_id: str,
    payload: Optional[PublishRequest] = None,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    force_override = payload.force_override if payload else False
    if task.workflow_state != "READY_TO_PUBLISH" and not force_override:
        raise HTTPException(
            status_code=400,
            detail=f"Task must be in READY_TO_PUBLISH state (current: '{task.workflow_state}')."
        )

    task.workflow_state = "PUBLISHING"
    await db.commit()

    gh = await get_github_client(db)
    publisher = PRPublisher(github_client=gh)
    pub_res = await publisher.publish_pull_request(
        worktree_path=task.worktree_path,
        owner=task.issue.repository.owner,
        repo=task.issue.repository.name,
        issue_number=task.issue.issue_number,
        issue_title=task.issue.title,
        branch_name=task.branch_name,
        default_branch=task.issue.repository.default_branch or "main"
    )

    if pub_res.get("success"):
        task.pr_number = pub_res.get("pr_number")
        task.pr_url = pub_res.get("pr_url")
        task.pr_state = pub_res.get("state", "open")
        task.workflow_state = "PR_CREATED"
        task.blocked_reason = None
        audit = AuditLog(
            task_id=task.id,
            issue_id=task.issue_id,
            tenant_id=ctx.organization.id,
            user_id=ctx.user.id,
            action="PR_PUBLISHED",
            actor="USER",
            details=pub_res
        )
        db.add(audit)
        await db.commit()
        return PublishResult(
            task_id=task.id,
            workflow_state="PR_CREATED",
            pr_number=task.pr_number,
            pr_url=task.pr_url,
            success=True,
            message=f"Pull request #{task.pr_number} successfully published to GitHub."
        )
    else:
        task.workflow_state = "PUBLICATION_BLOCKED"
        task.blocked_reason = f"Publishing blocked: {pub_res.get('error')}"
        await db.commit()
        return PublishResult(
            task_id=task.id,
            workflow_state="PUBLICATION_BLOCKED",
            success=False,
            message=f"Publishing blocked: {pub_res.get('error')}"
        )

@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.worktree_path:
        wm = WorkspaceManager()
        await wm.cleanup_workspace(task.worktree_path)

    task.workflow_state = "CANCELLED"
    audit = AuditLog(
        task_id=task.id,
        issue_id=task.issue_id,
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="TASK_CANCELLED",
        actor="USER",
        details={"previous_state": task.workflow_state}
    )
    db.add(audit)
    await db.commit()
    await db.refresh(task)
    return task

@router.post("/{task_id}/pr/sync", response_model=TaskRead)
async def sync_pr_status_endpoint(
    task_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Synchronizes pull request status, merge outcome, CI check runs, and maintainer reviews from GitHub."""
    stmt = select(Task).options(
        selectinload(Task.issue).selectinload(Issue.repository)
    ).where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if not task.pr_number:
        raise HTTPException(status_code=400, detail="Task does not have an associated pull request number.")

    gh = await get_github_client(db)
    from app.services.background_worker import sync_task_pr_status
    await sync_task_pr_status(task, db, gh)
    return task

