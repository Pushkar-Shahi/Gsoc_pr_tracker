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


class UpiSubmitRequest(BaseModel):
    payment_purpose: str = Field(..., description="'plan' or 'support'")
    plan_tier: Optional[str] = Field(None, description="'pro' or 'team' when purpose is 'plan'")
    billing_cycle: Optional[str] = Field("monthly", description="'monthly', 'annual', or 'one_time'")
    amount_inr: Optional[int] = Field(None, description="Amount in INR (server-validated for plans; custom 1-50000 for support)")
    utr_number: str = Field(..., description="12-digit UTR or UPI Transaction Reference ID")
    payer_upi_id: Optional[str] = Field(None, description="Optional sender UPI ID")
    note: Optional[str] = Field(None, description="Optional payment note")


class UpiReviewRequest(BaseModel):
    action: str = Field(..., description="'approve' or 'reject'")
    admin_note: Optional[str] = Field(None, description="Optional reviewer note")


def _require_platform_admin(ctx: TenantContext) -> None:
    if not getattr(ctx.user, "is_superuser", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access required to review UPI payments."
        )


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
    is_admin = bool(getattr(ctx.user, "is_superuser", False))
    return await BillingService.get_subscription_summary(ctx.organization.id, db, is_admin=is_admin)


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
    is_admin = bool(getattr(ctx.user, "is_superuser", False))
    return await BillingService.get_subscription_summary(ctx.organization.id, db, is_admin=is_admin)


# ==========================================
# Direct UPI Payment & Admin Review Endpoints
# ==========================================

@router.get("/upi/config")
async def get_upi_config():
    """Returns public Direct UPI payment metadata (VPA, QR URL, INR plan rates, AutoPay note)."""
    return BillingService.get_upi_config()


@router.post("/upi/submit")
async def submit_upi_payment(
    payload: UpiSubmitRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Submits a Direct UPI payment UTR / Reference ID for manual verification."""
    try:
        return await BillingService.submit_upi_payment_request(
            tenant_id=ctx.organization.id,
            user=ctx.user,
            payment_purpose=payload.payment_purpose,
            utr_number=payload.utr_number,
            plan_tier=payload.plan_tier,
            billing_cycle=payload.billing_cycle,
            amount_inr=payload.amount_inr,
            payer_upi_id=payload.payer_upi_id,
            note=payload.note,
            db=db,
        )
    except FileExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/upi/my-requests")
async def get_my_upi_requests(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lists Direct UPI submissions for the active organization workspace."""
    return await BillingService.list_tenant_upi_requests(ctx.organization.id, db)


@router.get("/upi/admin/requests")
async def get_admin_upi_requests(
    status_filter: Optional[str] = None,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lists all UPI payment submissions across workspaces for administrator review."""
    _require_platform_admin(ctx)
    return await BillingService.list_admin_upi_requests(db, status_filter=status_filter)


@router.post("/upi/admin/requests/{request_id}/review")
async def review_admin_upi_request(
    request_id: str,
    payload: UpiReviewRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Approves or rejects a UPI payment submission and activates the requested tier on approval."""
    _require_platform_admin(ctx)
    try:
        return await BillingService.review_upi_payment_request(
            request_id=request_id,
            action=payload.action,
            reviewer_user=ctx.user,
            admin_note=payload.admin_note,
            db=db,
        )
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
