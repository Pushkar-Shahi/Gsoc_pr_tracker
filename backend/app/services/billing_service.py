import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple, List

import stripe
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Organization, User, BillingCustomer, Subscription, UsageMeter

logger = logging.getLogger(__name__)

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
            {"name": "High-value bounty tracker (Algora/Polar)", "included": False},
            {"name": "Private repositories & orgs", "included": False},
        ],
    },
    {
        "id": "pro",
        "name": "Pro Developer",
        "description": "Unconstrained task automation, priority discovery, and bounty tracking for high-velocity builders.",
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
            {"name": "High-value bounty tracker (Algora/Polar)", "included": True, "highlight": True},
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
    async def get_monthly_task_usage(tenant_id: str, db: AsyncSession) -> Tuple[int, Optional[int]]:
        """Returns (usage_count, limit_count) for the tenant in the current calendar month."""
        if getattr(settings, "FREE_BETA_MODE", False):
            meter = await BillingService.get_or_create_task_usage_meter(tenant_id, db)
            return meter.usage_count, None  # Unlimited during Free Beta

        # Check org tier
        org_stmt = select(Organization).where(Organization.id == tenant_id)
        org_res = await db.execute(org_stmt)
        org = org_res.scalar_one_or_none()
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
    async def get_subscription_summary(tenant_id: str, db: AsyncSession) -> Dict[str, Any]:
        """Provides a complete snapshot of subscription, current tier, and month-to-date usage."""
        org_stmt = select(Organization).where(Organization.id == tenant_id)
        org_res = await db.execute(org_stmt)
        org = org_res.scalar_one_or_none()
        effective_tier = org.billing_tier if org else ("pro" if getattr(settings, "FREE_BETA_MODE", False) else "starter")

        sub_stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
        sub_res = await db.execute(sub_stmt)
        sub = sub_res.scalar_one_or_none()

        usage_count, limit_count = await BillingService.get_monthly_task_usage(tenant_id, db)

        return {
            "tier": effective_tier,
            "status": sub.status if sub else "active",
            "cancel_at_period_end": sub.cancel_at_period_end if sub else False,
            "current_period_end": sub.current_period_end.isoformat() if sub and sub.current_period_end else None,
            "tasks_created_this_month": usage_count,
            "monthly_task_limit": limit_count,
            "is_simulation": is_simulation_mode(),
            "free_beta_mode": getattr(settings, "FREE_BETA_MODE", False),
            "plan_display_name": "Early Adopter Founder Plan" if getattr(settings, "FREE_BETA_MODE", False) else f"{effective_tier.capitalize()} Plan",
        }
