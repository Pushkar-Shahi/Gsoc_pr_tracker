import math
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenant import TenantContext, get_current_tenant
from app.db.database import get_db
from app.models.models import (
    User,
    Organization,
    Membership,
    Subscription,
    UsageMeter,
    Repository,
    Issue,
    Task,
    Runner,
    RunnerJob,
    UpiPaymentRequest,
    DiscoveryCheckpoint,
    AuditLog,
    PlatformSettings,
)
from app.services.billing_service import BillingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Platform Administration"])

ALLOWED_TIERS = ("starter", "pro", "team")
ALLOWED_TASK_STATES = (
    "SELECTED",
    "DISCOVERY_QUEUED",
    "ELIGIBLE_READY",
    "ASSIGNMENT_PENDING",
    "IMPLEMENTATION_IN_PROGRESS",
    "VALIDATION_FAILED",
    "PR_CREATED",
    "MERGED",
    "BLOCKED",
    "CANCELED",
)


def _require_platform_admin(ctx: TenantContext) -> None:
    if not getattr(ctx.user, "is_superuser", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator privileges required."
        )


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AdminUserStatusRequest(BaseModel):
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class AdminOrgPlanRequest(BaseModel):
    tier: str = Field(..., description="'starter', 'pro', or 'team'")
    trial_days: Optional[int] = Field(None, description="Grant/reset trial days (>0), expire trial (0), or keep active paid subscription (None)")
    reset_credits: bool = Field(False, description="Also reset Starter lifetime credits counter to 0")


class AdminTaskForceStateRequest(BaseModel):
    workflow_state: str = Field(..., description="New workflow state")
    blocked_reason: Optional[str] = Field(None, description="Optional note or clear reason")


class AdminRuntimeConfigRequest(BaseModel):
    free_beta_mode: Optional[bool] = None
    free_trial_days: Optional[int] = Field(None, ge=0, le=365)
    free_tier_credit_limit: Optional[int] = Field(None, ge=1, le=1000)
    upi_vpa: Optional[str] = None


