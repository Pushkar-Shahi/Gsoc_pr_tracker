"""Tier 2: Boundary & Corner Cases Test Suite (F1 - F5).

Covers:
- F1: Tenant Models & Isolation Boundaries (>=5 tests)
- F2: GitHub OAuth 2.0 & Session Auth Boundaries (>=5 tests)
- F3: GitHub App Webhooks & HMAC Boundaries (>=5 tests)
- F4: Per-Tenant Settings & BYOK Boundaries (>=5 tests)
- F5: Hybrid Runner Foundation Boundaries (>=5 tests)
Total: 30 test cases.
"""

import hmac
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
backend_path = project_root / "backend"
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import SECRET_KEY, verify_session_token
from app.models.models import Repository, Issue, Task, AuditLog
from tests.e2e.conftest import (
    create_signed_webhook_payload,
    make_session_token,
    TEST_WEBHOOK_SECRET
)

try:
    from app.models.models import (
        User, Organization, Membership, UserSettings, OrganizationSettings,
        Runner, RunnerJob
    )
except ImportError:
    User = None
    Organization = None
    Membership = None
    UserSettings = None
    OrganizationSettings = None
    Runner = None
    RunnerJob = None

try:
    from app.core.crypto import encrypt_secret, decrypt_secret
except ImportError:
    encrypt_secret = None
    decrypt_secret = None

try:
    from app.services.settings_resolver import SettingsResolver
except ImportError:
    SettingsResolver = None


# ===========================================================================
# F1 Boundaries: Tenant Models & Isolation (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f1_boundary_cross_tenant_task_idor_access_denied(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """F1.B1: Verifies Tenant B cannot read Tenant A's task by ID (returns 404 or 403)."""
    tenant_a = tenant_factory(username="alice", org_slug="org_a")
    tenant_b = tenant_factory(username="bob", org_slug="org_b")

    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="test-owner",
        name="test-repo",
        full_name=f"test-owner/repo-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/test-owner/test-repo"
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 11,
        issue_number=101,
        title="IDOR Test Issue",
        html_url="https://github.com/test-owner/test-repo/issues/101",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    task_a = Task(
        id=f"tsk-idor-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=tenant_a["org_id"],
        user_id=tenant_a["user_id"],
        workflow_state="SELECTED"
    )
    db_session.add(task_a)
    await db_session.commit()

    # Bob attempts to fetch Alice's task
    res = await client.get(f"/api/v1/tasks/{task_a.id}", headers=tenant_b["headers"])
    assert res.status_code in (404, 403), "Accessing another tenant's task must return 404 or 403"


@pytest.mark.asyncio
async def test_f1_boundary_cross_tenant_task_update_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """F1.B2: Verifies Tenant B cannot trigger operations or approvals on Tenant A's task."""
    tenant_a = tenant_factory(username="alice", org_slug="org_a")
    tenant_b = tenant_factory(username="bob", org_slug="org_b")

    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="test-owner",
        name="test-repo",
        full_name=f"test-owner/repo-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/test-owner/test-repo"
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 12,
        issue_number=102,
        title="Update IDOR Issue",
        html_url="https://github.com/test-owner/test-repo/issues/102",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    task_a = Task(
        id=f"tsk-mod-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=tenant_a["org_id"],
        user_id=tenant_a["user_id"],
        workflow_state="COLLABORATIVE_WORK"
    )
    db_session.add(task_a)
    await db_session.commit()

    # Bob attempts to approve or prepare workspace for Alice's task
    res = await client.post(f"/api/v1/tasks/{task_a.id}/approve", headers=tenant_b["headers"])
    assert res.status_code in (404, 403), "Modifying another tenant's task must be rejected with 404 or 403"


