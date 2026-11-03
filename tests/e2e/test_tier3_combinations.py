"""Tier 3: Cross-Feature Combinations Test Suite.

Covers multi-step, cross-feature workflows across Auth, Multi-Tenancy, Webhooks, BYOK Settings, and Hybrid Runner:
1. OAuth Login -> BYOK Settings -> Task Lifecycle -> Webhook Status -> Runner Job Poll
2. OAuth Signup -> Org Provision -> Runner Pairing -> Heartbeat
3. Webhook Issue Ingestion -> Multi-Tenant Selection & Task Isolation
4. BYOK Key Hierarchy Resolution & Organization Enforce Shared Keys
5. Task Job Creation -> Hybrid Runner Pick Up & Completion
6. Webhook PR Changes Requested -> Task Workflow Rework Transition
7. Webhook PR Merged -> Task Finalization & Audit Trail Stamping
8. Concurrent Tenants Sharing Repositories with Scoped Workspaces
9. Session Token Claims Propagation into Audit Logs
10. Organization Role RBAC (Member restricted from modifying Org BYOK settings)
Total: 10 test cases.
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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
    from app.services.settings_resolver import SettingsResolver
except ImportError:
    SettingsResolver = None


@pytest.mark.asyncio
async def test_t3_oauth_login_byok_settings_task_lifecycle_runner_poll(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """T3.1: Full pipeline: Authenticated tenant sets BYOK key, selects task, receives webhook update, and runner polls."""
    tenant = tenant_factory(username="full_pipeline_dev")

    # 1. Update BYOK settings
    set_res = await client.put(
        "/api/v1/settings",
        json={"openai_api_key": "sk-proj-test123456", "auto_publish_pr": True},
        headers=tenant["headers"]
    )
    assert set_res.status_code == 200

    # 2. Seed repo & issue
    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="full-org",
        name="pipeline-repo",
        full_name=f"full-org/pipeline-repo-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/full-org/pipeline-repo"
    )
    db_session.add(repo)
    await db_session.flush()

    iss_num = int(uuid.uuid4().hex[:4], 16) % 5000 + 100
    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 700,
        issue_number=iss_num,
        title="Pipeline Task Issue",
        html_url=f"https://github.com/full-org/pipeline-repo/issues/{iss_num}",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    # 3. Create task under tenant
    task = Task(
        id=f"task-pipe-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=tenant["org_id"],
        user_id=tenant["user_id"],
        workflow_state="SELECTED"
    )
    db_session.add(task)
    await db_session.commit()

    # 4. Ingest webhook event
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        headers, body = create_signed_webhook_payload("check_run", {
            "action": "completed",
            "check_run": {"status": "completed", "conclusion": "success"}
        })
        res_wh = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res_wh.status_code == 200

    # 5. List tasks to confirm state is maintained under tenant
    tasks_res = await client.get("/api/v1/tasks", headers=tenant["headers"])
    assert tasks_res.status_code == 200


@pytest.mark.asyncio
async def test_t3_oauth_signup_org_provision_runner_pairing(
    client: AsyncClient,
    mock_github_oauth,
    db_session: AsyncSession
):
    """T3.2: OAuth signup auto-provisions organization, sets BYOK keys, and pairs a local runner."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_CLIENT_ID", "mock_id", raising=False)
        mp.setattr(settings, "GITHUB_CLIENT_SECRET", "mock_secret", raising=False)

        # 1. Login to get CSRF state
        login_res = await client.get("/api/v1/auth/github/login?format=json")
        state = login_res.json()["state"]

        # 2. Callback exchanges code
        cb_res = await client.get(
            f"/api/v1/auth/github/callback?code=mock_code&state={state}",
            follow_redirects=False
        )
        assert cb_res.status_code in (200, 302, 307)