@router.get("/overview")
async def get_admin_overview(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Returns global platform telemetry, revenue totals, worker status, and runtime flags."""
    _require_platform_admin(ctx)
    now_utc = _utcnow_naive()

    total_users = int((await db.execute(select(func.count(User.id)))).scalar() or 0)
    active_users = int((await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar() or 0)
    superusers = int((await db.execute(select(func.count(User.id)).where(User.is_superuser == True))).scalar() or 0)

    total_orgs = int((await db.execute(select(func.count(Organization.id)))).scalar() or 0)
    tier_rows = (
        await db.execute(select(Organization.billing_tier, func.count(Organization.id)).group_by(Organization.billing_tier))
    ).all()
    tier_counts = {"starter": 0, "pro": 0, "team": 0}
    for tier_name, cnt in tier_rows:
        key = (tier_name or "starter").lower()
        tier_counts[key] = tier_counts.get(key, 0) + int(cnt or 0)

    active_trials = int(
        (
            await db.execute(
                select(func.count(Subscription.id)).where(
                    Subscription.status == "trialing",
                    Subscription.stripe_subscription_id.like("trial_%"),
                    Subscription.current_period_end > now_utc,
                )
            )
        ).scalar()
        or 0
    )

    total_issues = int((await db.execute(select(func.count(Issue.id)))).scalar() or 0)
    eligible_issues = int(
        (
            await db.execute(
                select(func.count(Issue.id)).where(
                    Issue.state == "open",
                    Issue.is_eligible == True,
                )
            )
        ).scalar()
        or 0
    )
    total_repos = int((await db.execute(select(func.count(Repository.id)))).scalar() or 0)

    total_tasks = int((await db.execute(select(func.count(Task.id)))).scalar() or 0)
    pr_created_tasks = int((await db.execute(select(func.count(Task.id)).where(Task.pr_url.is_not(None)))).scalar() or 0)
    blocked_tasks = int((await db.execute(select(func.count(Task.id)).where(Task.workflow_state == "BLOCKED"))).scalar() or 0)
    merged_tasks = int((await db.execute(select(func.count(Task.id)).where(Task.pr_merged == True))).scalar() or 0)

    total_runners = int((await db.execute(select(func.count(Runner.id)))).scalar() or 0)
    online_cutoff = now_utc - timedelta(minutes=3)
    online_runners = int(
        (
            await db.execute(
                select(func.count(Runner.id)).where(
                    Runner.is_active == True,
                    Runner.last_heartbeat_at >= online_cutoff,
                )
            )
        ).scalar()
        or 0
    )
    queued_jobs = int((await db.execute(select(func.count(RunnerJob.id)).where(RunnerJob.status.in_(["queued", "running"])))).scalar() or 0)

    upi_rows = (
        await db.execute(
            select(
                UpiPaymentRequest.status,
                UpiPaymentRequest.payment_purpose,
                func.count(UpiPaymentRequest.id),
                func.coalesce(func.sum(UpiPaymentRequest.amount_inr), 0),
            ).group_by(UpiPaymentRequest.status, UpiPaymentRequest.payment_purpose)
        )
    ).all()

    upi_summary = {
        "pending_count": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "plan_revenue_inr": 0,
        "support_tips_inr": 0,
        "total_revenue_inr": 0,
    }
    for st, purpose, cnt, amt in upi_rows:
        cnt_i = int(cnt or 0)
        amt_i = int(amt or 0)
        if st == "pending":
            upi_summary["pending_count"] += cnt_i
        elif st == "approved":
            upi_summary["approved_count"] += cnt_i
            upi_summary["total_revenue_inr"] += amt_i
            if purpose == "support":
                upi_summary["support_tips_inr"] += amt_i
            else:
                upi_summary["plan_revenue_inr"] += amt_i
        elif st == "rejected":
            upi_summary["rejected_count"] += cnt_i

    latest_ckpt = (
        await db.execute(select(DiscoveryCheckpoint).order_by(desc(DiscoveryCheckpoint.updated_at)).limit(1))
    ).scalar_one_or_none()

    from app.services.background_worker import get_background_worker
    worker = get_background_worker()

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "suspended": max(0, total_users - active_users),
            "superusers": superusers,
        },
        "organizations": {
            "total": total_orgs,
            "by_tier": tier_counts,
            "active_trials": active_trials,
        },
        "issues": {
            "total": total_issues,
            "eligible_open": eligible_issues,
            "repositories": total_repos,
            "last_scan_at": latest_ckpt.updated_at.isoformat() if latest_ckpt and latest_ckpt.updated_at else None,
            "worker_running": bool(worker and getattr(worker, "_running", False)),
        },
        "tasks": {
            "total": total_tasks,
            "pr_created": pr_created_tasks,
            "merged": merged_tasks,
            "blocked": blocked_tasks,
        },
        "runners": {
            "total": total_runners,
            "online": online_runners,
            "active_jobs": queued_jobs,
        },
        "upi": upi_summary,
        "runtime": {
            "free_beta_mode": getattr(settings, "FREE_BETA_MODE", False),
            "free_trial_days": settings.FREE_TRIAL_DAYS,
            "free_tier_credit_limit": settings.FREE_TIER_MONTHLY_TASK_LIMIT,
            "upi_vpa": settings.UPI_VPA,
            "github_token_configured": bool(settings.GITHUB_TOKEN),
        },
    }


@router.get("/users")
async def list_admin_users(
    q: Optional[str] = Query(None, description="Search username, email, or name"),
    limit: int = Query(150, ge=1, le=500),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lists all platform users along with workspace tier, trial countdown, and credit usage."""
    _require_platform_admin(ctx)
    stmt = select(User).order_by(desc(User.created_at)).limit(limit)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = (
            select(User)
            .where(
                (User.github_username.ilike(pattern))
                | (User.email.ilike(pattern))
                | (User.name.ilike(pattern))
            )
            .order_by(desc(User.created_at))
            .limit(limit)
        )

    users = (await db.execute(stmt)).scalars().all()
    if not users:
        return []

    user_ids = [u.id for u in users]

    # Batch load memberships + orgs + subscriptions + usage + task counts
    mem_rows = (
        await db.execute(
            select(Membership, Organization)
            .join(Organization, Membership.org_id == Organization.id)
            .where(Membership.user_id.in_(user_ids))
        )
    ).all()

    org_ids = list({org.id for _, org in mem_rows})
    sub_by_org: Dict[str, Subscription] = {}
    usage_by_org: Dict[str, int] = {}

    if org_ids:
        subs = (await db.execute(select(Subscription).where(Subscription.tenant_id.in_(org_ids)))).scalars().all()
        sub_by_org = {s.tenant_id: s for s in subs}

        usage_rows = (
            await db.execute(
                select(UsageMeter.tenant_id, func.coalesce(func.sum(UsageMeter.usage_count), 0))
                .where(
                    UsageMeter.tenant_id.in_(org_ids),
                    UsageMeter.metric_name == "tasks_created",
                )
                .group_by(UsageMeter.tenant_id)
            )
        ).all()
        usage_by_org = {tid: int(total or 0) for tid, total in usage_rows}

    task_count_rows = (
        await db.execute(
            select(Task.user_id, func.count(Task.id))
            .where(Task.user_id.in_(user_ids))
            .group_by(Task.user_id)
        )
    ).all()
    tasks_by_user = {uid: int(cnt or 0) for uid, cnt in task_count_rows if uid}

    now_utc = _utcnow_naive()
    orgs_by_user: Dict[str, List[Dict[str, Any]]] = {}
    for mem, org in mem_rows:
        sub = sub_by_org.get(org.id)
        is_trial_sub = bool(sub and (sub.stripe_subscription_id or "").startswith("trial_"))
        end_utc = (
            sub.current_period_end.replace(tzinfo=None)
            if (sub and sub.current_period_end and sub.current_period_end.tzinfo)
            else (sub.current_period_end if sub else None)
        )
        remaining_sec = max(0.0, (end_utc - now_utc).total_seconds()) if end_utc else 0.0
        trial_days_left = math.ceil(remaining_sec / 86400.0) if (is_trial_sub and sub.status == "trialing" and remaining_sec > 0) else 0
        trial_active = bool(is_trial_sub and sub.status == "trialing" and remaining_sec > 0 and org.billing_tier in ("pro", "team", "enterprise"))
        trial_expired = bool(is_trial_sub and (sub.status == "canceled" or remaining_sec <= 0) and org.billing_tier == "starter")

        entry = {
            "org_id": org.id,
            "org_name": org.name,
            "is_personal": bool(org.is_personal),
            "role": mem.role,
            "billing_tier": org.billing_tier or "starter",
            "subscription_status": sub.status if sub else "active",
            "trial_active": trial_active,
            "trial_expired": trial_expired,
            "trial_days_remaining": trial_days_left,
            "tasks_used": usage_by_org.get(org.id, 0),
            "task_limit": None if (org.billing_tier in ("pro", "team", "enterprise") or settings.FREE_BETA_MODE) else settings.FREE_TIER_MONTHLY_TASK_LIMIT,
        }
        orgs_by_user.setdefault(mem.user_id, []).append(entry)

    result = []
    for u in users:
        workspaces = sorted(orgs_by_user.get(u.id, []), key=lambda x: (not x["is_personal"], x["org_name"] or ""))
        result.append({
            "id": u.id,
            "github_username": u.github_username,
            "email": u.email,
            "name": u.name,
            "avatar_url": u.avatar_url,
            "is_active": bool(u.is_active),
            "is_superuser": bool(u.is_superuser),
            "is_current_admin": u.id == ctx.user.id,
            "tasks_total": tasks_by_user.get(u.id, 0),
            "workspaces": workspaces,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })
    return result


@router.post("/users/{user_id}/status")
async def update_admin_user_status(
    user_id: str,
    payload: AdminUserStatusRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Activates/suspends a user account or grants/revokes superuser admin role."""
    _require_platform_admin(ctx)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.id == ctx.user.id:
        if payload.is_active is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot suspend your own active admin session.")
        if payload.is_superuser is False:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot revoke your own admin role from the UI.")

    changes: Dict[str, Any] = {}
    if payload.is_active is not None:
        user.is_active = bool(payload.is_active)
        changes["is_active"] = user.is_active
    if payload.is_superuser is not None:
        user.is_superuser = bool(payload.is_superuser)
        changes["is_superuser"] = user.is_superuser

    user.updated_at = _utcnow_naive()
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=ctx.organization.id,
            user_id=ctx.user.id,
            action="ADMIN_USER_UPDATED",
            actor="ADMIN",
            details={"target_user_id": user.id, "target_username": user.github_username, **changes},
        )
    )
    await db.commit()
    return {
        "status": "updated",
        "user_id": user.id,
        "github_username": user.github_username,
        "is_active": bool(user.is_active),
        "is_superuser": bool(user.is_superuser),
    }


@router.post("/organizations/{org_id}/plan")
async def override_admin_org_plan(
    org_id: str,
    payload: AdminOrgPlanRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Directly overrides any organization's billing tier, 15-day trial window, or active status."""
    _require_platform_admin(ctx)
    tier = payload.tier.lower().strip()
    if tier not in ALLOWED_TIERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tier must be starter, pro, or team.")

    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    now_utc = _utcnow_naive()
    sub = (await db.execute(select(Subscription).where(Subscription.tenant_id == org_id))).scalar_one_or_none()
    if not sub:
        customer = await BillingService.get_or_create_customer(org_id, ctx.user.id, None, db)
        sub = Subscription(
            id=str(uuid.uuid4()),
            tenant_id=org_id,
            user_id=ctx.user.id,
            stripe_subscription_id=f"admin_{uuid.uuid4().hex[:12]}",
            stripe_customer_id=customer.stripe_customer_id,
            plan_tier=tier,
            status="active",
            current_period_start=now_utc,
            current_period_end=now_utc + timedelta(days=30),
        )
        db.add(sub)
        await db.flush()

    if payload.trial_days is not None:
        if payload.trial_days > 0:
            effective_trial_tier = "pro" if tier == "starter" else tier
            org.billing_tier = effective_trial_tier
            sub.plan_tier = effective_trial_tier
            sub.status = "trialing"
            if not (sub.stripe_subscription_id or "").startswith("trial_"):
                sub.stripe_subscription_id = f"trial_admin_{uuid.uuid4().hex[:12]}"
            sub.current_period_start = now_utc
            sub.current_period_end = now_utc + timedelta(days=min(365, payload.trial_days))
        else:
            org.billing_tier = "starter"
            sub.plan_tier = "starter"
            sub.status = "canceled"
            sub.current_period_end = now_utc
    else:
        org.billing_tier = tier
        sub.plan_tier = tier
        if tier == "starter":
            sub.status = "canceled"
            sub.stripe_subscription_id = f"starter_admin_{uuid.uuid4().hex[:12]}"
            sub.current_period_end = now_utc
        else:
            sub.status = "active"
            sub.stripe_subscription_id = f"admin_comp_{uuid.uuid4().hex[:12]}"
            sub.current_period_start = now_utc
            sub.current_period_end = now_utc + timedelta(days=30)

    org.updated_at = now_utc
    sub.updated_at = now_utc

    if payload.reset_credits:
        await db.execute(
            update(UsageMeter)
            .where(UsageMeter.tenant_id == org_id, UsageMeter.metric_name == "tasks_created")
            .values(usage_count=0, updated_at=now_utc)
        )

    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=org_id,
            user_id=ctx.user.id,
            action="ADMIN_PLAN_OVERRIDE",
            actor="ADMIN",
            details={
                "org_name": org.name,
                "tier": org.billing_tier,
                "status": sub.status,
                "trial_days": payload.trial_days,
                "reset_credits": payload.reset_credits,
            },
        )
    )
    await db.commit()
    return await BillingService.get_subscription_summary(org_id, db, is_admin=True)


