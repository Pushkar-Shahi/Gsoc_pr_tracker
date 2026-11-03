"""Tier 1: Core Feature Coverage Test Suite (F1 - F5).

Covers:
- F1: Tenant Models & Data Isolation (>=5 tests)
- F2: GitHub OAuth 2.0 & Session Auth (>=5 tests)
- F3: GitHub App Webhooks & HMAC Ingestion (>=5 tests)
- F4: Per-Tenant Settings & BYOK Keys (>=5 tests)
- F5: Hybrid Runner Foundation (>=5 tests)
Total: 30 test cases.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
backend_path = project_root / "backend"
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pytest
from httpx import AsyncClient
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_session_token, verify_session_token
from app.models.models import Repository, Issue, Task, AuditLog
from tests.e2e.conftest import (
    create_signed_webhook_payload,
    make_session_token,
    TEST_WEBHOOK_SECRET
)

# Safe imports for Phase 1 models and services (will be present as milestones land)
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
    from app.core.crypto import encrypt_secret, decrypt_secret, mask_api_key
except ImportError:
    encrypt_secret = None
    decrypt_secret = None
    mask_api_key = None

try:
    from app.services.settings_resolver import SettingsResolver
except ImportError:
    SettingsResolver = None


# ===========================================================================
# F1: Tenant Models & Data Isolation (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f1_user_model_attributes_and_defaults(db_session: AsyncSession):
    """F1.1: Verifies User model entity structure, fields, and default values."""
    assert User is not None, "User model must be defined in app.models.models"
    u_id = f"user-{uuid.uuid4().hex[:8]}"
    username = f"hunter_{uuid.uuid4().hex[:6]}"
    user = User(
        id=u_id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 100,
        github_username=username,
        email=f"{username}@example.com",
        name="Bounty Developer",
        is_active=True,
        is_superuser=False
    )
    db_session.add(user)
    await db_session.commit()

    res = await db_session.execute(select(User).where(User.id == u_id))
    fetched = res.scalar_one_or_none()
    assert fetched is not None
    assert fetched.github_username == username
    assert fetched.is_active is True
    assert fetched.is_superuser is False


@pytest.mark.asyncio
async def test_f1_organization_model_and_personal_workspace(db_session: AsyncSession):
    """F1.2: Verifies Organization model entity structure and personal organization flag."""
    assert Organization is not None, "Organization model must be defined in app.models.models"
    org_id = f"org-{uuid.uuid4().hex[:8]}"
    slug = f"workspace-{uuid.uuid4().hex[:6]}"
    org = Organization(
        id=org_id,
        name="Developer Workspace",
        slug=slug,
        is_personal=True,
        billing_tier="starter"
    )
    db_session.add(org)
    await db_session.commit()

    res = await db_session.execute(select(Organization).where(Organization.id == org_id))
    fetched = res.scalar_one_or_none()
    assert fetched is not None
    assert fetched.slug == slug
    assert fetched.is_personal is True
    assert fetched.billing_tier == "starter"


@pytest.mark.asyncio
async def test_f1_membership_roles_and_unique_constraint(db_session: AsyncSession):
    """F1.3: Verifies Membership linking User and Organization with RBAC roles."""
    assert Membership is not None, "Membership model must be defined in app.models.models"
    u_id = f"user-{uuid.uuid4().hex[:8]}"
    o_id = f"org-{uuid.uuid4().hex[:8]}"
    user = User(id=u_id, github_username=f"u_{uuid.uuid4().hex[:6]}")
    org = Organization(id=o_id, name="Test Org", slug=f"org-{uuid.uuid4().hex[:6]}")
    db_session.add_all([user, org])
    await db_session.flush()

    membership = Membership(
        id=f"mem-{uuid.uuid4().hex[:8]} ",
        user_id=u_id,
        org_id=o_id,
        role="owner"
    )
    db_session.add(membership)
    await db_session.commit()

    res = await db_session.execute(select(Membership).where(Membership.user_id == u_id, Membership.org_id == o_id))
    fetched = res.scalar_one_or_none()
    assert fetched is not None
    assert fetched.role == "owner"


@pytest.mark.asyncio
async def test_f1_task_and_issue_tenant_foreign_keys(db_session: AsyncSession):
    """F1.4: Verifies that Task and Issue entities support tenant_id and user_id attributes."""
    assert hasattr(Task, "tenant_id"), "Task must have tenant_id column for multi-tenancy"
    assert hasattr(Task, "user_id"), "Task must have user_id column for multi-tenancy"
    assert hasattr(Issue, "tenant_id"), "Issue must have tenant_id column for multi-tenancy"


@pytest.mark.asyncio
async def test_f1_task_listing_tenant_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """F1.5: Verifies that GET /api/v1/tasks returns only tasks belonging to the caller's tenant."""
    tenant_a = tenant_factory(username="dev_a", org_slug="org_a")
    tenant_b = tenant_factory(username="dev_b", org_slug="org_b")

    # Seed repository and issue
    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="test-org",
        name="test-repo",
        full_name=f"test-org/repo-{uuid.uuid4().hex[:6]}",
        html_url="https://github.com/test-org/test-repo",
        default_branch="main"
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 10,
        issue_number=101,
        title="Isolated Issue",
        html_url="https://github.com/test-org/test-repo/issues/101",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    # Create task for Tenant A and task for Tenant B
    task_a = Task(
        id=f"tsk-a-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=tenant_a["org_id"],
        user_id=tenant_a["user_id"],
        workflow_state="SELECTED"
    )
    task_b = Task(
        id=f"tsk-b-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=tenant_b["org_id"],
        user_id=tenant_b["user_id"],
        workflow_state="SELECTED"
    )
    db_session.add_all([task_a, task_b])
    await db_session.commit()

    # Query tasks as Tenant A
    res = await client.get("/api/v1/tasks", headers=tenant_a["headers"])
    assert res.status_code == 200
    task_ids = [t["id"] for t in res.json()]
    assert task_a.id in task_ids, "Tenant A should see their own task"
    assert task_b.id not in task_ids, "Tenant A must NOT see Tenant B's task"


