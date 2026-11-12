import hashlib
import hmac
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

project_root = Path(__file__).resolve().parent.parent
backend_path = project_root / "backend"
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.main import app
from app.core.crypto import encrypt_secret
from app.db.database import get_session_factory
from app.models.models import (
    Issue,
    Membership,
    Organization,
    OrganizationSettings,
    Repository,
    Runner,
    RunnerJob,
    Task,
    User,
    UserSettings,
    WebhookSubscription,
)
from app.api.v1.runners import resolve_runner_priority
from app.services.issue_analyzer import IssueAnalyzer
from app.services.llm_service import LLMService
from app.services.queue_service import InMemoryAsyncQueueBackend
from app.services.settings_resolver import SettingsResolver
from tests.e2e.conftest import make_session_token


def _make_tenant_token(
    user_id: str,
    username: str,
    org_id: str,
    tier: str = "starter",
    role: str = "owner",
) -> str:
    claims = {
        "user_id": user_id,
        "username": username,
        "tenant_id": org_id,
        "role": role,
        "tier": tier,
    }
    return make_session_token(subject=user_id, claims=claims)


def _sign_gh_webhook(body_bytes: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ---------------------------------------------------------------------------
# 1. Real BYOK LLM Integration, Fallback & Org Key Precedence + Triage Policy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_service_custom_endpoint_and_fallback():
    """Verify LLMService parses OpenAI/custom JSON completions and safely returns None on failure."""
    custom_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "executive_summary": "Fixes race condition in worker heartbeat loop.",
                            "root_cause_analysis": "Shared dictionary mutated across coroutines without lock.",
                            "affected_files": ["backend/app/worker.py", "tests/test_worker.py"],
                            "proposed_plan": [
                                "Add asyncio.Lock around worker registry updates",
                                "Guard state transitions with atomic swap",
                                "Add concurrency regression test",
                            ],
                            "test_command": "pytest tests/test_worker.py -q",
                        }
                    )
                }
            }
        ]
    }
    mock_ok_resp = MagicMock()
    mock_ok_resp.status_code = 200
    mock_ok_resp.json.return_value = custom_payload

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.post = AsyncMock(return_value=mock_ok_resp)

    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        result = await LLMService.generate_issue_brief(
            api_key="sk-custom-test-key",
            provider="custom",
            owner="acme",
            repo="core",
            issue_number=42,
            title="Fix worker heartbeat race",
            body="Occurs under high concurrency.",
            language="Python",
            custom_endpoint="https://llm.internal.example/v1",
        )

    assert result is not None
    assert "race condition" in result["executive_summary"]
    assert result["affected_files"] == ["backend/app/worker.py", "tests/test_worker.py"]
    assert result["test_command"] == "pytest tests/test_worker.py -q"
    called_url = mock_client.post.call_args.args[0]
    assert called_url == "https://llm.internal.example/v1/chat/completions"

    # Malformed / HTTP 500 fallback should return None cleanly
    mock_err_resp = MagicMock()
    mock_err_resp.status_code = 500
    mock_client.post = AsyncMock(return_value=mock_err_resp)
    with patch("app.services.llm_service.httpx.AsyncClient", return_value=mock_client):
        fallback = await LLMService.generate_issue_brief(
            api_key="sk-custom-test-key",
            provider="openai",
            owner="acme",
            repo="core",
            issue_number=42,
            title="Fix worker heartbeat race",
            body="Occurs under high concurrency.",
        )
    assert fallback is None


@pytest.mark.asyncio
async def test_issue_analyzer_live_byok_and_triage_policy_override():
    """Verify IssueAnalyzer applies live BYOK output & enforces org triage_policy.require_maintainer_approval."""
    analyzer = IssueAnalyzer()
    policy_mock = AsyncMock(
        return_value={
            "assignment_required": False,
            "workflow_state": "READY_TO_WORK",
            "evidence": [],
            "draft_comment": None,
        }
    )
    llm_mock = AsyncMock(
        return_value={
            "executive_summary": "Live BYOK analysis of tensor shape bug.",
            "root_cause_analysis": "Broadcast dimension mismatch on channel axis.",
            "affected_files": ["src/ops/tensor.py"],
            "proposed_plan": ["Check axis alignment", "Add shape validation unit test"],
            "test_command": "pytest tests/test_tensor.py",
        }
    )

    with (
        patch.object(analyzer.policy_inspector, "inspect_repository_policy", policy_mock),
        patch("app.services.issue_analyzer.LLMService.generate_issue_brief", llm_mock),
    ):
        brief = await analyzer.analyze_issue(
            owner="kornia",
            repo="kornia",
            issue_number=999,
            title="Broadcast bug in resize",
            body="Fails on 3D tensors.",
            labels=[],
            language="Python",
            ai_api_key="sk-team-byok",
            ai_provider="anthropic",
            ai_key_source="organization",
            triage_policy={"require_maintainer_approval": True},
        )

    assert brief["ai_mode"] == "live_byok"
    assert brief["ai_provider"] == "anthropic"
    assert brief["ai_key_source"] == "organization"
    assert brief["executive_summary"] == "Live BYOK analysis of tensor shape bug."
    assert brief["test_strategy"]["command"] == "pytest tests/test_tensor.py"
    assert brief["rule_check"]["assignment_required"] is True
    assert brief["rule_check"]["workflow_state"] == "ASSIGNMENT_REQUIRED"
    assert brief["rule_check"]["draft_comment"] is not None


