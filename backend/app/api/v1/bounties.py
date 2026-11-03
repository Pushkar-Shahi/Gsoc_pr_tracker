import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenant import TenantContext, get_current_tenant
from app.db.database import get_db
from app.models.models import Issue, Repository, Task
from app.schemas.schemas import IssueRead, BountyStatsResponse, BountyClaimRequest
from app.services.bounty_service import BountyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bounties", tags=["Bounties & Monetization"])


@router.get("", response_model=List[IssueRead])
async def list_bounties(
    platform: Optional[str] = Query("all", description="polar, algora, or all"),
    min_amount: float = Query(0.0, ge=0.0, description="Minimum bounty reward in USD"),
    search: Optional[str] = Query(None, description="Search keyword in title or repo"),
    sort_by: str = Query("amount_desc", description="amount_desc, ranking_score, or newest"),
    limit: int = Query(50, ge=1, le=100),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns available open-source issues with financial bounties (Polar.sh, Algora, Sponsors).
    Auto-seeds the tenant bounty catalog if not already populated.
    """
    # Check if tenant has bounty issues; if not, sync initial catalog
    count_stmt = select(Issue).where(
        Issue.tenant_id == ctx.organization.id,
        Issue.bounty_amount > 0
    )
    res = await db.execute(count_stmt)
    existing = res.scalars().all()
    if not existing:
        await BountyService.sync_bounties_to_database(db, ctx.organization.id, ctx.user.id)

    stmt = (
        select(Issue)
        .options(selectinload(Issue.repository))
        .where(Issue.tenant_id == ctx.organization.id, Issue.bounty_amount >= min_amount)
    )

    if platform and platform.lower() != "all":
        stmt = stmt.where(Issue.bounty_platform.ilike(platform.lower()))

    if search:
        kw = f"%{search.lower()}%"
        stmt = stmt.join(Issue.repository).where(
            Issue.title.ilike(kw) | Issue.body.ilike(kw) | Repository.name.ilike(kw)
        )

    if sort_by == "amount_desc":
        stmt = stmt.order_by(desc(Issue.bounty_amount))
    elif sort_by == "ranking_score":
        stmt = stmt.order_by(desc(Issue.ranking_score))
    else:
        stmt = stmt.order_by(desc(Issue.created_at))

    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    issues = res.scalars().all()

    # Populate active_task dict if a task is already linked
    for iss in issues:
        task_res = await db.execute(
            select(Task).where(Task.issue_id == iss.id, Task.tenant_id == ctx.organization.id)
        )
        t = task_res.scalar_one_or_none()
        if t:
            iss.active_task = {
                "id": t.id,
                "workflow_state": t.workflow_state,
                "worktree_path": t.worktree_path,
                "branch_name": t.branch_name
            }

    return issues


@router.get("/stats", response_model=BountyStatsResponse)
async def get_bounty_stats(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Returns aggregate financial metrics for available and claimed bounties."""
    # Ensure catalog is populated
    count_stmt = select(Issue).where(
        Issue.tenant_id == ctx.organization.id,
        Issue.bounty_amount > 0
    )
    res = await db.execute(count_stmt)
    if not res.scalars().first():
        await BountyService.sync_bounties_to_database(db, ctx.organization.id, ctx.user.id)

    metrics = await BountyService.get_bounty_metrics(db, ctx.organization.id)
    return metrics


@router.post("/sync")
async def force_sync_bounties(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Manually refreshes the bounty catalog from live external APIs."""
    synced = await BountyService.sync_bounties_to_database(db, ctx.organization.id, ctx.user.id)
    return {
        "status": "success",
        "synced_count": len(synced),
        "message": f"Successfully synchronized {len(synced)} bounties."
    }


@router.post("/{issue_id}/start-work")
async def start_bounty_work(
    issue_id: str,
    req: BountyClaimRequest = BountyClaimRequest(),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Claims a high-value bounty ticket, provisions an isolated Git worktree,
    and writes explicit bounty payout instructions into .antigravity/BRIEF.md.
    """
    try:
        result = await BountyService.claim_bounty_and_prepare_task(
            db=db,
            issue_id=issue_id,
            tenant_id=ctx.organization.id,
            user_id=ctx.user.id,
            custom_notes=req.custom_notes
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error starting bounty work for issue {issue_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to claim bounty and prepare workspace: {str(e)}"
        )
