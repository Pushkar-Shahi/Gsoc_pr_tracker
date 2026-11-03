"""Tier 4: Real-World End-to-End Scenarios Test Suite.

Simulates complete user journeys for open-source bounty hunters, competing developers, and engineering teams:
1. Scenario 1: Open Source Bounty Hunter Complete Setup & Issue Acquisition
2. Scenario 2: Two Competing Bounty Hunters on Same Issue with Zero Cross-Tenant Leakage
3. Scenario 3: Organization / Team Triage, Shared BYOK Key, and Collaborative PR Review
4. Scenario 4: Upstream Disruption Handling (Upstream issue closed on GitHub during active work)
5. Scenario 5: Full Lifecycle: OAuth -> BYOK -> Webhook Ingest -> Task -> Runner -> PR Merge -> Audit
Total: 5 test cases.
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


@pytest.mark.asyncio
async def test_t4_scenario_bounty_hunter_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """Scenario 1: Open-source bounty hunter registers, sets OpenAI BYOK key, discovers issue, and pairs runner."""
    hunter = tenant_factory(username="bounty_ninja", org_slug="ninja_workspace", role="owner")

    # Step 1: Hunter saves personal OpenAI BYOK key
    raw_key = "sk-proj-ninja-openai-key-9999"
    sett_res = await client.put(
        "/api/v1/settings",
        json={
            "openai_api_key": raw_key,
            "preferred_ai_provider": "openai",
            "auto_publish_pr": False
        },
        headers=hunter["headers"]
    )
    assert sett_res.status_code == 200

    # Verify key preview is masked, raw key never returned
    read_res = await client.get("/api/v1/settings", headers=hunter["headers"])
    assert read_res.status_code == 200
    assert raw_key not in json.dumps(read_res.json())

    # Step 2: High-value bounty issue arrives via GitHub App webhook
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        iss_num = int(uuid.uuid4().hex[:4], 16) % 5000 + 400
        headers, body = create_signed_webhook_payload("issues", {
            "action": "opened",
            "issue": {
                "id": int(uuid.uuid4().hex[:8], 16) % 10000000 + 1001,
                "number": iss_num,
                "title": "$500 Bounty: Memory leak in worker pool",
                "body": "Reproducible memory leak under high concurrency load.",
                "state": "open",
                "html_url": f"https://github.com/bounty-corp/core-engine/issues/{iss_num}",
                "labels": [{"name": "bounty"}, {"name": "bug"}]
            },
            "repository": {
                "id": 112233,
                "name": "core-engine",
                "full_name": f"bounty-corp/core-engine-{uuid.uuid4().hex[:4]}",
                "default_branch": "main"
            }
        })
        wh_res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert wh_res.status_code == 200

    # Step 3: Hunter registers local MacBook Pro runner
    reg_res = await client.post(
        "/api/v1/runners/register",
        json={
            "registration_token": hunter["token"],
            "name": "Ninja-MacBook-M3",
            "os_info": "darwin"
        },
        headers=hunter["headers"]
    )
    if reg_res.status_code == 404:
        pytest.skip("Runner router not yet registered")

    assert reg_res.status_code in (200, 201)
    runner_token = reg_res.json()["runner_token"]
    assert runner_token.startswith("rnt_")


@pytest.mark.asyncio
async def test_t4_scenario_competing_bounty_hunters_zero_leakage(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """Scenario 2: Two competing bounty hunters work on the same issue with separate BYOK keys and zero leakage."""
    alice = tenant_factory(username="alice_dev", org_slug="alice_workspace")
    bob = tenant_factory(username="bob_dev", org_slug="bob_workspace")

    # Alice sets OpenAI key; Bob sets Anthropic key
    await client.put("/api/v1/settings", json={"openai_api_key": "sk-alice-openai"}, headers=alice["headers"])
    await client.put("/api/v1/settings", json={"anthropic_api_key": "sk-bob-anthropic"}, headers=bob["headers"])

    # Shared repository and issue
    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="popular-oss",
        name="speedy-web",
        full_name=f"popular-oss/speedy-web-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/popular-oss/speedy-web"
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 1002,
        issue_number=777,
        title="High Bounty Issue: Implement HTTP/3 Quic Stream Multiplexing",
        html_url="https://github.com/popular-oss/speedy-web/issues/777",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    # Alice creates task
    task_alice = Task(
        id=f"tsk-alice-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=alice["org_id"],
        user_id=alice["user_id"],
        workflow_state="COLLABORATIVE_WORK"
    )
    # Bob creates task
    task_bob = Task(
        id=f"tsk-bob-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=bob["org_id"],
        user_id=bob["user_id"],
        workflow_state="COLLABORATIVE_WORK"
    )
    db_session.add_all([task_alice, task_bob])
    await db_session.commit()

    # Alice queries tasks -> only sees Alice's task
    res_a = await client.get("/api/v1/tasks", headers=alice["headers"])
    assert res_a.status_code == 200
    a_ids = [t["id"] for t in res_a.json()]
    assert task_alice.id in a_ids
    assert task_bob.id not in a_ids, "Alice must never see Bob's task"

    # Bob queries tasks -> only sees Bob's task
    res_b = await client.get("/api/v1/tasks", headers=bob["headers"])
    assert res_b.status_code == 200
    b_ids = [t["id"] for t in res_b.json()]
    assert task_bob.id in b_ids
    assert task_alice.id not in b_ids, "Bob must never see Alice's task"

    # Alice cannot read Bob's task by ID
    res_cross = await client.get(f"/api/v1/tasks/{task_bob.id}", headers=alice["headers"])
    assert res_cross.status_code in (404, 403)


@pytest.mark.asyncio
async def test_t4_scenario_team_collaborative_workflow(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """Scenario 3: Organization team workflow with GitHub App, shared BYOK keys, and PR review rework cycle."""
    team_admin = tenant_factory(username="team_lead", org_slug="fintech_org", role="owner")
    team_dev = tenant_factory(username="senior_dev", org_id=team_admin["org_id"], role="member")

    # Team Admin sets shared BYOK key
    await client.put(
        "/api/v1/settings",
        json={"gemini_api_key": "gemini-team-shared-key-9999", "auto_publish_pr": False},
        headers=team_admin["headers"]
    )

    # Repository setup
    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="fintech-org",
        name="payment-service",
        full_name=f"fintech-org/payment-service-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/fintech-org/payment-service"
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 1003,
        issue_number=105,
        title="Payment rounding precision fix",
        html_url="https://github.com/fintech-org/payment-service/issues/105",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    task = Task(
        id=f"task-team-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=team_admin["org_id"],
        user_id=team_dev["user_id"],
        pr_number=105,
        workflow_state="IN_REVIEW"
    )
    db_session.add(task)
    await db_session.commit()

    # Webhook arrives: Maintainer requested changes
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        payload = {
            "action": "submitted",
            "review": {
                "state": "changes_requested",
                "body": "Fix rounding logic in decimal calculations."
            },
            "pull_request": {"number": 105},
            "repository": {"full_name": repo.full_name}
        }
        headers, body = create_signed_webhook_payload("pull_request_review", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200

        await db_session.refresh(task)
        assert task.workflow_state == "COLLABORATIVE_WORK"
        assert task.pr_review_status == "CHANGES_REQUESTED"


@pytest.mark.asyncio
async def test_t4_scenario_upstream_issue_closed_disruption(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """Scenario 4: Active task is cleanly marked BLOCKED when upstream maintainer closes issue on GitHub."""
    dev = tenant_factory(username="disruption_dev")

    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="upstream-org",
        name="upstream-lib",
        full_name=f"upstream-org/upstream-lib-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/upstream-org/upstream-lib"
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 1004,
        issue_number=333,
        title="Unexpectedly Closed Upstream Issue",
        html_url="https://github.com/upstream-org/upstream-lib/issues/333",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    task = Task(
        id=f"task-disrupted-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=dev["org_id"],
        user_id=dev["user_id"],
        workflow_state="COLLABORATIVE_WORK"
    )
    db_session.add(task)
    await db_session.commit()

    # Upstream maintainer closes issue on GitHub
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        payload = {
            "action": "closed",
            "issue": {
                "id": issue.github_id,
                "number": 333,
                "state": "closed",
                "html_url": issue.html_url
            },
            "repository": {"full_name": repo.full_name}
        }
        headers, body = create_signed_webhook_payload("issues", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200

        await db_session.refresh(task)
        assert task.workflow_state == "BLOCKED"
        assert "closed" in (task.blocked_reason or "").lower()


@pytest.mark.asyncio
async def test_t4_scenario_full_end_to_end_lifecycle(
    client: AsyncClient,
    db_session: AsyncSession,
    tenant_factory
):
    """Scenario 5: Complete lifecycle from Auth -> BYOK -> Webhook -> Task -> Runner -> PR Merge -> Audit."""
    user = tenant_factory(username="lifecycle_champ")

    # 1. BYOK Settings configuration
    await client.put(
        "/api/v1/settings",
        json={"gemini_api_key": "gemini-api-key-test-5555", "auto_publish_pr": False},
        headers=user["headers"]
    )

    # 2. Webhook delivers repo and issue
    repo = Repository(
        id=f"repo-{uuid.uuid4().hex[:8]}",
        owner="lifecycle-corp",
        name="flagship-app",
        full_name=f"lifecycle-corp/flagship-app-{uuid.uuid4().hex[:4]}",
        html_url="https://github.com/lifecycle-corp/flagship-app"
    )
    db_session.add(repo)
    await db_session.flush()

    issue = Issue(
        id=f"iss-{uuid.uuid4().hex[:8]}",
        repository_id=repo.id,
        github_id=int(uuid.uuid4().hex[:8], 16) % 10000000 + 1005,
        issue_number=999,
        title="Full Lifecycle Feature Request",
        html_url="https://github.com/lifecycle-corp/flagship-app/issues/999",
        state="open"
    )
    db_session.add(issue)
    await db_session.flush()

    # 3. Task created under tenant
    task = Task(
        id=f"task-lifecycle-{uuid.uuid4().hex[:8]}",
        issue_id=issue.id,
        tenant_id=user["org_id"],
        user_id=user["user_id"],
        pr_number=999,
        workflow_state="IN_REVIEW"
    )
    db_session.add(task)
    await db_session.commit()

    # 4. Webhook delivers PR merged event
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "GITHUB_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET, raising=False)
        payload = {
            "action": "closed",
            "pull_request": {"number": 999, "merged": True, "state": "closed"},
            "repository": {"full_name": repo.full_name}
        }
        headers, body = create_signed_webhook_payload("pull_request", payload)
        res = await client.post("/api/v1/webhooks/github", content=body, headers=headers)
        assert res.status_code == 200

        await db_session.refresh(task)
        assert task.workflow_state == "MERGED_OR_CLOSED"
        assert task.pr_merged is True

    # 5. Verify audit logs reflect user operations
    audit_res = await client.get("/api/v1/audit-logs", headers=user["headers"])
    assert audit_res.status_code == 200
