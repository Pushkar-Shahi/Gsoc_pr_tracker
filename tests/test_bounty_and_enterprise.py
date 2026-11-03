import csv
import io
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

from app.main import app
from app.core.config import settings
from app.db.database import get_session_factory
from app.models.models import Organization, User, Membership, Repository, Issue, Task, AuditLog
from app.services.bounty_service import BountyService, DEFAULT_HIGH_VALUE_BOUNTIES
from app.services.enterprise_sso import EnterpriseSSOService
from tests.e2e.conftest import make_session_token


def get_test_token(user_id: str, username: str, org_id: str, role: str = "owner", tier: str = "pro") -> str:
    unique_user = f"{username}_{uuid.uuid4().hex[:6]}"
    claims = {
        "user_id": user_id,
        "username": unique_user,
        "tenant_id": org_id,
        "role": role,
        "tier": tier
    }
    return make_session_token(subject=user_id, claims=claims)


@pytest.mark.asyncio
async def test_bounty_service_fetch_and_filtering():
    """Verify BountyService fetches and accurately filters bounties by amount and platform."""
    # 1. Fetch all bounties
    all_bounties = await BountyService.fetch_live_bounties()
    assert len(all_bounties) >= len(DEFAULT_HIGH_VALUE_BOUNTIES)
    first = all_bounties[0]
    assert "amount" in first
    assert "currency" in first
    assert "platform" in first
    assert "bounty_url" in first

    # 2. Filter by minimum amount
    high_value = await BountyService.fetch_live_bounties(min_amount=500.0)
    assert all(b["amount"] >= 500.0 for b in high_value)

    # 3. Filter by platform
    polar_only = await BountyService.fetch_live_bounties(platform="polar")
    assert all(b["platform"].lower() == "polar" for b in polar_only)

    algora_only = await BountyService.fetch_live_bounties(platform="algora")
    assert all(b["platform"].lower() == "algora" for b in algora_only)


@pytest.mark.asyncio
async def test_bounty_service_sync_and_metrics():
    """Verify BountyService syncs bounties into database and computes aggregate metrics."""
    session_factory = await get_session_factory()
    org_id = f"org_{uuid.uuid4().hex[:12]}"
    user_id = f"usr_{uuid.uuid4().hex[:12]}"

    async with session_factory() as session:
        user = User(id=user_id, github_username=f"hunter_{uuid.uuid4().hex[:6]}", name="Bounty Hunter")
        org = Organization(id=org_id, name="Bounty Squad Org", slug=org_id, billing_tier="pro")
        membership = Membership(user_id=user_id, org_id=org_id, role="owner")
        session.add_all([user, org, membership])
        await session.commit()

    async with session_factory() as session:
        # Sync initial catalog
        synced = await BountyService.sync_bounties_to_database(session, tenant_id=org_id, user_id=user_id)
        assert len(synced) >= 5

        # Check metrics
        metrics = await BountyService.get_bounty_metrics(session, tenant_id=org_id)
        assert metrics["total_available_usd"] > 1000.0
        assert metrics["total_bounties_count"] >= 5
        assert metrics["average_bounty_usd"] > 0
        assert metrics["claimed_bounties_count"] == 0