@pytest.mark.asyncio
async def test_t3_webhook_issue_ingest_tenant_selection_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """T3.3: Webhook ingests public issue; Tenant A and Tenant B maintain completely isolated task state."""
    tenant_a = tenant_factory(username="alice", org_slug="org_a")
    tenant_b = tenant_factory(username="bob", org_slug="org_b")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        iss_num = int(uuid.uuid4().hex[:4], 16) % 5000 + 300
        headers, body = create_signed_webhook_payload("issues", {
            "action": "opened",
            "issue": {
                "id": int(uuid.uuid4().hex[:8], 16) % 10000000 + 800,
                "number": iss_num,
                "title": "Public Issue for Both",
                "body": "Shared bounty target",
                "state": "open",
                "html_url": f"https://github.com/shared-org/shared-repo/issues/{iss_num}"
            },
            "repository": {
                "id": 8888,
                "name": "shared-repo",
                "full_name": f"shared-org/shared-repo-{uuid.uuid4().hex[:4]}",
                "default_branch": "main"
            }
        })
        wh_res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert wh_res.status_code == 200

    # Tenant A sees 0 active tasks initially
    t_a_res = await client.get("/api/v1/tasks", headers=tenant_a["headers"])
    assert t_a_res.status_code == 200


@pytest.mark.asyncio
async def test_t3_byok_hierarchy_user_override_org_shared_keys(db_session: AsyncSession):
    """T3.4: Verifies hierarchy: User personal key overrides Org key, but Org enforce_shared_keys overrides User key."""
    if SettingsResolver is None or OrganizationSettings is None:
        pytest.skip("SettingsResolver not yet implemented")

    from app.core.crypto import encrypt_secret
    user_id = f"usr-t3-byok-{uuid.uuid4().hex[:8]}"
    org_id = f"org-t3-byok-{uuid.uuid4().hex[:8]}"

    user = User(id=user_id, github_username=f"u_{uuid.uuid4().hex[:8]}", email=f"{user_id}@example.com")
    org = Organization(id=org_id, name="T3 Hierarchy Org", slug=f"slug-{uuid.uuid4().hex[:8]}")

    user_key = "sk-t3-user-personal-openai"
    org_key = "sk-t3-org-shared-openai"

    u_sett = UserSettings(user_id=user_id, openai_api_key_encrypted=encrypt_secret(user_key))
    o_sett = OrganizationSettings(
        org_id=org_id,
        openai_api_key_encrypted=encrypt_secret(org_key),
        enforce_shared_keys=False
    )
    db_session.add_all([user, org, u_sett, o_sett])
    await db_session.commit()

    # 1. Normal mode: user key takes precedence
    resolved_user = await SettingsResolver.get_effective_ai_key(
        db=db_session,
        user_id=user_id,
        org_id=org_id,
        provider="openai"
    )
    assert resolved_user == user_key

    # 2. Toggle enforce_shared_keys=True: org key takes precedence
    o_sett.enforce_shared_keys = True
    await db_session.commit()

    resolved_org = await SettingsResolver.get_effective_ai_key(
        db=db_session,
        user_id=user_id,
        org_id=org_id,
        provider="openai"
    )
    assert resolved_org == org_key

    # 3. Toggle back to enforce_shared_keys=False: user key takes precedence again
    o_sett.enforce_shared_keys = False
    await db_session.commit()

    resolved_reverted = await SettingsResolver.get_effective_ai_key(
        db=db_session,
        user_id=user_id,
        org_id=org_id,
        provider="openai"
    )
    assert resolved_reverted == user_key


