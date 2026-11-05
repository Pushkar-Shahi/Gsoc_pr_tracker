import logging
from typing import Callable
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenant import get_current_tenant, TenantContext
from app.db.database import get_db
from app.services.billing_service import BillingService

logger = logging.getLogger(__name__)

TIER_RANKS = {
    "starter": 0,
    "pro": 1,
    "team": 2,
    "enterprise": 3,
}

def require_tier(minimum_tier: str) -> Callable:
    """
    FastAPI route dependency that ensures the requesting tenant holds at least the required tier.
    Raises HTTP 403 with TIER_UPGRADE_REQUIRED code if under-provisioned.
    """
    min_rank = TIER_RANKS.get(minimum_tier.lower(), 1)

    async def tier_checker(ctx: TenantContext = Depends(get_current_tenant)) -> TenantContext:
        # Free Beta Mode or Superuser bypasses all tier restrictions
        if getattr(settings, "FREE_BETA_MODE", False) or ctx.user.is_superuser:
            return ctx

        current_tier = (ctx.organization.billing_tier or "starter").lower()
        curr_rank = TIER_RANKS.get(current_tier, 0)

        if curr_rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": f"This action requires a {minimum_tier.capitalize()} subscription.",
                    "code": "TIER_UPGRADE_REQUIRED",
                    "required_tier": minimum_tier,
                    "current_tier": current_tier,
                }
            )
        return ctx

    return tier_checker


async def enforce_task_creation_quota(ctx: TenantContext, db: AsyncSession) -> None:
    """
    Verifies that the tenant has not exceeded their monthly task quota.
    Raises HTTP 402 PAYMENT_REQUIRED with QUOTA_EXCEEDED code if limit is reached.
    """
    # Free Beta Mode or Superuser bypasses quotas completely
    if getattr(settings, "FREE_BETA_MODE", False) or ctx.user.is_superuser:
        return

    current_tier = (ctx.organization.billing_tier or "starter").lower()
    usage_count, limit = await BillingService.get_monthly_task_usage(ctx.organization.id, db)

    if limit is not None and usage_count >= limit:
        logger.warning(
            f"Tenant {ctx.organization.id} exceeded task limit: {usage_count}/{limit} on tier {current_tier}"
        )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": f"You have reached your free monthly limit of {limit} tasks on Community Starter. Upgrade to Pro for unlimited PR generation.",
                "code": "QUOTA_EXCEEDED",
                "tier": current_tier,
                "current_usage": usage_count,
                "monthly_limit": limit,
            }
        )

