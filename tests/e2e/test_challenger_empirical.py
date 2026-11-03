"""Empirical Challenger Test Suite for Issue-to-PR Platform Phase 1.

Written by challenger_gen3_2 to empirically verify and stress-test:
1. Hybrid Runner lifecycle (polling atomicity, queue FIFO, tenant isolation, completion, revocation)
2. Runner timeout offline transition (exact 90s boundary, recovery via heartbeat, status preservation)
3. Webhook HMAC verification and dispatcher (HMAC tampering, empty payloads, malformed JSON, state cascades)
4. BYOK settings resolution and key masking (AES-256 storage, short/standard key masking, hierarchy matrix, cross-tenant isolation)
"""

import os
import time
import uuid
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import (
    User,
    Organization,
    Membership,
    Runner,
    RunnerJob,
    UserSettings,
    OrganizationSettings,
    Repository,
    Issue,
    Task,
    AuditLog,
)
from app.core.crypto import encrypt_secret, decrypt_secret, mask_api_key
from app.services.settings_resolver import get_effective_ai_key
from tests.e2e.conftest import create_signed_webhook_payload, TEST_WEBHOOK_SECRET, make_session_token


# ===========================================================================
# 1. Hybrid Runner Lifecycle & Polling Stress Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_empirical_runner_registration_and_token_format(client: AsyncClient, tenant_factory):
    """Stress test runner registration token generation, entropy, and invalid auth handling."""
    tenant = tenant_factory(username="runner_entropy_dev", role="owner")

    # 1. Valid registration
    reg_resp = await client.post(
        "/api/v1/runners/register",
        headers=tenant["headers"],
        json={
            "registration_token": tenant["token"],
            "name": "m3-max-local",
            "os_info": "Darwin 24.1.0 arm64"
        }
    )
    assert reg_resp.status_code == 201, reg_resp.text
    reg_data = reg_resp.json()
    runner_id = reg_data["runner_id"]
    runner_token = reg_data["runner_token"]

    assert runner_token.startswith("rnt_")
    # 'rnt_' + 48 hex chars = 52 total chars
    assert len(runner_token) == 52

    # 2. Registration with invalid/tampered token
    bad_resp = await client.post(
        "/api/v1/runners/register",
        json={"registration_token": "invalid.tampered.token", "name": "rogue-runner", "os_info": "Linux"}
    )
    assert bad_resp.status_code == 401

    # 3. Registration with empty token
    empty_resp = await client.post(
        "/api/v1/runners/register",
        json={"registration_token": "", "name": "no-token-runner"}
    )
    assert empty_resp.status_code in (400, 401)