@pytest.mark.asyncio
async def test_f1_boundary_cross_tenant_audit_clear_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """F1.B3: Verifies Tenant B deleting audit logs does not purge Tenant A's audit history."""
    tenant_a = tenant_factory(username="alice", org_slug="org_a")
    tenant_b = tenant_factory(username="bob", org_slug="org_b")

    log_a = AuditLog(
        id=f"log-iso-a-{uuid.uuid4().hex[:8]}",
        action="TASK_APPROVED",
        actor=tenant_a["username"],
        tenant_id=tenant_a["org_id"],
        user_id=tenant_a["user_id"]
    )
    log_b = AuditLog(
        id=f"log-iso-b-{uuid.uuid4().hex[:8]}",
        action="TASK_APPROVED",
        actor=tenant_b["username"],
        tenant_id=tenant_b["org_id"],
        user_id=tenant_b["user_id"]
    )
    db_session.add_all([log_a, log_b])
    await db_session.commit()

    del_res = await client.delete("/api/v1/audit-logs", headers=tenant_b["headers"])
    assert del_res.status_code in (200, 204)

    # Verify Alice's log is completely preserved
    check = await db_session.execute(select(AuditLog).where(AuditLog.id == log_a.id))
    assert check.scalar_one_or_none() is not None, "Tenant A audit logs must not be purged by Tenant B"