@router.post("/organizations/{org_id}/credits/reset")
async def reset_admin_org_credits(
    org_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Resets Starter one-time task credit consumption back to 0 for the workspace."""
    _require_platform_admin(ctx)
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found.")

    now_utc = _utcnow_naive()
    await db.execute(
        update(UsageMeter)
        .where(UsageMeter.tenant_id == org_id, UsageMeter.metric_name == "tasks_created")
        .values(usage_count=0, updated_at=now_utc)
    )
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=org_id,
            user_id=ctx.user.id,
            action="ADMIN_CREDITS_RESET",
            actor="ADMIN",
            details={"org_name": org.name},
        )
    )
    await db.commit()
    return {"status": "reset", "org_id": org_id, "tasks_created": 0}


@router.get("/tasks")
async def list_admin_tasks(
    state: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lists recent tasks across all tenants so platform admins can inspect or unblock stuck runs."""
    _require_platform_admin(ctx)
    stmt = (
        select(Task, Issue, Repository, User, Organization)
        .join(Issue, Task.issue_id == Issue.id)
        .join(Repository, Issue.repository_id == Repository.id)
        .outerjoin(User, Task.user_id == User.id)
        .outerjoin(Organization, Task.tenant_id == Organization.id)
    )
    if state and state.strip():
        stmt = stmt.where(Task.workflow_state == state.strip().upper())
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            (Issue.title.ilike(pattern))
            | (Repository.full_name.ilike(pattern))
            | (User.github_username.ilike(pattern))
            | (Organization.name.ilike(pattern))
        )

    rows = (await db.execute(stmt.order_by(desc(Task.updated_at)).limit(limit))).all()
    return [
        {
            "id": task.id,
            "workflow_state": task.workflow_state,
            "issue_number": issue.issue_number,
            "issue_title": issue.title,
            "issue_url": issue.html_url,
            "repo_full_name": repo.full_name,
            "username": user.github_username if user else None,
            "org_id": task.tenant_id,
            "org_name": org.name if org else None,
            "pr_number": task.pr_number,
            "pr_url": task.pr_url,
            "pr_merged": bool(task.pr_merged),
            "blocked_reason": task.blocked_reason,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }
        for task, issue, repo, user, org in rows
    ]


