import hashlib
import hmac
import json
import sys
import uuid
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
        assert pro["price_monthly"] == 29
        assert pro["price_annual"] == 290
        assert pro["quota_tasks"] is None  # Unlimited


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