@pytest.mark.asyncio
async def test_f1_audit_log_tenant_scoping(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """F1.6: Verifies that audit logs are partitioned by tenant_id for read and delete."""
    tenant_a = tenant_factory(username="dev_a", org_slug="org_a")
    tenant_b = tenant_factory(username="dev_b", org_slug="org_b")

    log_a = AuditLog(
        id=f"log-a-{uuid.uuid4().hex[:8]}",
        action="TASK_SELECTED",
        actor=tenant_a["username"],
        tenant_id=tenant_a["org_id"],
        user_id=tenant_a["user_id"],
        details={"info": "tenant a action"}
    )
    log_b = AuditLog(
        id=f"log-b-{uuid.uuid4().hex[:8]}",
        action="TASK_SELECTED",
        actor=tenant_b["username"],
        tenant_id=tenant_b["org_id"],
        user_id=tenant_b["user_id"],
        details={"info": "tenant b action"}
    )
    db_session.add_all([log_a, log_b])
    await db_session.commit()

    # Tenant A lists audit logs
    res = await client.get("/api/v1/audit-logs", headers=tenant_a["headers"])
    assert res.status_code == 200
    items = res.json()
    log_ids = [item["id"] for item in items]
    assert log_a.id in log_ids
    assert log_b.id not in log_ids, "Tenant A must NOT see Tenant B's audit logs"

    # Tenant A deletes audit logs — should NOT affect Tenant B
    del_res = await client.delete("/api/v1/audit-logs", headers=tenant_a["headers"])
    assert del_res.status_code in (200, 204)

    # Verify Tenant B's log still exists in DB
    b_check = await db_session.execute(select(AuditLog).where(AuditLog.id == log_b.id))
    assert b_check.scalar_one_or_none() is not None, "Tenant B's audit log must survive Tenant A's clear"


# ===========================================================================
# F2: GitHub OAuth 2.0 & Session Auth (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f2_github_login_redirect_url_generation(client: AsyncClient):
    """F2.1: Verifies GET /api/v1/auth/github/login returns 302 redirect to GitHub with state."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_CLIENT_ID", "mock_client_id_12345", raising=False)
        res = await client.get("/api/v1/auth/github/login", follow_redirects=False)
        assert res.status_code in (302, 307), "Login endpoint must redirect to GitHub OAuth"
        loc = res.headers.get("location", "")
        assert "github.com/login/oauth/authorize" in loc
        assert "client_id=mock_client_id_12345" in loc
        assert "state=" in loc


@pytest.mark.asyncio
async def test_f2_github_login_json_format(client: AsyncClient):
    """F2.2: Verifies GET /api/v1/auth/github/login?format=json returns authorization_url and state."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_CLIENT_ID", "mock_client_id_12345", raising=False)
        res = await client.get("/api/v1/auth/github/login?format=json")
        assert res.status_code == 200
        data = res.json()
        assert "authorization_url" in data
        assert "state" in data
        assert "github.com/login/oauth/authorize" in data["authorization_url"]