@pytest.mark.asyncio
async def test_settings_resolver_shared_org_key_precedence():
    """Verify SettingsResolver honors enforce_shared_keys & exposes triage_policy and custom_endpoint."""
    uid = f"usr_res_{uuid.uuid4().hex[:8]}"
    oid = f"org_res_{uuid.uuid4().hex[:8]}"
    session_factory = await get_session_factory()
    async with session_factory() as db:
        db.add(User(id=uid, github_username=f"user_{uid}", email=f"{uid}@test.dev"))
        db.add(Organization(id=oid, name="Org", slug=oid, billing_tier="team"))
        db.add(
            UserSettings(
                user_id=uid,
                preferred_ai_provider="custom",
                custom_api_key_encrypted=encrypt_secret("personal-custom-secret"),
                custom_endpoint="https://personal.llm/v1",
            )
        )
        o_sett = OrganizationSettings(
            org_id=oid,
            custom_api_key_encrypted=encrypt_secret("org-custom-secret"),
            custom_endpoint="https://org.llm/v1",
            enforce_shared_keys=True,
            triage_policy={"require_maintainer_approval": True, "auto_sync_private_repos": True},
        )
        db.add(o_sett)
        await db.commit()

        cfg_enforced = await SettingsResolver.resolve_effective_ai_config(db=db, user_id=uid, org_id=oid)
        assert cfg_enforced["provider"] == "custom"
        assert cfg_enforced["api_key"] == "org-custom-secret"
        assert cfg_enforced["key_source"] == "organization"
        assert cfg_enforced["custom_endpoint"] == "https://org.llm/v1"
        assert cfg_enforced["enforce_shared_keys"] is True
        assert cfg_enforced["triage_policy"]["require_maintainer_approval"] is True

        o_sett.enforce_shared_keys = False
        await db.commit()

        cfg_personal = await SettingsResolver.resolve_effective_ai_config(db=db, user_id=uid, org_id=oid)
        assert cfg_personal["api_key"] == "personal-custom-secret"
        assert cfg_personal["key_source"] == "personal"
        assert cfg_personal["custom_endpoint"] == "https://personal.llm/v1"


