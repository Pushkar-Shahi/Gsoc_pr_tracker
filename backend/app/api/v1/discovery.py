from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.entitlements import require_tier
from app.core.tenant import TenantContext
from app.db.database import get_db
from app.models.models import Issue, PlatformSettings, UserSettings
from app.schemas.schemas import DiscoverySyncRequest, DiscoveryStatusResponse
from app.services.discovery_service import DiscoveryService
from app.services.github_client import GitHubClient
from app.services.ranking_service import RankingService

router = APIRouter(prefix="/discovery", tags=["Discovery"])

@router.post("/sync")
async def trigger_discovery_sync(
    payload: DiscoverySyncRequest,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    res = await db.execute(stmt)
    s = res.scalar_one_or_none()
    token = s.github_token if s else None

    gh = GitHubClient(token=token)
    service = DiscoveryService(db=db, github_client=gh)
    result = await service.run_discovery_sync(
        language=payload.language,
        force_refresh=payload.force_refresh,
        gsoc_only=payload.gsoc_only
    )
    return result

@router.get("/status", response_model=DiscoveryStatusResponse)
async def get_discovery_status(db: AsyncSession = Depends(get_db)):
    total_issues_res = await db.execute(select(func.count(Issue.id)))
    total_issues = total_issues_res.scalar() or 0

    eligible_res = await db.execute(select(func.count(Issue.id)).where(Issue.is_eligible == True))
    total_eligible = eligible_res.scalar() or 0

    latest_issue_res = await db.execute(select(Issue.last_verified_at).order_by(Issue.last_verified_at.desc()).limit(1))
    last_synced = latest_issue_res.scalar_one_or_none()

    stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    res = await db.execute(stmt)
    s = res.scalar_one_or_none()
    token = s.github_token if s else None

    gh = GitHubClient(token=token)

    return DiscoveryStatusResponse(
        last_synced_at=last_synced or datetime.utcnow(),
        total_issues=total_issues,
        total_eligible=total_eligible,
        rate_limit_remaining=gh.rate_limit_remaining,
        rate_limit_limit=gh.rate_limit_limit,
        rate_limit_reset=gh.rate_limit_reset,
        is_syncing=False,
        coverage_label="Last synced (Global Search)",
        errors=[]
    )


@router.get("/cron-status")
async def get_cron_status():
    from app.services.background_worker import get_background_worker
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    worker = get_background_worker()

    interval_sec = worker.discovery_interval_sec if worker else 7200
    now_epoch = int(now_utc.timestamp())
    cycle_start_epoch = (now_epoch // interval_sec) * interval_sec
    cycle_end_epoch = cycle_start_epoch + interval_sec
    cycle_start = datetime.fromtimestamp(cycle_start_epoch, tz=timezone.utc)
    cycle_end = datetime.fromtimestamp(cycle_end_epoch, tz=timezone.utc)

    if not worker:
        return {
            "active": True,
            "interval_hours": interval_sec // 3600,
            "interval_seconds": interval_sec,
            "is_running": False,
            "last_run_at": cycle_start.isoformat(),
            "next_run_at": cycle_end.isoformat(),
            "target_orgs": ["NumFOCUS", "Python Software Foundation", "DeepChem", "Kornia"],
            "priority": "Chronological (Time-based, newest first)",
        }

    # Keep worker sync aligned with universal internal schedule
    last_run = worker.last_cron_run_at
    if last_run and last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    if not last_run or last_run < cycle_start:
        worker.last_cron_run_at = cycle_start
    worker.next_cron_run_at = cycle_end

    return {
        "active": worker._running,
        "interval_hours": worker.discovery_interval_sec // 3600,
        "interval_seconds": worker.discovery_interval_sec,
        "is_running": worker.is_cron_running,
        "last_run_at": worker.last_cron_run_at.isoformat() if worker.last_cron_run_at else cycle_start.isoformat(),
        "next_run_at": worker.next_cron_run_at.isoformat() if worker.next_cron_run_at else cycle_end.isoformat(),
        "last_issues_synced": getattr(worker, "last_cron_discovered", 0),
        "last_issues_pruned": getattr(worker, "last_cron_pruned", 0),
        "target_orgs": worker.cron_target_orgs,
        "priority": "Chronological (Time-based, newest first)",
    }


@router.post("/cron-run-now")
async def trigger_cron_run_now(db: AsyncSession = Depends(get_db)):
    from app.services.background_worker import get_background_worker
    worker = get_background_worker()
    if worker:
        result = await worker.trigger_cron_scan()
        return result
    else:
        stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
        res = await db.execute(stmt)
        s = res.scalar_one_or_none()
        gh = GitHubClient(token=s.github_token if s else None)
        service = DiscoveryService(db=db, github_client=gh)
        result = await service.run_discovery_sync(force_refresh=True, page_limit=2)
        discovered = int(result.get("total_discovered", 0))
        return {
            "success": True,
            "status": "success",
            "discovered": discovered,
            "last_issues_synced": discovered,
            "last_issues_pruned": 0,
            "fallback": True,
            "last_run_at": datetime.utcnow().isoformat()
        }


class PriorityDiscoveryRequest(BaseModel):
    language: Optional[str] = None
    gsoc_only: bool = True


@router.post("/priority-sync")
async def trigger_priority_discovery_sync(
    payload: Optional[PriorityDiscoveryRequest] = None,
    ctx: TenantContext = Depends(require_tier("pro")),
    db: AsyncSession = Depends(get_db),
):
    """
    On-demand priority discovery sync using the Pro/Team user's weighted skill matrix
    instead of waiting for the standard 2-hour community crawl cycle.
    """
    p_res = await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))
    s = p_res.scalar_one_or_none()

    u_res = await db.execute(select(UserSettings).where(UserSettings.user_id == ctx.user.id))
    u_sett = u_res.scalar_one_or_none()
    filters = dict((u_sett.discovery_filters if u_sett else None) or {})
    ranking_svc = RankingService(
        user_skills=u_sett.skills_profile if (u_sett and u_sett.skills_profile) else None,
        skill_weights=filters.get("skill_weights"),
        tag_weights=filters.get("tag_weights"),
    )

    gh = GitHubClient(token=s.github_token if s else None)
    service = DiscoveryService(db=db, github_client=gh, ranking_service=ranking_svc)
    result = await service.run_discovery_sync(
        language=payload.language if payload else None,
        force_refresh=True,
        page_limit=2,
        gsoc_only=payload.gsoc_only if payload else True,
    )
    return {
        "status": "priority_synced",
        "tier": ctx.organization.billing_tier,
        "discovered": result.get("total_discovered", 0),
        "errors": result.get("errors", []),
        "synced_at": datetime.utcnow().isoformat(),
    }