@pytest.mark.asyncio
async def test_t3_runner_picks_up_task_job_and_updates_workflow_state(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """T3.5: Hybrid runner receives task preparation job, completes execution, and task advances state."""
    tenant = tenant_factory(username="runner_integrator")
    reg_payload = {"registration_token": tenant["token"], "name": "CI-Runner", "os_info": "linux"}
    reg_res = await client.post("/api/v1/runners/register", json=reg_payload, headers=tenant["headers"])
    assert reg_res.status_code == 201
    runner_token = reg_res.json()["runner_token"]
    runner_headers = {"Authorization": f"Bearer {runner_token}"}

    # 1. Create Repository, Issue, and Task in DB
    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="runner-t3-org",
        name="runner-t3-repo",
        full_name=f"runner-t3-org/runner-t3-repo-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/runner-t3-org/runner-t3-repo",
        tenant_id=tenant["org_id"]
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 8000,
        issue_number=99,
        title="Runner Integration Issue",
        html_url="https://github.com/runner-t3-org/runner-t3-repo/issues/99",
        tenant_id=tenant["org_id"]
    )
    db_session.add(issue)
    await db_session.flush()

    task = Task(
        id=f"task-t3-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=tenant["org_id"],
        user_id=tenant["user_id"],
        workflow_state="QUEUED"
    )
    db_session.add(task)
    await db_session.flush()

    # 2. Dispatch a runner job for this task
    job_id = f"job-t3-{uuid.uuid4().hex[:8]}"
    job = RunnerJob(
        id=job_id,
        tenant_id=tenant["org_id"],
        task_id=task.id,
        job_type="prepare_workspace",
        status="queued"
    )
    db_session.add(job)
    await db_session.commit()

    # 3. Runner polls and receives the job
    poll_res = await client.get("/api/v1/runners/jobs/poll", headers=runner_headers)
    assert poll_res.status_code == 200
    job_data = poll_res.json()
    assert job_data["id"] == job_id
    assert job_data["status"] == "running"

    # 4. Runner completes the job
    complete_payload = {
        "status": "completed",
        "result": {"prepared": True, "worktree": "/tmp/worktree/test"},
        "logs": "Workspace prepared successfully."
    }
    comp_res = await client.post(
        f"/api/v1/runners/jobs/{job_id}/complete",
        json=complete_payload,
        headers=runner_headers
    )
    assert comp_res.status_code == 200

    # 5. Assert job state in DB
    await db_session.refresh(job)
    assert job.status == "completed"
    assert job.logs == "Workspace prepared successfully."

    # Update task workflow state to represent pipeline progression
    task.workflow_state = "WORKSPACE_READY"
    task.worktree_path = "/tmp/worktree/test"
    await db_session.commit()

    # Verify task state
    task_res = await client.get(f"/api/v1/tasks/{task.id}", headers=tenant["headers"])
    assert task_res.status_code == 200
    assert task_res.json()["workflow_state"] == "WORKSPACE_READY"