# ---------------------------------------------------------------------------
# 2. Pro Custom Skill & Tag Weighting Matrix + Live Issue Rescore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pro_ranking_matrix_and_rescore():
    """Verify PUT /settings/ranking-matrix and POST /issues/rescore gate on Pro and re-rank issues."""
    starter_uid = f"usr_mat_s_{uuid.uuid4().hex[:8]}"
    starter_oid = f"org_mat_s_{uuid.uuid4().hex[:8]}"
    pro_uid = f"usr_mat_p_{uuid.uuid4().hex[:8]}"
    pro_oid = f"org_mat_p_{uuid.uuid4().hex[:8]}"

    starter_token = _make_tenant_token(starter_uid, f"s_{starter_uid}", starter_oid, tier="starter")
    pro_token = _make_tenant_token(pro_uid, f"p_{pro_uid}", pro_oid, tier="pro")

    session_factory = await get_session_factory()
    async with session_factory() as db:
        repo_id = f"repo-mat-{uuid.uuid4().hex[:8]}"
        issue_id = f"iss-mat-{uuid.uuid4().hex[:8]}"
        db.add(
            Repository(
                id=repo_id,
                owner="matrix-org",
                name="rust-engine",
                full_name=f"matrix-org/rust-engine-{uuid.uuid4().hex[:6]}",
                html_url="https://github.com/matrix-org/rust-engine",
                primary_language="Rust",
                license_spdx="MIT",
                stars_count=2500,
                is_private=False,
            )
        )
        await db.flush()
        db.add(
            Issue(
                id=issue_id,
                repository_id=repo_id,
                github_id=int(uuid.uuid4().int % 900_000_000) + 100_000_000,
                issue_number=101,
                title="Optimize async Tokio runtime batching in Rust",
                body="Fix slow flush handling for high throughput queues.",
                html_url="https://github.com/matrix-org/rust-engine/issues/101",
                state="open",
                is_eligible=True,
                labels=[{"name": "gsoc"}, {"name": "performance"}],
                ranking_score=40.0,
            )
        )
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Starter is blocked with 403
        deny_matrix = await client.put(
            "/api/v1/settings/ranking-matrix",
            headers={"Authorization": f"Bearer {starter_token}"},
            json={"skill_weights": {"rust": 2.5}, "tag_weights": {"gsoc": 2.0}},
        )
        assert deny_matrix.status_code == 403

        deny_rescore = await client.post(
            "/api/v1/issues/rescore",
            headers={"Authorization": f"Bearer {starter_token}"},
        )
        assert deny_rescore.status_code == 403

        # Configure user skills first for Pro user
        save_skills = await client.put(
            "/api/v1/settings",
            headers={"Authorization": f"Bearer {pro_token}"},
            json={"skills_profile": ["Rust", "Python"]},
        )
        assert save_skills.status_code == 200

        # Save weighted matrix as Pro (verify 0.25 - 3.0 clamping too)
        put_matrix = await client.put(
            "/api/v1/settings/ranking-matrix",
            headers={"Authorization": f"Bearer {pro_token}"},
            json={"skill_weights": {"rust": 2.8, "extreme": 10.0}, "tag_weights": {"gsoc": 2.2}},
        )
        assert put_matrix.status_code == 200
        mat_data = put_matrix.json()
        assert mat_data["skill_weights"]["rust"] == 2.8
        assert mat_data["skill_weights"]["extreme"] == 3.0
        assert mat_data["tag_weights"]["gsoc"] == 2.2

        # Rescore inbox issues
        rescore_resp = await client.post(
            "/api/v1/issues/rescore",
            headers={"Authorization": f"Bearer {pro_token}"},
        )
        assert rescore_resp.status_code == 200
        rescore_data = rescore_resp.json()
        assert rescore_data["status"] == "rescored"
        assert rescore_data["rescored_count"] >= 1

    async with session_factory() as db:
        iss = (await db.execute(select(Issue).where(Issue.id == issue_id))).scalar_one()
        assert iss.ranking_breakdown.get("weighted_matrix_applied") is True
        assert iss.ranking_score > 40.0


# ---------------------------------------------------------------------------
# 3. Priority Runner Job Queue (Team > Pro > Starter) & InMemory Priority Queue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inmemory_priority_queue_ordering():
    """Verify InMemoryAsyncQueueBackend dequeues highest priority first and preserves FIFO ties."""
    backend = InMemoryAsyncQueueBackend()
    await backend.enqueue("jobs", {"job_id": "starter-1", "priority": 10})
    await backend.enqueue("jobs", {"job_id": "pro-1", "priority": 20})
    await backend.enqueue("jobs", {"job_id": "team-1", "priority": 30})
    await backend.enqueue("jobs", {"job_id": "pro-2", "priority": 20})

    assert await backend.get_length("jobs") == 4
    order = []
    for _ in range(4):
        item = await backend.dequeue("jobs")
        order.append(item["job_id"])
    assert order == ["team-1", "pro-1", "pro-2", "starter-1"]


@pytest.mark.asyncio
async def test_priority_runner_job_queue_endpoints_and_poll_order():
    """Verify runner job priority stamps by tier (Team=30 > Pro=20 > Starter=10) & polls highest first."""
    assert resolve_runner_priority("starter") == 10
    assert resolve_runner_priority("pro") == 20
    assert resolve_runner_priority("team") == 30
    assert resolve_runner_priority("enterprise") == 40

    uid = f"usr_run_{uuid.uuid4().hex[:8]}"
    oid = f"org_run_{uuid.uuid4().hex[:8]}"
    token = _make_tenant_token(uid, f"r_{uid}", oid, tier="starter")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register runner in tenant (starts at starter)
        reg = await client.post(
            "/api/v1/runners/register",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": f"prio-runner-{uuid.uuid4().hex[:6]}", "os_info": "Linux x64", "registration_token": token},
        )
        assert reg.status_code == 201
        runner_token = reg.json()["runner_token"]

        # Queue older starter job (priority=10)
        j1 = await client.post(
            "/api/v1/runners/jobs",
            headers={"Authorization": f"Bearer {token}"},
            json={"job_type": "starter_scan", "payload": {"seq": 1}},
        )
        assert j1.status_code == 201
        assert j1.json()["priority"] == 10

        # Upgrade org to Team in DB and queue a newer priority=30 job
        session_factory = await get_session_factory()
        async with session_factory() as db:
            org = (await db.execute(select(Organization).where(Organization.id == oid))).scalar_one()
            org.billing_tier = "team"
            await db.commit()

        j2 = await client.post(
            "/api/v1/runners/jobs",
            headers={"Authorization": f"Bearer {token}"},
            json={"job_type": "team_hotfix", "payload": {"seq": 2}},
        )
        assert j2.status_code == 201
        assert j2.json()["priority"] == 30

        # List jobs confirms both present
        jobs_list = await client.get("/api/v1/runners/jobs", headers={"Authorization": f"Bearer {token}"})
        assert jobs_list.status_code == 200
        assert len(jobs_list.json()) >= 2

        # Runner poll MUST pop the priority=30 job before the older priority=10 job
        poll1 = await client.get(
            "/api/v1/runners/jobs/poll",
            headers={"Authorization": f"Bearer {runner_token}"},
        )
        assert poll1.status_code == 200
        assert poll1.json()["id"] == j2.json()["id"]
        assert poll1.json()["priority"] == 30

        poll2 = await client.get(
            "/api/v1/runners/jobs/poll",
            headers={"Authorization": f"Bearer {runner_token}"},
        )
        assert poll2.status_code == 200
        assert poll2.json()["id"] == j1.json()["id"]
        assert poll2.json()["priority"] == 10