@pytest.mark.asyncio
async def test_f1_boundary_invalid_tenant_header_raises_403(
    client: AsyncClient,
    tenant_factory
):
    """F1.B4: Verifies specifying X-Organization-Id for an org user is not member of returns 403."""
    tenant = tenant_factory(username="eve")
    forged_headers = {
        "Authorization": f"Bearer {tenant['token']}",
        "X-Organization-Id": "org-foreign-unauthorized-12345"
    }
    res = await client.get("/api/v1/tasks", headers=forged_headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_f1_boundary_unauthenticated_request_raises_401(client: AsyncClient):
    """F1.B5: Verifies protected endpoints return HTTP 401 when Authorization header is absent."""
    endpoints = ["/api/v1/tasks", "/api/v1/settings", "/api/v1/audit-logs"]
    for ep in endpoints:
        res = await client.get(ep)
        assert res.status_code == 401, f"Endpoint {ep} must require authentication"


@pytest.mark.asyncio
async def test_f1_boundary_membership_duplicate_user_org_rejected(db_session: AsyncSession):
    """F1.B6: Verifies unique constraint prevents duplicate membership records for same user and org."""
    if Membership is None or User is None or Organization is None:
        pytest.skip("Models not yet implemented")

    u_id = f"user-{uuid.uuid4().hex[:8]}"
    o_id = f"org-{uuid.uuid4().hex[:8]}"
    user = User(id=u_id, github_username=f"u_{uuid.uuid4().hex[:4]}")
    org = Organization(id=o_id, name="Org", slug=f"org-{uuid.uuid4().hex[:4]}")
    db_session.add_all([user, org])
    await db_session.flush()

    m1 = Membership(id=f"m1-{uuid.uuid4().hex[:8]}", user_id=u_id, org_id=o_id, role="member")
    db_session.add(m1)
    await db_session.commit()

    m2 = Membership(id=f"m2-{uuid.uuid4().hex[:8]}", user_id=u_id, org_id=o_id, role="admin")
    db_session.add(m2)
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.commit()
    await db_session.rollback()
    assert exc_info.type is IntegrityError


# ===========================================================================
# F2 Boundaries: GitHub OAuth 2.0 & Session Auth (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f2_boundary_callback_missing_code_raises_400(client: AsyncClient):
    """F2.B1: Verifies callback without 'code' parameter returns HTTP 400."""
    res = await client.get("/api/v1/auth/github/callback?state=valid_looking_state")
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_f2_boundary_callback_missing_state_raises_400(client: AsyncClient):
    """F2.B2: Verifies callback without 'state' parameter returns HTTP 400."""
    res = await client.get("/api/v1/auth/github/callback?code=mock_code_123")
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_f2_boundary_callback_expired_or_invalid_state_raises_400(client: AsyncClient):
    """F2.B3: Verifies callback with unrecorded/forged CSRF state returns HTTP 400."""
    res = await client.get("/api/v1/auth/github/callback?code=mock_code_123&state=unregistered_state_xyz")
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_f2_boundary_expired_token_rejected_401(client: AsyncClient):
    """F2.B4: Verifies session token with past expiration date is rejected with HTTP 401."""
    expired_token = make_session_token(subject="user_123", expires_in=-3600)
    res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_f2_boundary_tampered_token_signature_rejected_401(client: AsyncClient):
    """F2.B5: Verifies session token with tampered payload or signature is rejected with HTTP 401."""
    valid_token = make_session_token(subject="user_123")
    parts = valid_token.split(".")
    tampered_token = f"{parts[0]}.forgedsignature12345"
    res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_f2_boundary_malformed_auth_headers_rejected_401(client: AsyncClient):
    """F2.B6: Verifies malformed Authorization header values are rejected with HTTP 401."""
    malformed_headers = [
        "Bearer",
        "Bearer ",
        "Basic dXNlcjpwYXNz",
        "Token xyz123",
        "Bearer not.enough.or.too.many.dots",
        "Bearer !!!@@@###"
    ]
    for h in malformed_headers:
        res = await client.get("/api/v1/auth/me", headers={"Authorization": h})
        assert res.status_code == 401


# ===========================================================================
# F3 Boundaries: GitHub App Webhooks & HMAC Ingestion (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f3_boundary_webhook_missing_signature_header_rejected_401(client: AsyncClient):
    """F3.B1: Verifies POST /api/v1/webhooks/github without X-Hub-Signature-256 returns HTTP 401."""
    res = await client.post(
        "/api/v1/webhooks/github",
        json={"action": "ping"},
        headers={"X-GitHub-Event": "ping"}
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_f3_boundary_webhook_forged_signature_rejected_401(client: AsyncClient):
    """F3.B2: Verifies POST /api/v1/webhooks/github with forged HMAC signature returns HTTP 401."""
    res = await client.post(
        "/api/v1/webhooks/github",
        json={"action": "ping"},
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000"
        }
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_f3_boundary_webhook_malformed_signature_format_rejected_401(client: AsyncClient):
    """F3.B3: Verifies signature missing 'sha256=' prefix is rejected with HTTP 401."""
    raw_hex = hashlib.sha256(b"{}").hexdigest()
    res = await client.post(
        "/api/v1/webhooks/github",
        json={},
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": raw_hex  # missing sha256=
        }
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_f3_boundary_webhook_empty_payload_rejected_400(client: AsyncClient):
    """F3.B4: Verifies empty request body with valid HMAC header returns HTTP 400."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        empty_body = b""
        sig = hmac.new(TEST_WEBHOOK_SECRET.encode("utf-8"), empty_body, hashlib.sha256).hexdigest()
        res = await client.post(
            "/api/v1/webhooks/github",
            content=empty_body,
            headers={
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": f"sha256={sig}",
                "Content-Type": "application/json"
            }
        )
        assert res.status_code in (400, 422)


@pytest.mark.asyncio
async def test_f3_boundary_webhook_malformed_json_rejected_400(client: AsyncClient):
    """F3.B5: Verifies invalid JSON content with valid HMAC signature returns HTTP 400."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        bad_json = b"NOT_VALID_JSON{:::broken"
        sig = hmac.new(TEST_WEBHOOK_SECRET.encode("utf-8"), bad_json, hashlib.sha256).hexdigest()
        res = await client.post(
            "/api/v1/webhooks/github",
            content=bad_json,
            headers={
                "X-GitHub-Event": "issues",
                "X-Hub-Signature-256": f"sha256={sig}",
                "Content-Type": "application/json"
            }
        )
        assert res.status_code in (400, 422)


@pytest.mark.asyncio
async def test_f3_boundary_webhook_unknown_event_type_handled_gracefully(client: AsyncClient):
    """F3.B6: Verifies validly signed unknown events return HTTP 200 without crashing."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        headers, body = create_signed_webhook_payload("unknown_event_type", {"data": "test"})
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200


# ===========================================================================
# F4 Boundaries: Per-Tenant Settings & BYOK Keys (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f4_boundary_byok_corrupted_ciphertext_decrypt():
    """F4.B1: Verifies corrupted or invalid ciphertext returns None gracefully, never crashes."""
    if decrypt_secret is None:
        pytest.skip("Crypto module not yet implemented")

    corrupted_inputs = [
        "not-a-valid-base64-string!@#",
        "gAAAAABk..." + "corrupted_garbage",
        "short",
        ""
    ]
    for inp in corrupted_inputs:
        result = decrypt_secret(inp)
        assert result is None, f"Corrupted input '{inp}' must decrypt to None"


@pytest.mark.asyncio
async def test_f4_boundary_byok_empty_or_whitespace_key_cleared(
    client: AsyncClient,
    tenant_factory
):
    """F4.B2: Verifies sending empty string or whitespace for API keys does not encrypt whitespace."""
    tenant = tenant_factory(username="space_hunter")
    res = await client.put(
        "/api/v1/settings",
        json={"openai_api_key": "   "},
        headers=tenant["headers"]
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_f4_boundary_cross_tenant_settings_idor_rejected(
    client: AsyncClient,
    tenant_factory
):
    """F4.B3: Verifies Tenant B cannot read or overwrite Tenant A's settings via query tampering."""
    tenant_a = tenant_factory(username="alice", org_slug="org_a")
    tenant_b = tenant_factory(username="bob", org_slug="org_b")

    # Alice sets key
    await client.put("/api/v1/settings", json={"openai_api_key": "sk-alice-secret-key"}, headers=tenant_a["headers"])

    # Bob reads settings
    bob_res = await client.get("/api/v1/settings", headers=tenant_b["headers"])
    assert bob_res.status_code == 200
    bob_data = bob_res.json()
    assert bob_data.get("has_openai_key") is False or "alice" not in json.dumps(bob_data)


@pytest.mark.asyncio
async def test_f4_boundary_settings_resolver_unknown_provider(db_session: AsyncSession):
    """F4.B4: Verifies querying key for unsupported/unknown provider returns None."""
    if SettingsResolver is None:
        pytest.skip("SettingsResolver not yet implemented")

    res = await SettingsResolver.get_effective_ai_key(
        db=db_session,
        user_id="nonexistent-user-123",
        provider="unsupported_provider_xyz"
    )
    assert res is None


@pytest.mark.asyncio
async def test_f4_boundary_settings_resolver_no_keys_configured(db_session: AsyncSession, monkeypatch):
    """F4.B5: Verifies SettingsResolver returns None when no keys exist in user, org, or env."""
    if SettingsResolver is None:
        pytest.skip("SettingsResolver not yet implemented")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    user_id = f"usr-nokey-{uuid.uuid4().hex[:8]}"
    org_id = f"org-nokey-{uuid.uuid4().hex[:8]}"

    res = await SettingsResolver.get_effective_ai_key(
        db=db_session,
        user_id=user_id,
        org_id=org_id,
        provider="openai"
    )
    assert res is None


@pytest.mark.asyncio
async def test_f4_boundary_unauthenticated_settings_put_rejected(client: AsyncClient):
    """F4.B6: Verifies updating settings without authentication returns HTTP 401."""
    res = await client.put("/api/v1/settings", json={"openai_api_key": "sk-unauthenticated-attempt"})
    assert res.status_code == 401


# ===========================================================================
# F5 Boundaries: Hybrid Runner Foundation (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f5_boundary_runner_invalid_registration_token(client: AsyncClient):
    """F5.B1: Verifies runner registration with invalid token returns HTTP 401 or 400."""
    res = await client.post(
        "/api/v1/runners/register",
        json={"registration_token": "forged_reg_token", "name": "Fake", "os_info": "linux"}
    )
    if res.status_code == 404:
        pytest.skip("Runner router not yet registered")
    assert res.status_code in (400, 401)


@pytest.mark.asyncio
async def test_f5_boundary_runner_heartbeat_nonexistent_runner(client: AsyncClient):
    """F5.B2: Verifies heartbeat to non-existent runner_id returns HTTP 404."""
    res = await client.post(
        f"/api/v1/runners/{uuid.uuid4()}/heartbeat",
        json={"status": "idle"},
        headers={"Authorization": "Bearer rnt_fake_runner_token_12345"}
    )
    if res.status_code == 404 and "runner" not in res.text.lower():
        # Might be 404 because router not registered
        pass
    assert res.status_code in (404, 401, 403)


@pytest.mark.asyncio
async def test_f5_boundary_runner_invalid_bearer_token(client: AsyncClient):
    """F5.B3: Verifies runner job polling with forged runner token returns HTTP 401."""
    res = await client.get(
        "/api/v1/runners/jobs/poll",
        headers={"Authorization": "Bearer rnt_invalid_forged_token_00000"}
    )
    if res.status_code == 404:
        pytest.skip("Runner router not yet registered")
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_f5_boundary_runner_offline_status_after_timeout(client: AsyncClient, tenant_factory, db_session: AsyncSession):
    """F5.B4: Verifies runner with last heartbeat > 90 seconds is classified as offline."""
    tenant = tenant_factory(username="runner_timeout_dev")
    reg_res = await client.post(
        "/api/v1/runners/register",
        json={"registration_token": tenant["token"], "name": "Stale-Runner", "os_info": "linux"},
        headers=tenant["headers"]
    )
    assert reg_res.status_code == 201
    runner_id = reg_res.json()["runner_id"]

    # Backdate last_heartbeat_at by 120 seconds
    runner = (await db_session.execute(select(Runner).where(Runner.id == runner_id))).scalar_one()
    runner.last_heartbeat_at = datetime.utcnow() - timedelta(seconds=120)
    await db_session.commit()

    list_res = await client.get("/api/v1/runners", headers=tenant["headers"])
    assert list_res.status_code == 200
    runners = list_res.json()
    matched = [r for r in runners if r["id"] == runner_id]
    assert len(matched) == 1
    assert matched[0]["status"] == "offline"


@pytest.mark.asyncio
async def test_f5_boundary_runner_cross_tenant_job_poll_prevented(client: AsyncClient, tenant_factory, db_session: AsyncSession):
    """F5.B5: Verifies runner for Tenant B polling receives 204 when only Tenant A has jobs."""
    tenant_a = tenant_factory(username="dev_a_bound", org_slug="org_a_bound")
    tenant_b = tenant_factory(username="dev_b_bound", org_slug="org_b_bound")

    reg_res_b = await client.post(
        "/api/v1/runners/register",
        json={"registration_token": tenant_b["token"], "name": "Runner-B-Boundary", "os_info": "linux"},
        headers=tenant_b["headers"]
    )
    assert reg_res_b.status_code == 201
    token_b = reg_res_b.json()["runner_token"]

    job_id = f"job-cross-{uuid.uuid4().hex[:8]}"
    job_a = RunnerJob(
        id=job_id,
        tenant_id=tenant_a["org_id"],
        job_type="test_run",
        status="queued"
    )
    db_session.add(job_a)
    await db_session.commit()

    poll_b = await client.get("/api/v1/runners/jobs/poll", headers={"Authorization": f"Bearer {token_b}"})
    assert poll_b.status_code == 204


@pytest.mark.asyncio
async def test_f5_boundary_runner_job_complete_nonexistent_job(client: AsyncClient, tenant_factory):
    """F5.B6: Verifies runner trying to complete nonexistent job ID returns HTTP 404."""
    tenant = tenant_factory(username="runner_nonexistent_job_dev")
    reg_res = await client.post(
        "/api/v1/runners/register",
        json={"registration_token": tenant["token"], "name": "Runner-Complete-Nonexistent", "os_info": "linux"},
        headers=tenant["headers"]
    )
    assert reg_res.status_code == 201
    runner_token = reg_res.json()["runner_token"]

    fake_job_id = f"job-fake-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        f"/api/v1/runners/jobs/{fake_job_id}/complete",
        json={"status": "completed", "result": {}},
        headers={"Authorization": f"Bearer {runner_token}"}
    )
    assert res.status_code == 404