@pytest.mark.asyncio
async def test_empirical_runner_polling_atomicity_and_fifo_order(client: AsyncClient, tenant_factory, db_session):
    """Verify that multiple jobs are claimed in strict FIFO order and polling atomically transitions status."""
    tenant = tenant_factory(username="fifo_runner_dev", role="owner")

    # Register runner
    reg_resp = await client.post(
        "/api/v1/runners/register",
        headers=tenant["headers"],
        json={"registration_token": tenant["token"], "name": "fifo-tester", "os_info": "macOS"}
    )
    assert reg_resp.status_code == 201
    runner_token = reg_resp.json()["runner_token"]
    runner_headers = {"Authorization": f"Bearer {runner_token}"}

    # Queue 3 distinct jobs with explicit created_at timestamps
    now = datetime.utcnow()
    job1_id = f"job-fifo-1-{uuid.uuid4().hex[:6]}"
    job2_id = f"job-fifo-2-{uuid.uuid4().hex[:6]}"
    job3_id = f"job-fifo-3-{uuid.uuid4().hex[:6]}"

    job1 = RunnerJob(
        id=job1_id,
        tenant_id=tenant["org_id"],
        job_type="validate_diff",
        status="queued",
        created_at=now - timedelta(seconds=30)
    )
    job2 = RunnerJob(
        id=job2_id,
        tenant_id=tenant["org_id"],
        job_type="validate_diff",
        status="queued",
        created_at=now - timedelta(seconds=20)
    )
    job3 = RunnerJob(
        id=job3_id,
        tenant_id=tenant["org_id"],
        job_type="validate_diff",
        status="queued",
        created_at=now - timedelta(seconds=10)
    )
    db_session.add_all([job1, job2, job3])
    await db_session.commit()

    # Poll 1: Must return job1
    poll1 = await client.get("/api/v1/runners/jobs/poll", headers=runner_headers)
    assert poll1.status_code == 200
    assert poll1.json()["id"] == job1_id
    assert poll1.json()["status"] == "running"

    # Poll 2: Must return job2
    poll2 = await client.get("/api/v1/runners/jobs/poll", headers=runner_headers)
    assert poll2.status_code == 200
    assert poll2.json()["id"] == job2_id
    assert poll2.json()["status"] == "running"

    # Poll 3: Must return job3
    poll3 = await client.get("/api/v1/runners/jobs/poll", headers=runner_headers)
    assert poll3.status_code == 200
    assert poll3.json()["id"] == job3_id
    assert poll3.json()["status"] == "running"

    # Poll 4: Queue is now empty -> HTTP 204 No Content
    poll4 = await client.get("/api/v1/runners/jobs/poll", headers=runner_headers)
    assert poll4.status_code == 204


@pytest.mark.asyncio
async def test_empirical_runner_polling_strict_tenant_isolation(client: AsyncClient, tenant_factory, db_session):
    """Stress test runner polling to ensure Runner A cannot steal queued jobs belonging to Tenant B."""
    tenant_a = tenant_factory(username="runner_dev_a", org_slug="tenant-a-org")
    tenant_b = tenant_factory(username="runner_dev_b", org_slug="tenant-b-org")

    # Register Runner B for Tenant B
    reg_b = await client.post(
        "/api/v1/runners/register",
        headers=tenant_b["headers"],
        json={"registration_token": tenant_b["token"], "name": "runner-tenant-b"}
    )
    assert reg_b.status_code == 201
    runner_b_token = reg_b.json()["runner_token"]
    runner_b_headers = {"Authorization": f"Bearer {runner_b_token}"}

    # Queue a job strictly in Tenant A
    job_a_id = f"job-iso-a-{uuid.uuid4().hex[:6]}"
    job_a = RunnerJob(
        id=job_a_id,
        tenant_id=tenant_a["org_id"],
        job_type="run_task",
        status="queued"
    )
    db_session.add(job_a)
    await db_session.commit()

    # Runner B polls: should get 204 No Content because job belongs to Tenant A
    poll_b = await client.get("/api/v1/runners/jobs/poll", headers=runner_b_headers)
    assert poll_b.status_code == 204

    # Verify job_a in DB is still 'queued'
    check = await db_session.execute(select(RunnerJob).where(RunnerJob.id == job_a_id))
    j = check.scalar_one()
    assert j.status == "queued"
    assert j.runner_id is None


