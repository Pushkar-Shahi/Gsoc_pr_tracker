import hashlib
import hmac
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport

project_root = Path(__file__).resolve().parent.parent
backend_path = project_root / "backend"
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import select

from app.main import app
from app.core.config import settings
from app.db.database import get_session_factory
from app.models.models import Organization, User, Subscription, UsageMeter, Repository, Issue
from app.services.billing_service import BillingService, is_simulation_mode, get_current_month_bounds
from tests.e2e.conftest import make_session_token


def _sign_stripe_payload(payload_bytes: bytes, secret: str = "whsec_mock_stripe_webhook_secret_2026") -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def get_test_token(user_id: str, username: str, org_id: str, tier: str = "starter") -> str:
    unique_user = f"{username}_{uuid.uuid4().hex[:6]}"
    claims = {
        "user_id": user_id,
        "username": unique_user,
        "tenant_id": org_id,
        "role": "owner",
        "tier": tier
    }
    return make_session_token(subject=user_id, claims=claims)


@pytest.mark.asyncio
async def test_billing_plans_catalog():
    """Verify that the plans catalog exposes all 3 pricing tiers with features and quotas."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/billing/plans")
        assert resp.status_code == 200
        plans = resp.json()
        assert len(plans) == 3
        
        plan_ids = [p["id"] for p in plans]
        assert "starter" in plan_ids
        assert "pro" in plan_ids
        assert "team" in plan_ids

        starter = next(p for p in plans if p["id"] == "starter")
        assert starter["price_monthly"] == 0
        assert starter["quota_tasks"] == 5

        pro = next(p for p in plans if p["id"] == "pro")
        assert pro["price_monthly"] == 100
        assert pro["price_annual"] == 1000
        assert pro["currency"] == "INR"
        assert pro["currency_symbol"] == "₹"
        assert pro["quota_tasks"] is None  # Unlimited

        team = next(p for p in plans if p["id"] == "team")
        assert team["price_monthly"] == 300
        assert team["price_annual"] == 3000
        assert team["currency"] == "INR"
        assert team["currency_symbol"] == "₹"


@pytest.mark.asyncio
async def test_billing_subscription_endpoint():
    """Verify subscription endpoint reflects the tenant's tier and quota usage."""
    org_id = f"org_test_billing_{uuid.uuid4().hex[:8]}"
    user_id = f"usr_test_billing_{uuid.uuid4().hex[:8]}"
    token = get_test_token(user_id=user_id, username="billing_user", org_id=org_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/billing/subscription",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "starter"
        assert data["status"] == "active"
        assert data["monthly_task_limit"] == 5
        assert data["tasks_created_this_month"] >= 0


@pytest.mark.asyncio
async def test_checkout_session_creation():
    """Verify checkout session returns checkout_url and handles errors."""
    org_id = f"org_checkout_{uuid.uuid4().hex[:8]}"
    user_id = f"usr_checkout_{uuid.uuid4().hex[:8]}"
    token = get_test_token(user_id=user_id, username="checkout_user", org_id=org_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Valid pro checkout
        resp = await client.post(
            "/api/v1/billing/checkout-session",
            headers={"Authorization": f"Bearer {token}"},
            json={"plan_tier": "pro", "billing_cycle": "monthly"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "checkout_url" in body
        assert "session_id" in body
        assert body["plan_tier"] == "pro"

        # Invalid free tier checkout
        bad_resp = await client.post(
            "/api/v1/billing/checkout-session",
            headers={"Authorization": f"Bearer {token}"},
            json={"plan_tier": "starter"}
        )
        assert bad_resp.status_code == 400


@pytest.mark.asyncio
async def test_portal_session_creation():
    """Verify portal session generation."""
    org_id = f"org_portal_{uuid.uuid4().hex[:8]}"
    user_id = f"usr_portal_{uuid.uuid4().hex[:8]}"
    token = get_test_token(user_id=user_id, username="portal_user", org_id=org_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/billing/portal-session",
            headers={"Authorization": f"Bearer {token}"},
            json={"return_url": "http://localhost:5173/billing"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "portal_url" in body


@pytest.mark.asyncio
async def test_simulate_tier_transition():
    """Verify dev simulate-tier endpoint toggles organization tier and subscription."""
    org_id = f"org_sim_{uuid.uuid4().hex[:8]}"
    user_id = f"usr_sim_{uuid.uuid4().hex[:8]}"
    token = get_test_token(user_id=user_id, username="sim_user", org_id=org_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Upgrade to pro
        up_resp = await client.post(
            "/api/v1/billing/simulate-tier",
            headers={"Authorization": f"Bearer {token}"},
            json={"tier": "pro"}
        )
        assert up_resp.status_code == 200
        data = up_resp.json()
        assert data["tier"] == "pro"
        assert data["monthly_task_limit"] is None

        # Downgrade back to starter
        down_resp = await client.post(
            "/api/v1/billing/simulate-tier",
            headers={"Authorization": f"Bearer {token}"},
            json={"tier": "starter"}
        )
        assert down_resp.status_code == 200
        data = down_resp.json()
        assert data["tier"] == "starter"
        assert data["monthly_task_limit"] == 5


@pytest.mark.asyncio
async def test_stripe_webhook_signature_and_checkout_completed():
    """Verify webhook HMAC signature verification and checkout.session.completed processing."""
    session_factory = await get_session_factory()
    org_id = f"org_webhook_{uuid.uuid4().hex[:8]}"
    user_id = f"usr_webhook_{uuid.uuid4().hex[:8]}"

    # Provision organization and user
    async with session_factory() as session:
        user = User(
            id=user_id,
            github_username=f"webhook_user_{uuid.uuid4().hex[:6]}",
            name="Webhook User",
            email="wh@example.com"
        )
        session.add(user)
        org = Organization(id=org_id, name="Webhook Org", slug=org_id, billing_tier="starter")
        session.add(org)
        await session.commit()

    event = {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": f"cus_{uuid.uuid4().hex[:12]}",
                "subscription": f"sub_{uuid.uuid4().hex[:12]}",
                "metadata": {
                    "tenant_id": org_id,
                    "user_id": user_id,
                    "plan_tier": "pro"
                }
            }
        }
    }
    payload_bytes = json.dumps(event).encode("utf-8")
    sig = _sign_stripe_payload(payload_bytes, settings.STRIPE_WEBHOOK_SECRET)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Missing signature
        bad_req = await client.post("/api/v1/billing/webhook", content=payload_bytes)
        assert bad_req.status_code == 400

        # 2. Bad signature
        bad_sig_req = await client.post(
            "/api/v1/billing/webhook",
            content=payload_bytes,
            headers={"stripe-signature": "invalid_sig_hex"}
        )
        assert bad_sig_req.status_code == 400

        # 3. Valid signature
        good_req = await client.post(
            "/api/v1/billing/webhook",
            content=payload_bytes,
            headers={"stripe-signature": sig}
        )
        assert good_req.status_code == 200
        res = good_req.json()
        assert res["status"] == "success"

    # Verify organization upgraded to pro in DB
    async with session_factory() as session:
        updated_org = (await session.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
        assert updated_org.billing_tier == "pro"


@pytest.mark.asyncio
async def test_stripe_webhook_subscription_deleted_downgrades_tier():
    """Verify customer.subscription.deleted downgrades organization back to starter."""
    session_factory = await get_session_factory()
    org_id = f"org_sub_del_{uuid.uuid4().hex[:8]}"
    sub_id = f"sub_del_{uuid.uuid4().hex[:8]}"

    async with session_factory() as session:
        org = Organization(id=org_id, name="Sub Del Org", slug=org_id, billing_tier="pro")
        sub = Subscription(
            id=str(uuid.uuid4()),
            tenant_id=org_id,
            stripe_subscription_id=sub_id,
            stripe_customer_id="cus_test_123",
            plan_tier="pro",
            status="active"
        )
        session.add(org)
        session.add(sub)
        await session.commit()

    event = {
        "id": f"evt_{uuid.uuid4().hex[:12]}",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": sub_id,
                "status": "canceled"
            }
        }
    }
    payload_bytes = json.dumps(event).encode("utf-8")
    sig = _sign_stripe_payload(payload_bytes, settings.STRIPE_WEBHOOK_SECRET)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/billing/webhook",
            content=payload_bytes,
            headers={"stripe-signature": sig}
        )
        assert resp.status_code == 200

    # Verify downgraded to starter in DB
    async with session_factory() as session:
        org_check = (await session.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
        assert org_check.billing_tier == "starter"


@pytest.mark.asyncio
async def test_starter_monthly_task_quota_enforced():
    """Verify that a tenant on starter tier is blocked with HTTP 402 once they reach 5 tasks."""
    session_factory = await get_session_factory()
    org_id = f"org_quota_{uuid.uuid4().hex[:8]}"
    user_id = f"usr_quota_{uuid.uuid4().hex[:8]}"
    token = get_test_token(user_id=user_id, username="quota_user", org_id=org_id)

    # 1. Provision repository and issue
    async with session_factory() as session:
        user = User(
            id=user_id,
            github_username=f"quota_user_{uuid.uuid4().hex[:6]}",
            name="Quota User",
            email="quota@example.com"
        )
        session.add(user)
        org = Organization(id=org_id, name="Quota Org", slug=org_id, billing_tier="starter")
        session.add(org)
        
        repo = Repository(
            id=f"repo_{uuid.uuid4().hex[:8]}",
            tenant_id=org_id,
            user_id=user_id,
            owner="mock-owner",
            name="mock-repo",
            full_name=f"mock-owner/mock-repo-{uuid.uuid4().hex[:6]}",
            html_url="https://github.com/mock-owner/mock-repo"
        )
        session.add(repo)
        await session.flush()

        issue = Issue(
            id=f"iss_{uuid.uuid4().hex[:8]}",
            tenant_id=org_id,
            user_id=user_id,
            repository_id=repo.id,
            github_id=int(uuid.uuid4().int % 100000000),
            issue_number=101,
            title="Fix quota bug",
            html_url="https://github.com/mock-owner/mock-repo/issues/101",
            state="open"
        )
        session.add(issue)

        # Pre-seed usage meter with 5 tasks
        start_month, end_month = get_current_month_bounds()
        meter = UsageMeter(
            id=str(uuid.uuid4()),
            tenant_id=org_id,
            metric_name="tasks_created",
            period_start=start_month,
            period_end=end_month,
            usage_count=5,
            limit_count=5
        )
        session.add(meter)
        await session.commit()
        issue_id = issue.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attempt to select issue with quota exhausted
        resp = await client.post(
            "/api/v1/tasks/select",
            headers={"Authorization": f"Bearer {token}"},
            json={"issue_id": issue_id}
        )
        assert resp.status_code == 402
        err = resp.json()["detail"]
        assert err["code"] == "QUOTA_EXCEEDED"
        assert err["current_usage"] == 5
        assert err["monthly_limit"] == 5

        # Upgrade to pro
        await client.post(
            "/api/v1/billing/simulate-tier",
            headers={"Authorization": f"Bearer {token}"},
            json={"tier": "pro"}
        )

        # Retry selecting issue with Pro tier -> Should bypass quota check!
        pro_resp = await client.post(
            "/api/v1/tasks/select",
            headers={"Authorization": f"Bearer {token}"},
            json={"issue_id": issue_id}
        )
        # Should NOT return 402 Payment Required!
        assert pro_resp.status_code != 402


@pytest.mark.asyncio
async def test_require_tier_dependency():
    """Verify require_tier blocks lower tier tenants with HTTP 403 TIER_UPGRADE_REQUIRED."""
    from fastapi import HTTPException
    from app.core.entitlements import require_tier
    from app.core.tenant import TenantContext

    checker = require_tier("team")

    class DummyUser:
        is_superuser = False

    class DummyOrg:
        def __init__(self, tier: str):
            self.billing_tier = tier

    # 1. Starter tenant should be rejected with 403
    starter_ctx = TenantContext(user=DummyUser(), organization=DummyOrg("starter"), membership=None, role="member")
    with pytest.raises(HTTPException) as exc_info:
        await checker(starter_ctx)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "TIER_UPGRADE_REQUIRED"

    # 2. Pro tenant should also be rejected for team-required feature
    pro_ctx = TenantContext(user=DummyUser(), organization=DummyOrg("pro"), membership=None, role="member")
    with pytest.raises(HTTPException) as exc_info2:
        await checker(pro_ctx)
    assert exc_info2.value.status_code == 403
    assert exc_info2.value.detail["code"] == "TIER_UPGRADE_REQUIRED"

    # 3. Team tenant should succeed
    team_ctx = TenantContext(user=DummyUser(), organization=DummyOrg("team"), membership=None, role="member")
    res = await checker(team_ctx)
    assert res == team_ctx

    # 4. Superuser should bypass tier checks
    class SuperUser:
        is_superuser = True
    su_ctx = TenantContext(user=SuperUser(), organization=DummyOrg("starter"), membership=None, role="member")
    res_su = await checker(su_ctx)
    assert res_su == su_ctx


@pytest.mark.asyncio
async def test_upi_config_endpoint():
    """Verify public Direct UPI config exposes merchant VPA, QR asset path, and AutoPay disclosure."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/billing/upi/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["upi_vpa"] == "8116710520@sbi"
        assert data["payee_name"] == "Pushkar Shahi"
        assert data["qr_image_url"] == "/phonepe-upi-qr.jpg"
        assert data["currency"] == "INR"
        assert data["autopay_available"] is False
        assert data["plan_pricing"]["pro"]["monthly"] == 100
        assert data["plan_pricing"]["team"]["monthly"] == 300


@pytest.mark.asyncio
async def test_upi_submit_validation_tenant_isolation_and_duplicates():
    """Verify Direct UPI UTR submission validation, server-side plan pricing, duplicate guard, and isolation."""
    org_a = f"org_upi_a_{uuid.uuid4().hex[:8]}"
    user_a = f"usr_upi_a_{uuid.uuid4().hex[:8]}"
    token_a = get_test_token(user_id=user_a, username="upi_payer_a", org_id=org_a)

    org_b = f"org_upi_b_{uuid.uuid4().hex[:8]}"
    user_b = f"usr_upi_b_{uuid.uuid4().hex[:8]}"
    token_b = get_test_token(user_id=user_b, username="upi_payer_b", org_id=org_b)

    utr_plan = f"4312{uuid.uuid4().int % 100000000:08d}"
    utr_support = f"5312{uuid.uuid4().int % 100000000:08d}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid UTR rejected
        bad_utr = await client.post(
            "/api/v1/billing/upi/submit",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "payment_purpose": "support",
                "amount_inr": 100,
                "utr_number": "123",
            },
        )
        assert bad_utr.status_code == 400

        # 2. Plan submission enforces authoritative server price even if tampered
        plan_resp = await client.post(
            "/api/v1/billing/upi/submit",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "payment_purpose": "plan",
                "plan_tier": "pro",
                "billing_cycle": "monthly",
                "amount_inr": 1,
                "utr_number": utr_plan,
                "payer_upi_id": "payer@okaxis",
            },
        )
        assert plan_resp.status_code == 200
        plan_data = plan_resp.json()
        assert plan_data["amount_inr"] == 100
        assert plan_data["status"] == "pending"
        assert plan_data["utr_number"] == utr_plan

        # 3. Duplicate UTR rejected with 409 Conflict
        dup_resp = await client.post(
            "/api/v1/billing/upi/submit",
            headers={"Authorization": f"Bearer {token_b}"},
            json={
                "payment_purpose": "support",
                "amount_inr": 100,
                "utr_number": utr_plan,
            },
        )
        assert dup_resp.status_code == 409

        # 4. Support submission for tenant B
        sup_resp = await client.post(
            "/api/v1/billing/upi/submit",
            headers={"Authorization": f"Bearer {token_b}"},
            json={
                "payment_purpose": "support",
                "amount_inr": 250,
                "utr_number": utr_support,
                "note": "Thanks for GSoC tracker!",
            },
        )
        assert sup_resp.status_code == 200
        assert sup_resp.json()["amount_inr"] == 250

        # 5. Tenant isolation check on /my-requests
        list_a = (
            await client.get(
                "/api/v1/billing/upi/my-requests",
                headers={"Authorization": f"Bearer {token_a}"},
            )
        ).json()
        assert all(item["tenant_id"] == org_a for item in list_a)
        assert any(item["utr_number"] == utr_plan for item in list_a)
        assert not any(item["utr_number"] == utr_support for item in list_a)


@pytest.mark.asyncio
async def test_upi_admin_review_enforces_superuser_and_activates_tier():
    """Verify non-admins get 403 and superuser approval upgrades tenant organization tier."""
    session_factory = await get_session_factory()
    org_id = f"org_upi_rev_{uuid.uuid4().hex[:8]}"
    user_id = f"usr_upi_rev_{uuid.uuid4().hex[:8]}"
    admin_id = f"usr_admin_rev_{uuid.uuid4().hex[:8]}"
    admin_org = f"org_admin_rev_{uuid.uuid4().hex[:8]}"

    user_token = get_test_token(user_id=user_id, username="regular_user", org_id=org_id)
    admin_token = get_test_token(user_id=admin_id, username="admin_reviewer", org_id=admin_org)

    # Ensure admin user exists with is_superuser=True in DB
    async with session_factory() as session:
        session.add(
            User(
                id=admin_id,
                github_username=f"admin_rev_{uuid.uuid4().hex[:6]}",
                name="Admin Reviewer",
                email="adminrev@example.com",
                is_superuser=True,
            )
        )
        session.add(Organization(id=admin_org, name="Admin Org", slug=admin_org, billing_tier="pro"))
        await session.commit()

    utr_upgrade = f"6312{uuid.uuid4().int % 100000000:08d}"
    utr_reject = f"7312{uuid.uuid4().int % 100000000:08d}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User submits Team Annual UPI request (₹3000)
        sub_resp = await client.post(
            "/api/v1/billing/upi/submit",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "payment_purpose": "plan",
                "plan_tier": "team",
                "billing_cycle": "annual",
                "utr_number": utr_upgrade,
            },
        )
        assert sub_resp.status_code == 200
        req_id = sub_resp.json()["id"]
        assert sub_resp.json()["amount_inr"] == 3000

        # Also submit a support request to test rejection
        rej_sub = await client.post(
            "/api/v1/billing/upi/submit",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "payment_purpose": "support",
                "amount_inr": 49,
                "utr_number": utr_reject,
            },
        )
        assert rej_sub.status_code == 200
        rej_id = rej_sub.json()["id"]

        # Regular non-superuser must get 403 Forbidden on admin endpoints
        forbidden_list = await client.get(
            "/api/v1/billing/upi/admin/requests",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert forbidden_list.status_code == 403

        forbidden_review = await client.post(
            f"/api/v1/billing/upi/admin/requests/{req_id}/review",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"action": "approve"},
        )
        assert forbidden_review.status_code == 403

        # Superuser fetches admin queue and checks is_admin flag in subscription
        sub_summary = (
            await client.get(
                "/api/v1/billing/subscription",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        ).json()
        assert sub_summary["is_admin"] is True

        admin_list = await client.get(
            "/api/v1/billing/upi/admin/requests?status_filter=pending",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_list.status_code == 200
        assert any(r["id"] == req_id for r in admin_list.json())

        # Superuser approves -> Organization upgraded to 'team'
        approve_resp = await client.post(
            f"/api/v1/billing/upi/admin/requests/{req_id}/review",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"action": "approve", "admin_note": "Verified on PhonePe"},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"

        # Superuser rejects second request
        reject_resp = await client.post(
            f"/api/v1/billing/upi/admin/requests/{rej_id}/review",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"action": "reject", "admin_note": "UTR not found in statement"},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"

    # Verify DB shows Organization upgraded to team and active subscription
    async with session_factory() as session:
        org_obj = (await session.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
        assert org_obj.billing_tier == "team"
        sub_obj = (await session.execute(select(Subscription).where(Subscription.tenant_id == org_id))).scalar_one()
        assert sub_obj.plan_tier == "team"
        assert sub_obj.status == "active"


@pytest.mark.asyncio
async def test_reverse_free_trial_15_days_onboarding_and_expiration():
    """
    Verify new non-owner onboarding automatically grants a 15-day Pro Reverse Free Trial
    with unlimited quotas & Pro endpoints, then automatically downgrades to Starter
    with 5 tasks/mo limit after expiration without resetting on subsequent logins.
    """
    unique_email = f"trial_user_{uuid.uuid4().hex[:8]}@example.com"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fresh signup provisions 15-day Pro trial
        login_resp = await client.post(
            "/api/v1/auth/google/dev-login",
            json={"email": unique_email, "name": "Trial Contributor"},
        )
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        assert login_data["tier"] == "pro"
        token = login_data["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Verify subscription summary reports 15-day active trial
        sub_resp = await client.get("/api/v1/billing/subscription", headers=headers)
        assert sub_resp.status_code == 200
        sub_data = sub_resp.json()
        assert sub_data["tier"] == "pro"
        assert sub_data["status"] == "trialing"
        assert sub_data["trial_active"] is True
        assert sub_data["trial_expired"] is False
        assert sub_data["trial_total_days"] == 15
        assert sub_data["trial_days_remaining"] == 15
        assert sub_data["monthly_task_limit"] is None

        # 3. Pro-gated feature succeeds during active trial
        pro_check = await client.get("/api/v1/webhooks/subscriptions", headers=headers)
        assert pro_check.status_code == 200

        # 4. Expire trial in DB (simulate Day 16)
        session_factory = await get_session_factory()
        async with session_factory() as session:
            user_obj = (
                await session.execute(select(User).where(User.email == unique_email))
            ).scalar_one()
            sub_obj = (
                await session.execute(select(Subscription).where(Subscription.user_id == user_obj.id))
            ).scalar_one()
            sub_obj.current_period_end = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
            await session.commit()

        # 5. Pro endpoint immediately downgrades & returns 403 once trial expires
        expired_pro_check = await client.get("/api/v1/webhooks/subscriptions", headers=headers)
        assert expired_pro_check.status_code == 403

        # 6. Subscription summary now reflects Starter 5-task limit & expired trial banner state
        expired_sub = (await client.get("/api/v1/billing/subscription", headers=headers)).json()
        assert expired_sub["tier"] == "starter"
        assert expired_sub["status"] == "canceled"
        assert expired_sub["trial_active"] is False
        assert expired_sub["trial_expired"] is True
        assert expired_sub["trial_days_remaining"] == 0
        assert expired_sub["monthly_task_limit"] == 5

        # 7. Signing in again must NOT grant a second free trial
        relogin_resp = await client.post(
            "/api/v1/auth/google/dev-login",
            json={"email": unique_email, "name": "Trial Contributor"},
        )
        assert relogin_resp.status_code == 200
        assert relogin_resp.json()["tier"] == "starter"

