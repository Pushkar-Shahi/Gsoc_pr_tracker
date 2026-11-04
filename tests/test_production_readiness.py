import asyncio
import os
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch

from app.core.preflight import run_preflight_checks
from app.services.queue_service import (
    InMemoryAsyncQueueBackend,
    RedisQueueBackend,
    QueueService
)
from app.services.workspace_providers import (
    E2BSandboxProvider,
    LocalWorktreeProvider,
    EphemeralDockerSandboxProvider,
    WorkspaceProviderFactory
)


@pytest.mark.asyncio
async def test_preflight_checks_runs_successfully():
    """Verifies that preflight health checks run and return expected structure."""
    report = await run_preflight_checks()
    assert "status" in report
    assert report["status"] in ("healthy", "warning")
    assert "checks" in report
    assert "database" in report["checks"]
    assert report["checks"]["database"]["status"] == "ok"
    assert "storage" in report["checks"]
    assert "stripe" in report["checks"]
    assert "github" in report["checks"]
    assert "runtime" in report["checks"]


@pytest.mark.asyncio
async def test_preflight_secret_entropy_flagged_in_production(monkeypatch):
    """Verifies that preflight flags weak or default secret keys in production."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr("app.core.config.settings.SECRET_KEY", "issuetopr_secure_jwt_secret_mwps_2026")

    report = await run_preflight_checks()
    assert report["status"] == "error"
    assert any("SECRET_KEY must be a unique" in err for err in report["errors"])
    assert report["checks"]["secret_key"]["status"] == "error"


@pytest.mark.asyncio
async def test_in_memory_queue_backend_fifo():
    """Verifies FIFO queue semantics in InMemoryAsyncQueueBackend."""
    queue = InMemoryAsyncQueueBackend()
    queue_name = f"test-queue-{uuid.uuid4().hex[:6]}"

    assert await queue.get_length(queue_name) == 0

    job_id_1 = await queue.enqueue(queue_name, {"task": "first", "val": 100})
    job_id_2 = await queue.enqueue(queue_name, {"task": "second", "val": 200})
    job_id_3 = await queue.enqueue(queue_name, {"task": "third", "val": 300})

    assert await queue.get_length(queue_name) == 3

    # FIFO Dequeue
    item_1 = await queue.dequeue(queue_name)
    assert item_1["job_id"] == job_id_1
    assert item_1["task"] == "first"

    item_2 = await queue.dequeue(queue_name)
    assert item_2["job_id"] == job_id_2
    assert item_2["task"] == "second"

    item_3 = await queue.dequeue(queue_name)
    assert item_3["job_id"] == job_id_3
    assert item_3["task"] == "third"

    assert await queue.get_length(queue_name) == 0
    assert await queue.dequeue(queue_name) is None


@pytest.mark.asyncio
async def test_queue_service_singleton_lifecycle():
    """Verifies QueueService initialization, enqueueing, and dequeueing."""
    QueueService.reset_instance()
    qs = QueueService.get_instance()
    queue_name = f"qs-test-{uuid.uuid4().hex[:6]}"

    job_id = await qs.enqueue(queue_name, {"action": "sync_repo", "repo": "test/repo"})
    assert job_id is not None
    assert await qs.get_length(queue_name) == 1

    item = await qs.dequeue(queue_name)
    assert item["job_id"] == job_id
    assert item["action"] == "sync_repo"
    assert await qs.get_length(queue_name) == 0


@pytest.mark.asyncio
async def test_redis_queue_backend_graceful_fallback():
    """Verifies that RedisQueueBackend falls back to in-memory queue without raising exceptions when offline."""
    # Point to non-routable port to simulate offline Redis
    redis_backend = RedisQueueBackend("redis://127.0.0.1:54321/0")
    queue_name = f"redis-test-{uuid.uuid4().hex[:6]}"

    job_id = await redis_backend.enqueue(queue_name, {"type": "distributed_job", "data": "payload"})
    assert job_id is not None
    assert await redis_backend.get_length(queue_name) == 1

    item = await redis_backend.dequeue(queue_name)
    assert item is not None
    assert item["job_id"] == job_id
    assert item["type"] == "distributed_job"


@pytest.mark.asyncio
async def test_e2b_sandbox_provider_fallback_without_key(tmp_path):
    """Verifies that E2BSandboxProvider falls back to local worktrees when API key is missing."""
    provider = E2BSandboxProvider(api_key=None, workspace_root=tmp_path / "workspaces", cache_root=tmp_path / "cache")
    task_id = str(uuid.uuid4())

    res = await provider.prepare_workspace(
        task_id=task_id,
        owner="fastapi",
        repo="fastapi",
        clone_url="https://github.com/fastapi/fastapi.git",
        issue_number=42,
        issue_title="Bug in validation",
        issue_body="Reproduction code here",
        default_branch="main"
    )

    assert res["e2b_active"] is False
    assert res["provider"] == "e2b_sandbox_fallback_local"
    assert res["sandbox_id"] is None
    assert Path(res["worktree_path"]).exists()

    cleaned = await provider.cleanup_workspace(res["worktree_path"])
    assert cleaned is True


@pytest.mark.asyncio
async def test_e2b_sandbox_provider_with_api_key(tmp_path):
    """Verifies that E2BSandboxProvider activates micro-VM sandbox configuration when API key is present."""
    provider = E2BSandboxProvider(api_key="e2b_test_mock_api_key_12345", workspace_root=tmp_path / "workspaces", cache_root=tmp_path / "cache")
    task_id = str(uuid.uuid4())

    res = await provider.prepare_workspace(
        task_id=task_id,
        owner="langchain-ai",
        repo="langchain",
        clone_url="https://github.com/langchain-ai/langchain.git",
        issue_number=101,
        issue_title="Streaming callback issue",
        issue_body="Traceback here",
        default_branch="master"
    )

    assert res["e2b_active"] is True
    assert res["provider"] == "e2b_sandbox"
    assert res["sandbox_id"] == f"e2b-{task_id[:8]}"
    assert res["microvm_template"] == "base"
    assert res["timeout_sec"] == 120

    cleaned = await provider.cleanup_workspace(res["worktree_path"])
    assert cleaned is True


def test_workspace_provider_factory_routing():
    """Verifies that WorkspaceProviderFactory returns appropriate provider types."""
    e2b_prov = WorkspaceProviderFactory.get_provider("e2b")
    assert isinstance(e2b_prov, E2BSandboxProvider)

    docker_prov = WorkspaceProviderFactory.get_provider("docker")
    assert isinstance(docker_prov, EphemeralDockerSandboxProvider)

    local_prov = WorkspaceProviderFactory.get_provider("local")
    assert isinstance(local_prov, LocalWorktreeProvider)