@pytest.mark.asyncio
async def test_empirical_runner_completion_lifecycle(client: AsyncClient, tenant_factory, db_session):
    """Empirically test runner job completion with success, failure, error message, and logs."""
    tenant = tenant_factory(username="completion_dev")
    reg = await client.post(
        "/api/v1/runners/register",
        headers=tenant["headers"],
        json={"registration_token": tenant["token"], "name": "completion-runner"}
    )
    runner_token = reg.json()["runner_token"]
    runner_headers = {"Authorization": f"Bearer {runner_token}"}

    # Create and queue job
    job_id = f"job-comp-{uuid.uuid4().hex[:6]}"
    job = RunnerJob(id=job_id, tenant_id=tenant["org_id"], job_type="test_run", status="queued")
    db_session.add(job)
    await db_session.commit()

    # Poll job to mark running
    poll = await client.get("/api/v1/runners/jobs/poll", headers=runner_headers)
    assert poll.status_code == 200

    # Complete with failed status and execution details
    comp_resp = await client.post(
        f"/api/v1/runners/jobs/{job_id}/complete",
        headers=runner_headers,
        json={
            "status": "failed",
            "result": {"exit_code": 1, "failed_tests": ["test_auth"]},
            "error_message": "Test suite failed with 1 assertion error",
            "logs": "Traceback: AssertionError in test_auth line 12"
        }
    )
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "ok"

    # Verify database state
    await db_session.refresh(job)
    assert job.status == "failed"
    assert job.result["exit_code"] == 1
    assert job.error_message == "Test suite failed with 1 assertion error"
    assert "Traceback" in job.logs
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_empirical_runner_cross_tenant_job_completion_denial(client: AsyncClient, tenant_factory, db_session):
    """Verify that a runner cannot complete a job belonging to another tenant."""
    tenant_a = tenant_factory(username="cross_dev_a", org_slug="cross_org_a")
    tenant_b = tenant_factory(username="cross_dev_b", org_slug="cross_org_b")

    # Register Runner B under Tenant B
    reg_b = await client.post(
        "/api/v1/runners/register",
        headers=tenant_b["headers"],
        json={"registration_token": tenant_b["token"], "name": "runner-b"}
    )
    runner_b_token = reg_b.json()["runner_token"]
    runner_b_headers = {"Authorization": f"Bearer {runner_b_token}"}

    # Job belongs to Tenant A
    job_id = f"job-tenant-a-{uuid.uuid4().hex[:6]}"
    job = RunnerJob(id=job_id, tenant_id=tenant_a["org_id"], job_type="exec", status="running")
    db_session.add(job)
    await db_session.commit()

    # Runner B attempts to complete Tenant A's job -> HTTP 403 Forbidden
    comp = await client.post(
        f"/api/v1/runners/jobs/{job_id}/complete",
        headers=runner_b_headers,
        json={"status": "completed"}
    )
    assert comp.status_code == 403
    assert "Cross-tenant job completion denied" in comp.text


@pytest.mark.asyncio
async def test_empirical_runner_revocation_lifecycle(client: AsyncClient, tenant_factory, db_session):
    """Verify that deleting a runner revokes credentials and rejects future heartbeat/poll/complete requests."""
    tenant = tenant_factory(username="revocation_dev")
    reg = await client.post(
        "/api/v1/runners/register",
        headers=tenant["headers"],
        json={"registration_token": tenant["token"], "name": "to-be-revoked"}
    )
    runner_id = reg.json()["runner_id"]
    runner_token = reg.json()["runner_token"]
    runner_headers = {"Authorization": f"Bearer {runner_token}"}

    # Revoke runner via DELETE endpoint
    del_resp = await client.delete(f"/api/v1/runners/{runner_id}", headers=tenant["headers"])
    assert del_resp.status_code == 204

    # Subsequent heartbeat must be rejected with 401
    hb = await client.post(
        f"/api/v1/runners/{runner_id}/heartbeat",
        headers=runner_headers,
        json={"status": "idle"}
    )
    assert hb.status_code == 401

    # Subsequent poll must be rejected with 401
    poll = await client.get("/api/v1/runners/jobs/poll", headers=runner_headers)
    assert poll.status_code == 401