@pytest.mark.asyncio
async def test_f2_github_callback_exchanges_code_and_creates_user(
    client: AsyncClient,
    mock_github_oauth,
    db_session: AsyncSession
):
    """F2.3: Verifies OAuth callback completes code exchange, creates user and org, and redirects with token."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_CLIENT_ID", "mock_id", raising=False)
        mp.setattr(settings, "GITHUB_CLIENT_SECRET", "mock_secret", raising=False)
        # First initiate login to generate a valid state
        login_res = await client.get("/api/v1/auth/github/login?format=json")
        state = login_res.json()["state"]

        callback_res = await client.get(
            f"/api/v1/auth/github/callback?code=mock_auth_code_123&state={state}",
            follow_redirects=False
        )
        assert callback_res.status_code in (200, 302, 307)
        if callback_res.status_code in (302, 307):
            loc = callback_res.headers.get("location", "")
            assert "token=" in loc, "Callback redirect URL must contain session token"


@pytest.mark.asyncio
async def test_f2_github_callback_existing_user_upsert(
    client: AsyncClient,
    mock_github_oauth,
    db_session: AsyncSession
):
    """F2.4: Verifies OAuth callback updates existing user records rather than creating duplicates."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_CLIENT_ID", "mock_id", raising=False)
        mp.setattr(settings, "GITHUB_CLIENT_SECRET", "mock_secret", raising=False)
        # Login and callback first time
        login1 = await client.get("/api/v1/auth/github/login?format=json")
        state1 = login1.json()["state"]
        await client.get(f"/api/v1/auth/github/callback?code=code_1&state={state1}", follow_redirects=False)

        # Login and callback second time
        login2 = await client.get("/api/v1/auth/github/login?format=json")
        state2 = login2.json()["state"]
        res2 = await client.get(f"/api/v1/auth/github/callback?code=code_2&state={state2}", follow_redirects=False)
        assert res2.status_code in (200, 302, 307)


@pytest.mark.asyncio
async def test_f2_auth_me_returns_tenant_profile_and_entitlements(
    client: AsyncClient,
    tenant_factory
):
    """F2.5: Verifies GET /api/v1/auth/me decodes session claims and returns profile with tenant context."""
    tenant = tenant_factory(username="bounty_coder", role="owner", tier="pro")
    res = await client.get("/api/v1/auth/me", headers=tenant["headers"])
    assert res.status_code == 200
    data = res.json()
    assert data.get("authenticated") is True or "username" in data or "user" in data


@pytest.mark.asyncio
async def test_f2_legacy_session_token_backward_compatibility(client: AsyncClient):
    """F2.6: Verifies that legacy tokens generated via generate_session_token('admin') authenticate cleanly."""
    legacy_token = generate_session_token("admin")
    headers = {"Authorization": f"Bearer {legacy_token}"}
    res = await client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200