@router.post("/tasks/{task_id}/force-state")
async def force_admin_task_state(
    task_id: str,
    payload: AdminTaskForceStateRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Forces a task into a target workflow_state to recover stuck/blocked user workflows."""
    _require_platform_admin(ctx)
    next_state = payload.workflow_state.strip().upper()
    if next_state not in ALLOWED_TASK_STATES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid workflow_state. Allowed: {', '.join(ALLOWED_TASK_STATES)}"
        )

    task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    prev_state = task.workflow_state
    task.workflow_state = next_state
    if payload.blocked_reason is not None:
        task.blocked_reason = payload.blocked_reason or None
    elif next_state != "BLOCKED":
        task.blocked_reason = None
    task.updated_at = _utcnow_naive()

    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=task.tenant_id or ctx.organization.id,
            user_id=ctx.user.id,
            task_id=task.id,
            issue_id=task.issue_id,
            action="ADMIN_TASK_FORCE_STATE",
            actor="ADMIN",
            details={"from_state": prev_state, "to_state": next_state, "reason": payload.blocked_reason},
        )
    )
    await db.commit()
    return {"status": "updated", "task_id": task.id, "workflow_state": task.workflow_state}


@router.get("/audit")
async def list_admin_audit_logs(
    action: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=300),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Returns global cross-tenant audit logs across the entire platform."""
    _require_platform_admin(ctx)
    stmt = (
        select(AuditLog, User, Organization)
        .outerjoin(User, AuditLog.user_id == User.id)
        .outerjoin(Organization, AuditLog.tenant_id == Organization.id)
    )
    if action and action.strip():
        stmt = stmt.where(AuditLog.action.ilike(f"%{action.strip()}%"))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            (AuditLog.action.ilike(pattern))
            | (AuditLog.actor.ilike(pattern))
            | (User.github_username.ilike(pattern))
            | (Organization.name.ilike(pattern))
        )

    rows = (await db.execute(stmt.order_by(desc(AuditLog.created_at)).limit(limit))).all()
    return [
        {
            "id": log.id,
            "action": log.action,
            "actor": log.actor,
            "username": user.github_username if user else None,
            "org_name": org.name if org else None,
            "tenant_id": log.tenant_id,
            "task_id": log.task_id,
            "details": log.details or {},
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log, user, org in rows
    ]


@router.post("/discovery/run")
async def trigger_admin_global_discovery(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Triggers an immediate global GSoC issue discovery scan across curated orgs."""
    _require_platform_admin(ctx)
    from app.services.background_worker import get_background_worker
    from app.services.discovery_service import DiscoveryService

    worker = get_background_worker()
    if worker:
        res = await worker.trigger_cron_scan()
    else:
        res = await DiscoveryService(db).run_discovery_sync(force_refresh=True)

    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=ctx.organization.id,
            user_id=ctx.user.id,
            action="ADMIN_GLOBAL_DISCOVERY_RUN",
            actor="ADMIN",
            details={"discovered_count": res.get("total_discovered", 0)},
        )
    )
    await db.commit()
    return {"status": "completed", **res}


@router.post("/discovery/reconcile")
async def trigger_admin_issue_reconcile(
    purge: bool = Query(True, description="Purge closed or upstream-assigned issues from open pool"),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Re-checks open cached issues against GitHub upstream and prunes closed/claimed ones."""
    _require_platform_admin(ctx)
    from app.db.database import get_session_factory
    from app.services.background_worker import reconcile_inbox_issues_upstream

    session_factory = await get_session_factory()
    summary = await reconcile_inbox_issues_upstream(session_factory, max_issues=None, purge=purge)

    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=ctx.organization.id,
            user_id=ctx.user.id,
            action="ADMIN_ISSUE_RECONCILE",
            actor="ADMIN",
            details=summary if isinstance(summary, dict) else {"result": str(summary)},
        )
    )
    await db.commit()
    return {"status": "completed", "summary": summary}