# ---------------------------------------------------------------------------
# 4. Pro Per-Tenant Webhooks & Priority Discovery Sync
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pro_webhooks_and_priority_sync():
    """Verify Starter blocked from webhooks & priority-sync, while Pro receives signed tenant webhooks."""
    s_uid = f"usr_wh_s_{uuid.uuid4().hex[:8]}"
    s_oid = f"org_wh_s_{uuid.uuid4().hex[:8]}"
    p_uid = f"usr_wh_p_{uuid.uuid4().hex[:8]}"
    p_oid = f"org_wh_p_{uuid.uuid4().hex[:8]}"

    s_token = _make_tenant_token(s_uid, f"whs_{s_uid}", s_oid, tier="starter")
    p_token = _make_tenant_token(p_uid, f"whp_{p_uid}", p_oid, tier="pro")

    unique_repo = f"acme-webhook/app-{uuid.uuid4().hex[:6]}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unauthenticated subscription endpoint must reject (auth middleware fix check)
        unauth = await client.get("/api/v1/webhooks/subscriptions")
        assert unauth.status_code == 401

        # Starter gets 403 on Pro endpoints
        s_wh = await client.post(
            "/api/v1/webhooks/subscriptions",
            headers={"Authorization": f"Bearer {s_token}"},
            json={"repo_full_name": unique_repo},
        )
        assert s_wh.status_code == 403

        s_sync = await client.post(
            "/api/v1/discovery/priority-sync",
            headers={"Authorization": f"Bearer {s_token}"},
            json={"language": "Python", "gsoc_only": True},
        )
        assert s_sync.status_code == 403

        # Pro creates webhook subscription
        create_wh = await client.post(
            "/api/v1/webhooks/subscriptions",
            headers={"Authorization": f"Bearer {p_token}"},
            json={"repo_full_name": f"https://github.com/{unique_repo}", "events": ["issues", "pull_request"]},
        )
        assert create_wh.status_code == 201
        sub = create_wh.json()
        assert sub["repo_full_name"] == unique_repo
        assert sub["webhook_secret"].startswith("whsec_")
        assert sub["deliveries_count"] == 0

        # Invalid signature rejected
        gh_payload = json.dumps(
            {
                "action": "opened",
                "repository": {
                    "full_name": unique_repo,
                    "name": unique_repo.split("/")[1],
                    "owner": {"login": "acme-webhook"},
                    "private": False,
                    "language": "Python",
                },
                "issue": {
                    "id": int(uuid.uuid4().int % 900_000_000) + 100_000_000,
                    "number": 77,
                    "title": "Realtime webhook issue",
                    "body": "Delivered via Pro subscription secret.",
                    "state": "open",
                    "labels": [],
                    "assignees": [],
                },
            }
        ).encode("utf-8")

        bad_sig = await client.post(
            "/api/v1/webhooks/github",
            content=gh_payload,
            headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": "sha256=deadbeef"},
        )
        assert bad_sig.status_code == 401

        # Valid per-tenant subscription signature accepted & increments deliveries_count
        good_sig = _sign_gh_webhook(gh_payload, sub["webhook_secret"])
        ok_wh = await client.post(
            "/api/v1/webhooks/github",
            content=gh_payload,
            headers={"X-GitHub-Event": "issues", "X-Hub-Signature-256": good_sig},
        )
        assert ok_wh.status_code == 200
        assert ok_wh.json()["status"] == "ok"

        list_wh = await client.get(
            "/api/v1/webhooks/subscriptions",
            headers={"Authorization": f"Bearer {p_token}"},
        )
        assert list_wh.status_code == 200
        found = next(s for s in list_wh.json() if s["id"] == sub["id"])
        assert found["deliveries_count"] == 1
        assert found["last_delivery_at"] is not None

        # Delete subscription
        del_wh = await client.delete(
            f"/api/v1/webhooks/subscriptions/{sub['id']}",
            headers={"Authorization": f"Bearer {p_token}"},
        )
        assert del_wh.status_code == 204

        # Priority sync succeeds for Pro (mock DiscoveryService network crawl)
        with patch(
            "app.api.v1.discovery.DiscoveryService.run_discovery_sync",
            new=AsyncMock(return_value={"total_discovered": 7, "errors": []}),
        ):
            p_sync = await client.post(
                "/api/v1/discovery/priority-sync",
                headers={"Authorization": f"Bearer {p_token}"},
                json={"language": "Python", "gsoc_only": True},
            )
        assert p_sync.status_code == 200
        assert p_sync.json()["status"] == "priority_synced"
        assert p_sync.json()["discovered"] == 7