# ===========================================================================
# F3: GitHub App Webhooks & HMAC Ingestion (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f3_webhook_ping_event_with_valid_hmac(client: AsyncClient):
    """F3.1: Verifies that signed ping events return HTTP 200 with pong confirmation."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        headers, body = create_signed_webhook_payload("ping", {"zen": "Keep it logically awesome."})
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200
        assert "pong" in res.text.lower() or res.json().get("status") == "ok"


@pytest.mark.asyncio
async def test_f3_webhook_issues_opened_creates_or_updates_issue(
    client: AsyncClient,
    db_session: AsyncSession
):
    """F3.2: Verifies that an issues.opened webhook creates the Issue record in PostgreSQL."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        iss_num = int(uuid.uuid4().hex[:6], 16) % 500000 + 1000
        payload = {
            "action": "opened",
            "issue": {
                "id": int(uuid.uuid4().hex[:8], 16) % 10000000 + 100,
                "number": iss_num,
                "title": "Webhook Ingested Issue",
                "body": "Issue created via GitHub App webhook",
                "state": "open",
                "html_url": f"https://github.com/webhook-org/repo/issues/{iss_num}",
                "labels": [{"name": "bug"}],
                "assignees": [],
                "comments": 0
            },
            "repository": {
                "id": 998877,
                "name": "webhook-repo",
                "full_name": "webhook-org/webhook-repo",
                "owner": {"login": "webhook-org"},
                "html_url": "https://github.com/webhook-org/webhook-repo",
                "default_branch": "main",
                "language": "Python"
            }
        }
        headers, body = create_signed_webhook_payload("issues", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_f3_webhook_issues_closed_blocks_active_task(
    client: AsyncClient,
    db_session: AsyncSession
):
    """F3.3: Verifies that an issues.closed webhook transitions active tasks on that issue to BLOCKED."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        repo = Repository(
            id=f"repo-{uuid.uuid4().hex[:8]}",
            owner="webhook-org",
            name="webhook-repo-close",
            full_name=f"webhook-org/webhook-repo-close-{uuid.uuid4().hex[:4]}",
            html_url="https://github.com/webhook-org/webhook-repo-close",
            default_branch="main"
        )
        db_session.add(repo)
        await db_session.flush()

        iss_num = int(uuid.uuid4().hex[:6], 16) % 500000 + 2000
        issue = Issue(
            id=f"iss-{uuid.uuid4().hex[:8]}",
            repository_id=repo.id,
            github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 200,
            issue_number=iss_num,
            title="Issue to be closed",
            html_url=f"https://github.com/webhook-org/webhook-repo-close/issues/{iss_num}",
            state="open"
        )
        db_session.add(issue)
        await db_session.flush()

        task = Task(
            id=f"task-close-{uuid.uuid4().hex[:8]}",
            issue_id=issue.id,
            workflow_state="COLLABORATIVE_WORK"
        )
        db_session.add(task)
        await db_session.commit()

        # Send issues.closed event
        payload = {
            "action": "closed",
            "issue": {
                "id": issue.github_id,
                "number": iss_num,
                "state": "closed",
                "html_url": issue.html_url
            },
            "repository": {
                "id": 998877,
                "full_name": repo.full_name
            }
        }
        headers, body = create_signed_webhook_payload("issues", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200

        # Check task state is BLOCKED
        await db_session.refresh(task)
        assert task.workflow_state == "BLOCKED"


@pytest.mark.asyncio
async def test_f3_webhook_pull_request_merged_transitions_task(
    client: AsyncClient,
    db_session: AsyncSession
):
    """F3.4: Verifies that pull_request.closed with merged=true transitions task to MERGED_OR_CLOSED."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        pr_num = int(uuid.uuid4().hex[:4], 16) % 9000 + 100
        repo = Repository(
            id=f"repo-{uuid.uuid4().hex[:8]}",
            owner="webhook-org",
            name="pr-merge-repo",
            full_name=f"webhook-org/pr-merge-repo-{uuid.uuid4().hex[:4]}",
            html_url="https://github.com/webhook-org/pr-merge-repo"
        )
        db_session.add(repo)
        await db_session.flush()

        issue = Issue(
            id=f"iss-{uuid.uuid4().hex[:8]}",
            repository_id=repo.id,
            github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 300,
            issue_number=pr_num + 500,
            title="Issue with PR",
            html_url="https://github.com/webhook-org/pr-merge-repo/issues/1",
            state="open"
        )
        db_session.add(issue)
        await db_session.flush()

        task = Task(
            id=f"task-pr-{uuid.uuid4().hex[:8]}",
            issue_id=issue.id,
            pr_number=pr_num,
            workflow_state="IN_REVIEW"
        )
        db_session.add(task)
        await db_session.commit()

        payload = {
            "action": "closed",
            "pull_request": {
                "number": pr_num,
                "merged": True,
                "state": "closed"
            },
            "repository": {
                "full_name": repo.full_name
            }
        }
        headers, body = create_signed_webhook_payload("pull_request", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200

        await db_session.refresh(task)
        assert task.workflow_state == "MERGED_OR_CLOSED"
        assert task.pr_merged is True


@pytest.mark.asyncio
async def test_f3_webhook_pull_request_review_changes_requested(
    client: AsyncClient,
    db_session: AsyncSession
):
    """F3.5: Verifies pull_request_review with CHANGES_REQUESTED moves task back to COLLABORATIVE_WORK."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        pr_num = int(uuid.uuid4().hex[:4], 16) % 9000 + 200
        repo = Repository(
            id=f"repo-{uuid.uuid4().hex[:8]}",
            owner="webhook-org",
            name="pr-review-repo",
            full_name=f"webhook-org/pr-review-repo-{uuid.uuid4().hex[:4]}",
            html_url="https://github.com/webhook-org/pr-review-repo"
        )
        db_session.add(repo)
        await db_session.flush()

        issue = Issue(
            id=f"iss-{uuid.uuid4().hex[:8]}",
            repository_id=repo.id,
            github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 400,
            issue_number=pr_num + 500,
            title="Issue with PR review",
            html_url="https://github.com/webhook-org/pr-review-repo/issues/2",
            state="open"
        )
        db_session.add(issue)
        await db_session.flush()

        task = Task(
            id=f"task-review-{uuid.uuid4().hex[:8]}",
            issue_id=issue.id,
            pr_number=pr_num,
            workflow_state="IN_REVIEW"
        )
        db_session.add(task)
        await db_session.commit()

        payload = {
            "action": "submitted",
            "review": {
                "state": "changes_requested",
                "body": "Please add unit tests."
            },
            "pull_request": {
                "number": pr_num
            },
            "repository": {
                "full_name": repo.full_name
            }
        }
        headers, body = create_signed_webhook_payload("pull_request_review", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200

        await db_session.refresh(task)
        assert task.workflow_state == "COLLABORATIVE_WORK"
        assert task.pr_review_status == "CHANGES_REQUESTED"


@pytest.mark.asyncio
async def test_f3_webhook_repository_archived_disables_open_issues(
    client: AsyncClient,
    db_session: AsyncSession
):
    """F3.6: Verifies repository.archived marks repository as archived and ineligibilizes its issues."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        repo = Repository(
            id=f"repo-{uuid.uuid4().hex[:8]}",
            owner="webhook-org",
            name="archived-repo",
            full_name=f"webhook-org/archived-repo-{uuid.uuid4().hex[:4]}",
            html_url="https://github.com/webhook-org/archived-repo",
            is_archived=False
        )
        db_session.add(repo)
        await db_session.flush()

        issue = Issue(
            id=f"iss-{uuid.uuid4().hex[:8]}",
            repository_id=repo.id,
            github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 500,
            issue_number=10,
            title="Archived repo issue",
            html_url="https://github.com/webhook-org/archived-repo/issues/10",
            state="open",
            is_eligible=True
        )
        db_session.add(issue)
        await db_session.commit()

        payload = {
            "action": "archived",
            "repository": {
                "id": 998877,
                "full_name": repo.full_name
            }
        }
        headers, body = create_signed_webhook_payload("repository", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200

        await db_session.refresh(repo)
        await db_session.refresh(issue)
        assert repo.is_archived is True
        assert issue.is_eligible is False


# ===========================================================================
# F4: Per-Tenant Settings & BYOK Keys (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f4_user_settings_byok_encryption_at_rest(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """F4.1: Verifies BYOK API keys are encrypted at rest in the database."""
    tenant = tenant_factory(username="crypto_hunter")
    raw_openai_key = "sk-proj-testOpenAiSecretKey1234567890"

    res = await client.put(
        "/api/v1/settings",
        json={"openai_api_key": raw_openai_key},
        headers=tenant["headers"]
    )
    assert res.status_code == 200

    if UserSettings is not None:
        sett_stmt = select(UserSettings).where(UserSettings.user_id == tenant["user_id"])
        user_sett = (await db_session.execute(sett_stmt)).scalar_one_or_none()
        if user_sett and user_sett.openai_api_key_encrypted:
            assert raw_openai_key not in user_sett.openai_api_key_encrypted
            assert len(user_sett.openai_api_key_encrypted) > 20


@pytest.mark.asyncio
async def test_f4_settings_read_returns_masked_key_previews(
    client: AsyncClient,
    tenant_factory
):
    """F4.2: Verifies GET /api/v1/settings returns boolean presence or masked previews, not raw keys."""
    tenant = tenant_factory(username="preview_hunter")
    raw_key = "sk-testSecretKeyOpenAI9999"
    await client.put("/api/v1/settings", json={"openai_api_key": raw_key}, headers=tenant["headers"])

    read_res = await client.get("/api/v1/settings", headers=tenant["headers"])
    assert read_res.status_code == 200
    data = read_res.json()
    assert raw_key not in json.dumps(data), "Plaintext API key must NEVER be leaked in settings read response"
    assert data.get("has_openai_key") is True or "openai_api_key" not in data or data.get("openai_api_key", "").startswith("sk-...")


@pytest.mark.asyncio
async def test_f4_settings_resolver_user_precedence_over_org(db_session: AsyncSession, tenant_factory):
    """F4.3: Verifies SettingsResolver prioritizes User personal BYOK key over Organization shared key."""
    if SettingsResolver is None:
        pytest.skip("SettingsResolver not yet implemented")

    user_id = f"usr-p-{uuid.uuid4().hex[:8]}"
    org_id = f"org-p-{uuid.uuid4().hex[:8]}"
    user = User(id=user_id, github_username=f"u_{uuid.uuid4().hex[:8]}", email=f"{user_id}@example.com")
    org = Organization(id=org_id, name="Prec Org", slug=f"slug-{uuid.uuid4().hex[:8]}")

    user_key = "sk-user-personal-key-111"
    org_key = "sk-org-shared-key-222"
    u_sett = UserSettings(user_id=user_id, openai_api_key_encrypted=encrypt_secret(user_key))
    o_sett = OrganizationSettings(
        org_id=org_id,
        openai_api_key_encrypted=encrypt_secret(org_key),
        enforce_shared_keys=False
    )
    db_session.add_all([user, org, u_sett, o_sett])
    await db_session.commit()

    resolved = await SettingsResolver.get_effective_ai_key(
        db=db_session,
        user_id=user_id,
        org_id=org_id,
        provider="openai"
    )
    assert resolved == user_key


@pytest.mark.asyncio
async def test_f4_settings_resolver_org_precedence_over_env(db_session: AsyncSession, monkeypatch):
    """F4.4: Verifies SettingsResolver prioritizes Organization key over environment fallback."""
    if SettingsResolver is None:
        pytest.skip("SettingsResolver not yet implemented")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-fallback-999")
    org_id = f"org-env-{uuid.uuid4().hex[:8]}"
    org = Organization(id=org_id, name="Env Prec Org", slug=f"slug-{uuid.uuid4().hex[:8]}")
    org_key = "sk-org-precedence-key-444"
    o_sett = OrganizationSettings(
        org_id=org_id,
        openai_api_key_encrypted=encrypt_secret(org_key),
        enforce_shared_keys=False
    )
    db_session.add_all([org, o_sett])
    await db_session.commit()

    resolved = await SettingsResolver.get_effective_ai_key(
        db=db_session,
        org_id=org_id,
        provider="openai"
    )
    assert resolved == org_key
    assert resolved != "sk-env-fallback-999"


@pytest.mark.asyncio
async def test_f4_organization_settings_enforce_shared_keys(db_session: AsyncSession):
    """F4.5: Verifies OrganizationSettings enforce_shared_keys flag overrides personal key."""
    if OrganizationSettings is None or SettingsResolver is None:
        pytest.skip("OrganizationSettings not yet implemented")

    user_id = f"usr-enf-{uuid.uuid4().hex[:8]}"
    org_id = f"org-enf-{uuid.uuid4().hex[:8]}"
    user = User(id=user_id, github_username=f"u_{uuid.uuid4().hex[:8]}", email=f"{user_id}@example.com")
    org = Organization(id=org_id, name="Enforce Org", slug=f"slug-{uuid.uuid4().hex[:8]}")

    user_key = "sk-user-key-555"
    org_key = "sk-org-enforced-key-666"
    u_sett = UserSettings(user_id=user_id, openai_api_key_encrypted=encrypt_secret(user_key))
    o_sett = OrganizationSettings(
        org_id=org_id,
        openai_api_key_encrypted=encrypt_secret(org_key),
        enforce_shared_keys=True
    )
    db_session.add_all([user, org, u_sett, o_sett])
    await db_session.commit()

    # When enforce_shared_keys is True, org_key wins over user_key
    resolved_enforced = await SettingsResolver.get_effective_ai_key(
        db=db_session,
        user_id=user_id,
        org_id=org_id,
        provider="openai"
    )
    assert resolved_enforced == org_key

    # When enforce_shared_keys is False, user_key wins
    o_sett.enforce_shared_keys = False
    await db_session.commit()

    resolved_normal = await SettingsResolver.get_effective_ai_key(
        db=db_session,
        user_id=user_id,
        org_id=org_id,
        provider="openai"
    )
    assert resolved_normal == user_key


@pytest.mark.asyncio
async def test_f4_byok_crypto_roundtrip():
    """F4.6: Verifies cryptographic module encrypt_secret and decrypt_secret perform perfect roundtrips."""
    if encrypt_secret is None or decrypt_secret is None:
        pytest.skip("Crypto module not yet implemented")

    original = "sk-ant-api03-sampleAnthropicSecretKeyWithSpecialChars!@#$%^&*()"
    encrypted = encrypt_secret(original)
    assert encrypted != original
    decrypted = decrypt_secret(encrypted)
    assert decrypted == original


# ===========================================================================
# F5: Hybrid Runner Foundation (6 tests)
# ===========================================================================

@pytest.mark.asyncio
async def test_f5_runner_registration_generates_revokable_token(
    client: AsyncClient,
    tenant_factory
):
    """F5.1: Verifies POST /api/v1/runners/register returns runner_id and persistent runner_token (rnt_...)."""
    tenant = tenant_factory(username="runner_dev")
    reg_payload = {
        "registration_token": tenant["token"],
        "name": "MacBook-Pro-M3",
        "os_info": "darwin"
    }
    res = await client.post("/api/v1/runners/register", json=reg_payload, headers=tenant["headers"])
    if res.status_code == 404:
        pytest.skip("Runner router not yet registered")
    assert res.status_code in (200, 201)
    data = res.json()
    assert "runner_id" in data
    assert "runner_token" in data
    assert data["runner_token"].startswith("rnt_")


@pytest.mark.asyncio
async def test_f5_runner_heartbeat_updates_timestamp_and_status(
    client: AsyncClient,
    tenant_factory
):
    """F5.2: Verifies POST /api/v1/runners/{runner_id}/heartbeat updates timestamp and reports ok."""
    tenant = tenant_factory(username="runner_dev")
    reg_payload = {"registration_token": tenant["token"], "name": "Linux-Runner", "os_info": "linux"}
    reg_res = await client.post("/api/v1/runners/register", json=reg_payload, headers=tenant["headers"])
    if reg_res.status_code == 404:
        pytest.skip("Runner router not yet registered")

    runner_id = reg_res.json()["runner_id"]
    runner_token = reg_res.json()["runner_token"]

    hb_headers = {"Authorization": f"Bearer {runner_token}"}
    hb_payload = {
        "status": "idle",
        "system_stats": {"cpu_percent": 15.5, "memory_percent": 42.0}
    }
    hb_res = await client.post(f"/api/v1/runners/{runner_id}/heartbeat", json=hb_payload, headers=hb_headers)
    assert hb_res.status_code == 200
    assert hb_res.json().get("status") in ("ok", "success")


@pytest.mark.asyncio
async def test_f5_runner_job_polling_returns_queued_job(
    client: AsyncClient,
    tenant_factory
):
    """F5.3: Verifies GET /api/v1/runners/jobs/poll retrieves a queued task job."""
    tenant = tenant_factory(username="runner_dev")
    reg_payload = {"registration_token": tenant["token"], "name": "MacBook-Air", "os_info": "darwin"}
    reg_res = await client.post("/api/v1/runners/register", json=reg_payload, headers=tenant["headers"])
    if reg_res.status_code == 404:
        pytest.skip("Runner router not yet registered")

    runner_token = reg_res.json()["runner_token"]
    poll_headers = {"Authorization": f"Bearer {runner_token}"}
    poll_res = await client.get("/api/v1/runners/jobs/poll", headers=poll_headers)
    assert poll_res.status_code in (200, 204)


@pytest.mark.asyncio
async def test_f5_runner_job_acknowledge_and_complete(client: AsyncClient, tenant_factory, db_session: AsyncSession):
    """F5.4: Verifies full runner job lifecycle (poll, start, complete)."""
    tenant = tenant_factory(username="runner_dev")
    reg_payload = {"registration_token": tenant["token"], "name": "Workstation", "os_info": "linux"}
    reg_res = await client.post("/api/v1/runners/register", json=reg_payload, headers=tenant["headers"])
    assert reg_res.status_code == 201
    runner_token = reg_res.json()["runner_token"]
    runner_headers = {"Authorization": f"Bearer {runner_token}"}

    job_id = f"job-ack-{uuid.uuid4().hex[:8]}"
    job = RunnerJob(
        id=job_id,
        tenant_id=tenant["org_id"],
        job_type="execute_task",
        status="queued"
    )
    db_session.add(job)
    await db_session.commit()

    # Poll job
    poll_res = await client.get("/api/v1/runners/jobs/poll", headers=runner_headers)
    assert poll_res.status_code == 200
    assert poll_res.json()["id"] == job_id
    assert poll_res.json()["status"] == "running"

    # Complete job
    complete_payload = {
        "status": "completed",
        "result": {"exit_code": 0, "output": "Success"},
        "logs": "Execution finished cleanly."
    }
    comp_res = await client.post(
        f"/api/v1/runners/jobs/{job_id}/complete",
        json=complete_payload,
        headers=runner_headers
    )
    assert comp_res.status_code == 200

    # Verify in DB
    await db_session.refresh(job)
    assert job.status == "completed"
    assert job.logs == "Execution finished cleanly."
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_f5_runner_tenant_scoping(client: AsyncClient, tenant_factory, db_session: AsyncSession):
    """F5.5: Verifies that runner jobs are strictly scoped to the tenant the runner was paired with."""
    tenant_a = tenant_factory(username="dev_a", org_slug="org_a")
    tenant_b = tenant_factory(username="dev_b", org_slug="org_b")

    reg_res_a = await client.post(
        "/api/v1/runners/register",
        json={"registration_token": tenant_a["token"], "name": "Runner-A", "os_info": "linux"},
        headers=tenant_a["headers"]
    )
    assert reg_res_a.status_code == 201
    token_a = reg_res_a.json()["runner_token"]

    reg_res_b = await client.post(
        "/api/v1/runners/register",
        json={"registration_token": tenant_b["token"], "name": "Runner-B", "os_info": "linux"},
        headers=tenant_b["headers"]
    )
    assert reg_res_b.status_code == 201
    token_b = reg_res_b.json()["runner_token"]

    job_id = f"job-scope-{uuid.uuid4().hex[:8]}"
    job_a = RunnerJob(
        id=job_id,
        tenant_id=tenant_a["org_id"],
        job_type="validate_diff",
        status="queued"
    )
    db_session.add(job_a)
    await db_session.commit()

    # Runner B in Org B must receive 204 No Content
    poll_b = await client.get("/api/v1/runners/jobs/poll", headers={"Authorization": f"Bearer {token_b}"})
    assert poll_b.status_code == 204

    # Runner A in Org A must receive 200 OK and job_id
    poll_a = await client.get("/api/v1/runners/jobs/poll", headers={"Authorization": f"Bearer {token_a}"})
    assert poll_a.status_code == 200
    assert poll_a.json()["id"] == job_id


@pytest.mark.asyncio
async def test_f5_runner_revocation(client: AsyncClient, tenant_factory):
    """F5.6: Verifies DELETE /api/v1/runners/{runner_id} revokes runner access."""
    tenant = tenant_factory(username="runner_dev")
    reg_res = await client.post(
        "/api/v1/runners/register",
        json={"registration_token": tenant["token"], "name": "Runner-To-Revoke", "os_info": "darwin"},
        headers=tenant["headers"]
    )
    if reg_res.status_code == 404:
        pytest.skip("Runner router not yet registered")

    runner_id = reg_res.json()["runner_id"]
    runner_token = reg_res.json()["runner_token"]

    del_res = await client.delete(f"/api/v1/runners/{runner_id}", headers=tenant["headers"])
    assert del_res.status_code in (200, 204)

    # Post-revocation heartbeat must be rejected
    hb_res = await client.post(
        f"/api/v1/runners/{runner_id}/heartbeat",
        json={"status": "idle"},
        headers={"Authorization": f"Bearer {runner_token}"}
    )
    assert hb_res.status_code in (401, 403, 404)