@router.post("/runtime-config")
async def update_admin_runtime_config(
    payload: AdminRuntimeConfigRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Persists monetization & UPI runtime flags in DB and applies them live without redeploy."""
    _require_platform_admin(ctx)
    sett_row = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))).scalar_one_or_none()
    if not sett_row:
        sett_row = PlatformSettings(id=1, discovery_filters={})
        db.add(sett_row)
        await db.flush()

    filters = dict(sett_row.discovery_filters or {})
    overrides = dict(filters.get("_admin_runtime") or {})

    if payload.free_beta_mode is not None:
        overrides["free_beta_mode"] = bool(payload.free_beta_mode)
    if payload.free_trial_days is not None:
        overrides["free_trial_days"] = int(payload.free_trial_days)
    if payload.free_tier_credit_limit is not None:
        overrides["free_tier_credit_limit"] = int(payload.free_tier_credit_limit)
    if payload.upi_vpa is not None:
        cleaned_vpa = payload.upi_vpa.strip()
        if "@" not in cleaned_vpa or len(cleaned_vpa) < 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UPI VPA must look like name@bank.")
        overrides["upi_vpa"] = cleaned_vpa

    filters["_admin_runtime"] = overrides
    sett_row.discovery_filters = filters
    sett_row.updated_at = _utcnow_naive()

    settings.apply_runtime_overrides(overrides)

    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=ctx.organization.id,
            user_id=ctx.user.id,
            action="ADMIN_RUNTIME_CONFIG_UPDATED",
            actor="ADMIN",
            details=overrides,
        )
    )
    await db.commit()
    return {
        "status": "updated",
        "runtime": {
            "free_beta_mode": getattr(settings, "FREE_BETA_MODE", False),
            "free_trial_days": settings.FREE_TRIAL_DAYS,
            "free_tier_credit_limit": settings.FREE_TIER_MONTHLY_TASK_LIMIT,
            "upi_vpa": settings.UPI_VPA,
        },
    }
