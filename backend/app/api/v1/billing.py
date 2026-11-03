import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenant import TenantContext, get_current_tenant
from app.db.database import get_db
from app.models.models import Organization, Subscription
from app.services.billing_service import BillingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing & Subscriptions"])


class CheckoutSessionRequest(BaseModel):
    plan_tier: str = Field(..., description="'pro' or 'team'")
    billing_cycle: str = Field("monthly", description="'monthly' or 'annual'")
    return_url: Optional[str] = Field(None, description="Frontend callback redirect URL")


class PortalSessionRequest(BaseModel):
    return_url: Optional[str] = Field(None, description="Frontend return URL from customer portal")


class SimulateTierRequest(BaseModel):
    tier: str = Field(..., description="'starter', 'pro', or 'team'")


@router.get("/plans")
async def get_plans_catalog():
    """Returns the pricing catalog with tier features, quotas, and pricing."""
    return BillingService.get_plans_catalog()


@router.get("/subscription")
async def get_current_subscription(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Returns the requesting organization's subscription status and current month's task quota usage."""
    return await BillingService.get_subscription_summary(ctx.organization.id, db)


@router.post("/checkout-session")
async def create_checkout_session(
    payload: CheckoutSessionRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Creates a Stripe Checkout Session or returns a simulated checkout link."""
    tier = payload.plan_tier.lower()
    if tier not in ("pro", "team"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan tier. Only 'pro' or 'team' require a checkout session."
        )

    try:
        session_data = await BillingService.create_checkout_session(
            tenant_id=ctx.organization.id,
            user_id=ctx.user.id,
            plan_tier=tier,
            billing_cycle=payload.billing_cycle,
            return_url=payload.return_url,
            db=db
        )
        return session_data
    except Exception as e:
        logger.error(f"Failed to create checkout session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Checkout session creation failed: {str(e)}"
        )


@router.post("/portal-session")
async def create_portal_session(
    payload: Optional[PortalSessionRequest] = None,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Creates a Stripe Customer Portal session for invoice downloads and card updates."""
    return_url = payload.return_url if payload else None
    try:
        portal_data = await BillingService.create_portal_session(
            tenant_id=ctx.organization.id,
            return_url=return_url,
            db=db
        )
        return portal_data
    except Exception as e:
        logger.error(f"Failed to create portal session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Customer portal session creation failed: {str(e)}"
        )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Receives and processes incoming Stripe webhook events with HMAC signature validation.
    Exempted from standard user authentication middleware.
    """
    payload_bytes = await request.body()
    sig_header = request.headers.get("stripe-signature") or request.headers.get("x-stripe-signature")

    # In production or strict mode, verify signature
    if not BillingService.verify_webhook_signature(payload_bytes, sig_header):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature"
        )

    try:
        event_dict = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON in webhook payload"
        )

    result = await BillingService.process_stripe_event(event_dict, db)
    return {"status": "success", "result": result}


@router.post("/simulate-tier")
async def simulate_tier_transition(
    payload: SimulateTierRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Developer shortcut to simulate upgrading/downgrading the active organization's plan tier
    for local testing without needing a Stripe credit card.
    """
    target_tier = payload.tier.lower()
    if target_tier not in ("starter", "pro", "team", "enterprise"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tier. Choose 'starter', 'pro', or 'team'."
        )

    # 1. Update Organization billing_tier
    await db.execute(
        update(Organization)
        .where(Organization.id == ctx.organization.id)
        .values(billing_tier=target_tier)
    )

    # 2. Update or insert Subscription
    sub_stmt = select(Subscription).where(Subscription.tenant_id == ctx.organization.id)
    sub_res = await db.execute(sub_stmt)
    sub = sub_res.scalar_one_or_none()
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    if target_tier == "starter":
        if sub:
            sub.status = "canceled"
            sub.plan_tier = "starter"
            sub.updated_at = now_utc
    else:
        if not sub:
            sub = Subscription(
                id=str(uuid.uuid4()),
                tenant_id=ctx.organization.id,
                user_id=ctx.user.id,
                stripe_subscription_id=f"sub_sim_{uuid.uuid4().hex[:12]}",
                stripe_customer_id=f"cus_sim_{uuid.uuid4().hex[:12]}",
                plan_tier=target_tier,
                status="active",
                current_period_start=now_utc,
                current_period_end=now_utc + timedelta(days=30),
            )
            db.add(sub)
        else:
            sub.status = "active"
            sub.plan_tier = target_tier
            sub.current_period_end = now_utc + timedelta(days=30)
            sub.updated_at = now_utc

    await db.commit()
    return await BillingService.get_subscription_summary(ctx.organization.id, db)