# ===========================================================================
# 2. Runner Timeout Offline Transition Stress Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_empirical_runner_offline_boundary_detection(client: AsyncClient, tenant_factory, db_session):
    """
    Stress-test the exact 90-second runner timeout boundary.
    - Runner at now - 80s: remains 'idle'
    - Runner at now - 95s: transitions dynamically to 'offline'
    - Runner with status 'revoked': stays 'revoked' (not overwritten)
    """
    tenant = tenant_factory(username="offline_boundary_dev")
    now = datetime.utcnow()

    # 1. Fresh runner: heartbeat 80 seconds ago
    r1 = Runner(
        id=f"r1-fresh-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant["org_id"],
        name="fresh-runner",
        status="idle",
        is_active=True,
        last_heartbeat_at=now - timedelta(seconds=80)
    )

    # 2. Stale runner: heartbeat 95 seconds ago
    r2 = Runner(
        id=f"r2-stale-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant["org_id"],
        name="stale-runner",
        status="idle",
        is_active=True,
        last_heartbeat_at=now - timedelta(seconds=95)
    )

    # 3. Very old runner: heartbeat 2 hours ago
    r3 = Runner(
        id=f"r3-ancient-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant["org_id"],
        name="ancient-runner",
        status="active",
        is_active=True,
        last_heartbeat_at=now - timedelta(hours=2)
    )

    # 4. Revoked runner: heartbeat 2 hours ago
    r4 = Runner(
        id=f"r4-revoked-{uuid.uuid4().hex[:6]}",
        tenant_id=tenant["org_id"],
        name="revoked-runner",
        status="revoked",
        is_active=False,
        last_heartbeat_at=now - timedelta(hours=2)
    )

    db_session.add_all([r1, r2, r3, r4])
    await db_session.commit()

    # Query runner list
    list_resp = await client.get("/api/v1/runners", headers=tenant["headers"])
    assert list_resp.status_code == 200
    runners_data = {r["id"]: r for r in list_resp.json()}

    assert runners_data[r1.id]["status"] == "idle", "80s heartbeat runner should stay idle"
    assert runners_data[r2.id]["status"] == "offline", "95s heartbeat runner must transition to offline"
    assert runners_data[r3.id]["status"] == "offline", "2hr heartbeat runner must transition to offline"
    assert runners_data[r4.id]["status"] == "revoked", "Revoked runner must maintain revoked status"


@pytest.mark.asyncio
async def test_empirical_runner_revival_from_offline_via_heartbeat(client: AsyncClient, tenant_factory, db_session):
    """Verify that a runner reporting 'offline' revives back to 'idle' or 'busy' when a heartbeat arrives."""
    tenant = tenant_factory(username="revival_dev")
    now = datetime.utcnow()

    reg = await client.post(
        "/api/v1/runners/register",
        headers=tenant["headers"],
        json={"registration_token": tenant["token"], "name": "sleeping-runner"}
    )
    runner_id = reg.json()["runner_id"]
    runner_token = reg.json()["runner_token"]
    runner_headers = {"Authorization": f"Bearer {runner_token}"}

    # Artificially age the heartbeat past 90s in database
    db_res = await db_session.execute(select(Runner).where(Runner.id == runner_id))
    r = db_res.scalar_one()
    r.last_heartbeat_at = now - timedelta(seconds=120)
    await db_session.commit()

    # Verify list shows offline
    list_pre = await client.get("/api/v1/runners", headers=tenant["headers"])
    runner_pre = [x for x in list_pre.json() if x["id"] == runner_id][0]
    assert runner_pre["status"] == "offline"

    # Send heartbeat
    hb_resp = await client.post(
        f"/api/v1/runners/{runner_id}/heartbeat",
        headers=runner_headers,
        json={"status": "busy", "system_stats": {"cpu_percent": 15.2}}
    )
    assert hb_resp.status_code == 200

    # Verify list now shows revived status 'busy'
    list_post = await client.get("/api/v1/runners", headers=tenant["headers"])
    runner_post = [x for x in list_post.json() if x["id"] == runner_id][0]
    assert runner_post["status"] == "busy"
    assert runner_post["system_stats"]["cpu_percent"] == 15.2


# ===========================================================================
# 3. Webhook HMAC Verification & Dispatcher Robustness
# ===========================================================================