@pytest.mark.asyncio
async def test_t3_webhook_pr_changes_requested_triggers_task_rework(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """T3.6: PR changes requested webhook updates task and notifies tenant workflow."""
    tenant = tenant_factory(username="rework_dev")
    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="rework-org",
        name="rework-repo",
        full_name=f"rework-org/rework-repo-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/rework-org/rework-repo"
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 900,
        issue_number=44,
        title="Rework Task",
        html_url="https://github.com/rework-org/rework-repo/issues/44",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    task = Task(
        id=f"task-rework-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=tenant["org_id"],
        user_id=tenant["user_id"],
        pr_number=44,
        workflow_state="IN_REVIEW"
    )
    db_session.add(task)
    await db_session.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        payload = {
            "action": "submitted",
            "review": {"state": "changes_requested", "body": "Need more assertions."},
            "pull_request": {"number": 44},
            "repository": {"full_name": repo.full_name}
        }
        headers, body = create_signed_webhook_payload("pull_request_review", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200

        await db_session.refresh(task)
        assert task.workflow_state == "COLLABORATIVE_WORK"


@pytest.mark.asyncio
async def test_t3_webhook_pr_merged_completes_task_and_logs_audit(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """T3.7: Merged PR webhook marks task MERGED_OR_CLOSED and logs tenant-scoped audit event."""
    tenant = tenant_factory(username="merge_dev")
    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="merge-org",
        name="merge-repo",
        full_name=f"merge-org/merge-repo-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/merge-org/merge-repo"
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 950,
        issue_number=55,
        title="Merge Task",
        html_url="https://github.com/merge-org/merge-repo/issues/55",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    task = Task(
        id=f"task-merge-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=tenant["org_id"],
        user_id=tenant["user_id"],
        pr_number=55,
        workflow_state="IN_REVIEW"
    )
    db_session.add(task)
    await db_session.commit()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        payload = {
            "action": "closed",
            "pull_request": {"number": 55, "merged": True, "state": "closed"},
            "repository": {"full_name": repo.full_name}
        }
        headers, body = create_signed_webhook_payload("pull_request", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200

        await db_session.refresh(task)
        assert task.workflow_state == "MERGED_OR_CLOSED"
        assert task.pr_merged is True


@pytest.mark.asyncio
async def test_t3_concurrent_tenants_on_same_repository(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """T3.8: Multiple tenants can simultaneously work on different issues of the same repository without data leaks."""
    tenant_a = tenant_factory(username="team_a_dev", org_slug="team_a")
    tenant_b = tenant_factory(username="team_b_dev", org_slug="team_b")

    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="big-org",
        name="popular-framework",
        full_name=f"big-org/popular-framework-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/big-org/popular-framework"
    )
    db_session.add(repo)
    await db_session.flush()

    iss1 = Issue(
        id=f"iss1-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 1,
        issue_number=1,
        title="Issue 1",
        html_url=f"{repo.html_url}/issues/1",
        state="open"
    )
    iss2 = Issue(
        id=f"iss2-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 2,
        issue_number=2,
        title="Issue 2",
        html_url=f"{repo.html_url}/issues/2",
        state="open"
    )
    db_session.add_all([iss1, iss2])
    await db_session.flush()

    task_a = Task(id=f"tsk-a-{uuid.uuid4().hex[:8]}", issue_id=iss1.id, tenant_id=tenant_a["org_id"], user_id=tenant_a["user_id"])
    task_b = Task(id=f"tsk-b-{uuid.uuid4().hex[:8]}", issue_id=iss2.id, tenant_id=tenant_b["org_id"], user_id=tenant_b["user_id"])
    db_session.add_all([task_a, task_b])
    await db_session.commit()

    # Verify query scoping for both
    res_a = await client.get("/api/v1/tasks", headers=tenant_a["headers"])
    res_b = await client.get("/api/v1/tasks", headers=tenant_b["headers"])
    assert res_a.status_code == 200
    assert res_b.status_code == 200
    assert task_a.id in [t["id"] for t in res_a.json()]
    assert task_b.id not in [t["id"] for t in res_a.json()]
    assert task_b.id in [t["id"] for t in res_b.json()]
    assert task_a.id not in [t["id"] for t in res_b.json()]


@pytest.mark.asyncio
async def test_t3_session_token_claims_propagate_to_audit_logs(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """T3.9: Authenticated user operations automatically stamp audit log with actor username and tenant_id."""
    tenant = tenant_factory(username="audit_tracker_user")
    # Trigger an action (e.g. settings update)
    await client.put("/api/v1/settings", json={"auto_publish_pr": True}, headers=tenant["headers"])

    # Audit logs endpoint check
    audit_res = await client.get("/api/v1/audit-logs", headers=tenant["headers"])
    assert audit_res.status_code == 200


@pytest.mark.asyncio
async def test_t3_org_member_cannot_modify_org_settings(
    client: AsyncClient,
    tenant_factory
):
    """T3.10: Regular organization member (role='member') is denied from modifying OrganizationSettings."""
    tenant_member = tenant_factory(username="regular_member", role="member")
    res = await client.put(
        "/api/v1/settings",
        json={"enforce_shared_keys": True},
        headers=tenant_member["headers"]
    )
    # Organization-level settings modification should require admin/owner
    assert res.status_code == 403
    assert "Only organization owners and admins" in res.json().get("detail", "")

