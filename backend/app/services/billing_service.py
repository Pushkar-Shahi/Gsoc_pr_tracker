import hashlib
import hmac
import logging
import math
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple, List

import stripe
from sqlalchemy import select, update, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import (
    Organization, User, BillingCustomer, Subscription, UsageMeter,
    UpiPaymentRequest, AuditLog
)

logger = logging.getLogger(__name__)

UPI_UTR_PATTERN = re.compile(r"^[A-Z0-9]{10,35}$")

# Initialize Stripe API Key if configured
if settings.STRIPE_SECRET_KEY and not settings.STRIPE_SECRET_KEY.startswith("sk_test_mock"):
    stripe.api_key = settings.STRIPE_SECRET_KEY

PLANS_CATALOG = [
    {
        "id": "starter",
        "name": "Community Starter",
        "description": "Essential automated PR discovery and guided Antigravity handoff for open source contributors.",
        "currency": "INR",
        "currency_symbol": "₹",
        "price_monthly": 0,
        "price_annual": 0,
        "price_id_monthly": "free",
        "price_id_annual": "free",
        "quota_tasks": 5,
        "features": [
            {"name": "5 active tasks per month", "included": True},
            {"name": "Public open source repositories", "included": True},
            {"name": "Local hybrid runner execution", "included": True},
            {"name": "Diff secret & credential scanning", "included": True},
            {"name": "Standard discovery sync (2-hr cycle)", "included": True},
            {"name": "Bring-Your-Own-Key (BYOK) AI tokens", "included": True},
            {"name": "Real-time webhook issue alerts", "included": False},
            {"name": "Priority GSoC 2026 org filters & PR guard", "included": False},
            {"name": "Private repositories & orgs", "included": False},
        ],
    },
    {
        "id": "pro",
        "name": "Pro Developer",
        "description": "Unconstrained task automation and priority GSoC issue discovery for high-velocity contributors.",
        "currency": "INR",
        "currency_symbol": "₹",
        "price_monthly": 100,
        "price_annual": 1000,
        "price_id_monthly": settings.STRIPE_PRO_MONTHLY_PRICE_ID,
        "price_id_annual": settings.STRIPE_PRO_ANNUAL_PRICE_ID,
        "quota_tasks": None,  # Unlimited
        "features": [
            {"name": "Unlimited tasks and PR creations", "included": True, "highlight": True},
            {"name": "Public open source repositories", "included": True},
            {"name": "Local hybrid runner execution", "included": True},
            {"name": "Diff secret & credential scanning", "included": True},
            {"name": "Priority real-time discovery & webhooks", "included": True, "highlight": True},
            {"name": "Real-time GSoC PR-free verification", "included": True, "highlight": True},
            {"name": "Custom skill & tag weighting matrix", "included": True},
            {"name": "Priority runner job queue", "included": True},
            {"name": "Private repositories & orgs", "included": False},
        ],
    },
    {
        "id": "team",
        "name": "Engineering Team",
        "description": "Complete codebase triage, private org management, shared BYOK secrets, and centralized velocity metrics.",
        "currency": "INR",
        "currency_symbol": "₹",
        "price_monthly": 300,
        "price_annual": 3000,
        "price_id_monthly": settings.STRIPE_TEAM_SEAT_PRICE_ID,
        "price_id_annual": settings.STRIPE_TEAM_SEAT_PRICE_ID,
        "quota_tasks": None,  # Unlimited
        "features": [
            {"name": "Everything in Pro Developer", "included": True},
            {"name": "Private GitHub Organizations & Repositories", "included": True, "highlight": True},
            {"name": "Multi-user seats & RBAC governance", "included": True, "highlight": True},
            {"name": "Shared team BYOK AI keys & triage policy", "included": True},
            {"name": "Centralized team PR velocity dashboard", "included": True},
            {"name": "Automated branch & PR provisioning", "included": True},
            {"name": "Dedicated team audit trail exports", "included": True},
        ],
    },
]


def is_simulation_mode() -> bool:
    """Checks whether the system is running in mock/simulation mode without live Stripe secrets."""
    key = settings.STRIPE_SECRET_KEY or ""
    return not key or key.startswith("sk_test_mock") or key == "test_secret"


def get_current_month_bounds() -> Tuple[datetime, datetime]:
    """Returns (start_of_month, end_of_month) in UTC for quota metering."""
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
    # Next month start
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return start.replace(tzinfo=None), end.replace(tzinfo=None)