@pytest.mark.asyncio
async def test_bounty_claim_and_brief_generation(tmp_path):
    """Verify claiming a bounty creates task, marks issue as CLAIMED, and injects bounty brief."""
    session_factory = await get_session_factory()
    org_id = f"org_{uuid.uuid4().hex[:12]}"
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    repo_id = f"rep_{uuid.uuid4().hex[:12]}"
    issue_id = f"iss_{uuid.uuid4().hex[:12]}"

    async with session_factory() as session:
        user = User(id=user_id, github_username=f"claimer_{uuid.uuid4().hex[:6]}", name="Claimer")
        org = Organization(id=org_id, name="Claim Org", slug=org_id, billing_tier="pro")
        membership = Membership(user_id=user_id, org_id=org_id, role="owner")
        unique_suffix = uuid.uuid4().hex[:6]
        repo = Repository(
            id=repo_id,
            tenant_id=org_id,
            user_id=user_id,
            owner="Pushkar-Shahi",
            name=f"Gsoc_pr_tracker_{unique_suffix}",
            full_name=f"Pushkar-Shahi/Gsoc_pr_tracker_{unique_suffix}",
            html_url="https://github.com/Pushkar-Shahi/Gsoc_pr_tracker",
            default_branch="main"
        )
        issue = Issue(
            id=issue_id,
            tenant_id=org_id,
            user_id=user_id,
            repository_id=repo_id,
            github_id=int(uuid.uuid4().int % 1000000000),
            issue_number=42,
            title="Optimized Bounty Issue",
            html_url="https://github.com/Pushkar-Shahi/Gsoc_pr_tracker/issues/42",
            bounty_amount=500.0,
            bounty_currency="USD",
            bounty_platform="polar",
            bounty_url="https://polar.sh/test/issue/42",
            bounty_status="AVAILABLE"
        )
        session.add_all([user, org, membership, repo, issue])
        await session.commit()

    async with session_factory() as session:
        claim_res = await BountyService.claim_bounty_and_prepare_task(
            db=session,
            issue_id=issue_id,
            tenant_id=org_id,
            user_id=user_id,
            custom_notes="Urgent fix needed for polar payout"
        )

        assert claim_res["success"] is True
        assert claim_res["bounty_status"] == "CLAIMED"
        assert claim_res["bounty_amount"] == 500.0
        assert claim_res["worktree_path"] is not None

        # Verify BRIEF.md contains bounty rules
        worktree_p = Path(claim_res["worktree_path"])
        brief_p = worktree_p / ".antigravity" / "BRIEF.md"
        assert brief_p.exists()
        brief_text = brief_p.read_text(encoding="utf-8")
        assert "POLAR" in brief_text
        assert "500" in brief_text
        assert "Resolves #42" in brief_text