# ---------------------------------------------------------------------------
# 5. Team Private Repos Sync + Cross-Tenant Isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_team_private_repos_sync_and_tenant_isolation():
    """Verify Team private repo endpoints gate on Team tier & enforce strict cross-tenant isolation."""
    pro_uid = f"usr_pr_p_{uuid.uuid4().hex[:8]}"
    pro_oid = f"org_pr_p_{uuid.uuid4().hex[:8]}"
    team_a_uid = f"usr_pr_a_{uuid.uuid4().hex[:8]}"
    team_a_oid = f"org_pr_a_{uuid.uuid4().hex[:8]}"
    team_b_uid = f"usr_pr_b_{uuid.uuid4().hex[:8]}"
    team_b_oid = f"org_pr_b_{uuid.uuid4().hex[:8]}"

    pro_token = _make_tenant_token(pro_uid, f"prp_{pro_uid}", pro_oid, tier="pro")
    team_a_token = _make_tenant_token(team_a_uid, f"pra_{team_a_uid}", team_a_oid, tier="team")
    team_b_token = _make_tenant_token(team_b_uid, f"prb_{team_b_uid}", team_b_oid, tier="team")

    priv_full_name = f"secret-corp/internal-api-{uuid.uuid4().hex[:6]}"
    priv_issue_gh_id = int(uuid.uuid4().int % 900_000_000) + 100_000_000

    mock_repo_payload = {
        "full_name": priv_full_name,
        "html_url": f"https://github.com/{priv_full_name}",
        "default_branch": "main",
        "language": "Python",
        "stargazers_count": 3,
        "open_issues_count": 1,
        "private": True,
    }
    mock_issues_payload = [
        {
            "id": priv_issue_gh_id,
            "number": 12,
            "title": "Internal auth key rotation bug",
            "body": "Confidential stack trace in internal service.",
            "html_url": f"https://github.com/{priv_full_name}/issues/12",
            "state": "open",
            "user": {"login": "staff-eng"},
            "labels": [{"name": "bug"}],
            "assignees": [],
            "comments": 0,
        }
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Pro tier cannot list/sync Team private repos or import a private repo
        deny_list = await client.get(
            f"/api/v1/organizations/{pro_oid}/private-repos",
            headers={"Authorization": f"Bearer {pro_token}"},
        )
        assert deny_list.status_code == 403

        deny_sync = await client.post(
            f"/api/v1/organizations/{pro_oid}/private-repos/sync",
            headers={"Authorization": f"Bearer {pro_token}"},
            json={},
        )
        assert deny_sync.status_code == 403

        with patch("app.api.v1.issues.GitHubClient.get_repository", new=AsyncMock(return_value=mock_repo_payload)):
            deny_import = await client.post(
                "/api/v1/issues/import",
                headers={"Authorization": f"Bearer {pro_token}"},
                json={"url": f"https://github.com/{priv_full_name}/issues/12"},
            )
            assert deny_import.status_code == 403

        # Team A syncs its private repositories
        with (
            patch("app.api.v1.organizations.GitHubClient.list_user_private_repos", new=AsyncMock(return_value=[mock_repo_payload])),
            patch("app.api.v1.organizations.GitHubClient.get_repo_issues", new=AsyncMock(return_value=mock_issues_payload)),
        ):
            sync_ok = await client.post(
                f"/api/v1/organizations/{team_a_oid}/private-repos/sync",
                headers={"Authorization": f"Bearer {team_a_token}"},
                json={},
            )
            assert sync_ok.status_code == 200
            assert sync_ok.json()["synced_repos"] == 1
            assert sync_ok.json()["synced_issues"] == 1

        list_priv = await client.get(
            f"/api/v1/organizations/{team_a_oid}/private-repos",
            headers={"Authorization": f"Bearer {team_a_token}"},
        )
        assert list_priv.status_code == 200
        assert any(r["full_name"] == priv_full_name for r in list_priv.json())

        # Find created private issue ID
        session_factory = await get_session_factory()
        async with session_factory() as db:
            priv_issue = (await db.execute(select(Issue).where(Issue.github_id == priv_issue_gh_id))).scalar_one()
            priv_issue_id = priv_issue.id

        # Team A sees its private issue in /issues and /issues/{id}
        team_a_get = await client.get(
            f"/api/v1/issues/{priv_issue_id}",
            headers={"Authorization": f"Bearer {team_a_token}"},
        )
        assert team_a_get.status_code == 200
        assert team_a_get.json()["repository"]["is_private"] is True

        with patch("app.api.v1.issues.GitHubClient.get_issue_linked_prs", new=AsyncMock(return_value=[])):
            team_a_inbox = await client.get(
                f"/api/v1/issues?repository={priv_full_name}",
                headers={"Authorization": f"Bearer {team_a_token}"},
            )
            assert team_a_inbox.status_code == 200
            assert any(i["id"] == priv_issue_id for i in team_a_inbox.json()["items"])

            # Team B is strictly isolated: gets 404 on direct get and 0 matches in inbox
            team_b_get = await client.get(
                f"/api/v1/issues/{priv_issue_id}",
                headers={"Authorization": f"Bearer {team_b_token}"},
            )
            assert team_b_get.status_code == 404

            team_b_inbox = await client.get(
                f"/api/v1/issues?repository={priv_full_name}",
                headers={"Authorization": f"Bearer {team_b_token}"},
            )
            assert team_b_inbox.status_code == 200
            assert not any(i["id"] == priv_issue_id for i in team_b_inbox.json()["items"])


# ---------------------------------------------------------------------------
# 6. Team Multi-User Seats & RBAC Governance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multi_user_seats_rbac_and_seat_cap():
    """Verify Starter allows 2 seats max, Team allows 3+, RBAC PATCH/DELETE & last-owner protection."""
    starter_uid = f"usr_rbac_s_{uuid.uuid4().hex[:8]}"
    starter_oid = f"org_rbac_s_{uuid.uuid4().hex[:8]}"
    team_uid = f"usr_rbac_t_{uuid.uuid4().hex[:8]}"
    team_oid = f"org_rbac_t_{uuid.uuid4().hex[:8]}"

    starter_token = _make_tenant_token(starter_uid, f"rbacs_{starter_uid}", starter_oid, tier="starter")
    team_token = _make_tenant_token(team_uid, f"rbact_{team_uid}", team_oid, tier="team")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Starter: 2nd seat OK, 3rd seat blocked (requires Team)
        seat2 = await client.post(
            f"/api/v1/organizations/{starter_oid}/members",
            headers={"Authorization": f"Bearer {starter_token}"},
            json={"username_or_email": f"dev2_{uuid.uuid4().hex[:6]}", "role": "member"},
        )
        assert seat2.status_code == 201

        seat3_denied = await client.post(
            f"/api/v1/organizations/{starter_oid}/members",
            headers={"Authorization": f"Bearer {starter_token}"},
            json={"username_or_email": f"dev3_{uuid.uuid4().hex[:6]}", "role": "member"},
        )
        assert seat3_denied.status_code == 403
        assert seat3_denied.json()["detail"]["required_tier"] == "team"

        # Team: 2nd and 3rd seats allowed
        m2 = await client.post(
            f"/api/v1/organizations/{team_oid}/members",
            headers={"Authorization": f"Bearer {team_token}"},
            json={"username_or_email": f"t_dev2_{uuid.uuid4().hex[:6]}", "role": "member"},
        )
        assert m2.status_code == 201
        m3 = await client.post(
            f"/api/v1/organizations/{team_oid}/members",
            headers={"Authorization": f"Bearer {team_token}"},
            json={"username_or_email": f"t_dev3_{uuid.uuid4().hex[:6]}", "role": "member"},
        )
        assert m3.status_code == 201
        m2_data = m2.json()

        # Non-admin member cannot PATCH roles
        m2_token = _make_tenant_token(m2_data["user_id"], m2_data["username"], team_oid, tier="team", role="member")
        non_admin_patch = await client.patch(
            f"/api/v1/organizations/{team_oid}/members/{m3.json()['id']}",
            headers={"Authorization": f"Bearer {m2_token}"},
            json={"role": "admin"},
        )
        assert non_admin_patch.status_code == 403

        # Owner promotes m2 -> admin
        promote = await client.patch(
            f"/api/v1/organizations/{team_oid}/members/{m2_data['id']}",
            headers={"Authorization": f"Bearer {team_token}"},
            json={"role": "admin"},
        )
        assert promote.status_code == 200
        assert promote.json()["role"] == "admin"

        # Sole owner cannot be demoted or deleted
        members_list = (
            await client.get(
                f"/api/v1/organizations/{team_oid}/members",
                headers={"Authorization": f"Bearer {team_token}"},
            )
        ).json()
        owner_mem = next(m for m in members_list if m["role"] == "owner")

        demote_owner = await client.patch(
            f"/api/v1/organizations/{team_oid}/members/{owner_mem['id']}",
            headers={"Authorization": f"Bearer {team_token}"},
            json={"role": "admin"},
        )
        assert demote_owner.status_code == 400

        del_owner = await client.delete(
            f"/api/v1/organizations/{team_oid}/members/{owner_mem['id']}",
            headers={"Authorization": f"Bearer {team_token}"},
        )
        assert del_owner.status_code == 400

        # Non-owner member can be removed cleanly
        del_m3 = await client.delete(
            f"/api/v1/organizations/{team_oid}/members/{m3.json()['id']}",
            headers={"Authorization": f"Bearer {team_token}"},
        )
        assert del_m3.status_code == 204


# ---------------------------------------------------------------------------
# 7. Team Centralized PR Velocity Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_team_pr_velocity_dashboard():
    """Verify GET /organizations/{org_id}/velocity gates on Team & aggregates PR/CI metrics."""
    pro_uid = f"usr_vel_p_{uuid.uuid4().hex[:8]}"
    pro_oid = f"org_vel_p_{uuid.uuid4().hex[:8]}"
    team_uid = f"usr_vel_t_{uuid.uuid4().hex[:8]}"
    team_oid = f"org_vel_t_{uuid.uuid4().hex[:8]}"

    pro_token = _make_tenant_token(pro_uid, f"vp_{pro_uid}", pro_oid, tier="pro")
    team_token = _make_tenant_token(team_uid, f"vt_{team_uid}", team_oid, tier="team")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Pro gets 403
        deny_vel = await client.get(
            f"/api/v1/organizations/{pro_oid}/velocity",
            headers={"Authorization": f"Bearer {pro_token}"},
        )
        assert deny_vel.status_code == 403

        # Trigger JIT creation of Team user/org and add a teammate
        teammate = await client.post(
            f"/api/v1/organizations/{team_oid}/members",
            headers={"Authorization": f"Bearer {team_token}"},
            json={"username_or_email": f"vel_eng_{uuid.uuid4().hex[:6]}", "role": "member"},
        )
        assert teammate.status_code == 201
        teammate_uid = teammate.json()["user_id"]

        # Seed repository, issues, and PR tasks scoped to team_oid
        session_factory = await get_session_factory()
        async with session_factory() as db:
            repo_id = f"repo-vel-{uuid.uuid4().hex[:8]}"
            iss1_id = f"iss-vel1-{uuid.uuid4().hex[:8]}"
            iss2_id = f"iss-vel2-{uuid.uuid4().hex[:8]}"
            db.add(
                Repository(
                    id=repo_id,
                    tenant_id=team_oid,
                    owner="vel-org",
                    name="backend",
                    full_name=f"vel-org/backend-{uuid.uuid4().hex[:6]}",
                    html_url="https://github.com/vel-org/backend",
                    primary_language="Python",
                )
            )
            await db.flush()
            db.add(
                Issue(
                    id=iss1_id,
                    tenant_id=team_oid,
                    repository_id=repo_id,
                    github_id=int(uuid.uuid4().int % 900_000_000) + 100_000_000,
                    issue_number=1,
                    title="Speed up serialization",
                    html_url="https://github.com/vel-org/backend/issues/1",
                )
            )
            db.add(
                Issue(
                    id=iss2_id,
                    tenant_id=team_oid,
                    repository_id=repo_id,
                    github_id=int(uuid.uuid4().int % 900_000_000) + 100_000_000,
                    issue_number=2,
                    title="Fix timeout retry",
                    html_url="https://github.com/vel-org/backend/issues/2",
                )
            )
            await db.flush()
            now = datetime.utcnow()
            db.add(
                Task(
                    id=f"tsk-v1-{uuid.uuid4().hex[:8]}",
                    tenant_id=team_oid,
                    user_id=team_uid,
                    issue_id=iss1_id,
                    workflow_state="PR_SUBMITTED",
                    pr_number=201,
                    pr_url="https://github.com/vel-org/backend/pull/201",
                    pr_state="closed",
                    pr_merged=True,
                    pr_ci_status="success",
                    pr_review_status="APPROVED",
                    created_at=now - timedelta(hours=6),
                    updated_at=now,
                )
            )
            db.add(
                Task(
                    id=f"tsk-v2-{uuid.uuid4().hex[:8]}",
                    tenant_id=team_oid,
                    user_id=teammate_uid,
                    issue_id=iss2_id,
                    workflow_state="PR_SUBMITTED",
                    pr_number=202,
                    pr_url="https://github.com/vel-org/backend/pull/202",
                    pr_state="open",
                    pr_merged=False,
                    pr_ci_status="failure",
                    pr_review_status="CHANGES_REQUESTED",
                    created_at=now - timedelta(hours=2),
                    updated_at=now,
                )
            )
            await db.commit()

        vel_res = await client.get(
            f"/api/v1/organizations/{team_oid}/velocity",
            headers={"Authorization": f"Bearer {team_token}"},
        )
        assert vel_res.status_code == 200
        vel = vel_res.json()
        assert vel["organization_id"] == team_oid
        assert vel["total_tasks"] == 2
        assert vel["total_prs"] == 2
        assert vel["merged_prs"] == 1
        assert vel["open_prs"] == 1
        assert vel["changes_requested_prs"] == 1
        assert vel["merge_rate_pct"] == 50.0
        assert vel["ci_pass_rate_pct"] == 50.0
        assert vel["avg_cycle_hours"] == 4.0
        assert vel["seat_count"] == 2
        assert len(vel["contributors"]) == 2
        assert len(vel["recent_merges"]) == 1


@pytest.mark.asyncio
async def test_cron_scan_coalescing_and_response_fields():
    """Verify 2h cron scan coalesces concurrent calls and returns normalized sync/prune counts."""
    import asyncio
    from app.services.background_worker import BackgroundWorkerService

    session_factory = await get_session_factory()
    worker = BackgroundWorkerService(session_factory=session_factory)
    calls = 0

    async def fake_execute():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {
            "success": True,
            "status": "success",
            "discovered": 14,
            "last_issues_synced": 14,
            "last_issues_pruned": 3,
            "last_run_at": datetime.utcnow().isoformat(),
            "next_run_at": (datetime.utcnow() + timedelta(hours=2)).isoformat(),
        }

    worker._execute_cron_scan = fake_execute  # type: ignore[method-assign]
    r1, r2 = await asyncio.gather(worker.trigger_cron_scan(), worker.trigger_cron_scan())
    assert calls == 1
    assert r1["last_issues_synced"] == 14
    assert r1["last_issues_pruned"] == 3
    assert r2["discovered"] == 14

    uid = f"usr_cron_{uuid.uuid4().hex[:8]}"
    oid = f"org_cron_{uuid.uuid4().hex[:8]}"
    token = _make_tenant_token(uid, f"c_{uid}", oid, tier="starter")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.services.background_worker.get_background_worker", return_value=worker):
            resp = await client.post(
                "/api/v1/discovery/cron-run-now",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_issues_synced"] == 14
        assert body["last_issues_pruned"] == 3
        assert body["discovered"] == 14


@pytest.mark.asyncio
async def test_fast_discovery_sync_grouped_search_and_returns_total_discovered():
    """Verify DiscoveryService uses grouped Search queries concurrently & returns total_discovered."""
    from app.services.discovery_service import DiscoveryService

    session_factory = await get_session_factory()
    async with session_factory() as db:
        gh = MagicMock()
        gh.rate_limit_remaining = 4990
        gh.rate_limit_limit = 5000
        gh.get_repo_issues = AsyncMock(return_value=[])
        unique_gh_id = int(uuid.uuid4().int % 900_000_000) + 100_000_000
        search_call_count = 0

        async def fake_search(query: str, page: int = 1, per_page: int = 20):
            nonlocal search_call_count
            search_call_count += 1
            if "batch1" in query or "numfocus" in query:
                return {
                    "items": [
                        {
                            "id": unique_gh_id,
                            "number": 9876,
                            "title": "Fix fast numpy broadcast edge case",
                            "body": "Simple clean fix needed.",
                            "html_url": "https://github.com/numpy/numpy/issues/9876",
                            "repository_url": "https://api.github.com/repos/numpy/numpy",
                            "state": "open",
                            "user": {"login": "contributor"},
                            "labels": [{"name": "bug"}],
                            "assignees": [],
                            "comments": 1,
                        }
                    ]
                }
            return {"items": []}

        gh.search_issues = AsyncMock(side_effect=fake_search)
        gh.get_repository = AsyncMock(
            return_value={
                "stargazers_count": 28000,
                "license": {"spdx_id": "BSD-3-Clause", "name": "BSD 3-Clause"},
                "archived": False,
                "default_branch": "main",
            }
        )
        gh.get_issue_linked_prs = AsyncMock(return_value=[])

        svc = DiscoveryService(db=db, github_client=gh)
        res = await svc.run_discovery_sync(force_refresh=True, page_limit=1)
        assert search_call_count == 2  # 2 grouped batches instead of 13 separate org searches
        assert res["total_discovered"] >= 1
        assert res["items_synced"] == res["total_discovered"]