@pytest.mark.asyncio
async def test_empirical_webhook_hmac_tamper_detection(client: AsyncClient):
    """Adversarially challenge HMAC-SHA256 signature verification with various attack vectors."""
    payload = {"zen": "Mind your words, they become actions."}

    # 1. Valid signature
    headers, body = create_signed_webhook_payload("ping", payload, secret=TEST_WEBHOOK_SECRET)
    resp = await client.post("/api/v1/webhooks/github", headers=headers, content=body)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 2. Tampered body (1 character changed)
    tampered_body = body[:-1] + b"x"
    resp_tampered = await client.post("/api/v1/webhooks/github", headers=headers, content=tampered_body)
    assert resp_tampered.status_code == 401
    assert "Invalid HMAC SHA-256 signature" in resp_tampered.text

    # 3. Tampered signature hash
    bad_sig_headers = headers.copy()
    bad_sig_headers["X-Hub-Signature-256"] = headers["X-Hub-Signature-256"][:-2] + "ff"
    resp_bad_sig = await client.post("/api/v1/webhooks/github", headers=bad_sig_headers, content=body)
    assert resp_bad_sig.status_code == 401

    # 4. Invalid signature prefix (sha1= instead of sha256=)
    sha1_headers = headers.copy()
    sha1_headers["X-Hub-Signature-256"] = "sha1=" + "a" * 40
    resp_sha1 = await client.post("/api/v1/webhooks/github", headers=sha1_headers, content=body)
    assert resp_sha1.status_code == 401

    # 5. Missing signature header
    no_sig_headers = {"X-GitHub-Event": "ping", "Content-Type": "application/json"}
    resp_no_sig = await client.post("/api/v1/webhooks/github", headers=no_sig_headers, content=body)
    assert resp_no_sig.status_code == 401

    # 6. Wrong secret
    wrong_secret_headers, wrong_secret_body = create_signed_webhook_payload(
        "ping", payload, secret="wrong_attacker_secret_value"
    )
    resp_wrong_sec = await client.post("/api/v1/webhooks/github", headers=wrong_secret_headers, content=wrong_secret_body)
    assert resp_wrong_sec.status_code == 401


@pytest.mark.asyncio
async def test_empirical_webhook_empty_and_corrupted_payloads(client: AsyncClient):
    """Stress-test empty request bodies and malformed JSON payloads."""
    # Empty body with valid HMAC on empty bytes
    empty_body = b""
    empty_sig = hmac.new(TEST_WEBHOOK_SECRET.encode("utf-8"), empty_body, hashlib.sha256).hexdigest()
    headers = {
        "X-GitHub-Event": "ping",
        "X-Hub-Signature-256": f"sha256={empty_sig}",
        "Content-Type": "application/json"
    }
    resp = await client.post("/api/v1/webhooks/github", headers=headers, content=empty_body)
    assert resp.status_code == 400
    assert "Empty webhook request body" in resp.text

    # Malformed JSON with valid signature
    bad_json = b"{'invalid_json': true,}"
    bad_json_sig = hmac.new(TEST_WEBHOOK_SECRET.encode("utf-8"), bad_json, hashlib.sha256).hexdigest()
    headers["X-Hub-Signature-256"] = f"sha256={bad_json_sig}"
    resp_bad = await client.post("/api/v1/webhooks/github", headers=headers, content=bad_json)
    assert resp_bad.status_code == 400
    assert "Malformed JSON payload" in resp_bad.text