class BillingService:
    @staticmethod
    def get_plans_catalog() -> List[Dict[str, Any]]:
        return PLANS_CATALOG

    @staticmethod
    async def get_or_create_customer(
        tenant_id: str,
        user_id: Optional[str],
        email: Optional[str],
        db: AsyncSession
    ) -> BillingCustomer:
        """Finds existing BillingCustomer or registers a new one via Stripe or Simulation."""
        stmt = select(BillingCustomer).where(BillingCustomer.tenant_id == tenant_id)
        res = await db.execute(stmt)
        customer = res.scalar_one_or_none()
        if customer:
            return customer

        stripe_cus_id: str
        if not is_simulation_mode():
            try:
                sc = stripe.Customer.create(
                    email=email or f"tenant_{tenant_id}@example.com",
                    metadata={"tenant_id": tenant_id, "user_id": user_id or ""}
                )
                stripe_cus_id = sc.id
            except Exception as e:
                logger.error(f"Failed to create Stripe customer: {e}")
                stripe_cus_id = f"cus_sim_{uuid.uuid4().hex[:14]}"
        else:
            stripe_cus_id = f"cus_sim_{uuid.uuid4().hex[:14]}"

        customer = BillingCustomer(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            stripe_customer_id=stripe_cus_id,
            email=email
        )
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
        return customer

    @staticmethod
    async def create_checkout_session(
        tenant_id: str,
        user_id: Optional[str],
        plan_tier: str,
        billing_cycle: str = "monthly",
        return_url: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Creates a Stripe Checkout Session or returns a simulated checkout URL."""
        if plan_tier not in ("pro", "team"):
            raise ValueError(f"Invalid plan tier for checkout: {plan_tier}. Only 'pro' or 'team' require checkout.")

        customer = None
        if db is not None:
            customer = await BillingService.get_or_create_customer(tenant_id, user_id, None, db)

        price_id = settings.STRIPE_PRO_MONTHLY_PRICE_ID
        if plan_tier == "pro":
            price_id = settings.STRIPE_PRO_ANNUAL_PRICE_ID if billing_cycle == "annual" else settings.STRIPE_PRO_MONTHLY_PRICE_ID
        elif plan_tier == "team":
            price_id = settings.STRIPE_TEAM_SEAT_PRICE_ID

        success_url = (return_url or settings.BILLING_SUCCESS_URL) + "&session_id={CHECKOUT_SESSION_ID}"
        cancel_url = return_url or settings.BILLING_CANCEL_URL

        if is_simulation_mode():
            sim_session_id = f"cs_sim_{uuid.uuid4().hex[:18]}"
            # Replace placeholder in simulated URL
            sim_redirect = success_url.replace("{CHECKOUT_SESSION_ID}", sim_session_id) + f"&tier={plan_tier}"
            return {
                "checkout_url": sim_redirect,
                "session_id": sim_session_id,
                "is_simulated": True,
                "plan_tier": plan_tier,
                "billing_cycle": billing_cycle,
            }

        try:
            session = stripe.checkout.Session.create(
                customer=customer.stripe_customer_id if customer else None,
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "tenant_id": tenant_id,
                    "user_id": user_id or "",
                    "plan_tier": plan_tier,
                },
            )
            return {
                "checkout_url": session.url,
                "session_id": session.id,
                "is_simulated": False,
                "plan_tier": plan_tier,
                "billing_cycle": billing_cycle,
            }
        except Exception as e:
            logger.error(f"Error creating Stripe checkout session: {e}")
            sim_session_id = f"cs_sim_fallback_{uuid.uuid4().hex[:12]}"
            return {
                "checkout_url": (return_url or settings.BILLING_SUCCESS_URL) + f"&session_id={sim_session_id}&tier={plan_tier}",
                "session_id": sim_session_id,
                "is_simulated": True,
                "plan_tier": plan_tier,
            }

    @staticmethod
    async def create_portal_session(
        tenant_id: str,
        return_url: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Creates a Stripe Billing Customer Portal session."""
        customer = None
        if db is not None:
            customer = await BillingService.get_or_create_customer(tenant_id, None, None, db)

        back_url = return_url or "http://localhost:5173/?billing=portal_return"

        if is_simulation_mode() or not customer or customer.stripe_customer_id.startswith("cus_sim"):
            return {
                "portal_url": f"{back_url}&portal=simulated_success",
                "is_simulated": True
            }

        try:
            portal_session = stripe.billing_portal.Session.create(
                customer=customer.stripe_customer_id,
                return_url=back_url
            )
            return {
                "portal_url": portal_session.url,
                "is_simulated": False
            }
        except Exception as e:
            logger.error(f"Error creating Stripe billing portal session: {e}")
            return {
                "portal_url": f"{back_url}&portal=fallback_simulated",
                "is_simulated": True
            }

    @staticmethod
    def verify_webhook_signature(payload_bytes: bytes, sig_header: Optional[str]) -> bool:
        """Verifies Stripe HMAC signature or test secret."""
        if not sig_header:
            return False

        secret = settings.STRIPE_WEBHOOK_SECRET
        if not secret:
            return False

        # In simulation/mock mode with custom test headers
        if secret.startswith("whsec_mock") or secret == "test_secret":
            # Compute standard HMAC SHA256
            expected = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
            # Allow direct match or t=... header format
            if sig_header == expected or f"v1={expected}" in sig_header:
                return True

        try:
            stripe.Webhook.construct_event(payload_bytes, sig_header, secret)
            return True
        except Exception as e:
            logger.warning(f"Stripe webhook signature validation failed: {e}")
            return False

    @staticmethod
    async def process_stripe_event(event_dict: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
        """Processes a verified Stripe event and updates subscriptions/organizations accordingly."""
        event_type = event_dict.get("type", "")
        data_object = event_dict.get("data", {}).get("object", {})

        logger.info(f"Processing Stripe billing event: {event_type}")

        if event_type == "checkout.session.completed":
            metadata = data_object.get("metadata", {})
            tenant_id = metadata.get("tenant_id")
            user_id = metadata.get("user_id")
            plan_tier = metadata.get("plan_tier", "pro")
            stripe_cus_id = data_object.get("customer")
            stripe_sub_id = data_object.get("subscription") or f"sub_sim_{uuid.uuid4().hex[:12]}"

            if tenant_id:
                # Safely resolve user_id foreign key if present
                actual_user_id = None
                if user_id:
                    chk_u = await db.execute(select(User).where(User.id == user_id))
                    if chk_u.scalar_one_or_none():
                        actual_user_id = user_id

                # 1. Update Organization tier
                await db.execute(
                    update(Organization)
                    .where(Organization.id == tenant_id)
                    .values(billing_tier=plan_tier)
                )

                # 2. Upsert Subscription
                sub_stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
                sub_res = await db.execute(sub_stmt)
                sub = sub_res.scalar_one_or_none()
                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                if not sub:
                    sub = Subscription(
                        id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        user_id=actual_user_id,
                        stripe_subscription_id=stripe_sub_id,
                        stripe_customer_id=stripe_cus_id or f"cus_{uuid.uuid4().hex[:12]}",
                        plan_tier=plan_tier,
                        status="active",
                        current_period_start=now_utc,
                        current_period_end=now_utc + timedelta(days=30),
                    )
                    db.add(sub)
                else:
                    sub.plan_tier = plan_tier
                    sub.status = "active"
                    if actual_user_id:
                        sub.user_id = actual_user_id
                    sub.stripe_subscription_id = stripe_sub_id
                    if stripe_cus_id:
                        sub.stripe_customer_id = stripe_cus_id
                    sub.updated_at = now_utc

                await db.commit()
                return {"status": "upgraded", "tenant_id": tenant_id, "tier": plan_tier}

        elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
            stripe_sub_id = data_object.get("id")
            status = data_object.get("status", "active")
            cancel_at_period_end = data_object.get("cancel_at_period_end", False)

            sub_stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
            sub_res = await db.execute(sub_stmt)
            sub = sub_res.scalar_one_or_none()
            if sub:
                sub.status = status
                sub.cancel_at_period_end = cancel_at_period_end
                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                sub.updated_at = now_utc

                # If subscription has lapsed or is past due, downgrade tenant to starter
                if status in ("past_due", "unpaid", "canceled"):
                    await db.execute(
                        update(Organization)
                        .where(Organization.id == sub.tenant_id)
                        .values(billing_tier="starter")
                    )

                await db.commit()
                return {"status": "subscription_updated", "tenant_id": sub.tenant_id, "sub_status": status}

        elif event_type == "customer.subscription.deleted":
            stripe_sub_id = data_object.get("id")
            sub_stmt = select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
            sub_res = await db.execute(sub_stmt)
            sub = sub_res.scalar_one_or_none()
            if sub:
                sub.status = "canceled"
                now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
                sub.updated_at = now_utc

                # Downgrade organization back to starter
                await db.execute(
                    update(Organization)
                    .where(Organization.id == sub.tenant_id)
                    .values(billing_tier="starter")
                )
                await db.commit()
                return {"status": "subscription_canceled", "tenant_id": sub.tenant_id, "tier": "starter"}

        return {"status": "unhandled_or_ignored", "event_type": event_type}

    # ==========================================
    # Usage Metering & Quota Tracking
    # ==========================================

    @staticmethod
    async def get_or_create_task_usage_meter(tenant_id: str, db: AsyncSession) -> UsageMeter:
        """Finds or initializes the monthly usage meter for a tenant."""
        start_month, end_month = get_current_month_bounds()
        stmt = select(UsageMeter).where(
            UsageMeter.tenant_id == tenant_id,
            UsageMeter.metric_name == "tasks_created",
            UsageMeter.period_start == start_month
        )
        res = await db.execute(stmt)
        meter = res.scalar_one_or_none()
        if not meter:
            meter = UsageMeter(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                metric_name="tasks_created",
                period_start=start_month,
                period_end=end_month,
                usage_count=0,
                limit_count=settings.FREE_TIER_MONTHLY_TASK_LIMIT
            )
            db.add(meter)
            await db.commit()
            await db.refresh(meter)
        return meter

    @staticmethod
    async def provision_reverse_free_trial(
        tenant_id: str,
        user_id: Optional[str],
        db: AsyncSession,
        trial_days: Optional[int] = None,
    ) -> Optional[Subscription]:
        """
        Provisions a 15-day Pro Reverse Free Trial for newly onboarded workspaces
        without requiring an upfront credit card or UPI mandate.
        """
        days = settings.FREE_TRIAL_DAYS if trial_days is None else int(trial_days)
        if days <= 0:
            return None

        existing_sub = (
            await db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        ).scalar_one_or_none()
        if existing_sub:
            return existing_sub

        org = (
            await db.execute(select(Organization).where(Organization.id == tenant_id))
        ).scalar_one_or_none()
        if org:
            org.billing_tier = "pro"

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        trial_sub = Subscription(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            stripe_subscription_id=f"trial_{tenant_id}",
            stripe_customer_id=f"trial_cust_{tenant_id}",
            plan_tier="pro",
            status="trialing",
            current_period_start=now_utc,
            current_period_end=now_utc + timedelta(days=days),
            cancel_at_period_end=False,
        )
        db.add(trial_sub)
        await db.flush()
        return trial_sub

    @staticmethod
    async def sync_trial_expiration(
        tenant_id: str,
        db: AsyncSession,
    ) -> Tuple[Optional[Organization], Optional[Subscription]]:
        """
        Checks if a Reverse Free Trial has passed its deadline and automatically
        downgrades the organization to Community Starter limits if unpaid.
        """
        org = (
            await db.execute(select(Organization).where(Organization.id == tenant_id))
        ).scalar_one_or_none()
        sub = (
            await db.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))
        ).scalar_one_or_none()

        if sub and sub.status == "trialing" and sub.current_period_end:
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            end_utc = (
                sub.current_period_end.replace(tzinfo=None)
                if sub.current_period_end.tzinfo
                else sub.current_period_end
            )
            if now_utc >= end_utc:
                sub.status = "canceled"
                sub.plan_tier = "starter"
                sub.updated_at = now_utc
                if org:
                    org.billing_tier = "starter"
                db.add(AuditLog(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    user_id=sub.user_id,
                    action="FREE_TRIAL_EXPIRED",
                    actor="SYSTEM",
                    details={"downgraded_to": "starter", "expired_at": now_utc.isoformat()},
                ))
                await db.commit()
                await db.refresh(sub)
                if org:
                    await db.refresh(org)

        return org, sub

    @staticmethod
    async def get_monthly_task_usage(tenant_id: str, db: AsyncSession) -> Tuple[int, Optional[int]]:
        """Returns (usage_count, limit_count) for the tenant in the current calendar month."""
        if getattr(settings, "FREE_BETA_MODE", False):
            meter = await BillingService.get_or_create_task_usage_meter(tenant_id, db)
            return meter.usage_count, None  # Unlimited during Free Beta

        org, _ = await BillingService.sync_trial_expiration(tenant_id, db)
        tier = org.billing_tier if org else "starter"

        meter = await BillingService.get_or_create_task_usage_meter(tenant_id, db)

        if tier in ("pro", "team", "enterprise"):
            return meter.usage_count, None  # Unlimited
        return meter.usage_count, settings.FREE_TIER_MONTHLY_TASK_LIMIT

    @staticmethod
    async def record_task_created(tenant_id: str, db: AsyncSession) -> int:
        """Increments task creation counter for the tenant and returns new count."""
        meter = await BillingService.get_or_create_task_usage_meter(tenant_id, db)
        meter.usage_count += 1
        meter.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        await db.refresh(meter)
        return meter.usage_count

    @staticmethod
    async def get_subscription_summary(
        tenant_id: str,
        db: AsyncSession,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """Provides a complete snapshot of subscription, current tier, and month-to-date usage."""
        org, sub = await BillingService.sync_trial_expiration(tenant_id, db)
        effective_tier = org.billing_tier if org else ("pro" if getattr(settings, "FREE_BETA_MODE", False) else "starter")

        usage_count, limit_count = await BillingService.get_monthly_task_usage(tenant_id, db)

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        is_trial_sub = bool(sub and (sub.stripe_subscription_id or "").startswith("trial_"))
        trial_active = bool(is_trial_sub and sub.status == "trialing" and effective_tier in ("pro", "team", "enterprise"))
        trial_expired = bool(is_trial_sub and sub.status == "canceled" and effective_tier == "starter")
        trial_days_remaining = 0
        if trial_active and sub and sub.current_period_end:
            end_utc = (
                sub.current_period_end.replace(tzinfo=None)
                if sub.current_period_end.tzinfo
                else sub.current_period_end
            )
            remaining_sec = max(0.0, (end_utc - now_utc).total_seconds())
            trial_days_remaining = math.ceil(remaining_sec / 86400.0) if remaining_sec > 0 else 0

        pending_upi_stmt = select(func.count(UpiPaymentRequest.id)).where(
            UpiPaymentRequest.tenant_id == tenant_id,
            UpiPaymentRequest.status == "pending"
        )
        pending_upi_count = (await db.execute(pending_upi_stmt)).scalar() or 0

        pending_admin_upi_count = 0
        if is_admin:
            pending_admin_stmt = select(func.count(UpiPaymentRequest.id)).where(
                UpiPaymentRequest.status == "pending"
            )
            pending_admin_upi_count = (await db.execute(pending_admin_stmt)).scalar() or 0

        if getattr(settings, "FREE_BETA_MODE", False):
            plan_display = "Early Adopter Founder Plan"
        elif trial_active:
            plan_display = f"Pro Developer ({settings.FREE_TRIAL_DAYS}-Day Free Trial)"
        else:
            plan_display = f"{effective_tier.capitalize()} Plan"

        return {
            "tier": effective_tier,
            "status": sub.status if sub else "active",
            "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
            "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
            "tasks_created_this_month": usage_count,
            "monthly_task_limit": limit_count,
            "is_simulation": is_simulation_mode(),
            "free_beta_mode": getattr(settings, "FREE_BETA_MODE", False),
            "plan_display_name": plan_display,
            "is_admin": is_admin,
            "pending_upi_count": int(pending_upi_count),
            "pending_admin_upi_count": int(pending_admin_upi_count),
            "trial_active": trial_active,
            "trial_expired": trial_expired,
            "trial_days_remaining": trial_days_remaining,
            "trial_total_days": settings.FREE_TRIAL_DAYS,
            "trial_ends_at": sub.current_period_end.isoformat() if (is_trial_sub and sub and sub.current_period_end) else None,
        }

    # ==========================================
    # Direct UPI Payments & Verification Queue
    # ==========================================

    @staticmethod
    def get_upi_config() -> Dict[str, Any]:
        """Returns public Direct UPI payment metadata for QR & intent links."""
        plan_pricing = {
            p["id"]: {
                "monthly": p["price_monthly"],
                "annual": p["price_annual"],
                "name": p["name"],
            }
            for p in PLANS_CATALOG
            if p["id"] in ("pro", "team")
        }
        return {
            "upi_vpa": settings.UPI_VPA,
            "payee_name": settings.UPI_PAYEE_NAME,
            "qr_image_url": settings.UPI_QR_IMAGE_PATH,
            "currency": "INR",
            "currency_symbol": "₹",
            "suggested_support_amounts": [49, 100, 250, 500],
            "autopay_available": False,
            "autopay_note": (
                "Direct personal UPI supports instant 0%-fee one-time transfers. "
                "Automated monthly UPI AutoPay mandates require a merchant payment gateway (planned for later)."
            ),
            "plan_pricing": plan_pricing,
        }

    @staticmethod
    def serialize_upi_request(req: UpiPaymentRequest) -> Dict[str, Any]:
        return {
            "id": req.id,
            "tenant_id": req.tenant_id,
            "user_id": req.user_id,
            "payer_username": req.payer_username,
            "payer_email": req.payer_email,
            "payment_purpose": req.payment_purpose,
            "plan_tier": req.plan_tier,
            "billing_cycle": req.billing_cycle,
            "amount_inr": req.amount_inr,
            "upi_vpa": req.upi_vpa,
            "utr_number": req.utr_number,
            "payer_upi_id": req.payer_upi_id,
            "note": req.note,
            "status": req.status,
            "admin_note": req.admin_note,
            "reviewed_by_user_id": req.reviewed_by_user_id,
            "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "updated_at": req.updated_at.isoformat() if req.updated_at else None,
        }

    @staticmethod
    async def submit_upi_payment_request(
        tenant_id: str,
        user: User,
        payment_purpose: str,
        utr_number: str,
        plan_tier: Optional[str] = None,
        billing_cycle: Optional[str] = None,
        amount_inr: Optional[int] = None,
        payer_upi_id: Optional[str] = None,
        note: Optional[str] = None,
        db: AsyncSession = None,
    ) -> Dict[str, Any]:
        """Validates and logs a user's Direct UPI payment submission for manual verification."""
        purpose = (payment_purpose or "").strip().lower()
        if purpose not in ("plan", "support"):
            raise ValueError("Invalid payment purpose. Expected 'plan' or 'support'.")

        normalized_utr = re.sub(r"\s+", "", (utr_number or "")).upper()
        if not UPI_UTR_PATTERN.match(normalized_utr):
            raise ValueError(
                "Please enter a valid 12-digit UTR or UPI Transaction Reference ID (10-35 alphanumeric characters)."
            )

        resolved_tier: Optional[str] = None
        resolved_cycle: str = "one_time"
        resolved_amount: int

        if purpose == "plan":
            resolved_tier = (plan_tier or "").strip().lower()
            if resolved_tier not in ("pro", "team"):
                raise ValueError("Invalid plan tier. Choose 'pro' or 'team'.")
            resolved_cycle = (billing_cycle or "monthly").strip().lower()
            if resolved_cycle not in ("monthly", "annual"):
                raise ValueError("Invalid billing cycle. Choose 'monthly' or 'annual'.")
            plan_obj = next((p for p in PLANS_CATALOG if p["id"] == resolved_tier), None)
            if not plan_obj:
                raise ValueError("Requested plan not found.")
            resolved_amount = int(
                plan_obj["price_annual"] if resolved_cycle == "annual" else plan_obj["price_monthly"]
            )
        else:
            if amount_inr is None or int(amount_inr) < 1 or int(amount_inr) > 50000:
                raise ValueError("Support amount must be between ₹1 and ₹50,000.")
            resolved_amount = int(amount_inr)

        dup_stmt = select(UpiPaymentRequest).where(
            UpiPaymentRequest.utr_number == normalized_utr,
            UpiPaymentRequest.status.in_(["pending", "approved"])
        )
        dup_existing = (await db.execute(dup_stmt)).scalar_one_or_none()
        if dup_existing:
            raise FileExistsError(
                f"UTR/Reference ID '{normalized_utr}' has already been submitted ({dup_existing.status})."
            )

        req = UpiPaymentRequest(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user.id,
            payer_username=user.github_username or user.name or "contributor",
            payer_email=user.email,
            payment_purpose=purpose,
            plan_tier=resolved_tier,
            billing_cycle=resolved_cycle,
            amount_inr=resolved_amount,
            upi_vpa=settings.UPI_VPA,
            utr_number=normalized_utr,
            payer_upi_id=(payer_upi_id or "").strip()[:255] or None,
            note=(note or "").strip()[:512] or None,
            status="pending",
        )
        db.add(req)

        audit = AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user.id,
            action="UPI_PAYMENT_SUBMITTED",
            actor=user.github_username or "USER",
            details={
                "request_id": req.id,
                "purpose": purpose,
                "plan_tier": resolved_tier,
                "billing_cycle": resolved_cycle,
                "amount_inr": resolved_amount,
                "utr_number": normalized_utr,
                "upi_vpa": settings.UPI_VPA,
            },
        )
        db.add(audit)
        await db.commit()
        await db.refresh(req)
        return BillingService.serialize_upi_request(req)

    @staticmethod
    async def list_tenant_upi_requests(tenant_id: str, db: AsyncSession) -> List[Dict[str, Any]]:
        stmt = (
            select(UpiPaymentRequest)
            .where(UpiPaymentRequest.tenant_id == tenant_id)
            .order_by(desc(UpiPaymentRequest.created_at))
            .limit(50)
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [BillingService.serialize_upi_request(r) for r in rows]

    @staticmethod
    async def list_admin_upi_requests(
        db: AsyncSession,
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        stmt = select(UpiPaymentRequest)
        if status_filter and status_filter.lower() in ("pending", "approved", "rejected"):
            stmt = stmt.where(UpiPaymentRequest.status == status_filter.lower())
        stmt = stmt.order_by(desc(UpiPaymentRequest.created_at)).limit(100)
        rows = (await db.execute(stmt)).scalars().all()
        return [BillingService.serialize_upi_request(r) for r in rows]

    @staticmethod
    async def review_upi_payment_request(
        request_id: str,
        action: str,
        reviewer_user: User,
        admin_note: Optional[str],
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Approves or rejects a submitted UPI payment request and unlocks plan tier if approved."""
        normalized_action = (action or "").strip().lower()
        if normalized_action not in ("approve", "reject"):
            raise ValueError("Action must be 'approve' or 'reject'.")

        stmt = select(UpiPaymentRequest).where(UpiPaymentRequest.id == request_id)
        req = (await db.execute(stmt)).scalar_one_or_none()
        if not req:
            raise LookupError("UPI payment request not found.")
        if req.status != "pending":
            raise ValueError(f"Payment request has already been {req.status}.")

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        req.status = "approved" if normalized_action == "approve" else "rejected"
        req.admin_note = (admin_note or "").strip()[:512] or None
        req.reviewed_by_user_id = reviewer_user.id
        req.reviewed_at = now_utc
        req.updated_at = now_utc

        if normalized_action == "approve" and req.payment_purpose == "plan" and req.plan_tier in ("pro", "team"):
            duration_days = 365 if req.billing_cycle == "annual" else 30
            await db.execute(
                update(Organization)
                .where(Organization.id == req.tenant_id)
                .values(billing_tier=req.plan_tier)
            )
            sub_stmt = select(Subscription).where(Subscription.tenant_id == req.tenant_id)
            sub = (await db.execute(sub_stmt)).scalar_one_or_none()
            if not sub:
                sub = Subscription(
                    id=str(uuid.uuid4()),
                    tenant_id=req.tenant_id,
                    user_id=req.user_id,
                    stripe_subscription_id=f"upi_sub_{req.id[:12]}",
                    stripe_customer_id=f"upi_cus_{req.tenant_id[:12]}",
                    plan_tier=req.plan_tier,
                    status="active",
                    current_period_start=now_utc,
                    current_period_end=now_utc + timedelta(days=duration_days),
                )
                db.add(sub)
            else:
                sub.stripe_subscription_id = f"upi_sub_{req.id[:12]}"
                sub.stripe_customer_id = f"upi_cus_{req.tenant_id[:12]}"
                sub.plan_tier = req.plan_tier
                sub.status = "active"
                sub.cancel_at_period_end = False
                sub.current_period_start = now_utc
                sub.current_period_end = now_utc + timedelta(days=duration_days)
                sub.updated_at = now_utc

        audit = AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=req.tenant_id,
            user_id=reviewer_user.id,
            action=f"UPI_PAYMENT_{req.status.upper()}",
            actor=reviewer_user.github_username or "ADMIN",
            details={
                "request_id": req.id,
                "utr_number": req.utr_number,
                "amount_inr": req.amount_inr,
                "purpose": req.payment_purpose,
                "plan_tier": req.plan_tier,
                "admin_note": req.admin_note,
            },
        )
        db.add(audit)
        await db.commit()
        await db.refresh(req)
        return BillingService.serialize_upi_request(req)