@pytest.mark.asyncio
async def test_bounties_api_endpoints():
    """Verify GET /api/v1/bounties and GET /api/v1/bounties/stats."""
    session_factory = await get_session_factory()
    org_id = f"org_{uuid.uuid4().hex[:12]}"
    user_id = f"usr_{uuid.uuid4().hex[:12]}"

    async with session_factory() as session:
        user = User(id=user_id, github_username=f"api_user_{uuid.uuid4().hex[:6]}", name="API User")
        org = Organization(id=org_id, name="API Org", slug=org_id, billing_tier="pro")
        membership = Membership(user_id=user_id, org_id=org_id, role="owner")
        session.add_all([user, org, membership])
        await session.commit()

    token = get_test_token(user_id=user_id, username="api_user", org_id=org_id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fetch bounties list
        resp = await client.get("/api/v1/bounties", headers=headers)
        assert resp.status_code == 200
        bounties = resp.json()
        assert len(bounties) > 0
        assert all("bounty_amount" in b for b in bounties)

        # 2. Filter by minimum amount
        resp_500 = await client.get("/api/v1/bounties?min_amount=500", headers=headers)
        assert resp_500.status_code == 200
        bounties_500 = resp_500.json()
        assert all(b["bounty_amount"] >= 500 for b in bounties_500)

        # 3. Filter by platform
        resp_polar = await client.get("/api/v1/bounties?platform=polar", headers=headers)
        assert resp_polar.status_code == 200
        polar_bounties = resp_polar.json()
        assert all(b["bounty_platform"] == "polar" for b in polar_bounties)

        # 4. Fetch stats
        stats_resp = await client.get("/api/v1/bounties/stats", headers=headers)
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["total_available_usd"] > 0
        assert stats["total_bounties_count"] > 0


@pytest.mark.asyncio
async def test_audit_logs_export_csv_and_json():
    """Verify GET /api/v1/audit-logs/export delivers RFC 4180 CSV and SIEM JSON."""
    session_factory = await get_session_factory()
    org_id = f"org_{uuid.uuid4().hex[:12]}"
    user_id = f"usr_{uuid.uuid4().hex[:12]}"

    async with session_factory() as session:
        user = User(id=user_id, github_username=f"auditor_{uuid.uuid4().hex[:6]}", name="Auditor")
        org = Organization(id=org_id, name="Audit Org", slug=org_id, billing_tier="team")
        membership = Membership(user_id=user_id, org_id=org_id, role="owner")
        
        # Add test audit logs
        log1 = AuditLog(
            id=f"log_{uuid.uuid4().hex[:8]}",
            tenant_id=org_id,
            user_id=user_id,
            action="PR_PUBLISHED",
            actor="Auditor",
            details={"pr_number": 101, "target": "main"}
        )
        log2 = AuditLog(
            id=f"log_{uuid.uuid4().hex[:8]}",
            tenant_id=org_id,
            user_id=user_id,
            action="BOUNTY_CLAIMED",
            actor="Auditor",
            details={"reward": 500, "platform": "polar"}
        )
        session.add_all([user, org, membership, log1, log2])
        await session.commit()

    token = get_test_token(user_id=user_id, username="auditor", org_id=org_id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Export CSV
        csv_resp = await client.get("/api/v1/audit-logs/export?format=csv", headers=headers)
        assert csv_resp.status_code == 200
        assert "text/csv" in csv_resp.headers.get("content-type", "")
        assert "attachment" in csv_resp.headers.get("content-disposition", "")
        
        reader = csv.reader(io.StringIO(csv_resp.text))
        rows = list(reader)
        assert len(rows) >= 3  # header + 2 logs
        assert rows[0] == ["id", "created_at", "actor", "action", "task_id", "issue_id", "details"]
        actions = [r[3] for r in rows[1:]]
        assert "PR_PUBLISHED" in actions
        assert "BOUNTY_CLAIMED" in actions

        # 2. Export SIEM JSON
        json_resp = await client.get("/api/v1/audit-logs/export?format=json", headers=headers)
        assert json_resp.status_code == 200
        assert "application/json" in json_resp.headers.get("content-type", "")
        records = json_resp.json()
        assert len(records) >= 2
        record_actions = [r["action"] for r in records]
        assert "PR_PUBLISHED" in record_actions
        assert "BOUNTY_CLAIMED" in record_actions


@pytest.mark.asyncio
async def test_enterprise_sso_service_and_endpoints():
    """Verify EnterpriseSSOService IdP detection, test probing, and configuration persistence."""
    # 1. IdP Auto-detection & Metadata parsing
    meta = EnterpriseSSOService.parse_and_validate_metadata(
        metadata_url="https://company.okta.com/app/exk12345/sso/saml/metadata"
    )
    assert meta["valid"] is True
    assert meta["provider"] == "okta"
    assert "https://company.okta.com" in meta["login_url"]
    assert "SHA256:" in meta["cert_fingerprint"]

    # 2. Setup organization and admin token
    session_factory = await get_session_factory()
    org_id = f"org_{uuid.uuid4().hex[:12]}"
    user_id = f"usr_{uuid.uuid4().hex[:12]}"

    async with session_factory() as session:
        user = User(id=user_id, github_username=f"admin_{uuid.uuid4().hex[:6]}", name="Org Admin")
        org = Organization(id=org_id, name="Enterprise Corp", slug=org_id, billing_tier="team")
        membership = Membership(user_id=user_id, org_id=org_id, role="owner")
        session.add_all([user, org, membership])
        await session.commit()

    token = get_test_token(user_id=user_id, username="admin_user", org_id=org_id, role="owner")
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test connection endpoint
        test_resp = await client.post(
            "/api/v1/enterprise/sso/test",
            headers=headers,
            json={"metadata_url": "https://sts.windows.net/tenant-uuid-1234/federationmetadata/2007-06/federationmetadata.xml"}
        )
        assert test_resp.status_code == 200
        data = test_resp.json()
        assert data["status"] == "success"
        assert data["provider"] == "azure_ad"

        # Configure SSO
        conf_resp = await client.post(
            "/api/v1/enterprise/sso",
            headers=headers,
            json={
                "sso_provider": "okta",
                "sso_metadata_url": "https://company.okta.com/app/exk999/sso/saml/metadata",
                "sso_entity_id": "https://issuetopr.dev/sp",
                "sso_enforced": True
            }
        )
        assert conf_resp.status_code == 200
        conf_data = conf_resp.json()
        assert conf_data["sso_provider"] == "okta"
        assert conf_data["sso_enforced"] is True
        assert conf_data["sso_configured"] is True

        # Read back SSO config
        get_resp = await client.get("/api/v1/enterprise/sso", headers=headers)
        assert get_resp.status_code == 200
        saved = get_resp.json()
        assert saved["sso_provider"] == "okta"
        assert saved["sso_enforced"] is True
        assert saved["sso_metadata_url"] == "https://company.okta.com/app/exk999/sso/saml/metadata"