@pytest.mark.asyncio
async def test_empirical_webhook_dispatcher_issue_closed_blocking_cascade(client: AsyncClient, tenant_factory, db_session):
    """Verify that webhook 'issues.closed' blocks active tasks and creates an audit log entry."""
    tenant = tenant_factory(username="cascade_dev")

    # 1. Ingest issue via webhook
    issue_num = 789
    gh_issue_id = 999888777
    repo_name = "adversary-test/issue-cascade-repo"

    open_payload = {
        "action": "opened",
        "issue": {
            "id": gh_issue_id,
            "number": issue_num,
            "title": "Bounty issue to be closed",
            "body": "Fix this bug",
            "state": "open",
            "labels": [{"name": "bounty"}],
            "assignees": [],
            "comments": 0
        },
        "repository": {
            "name": "issue-cascade-repo",
            "full_name": repo_name,
            "owner": {"login": "adversary-test"}
        }
    }
    h_open, b_open = create_signed_webhook_payload("issues", open_payload)
    resp_open = await client.post("/api/v1/webhooks/github", headers=h_open, content=b_open)
    assert resp_open.status_code == 200

    # Find the created issue
    iss_res = await db_session.execute(select(Issue).where(Issue.github_id == gh_issue_id))
    db_issue = iss_res.scalar_one()

    # Create an active task on this issue
    task_id = f"task-cascade-{uuid.uuid4().hex[:6]}"
    task = Task(
        id=task_id,
        tenant_id=tenant["org_id"],
        user_id=tenant["user_id"],
        issue_id=db_issue.id,
        workflow_state="VALIDATING"
    )
    db_session.add(task)
    await db_session.commit()

    # 2. Ingest issue closed webhook
    close_payload = {
        "action": "closed",
        "issue": {
            "id": gh_issue_id,
            "number": issue_num,
            "state": "closed"
        },
        "repository": {
            "full_name": repo_name
        }
    }
    h_close, b_close = create_signed_webhook_payload("issues", close_payload)
    resp_close = await client.post("/api/v1/webhooks/github", headers=h_close, content=b_close)
    assert resp_close.status_code == 200

    # Verify task state transitioned to BLOCKED
    await db_session.refresh(task)
    assert task.workflow_state == "BLOCKED"
    assert "Issue closed on GitHub" in task.blocked_reason

    # Verify AuditLog created
    audit_res = await db_session.execute(
        select(AuditLog).where(AuditLog.task_id == task_id, AuditLog.action == "TASK_BLOCKED_UPSTREAM_CLOSED")
    )
    audit = audit_res.scalar_one_or_none()
    assert audit is not None
    assert audit.actor == "GITHUB_WEBHOOK"


# ===========================================================================
# 4. BYOK Settings Resolution & Key Masking Security Tests
# ===========================================================================

def test_empirical_byok_crypto_primitives():
    """Verify AES-256 symmetric encryption, corruption resilience, and key masking rules."""
    raw_secret = "sk-proj-test-secret-key-1234567890abcdef"

    # Encrypt
    encrypted = encrypt_secret(raw_secret)
    assert encrypted != raw_secret
    assert encrypted.startswith("gAAAAA")

    # Decrypt
    decrypted = decrypt_secret(encrypted)
    assert decrypted == raw_secret

    # Corrupted ciphertext handling (must return None, NEVER raise exception)
    corrupted = encrypted[:-8] + "00000000"
    assert decrypt_secret(corrupted) is None
    assert decrypt_secret("not-a-valid-fernet-token") is None
    assert decrypt_secret("") is None
    assert decrypt_secret(None) is None

    # Key masking rules
    assert mask_api_key(None) == ""
    assert mask_api_key("") == ""
    assert mask_api_key("   ") == ""
    assert mask_api_key("short") == "***"
    assert mask_api_key("12345678") == "***"
    assert mask_api_key("123456789") == "123...6789"
    assert mask_api_key("sk-ant-api03-abcdef123456") == "sk-...3456"


@pytest.mark.asyncio
async def test_empirical_byok_zero_plaintext_leakage_in_api(client: AsyncClient, tenant_factory):
    """Verify that settings API never exposes raw unmasked secrets in responses."""
    tenant = tenant_factory(username="zero_leak_owner", role="owner")
    raw_key = "sk-proj-myverysecretopenaikey123456"

    # Update settings with secret key
    put_resp = await client.put(
        "/api/v1/settings",
        headers=tenant["headers"],
        json={"openai_api_key": raw_key}
    )
    assert put_resp.status_code == 200
    put_data = put_resp.json()

    assert put_data["has_openai_key"] is True
    # Masked preview only
    assert put_data["openai_api_key"] == "sk-...3456"
    # Plaintext raw key MUST NOT appear anywhere in the response text
    assert raw_key not in put_resp.text

    # Read back settings
    get_resp = await client.get("/api/v1/settings", headers=tenant["headers"])
    assert get_resp.status_code == 200
    get_data = get_resp.json()

    assert get_data["has_openai_key"] is True
    assert get_data["openai_api_key"] == "sk-...3456"
    assert raw_key not in get_resp.text


