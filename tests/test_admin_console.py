import sys
import uuid
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

project_root = Path(__file__).resolve().parent.parent
backend_path = project_root / "backend"
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.main import app
from app.core.config import settings
from app.db.database import get_session_factory
from app.models.models import User, UsageMeter, Repository, Issue, Task
from tests.e2e.conftest import make_session_token


def _make_token(user_id: str, username: str, org_id: str, tier: str = "starter") -> str:
    return make_session_token(
        subject=user_id,
        claims={
            "user_id": user_id,
            "username": username,
            "tenant_id": org_id,
            "role": "owner",
            "tier": tier,
        },
    )


async def _promote_superuser(user_id: str) -> None:
    session_factory = await get_session_factory()
    async with session_factory() as db:
        res = await db.execute(select(User).where(User.id == user_id))
        u = res.scalar_one()
        u.is_superuser = True
        await db.commit()


@pytest.mark.asyncio
async def test_admin_endpoints_reject_non_superuser():
    user_id = f"usr-nonadmin-{uuid.uuid4().hex[:6]}"
    org_id = f"org-nonadmin-{uuid.uuid4().hex[:6]}"
    token = _make_token(user_id, f"regular_{uuid.uuid4().hex[:6]}", org_id)
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/admin/overview", headers=headers)
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_user_suspension_plan_override_credits_reset_and_task_control():
    admin_id = f"usr-admin-{uuid.uuid4().hex[:6]}"
    admin_org = f"org-admin-{uuid.uuid4().hex[:6]}"
    admin_token = _make_token(admin_id, f"boss_{uuid.uuid4().hex[:6]}", admin_org, tier="team")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    target_id = f"usr-target-{uuid.uuid4().hex[:6]}"
    target_username = f"contrib_{uuid.uuid4().hex[:6]}"
    target_org = f"org-target-{uuid.uuid4().hex[:6]}"
    target_token = _make_token(target_id, target_username, target_org, tier="starter")
    target_headers = {"Authorization": f"Bearer {target_token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Bootstrap both users via JIT tenant resolution
        assert (await client.get("/api/v1/billing/subscription", headers=admin_headers)).status_code == 200
        assert (await client.get("/api/v1/billing/subscription", headers=target_headers)).status_code == 200

        await _promote_superuser(admin_id)

        # Seed usage meter + task for target user
        session_factory = await get_session_factory()
        async with session_factory() as db:
            from app.services.billing_service import BillingService
            meter = await BillingService.get_or_create_task_usage_meter(target_org, db)
            meter.usage_count = 5
            repo = Repository(
                id=str(uuid.uuid4()),
                owner="psf",
                name=f"cpython-{uuid.uuid4().hex[:6]}",
                full_name=f"psf/cpython-{uuid.uuid4().hex[:6]}",
                html_url="https://github.com/psf/cpython",
            )
            db.add(repo)
            await db.flush()
            issue = Issue(
                id=str(uuid.uuid4()),
                repository_id=repo.id,
                github_id=int(uuid.uuid4().int % 1_000_000_000),
                issue_number=42,
                title="Fix async edge case",
                html_url="https://github.com/psf/cpython/issues/42",
                state="open",
                is_eligible=True,
            )
            db.add(issue)
            await db.flush()
            task = Task(
                id=str(uuid.uuid4()),
                tenant_id=target_org,
                user_id=target_id,
                issue_id=issue.id,
                workflow_state="BLOCKED",
                blocked_reason="Stuck runner",
            )
            db.add(task)
            await db.commit()
            task_id = task.id

        # 1. Overview & User listing
        ov = await client.get("/api/v1/admin/overview", headers=admin_headers)
        assert ov.status_code == 200
        assert ov.json()["users"]["total"] >= 2

        users_res = await client.get(f"/api/v1/admin/users?q={target_username}", headers=admin_headers)
        assert users_res.status_code == 200
        found = users_res.json()
        assert len(found) == 1
        assert found[0]["workspaces"][0]["tasks_used"] == 5

        # 2. Override target workspace to +15d Pro trial & reset credits
        override_res = await client.post(
            f"/api/v1/admin/organizations/{target_org}/plan",
            json={"tier": "pro", "trial_days": 15, "reset_credits": True},
            headers=admin_headers,
        )
        assert override_res.status_code == 200
        assert override_res.json()["tier"] == "pro"
        assert override_res.json()["trial_active"] is True

        # 3. Direct credit reset endpoint
        reset_res = await client.post(
            f"/api/v1/admin/organizations/{target_org}/credits/reset",
            headers=admin_headers,
        )
        assert reset_res.status_code == 200
        assert reset_res.json()["tasks_created"] == 0

        # 4. Self-suspension guard
        self_ban = await client.post(
            f"/api/v1/admin/users/{admin_id}/status",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert self_ban.status_code == 400

        # 5. Suspend target user -> target immediately gets 403
        ban_res = await client.post(
            f"/api/v1/admin/users/{target_id}/status",
            json={"is_active": False},
            headers=admin_headers,
        )
        assert ban_res.status_code == 200
        assert ban_res.json()["is_active"] is False

        blocked_call = await client.get("/api/v1/billing/subscription", headers=target_headers)
        assert blocked_call.status_code == 403

        # Reactivate target user -> restored
        unban_res = await client.post(
            f"/api/v1/admin/users/{target_id}/status",
            json={"is_active": True},
            headers=admin_headers,
        )
        assert unban_res.status_code == 200
        assert (await client.get("/api/v1/billing/subscription", headers=target_headers)).status_code == 200

        # 6. Force task state from BLOCKED -> SELECTED
        tasks_res = await client.get(f"/api/v1/admin/tasks?q={target_username}", headers=admin_headers)
        assert tasks_res.status_code == 200
        assert any(t["id"] == task_id for t in tasks_res.json())

        force_res = await client.post(
            f"/api/v1/admin/tasks/{task_id}/force-state",
            json={"workflow_state": "SELECTED"},
            headers=admin_headers,
        )
        assert force_res.status_code == 200
        assert force_res.json()["workflow_state"] == "SELECTED"

        # 7. Global audit logs include ADMIN actions
        aud_res = await client.get("/api/v1/admin/audit?action=ADMIN_", headers=admin_headers)
        assert aud_res.status_code == 200
        actions = {a["action"] for a in aud_res.json()}
        assert "ADMIN_PLAN_OVERRIDE" in actions
        assert "ADMIN_TASK_FORCE_STATE" in actions

        # 8. Runtime config update & restore
        orig_trial = settings.FREE_TRIAL_DAYS
        orig_limit = settings.FREE_TIER_MONTHLY_TASK_LIMIT
        orig_vpa = settings.UPI_VPA
        orig_beta = settings._free_beta_mode_override
        try:
            cfg_res = await client.post(
                "/api/v1/admin/runtime-config",
                json={"free_trial_days": 21, "free_tier_credit_limit": 7, "upi_vpa": "8116710520@sbi"},
                headers=admin_headers,
            )
            assert cfg_res.status_code == 200
            assert settings.FREE_TRIAL_DAYS == 21
            assert settings.FREE_TIER_MONTHLY_TASK_LIMIT == 7
        finally:
            settings.FREE_TRIAL_DAYS = orig_trial
            settings.FREE_TIER_MONTHLY_TASK_LIMIT = orig_limit
            settings.UPI_VPA = orig_vpa
            settings._free_beta_mode_override = orig_beta
            async with session_factory() as db:
                from app.models.models import PlatformSettings
                sett = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))).scalar_one_or_none()
                if sett and isinstance(sett.discovery_filters, dict) and "_admin_runtime" in sett.discovery_filters:
                    cleaned = dict(sett.discovery_filters)
                    cleaned.pop("_admin_runtime", None)
                    sett.discovery_filters = cleaned
                    await db.commit()