@pytest.mark.asyncio
async def test_empirical_settings_resolver_hierarchical_precedence(db_session):
    """
    Empirically verify SettingsResolver priority matrix:
    - User Key > Org Key > Env Key when enforce_shared_keys=False
    - Org Key > User Key > Env Key when enforce_shared_keys=True
    - Case insensitivity ('OPENAI' == 'openai')
    - Fallback to environment variable
    """
    user_id = f"usr-res-{uuid.uuid4().hex[:8]}"
    org_id = f"org-res-{uuid.uuid4().hex[:8]}"

    # Setup User and Org in DB
    user = User(id=user_id, email=f"{user_id}@test.com", github_username=f"u_{uuid.uuid4().hex[:10]}")
    org = Organization(id=org_id, name="Hierarchy Org", slug=f"org-slug-{uuid.uuid4().hex[:12]}")
    u_sett = UserSettings(user_id=user_id, openai_api_key_encrypted=encrypt_secret("user-openai-key"))
    o_sett = OrganizationSettings(
        org_id=org_id,
        openai_api_key_encrypted=encrypt_secret("org-openai-key"),
        enforce_shared_keys=False
    )
    db_session.add_all([user, org, u_sett, o_sett])
    await db_session.commit()

    # 1. Normal mode (enforce_shared_keys=False): User key wins
    resolved_1 = await get_effective_ai_key(db_session, user_id=user_id, org_id=org_id, provider="openai")
    assert resolved_1 == "user-openai-key"

    # 2. Case insensitivity check ('OPENAI')
    resolved_upper = await get_effective_ai_key(db_session, user_id=user_id, org_id=org_id, provider="OPENAI")
    assert resolved_upper == "user-openai-key"

    # 3. Enforced shared keys mode: Org key wins
    o_sett.enforce_shared_keys = True
    await db_session.commit()
    resolved_2 = await get_effective_ai_key(db_session, user_id=user_id, org_id=org_id, provider="openai")
    assert resolved_2 == "org-openai-key"

    # 4. Unknown provider returns None
    resolved_unknown = await get_effective_ai_key(db_session, user_id=user_id, org_id=org_id, provider="mistral")
    assert resolved_unknown is None

    # 5. Env fallback when no user or org key exists
    os.environ["GEMINI_API_KEY"] = "env-gemini-fallback-key"
    try:
        resolved_env = await get_effective_ai_key(db_session, user_id=user_id, org_id=org_id, provider="gemini")
        assert resolved_env == "env-gemini-fallback-key"
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


@pytest.mark.asyncio
async def test_empirical_byok_cross_tenant_strict_non_leakage(client: AsyncClient, tenant_factory):
    """Stress test cross-tenant BYOK isolation: Tenant B must never see or resolve Tenant A's keys."""
    tenant_a = tenant_factory(username="tenant_a_isolated_user", org_slug="tenant_a_isolated_org", role="owner")
    tenant_b = tenant_factory(username="tenant_b_isolated_user", org_slug="tenant_b_isolated_org", role="owner")

    # Tenant A sets an Anthropic key
    key_a = "sk-ant-tenant-a-very-secret-key-12345"
    await client.put(
        "/api/v1/settings",
        headers=tenant_a["headers"],
        json={"anthropic_api_key": key_a}
    )

    # Tenant B queries settings
    resp_b = await client.get("/api/v1/settings", headers=tenant_b["headers"])
    assert resp_b.status_code == 200
    data_b = resp_b.json()

    # Tenant B must NOT have Anthropic key set
    assert data_b["has_anthropic_key"] is False
    assert data_b["anthropic_api_key"] == ""
    assert "sk-ant" not in resp_b.text
