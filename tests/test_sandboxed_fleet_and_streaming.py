import asyncio
import json
import os
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
from app.models.models import Organization, User, Membership, Repository, Issue, Task
from app.services.workspace_providers import (
    WorkspaceProviderFactory,
    LocalWorktreeProvider,
    EphemeralDockerSandboxProvider,
    is_docker_available
)
from app.services.sandbox_executor import (
    SandboxedExecutionEngine,
    get_sanitized_environment,
    SENSITIVE_ENV_PREFIXES
)
from app.services.antigravity_handoff import AntigravityHandoffService
from runner.agent import RunnerDaemon, parse_args
from tests.e2e.conftest import make_session_token


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
async def test_workspace_provider_factory():
    """Verify that the factory auto-detects system capabilities and creates proper providers."""
    provider = WorkspaceProviderFactory.get_provider()
    assert provider is not None
    assert isinstance(provider, (LocalWorktreeProvider, EphemeralDockerSandboxProvider))
    
    # Explicit provider requests
    local_p = WorkspaceProviderFactory.get_provider(provider_type="local")
    assert isinstance(local_p, LocalWorktreeProvider)

    docker_p = WorkspaceProviderFactory.get_provider(provider_type="docker")
    assert isinstance(docker_p, EphemeralDockerSandboxProvider)


@pytest.mark.asyncio
async def test_local_worktree_provider_lifecycle(tmp_path):
    """Verify LocalWorktreeProvider creates ephemeral directory with brief and cleans up."""
    provider = LocalWorktreeProvider(workspace_root=tmp_path, cache_root=tmp_path / "cache")
    
    task_id = str(uuid.uuid4())
    res = await provider.prepare_workspace(
        task_id=task_id,
        owner="Pushkar-Shahi",
        repo="Gsoc_pr_tracker",
        clone_url="https://github.com/Pushkar-Shahi/Gsoc_pr_tracker.git",
        issue_number=42,
        issue_title="Ephemeral Sandboxed Test Fleet",
        issue_body="Implement Phase 3 test isolation and real-time streaming",
        default_branch="main"
    )
    
    assert "worktree_path" in res
    assert res["provider"] == "local_worktree"
    
    worktree_path = Path(res["worktree_path"])
    assert worktree_path.exists()
    assert (worktree_path / ".antigravity" / "BRIEF.md").exists()
    
    # Read brief content
    brief_data = (worktree_path / ".antigravity" / "BRIEF.md").read_text(encoding="utf-8")
    assert "#42" in brief_data
    assert "Pushkar-Shahi" in brief_data

    # Cleanup
    cleaned = await provider.cleanup_workspace(str(worktree_path))
    assert cleaned is True
    assert not worktree_path.exists()


def test_environment_sanitization():
    """Verify sensitive environment variables (API keys, secrets) are stripped from execution environment."""
    os.environ["GITHUB_TOKEN"] = "ghp_leaked_secret_token_12345"
    os.environ["STRIPE_SECRET_KEY"] = "sk_live_very_secret_stripe_key"
    os.environ["DATABASE_URL"] = "postgresql://user:pass@secret-db:5432/prod"
    os.environ["OPENAI_API_KEY"] = "sk-leaked-openai-key"
    os.environ["SAFE_PUBLIC_FLAG"] = "developer_machine_flag"

    sanitized = get_sanitized_environment(base_dir=Path("/tmp/safe-sandbox"))

    assert "GITHUB_TOKEN" not in sanitized
    assert "STRIPE_SECRET_KEY" not in sanitized
    assert "DATABASE_URL" not in sanitized
    assert "OPENAI_API_KEY" not in sanitized
    assert sanitized.get("SAFE_PUBLIC_FLAG") == "developer_machine_flag"
    assert sanitized.get("CI") == "true"
    assert sanitized.get("NODE_ENV") == "test"
    assert "PYTHONPATH" in sanitized


@pytest.mark.asyncio
async def test_sandboxed_execution_command_success(tmp_path):
    """Verify SandboxedExecutionEngine executes commands and captures exit code, stdout, and timing."""
    engine = SandboxedExecutionEngine()
    cmd = 'python3 -c "import sys; print(\'SANDBOX_STDOUT_OK\'); sys.stderr.write(\'SANDBOX_STDERR_OK\\n\')"'
    
    result = await engine.execute_command(cmd_str=cmd, cwd=tmp_path, timeout_sec=10.0)

    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    assert "SANDBOX_STDOUT_OK" in result["stdout"]
    assert "SANDBOX_STDERR_OK" in result["stderr"]
    assert result["duration_sec"] > 0
    assert result["command"] == cmd


@pytest.mark.asyncio
async def test_sandboxed_execution_timeout_enforcement(tmp_path):
    """Verify SandboxedExecutionEngine terminates long-running commands that exceed the timeout limit."""
    engine = SandboxedExecutionEngine()
    # Command that sleeps longer than timeout
    cmd = 'python3 -c "import time; time.sleep(10)"'

    result = await engine.execute_command(cmd_str=cmd, cwd=tmp_path, timeout_sec=0.5)

    assert result["exit_code"] != 0
    assert result["timed_out"] is True
    assert "timed out" in result["stderr"].lower() or "timed out" in result["stdout"].lower()


@pytest.mark.asyncio
async def test_streaming_command_generator(tmp_path):
    """Verify stream_command yields formatted chunks and emits exit code."""
    engine = SandboxedExecutionEngine()
    cmd = 'python3 -c "print(\'CHUNK_ALPHA\'); print(\'CHUNK_BETA\')"'

    chunks = []
    async for chunk in engine.stream_command(cmd_str=cmd, cwd=tmp_path, timeout_sec=5.0):
        chunks.append(chunk)

    full_output = "".join(chunks)
    assert "CHUNK_ALPHA" in full_output
    assert "CHUNK_BETA" in full_output
    assert '"exit_code": 0' in full_output


@pytest.mark.asyncio
async def test_task_validation_sse_endpoint():
    """Verify GET /api/v1/streaming/tasks/{id}/validation delivers real-time SSE event stream."""
    session_factory = await get_session_factory()
    org_id = f"org_{uuid.uuid4().hex[:12]}"
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    task_id = f"tsk_{uuid.uuid4().hex[:12]}"
    issue_id = f"iss_{uuid.uuid4().hex[:12]}"
    repo_id = f"rep_{uuid.uuid4().hex[:12]}"

    # Setup database fixture
    async with session_factory() as session:
        user = User(
            id=user_id,
            github_username=f"fleet_{uuid.uuid4().hex[:6]}",
            name="Fleet Admin",
            email="fleet@example.com"
        )
        session.add(user)
        org = Organization(id=org_id, name="Fleet Test Org", slug=org_id, billing_tier="pro")
        session.add(org)
        membership = Membership(user_id=user_id, org_id=org_id, role="owner")
        session.add(membership)
        await session.flush()

        repo = Repository(
            id=repo_id,
            tenant_id=org_id,
            user_id=user_id,
            owner="Pushkar-Shahi",
            name="fleet-repo",
            full_name=f"Pushkar-Shahi/fleet-repo-{uuid.uuid4().hex[:6]}",
            html_url="https://github.com/Pushkar-Shahi/Gsoc_pr_tracker"
        )
        session.add(repo)
        await session.flush()

        issue = Issue(
            id=issue_id,
            tenant_id=org_id,
            user_id=user_id,
            repository_id=repo_id,
            github_id=int(uuid.uuid4().int % 100000000),
            issue_number=1,
            title="Fleet Test Issue",
            html_url="https://github.com/Pushkar-Shahi/Gsoc_pr_tracker/issues/1"
        )
        session.add(issue)
        await session.flush()
        
        # Point worktree to a valid local path for instant validation execution
        task = Task(
            id=task_id,
            tenant_id=org_id,
            user_id=user_id,
            issue_id=issue_id,
            workflow_state="PREPARED",
            worktree_path=str(project_root)
        )
        session.add(task)
        await session.commit()

    token = get_test_token(user_id=user_id, username="fleet_admin", org_id=org_id, tier="pro")
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request validation stream with an instant custom echo command
        async with client.stream(
            "GET",
            f"/api/v1/streaming/tasks/{task_id}/validation?custom_command=echo%20FLEET_STREAM_SUCCESS",
            headers=headers
        ) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

            raw_stream_text = ""
            async for chunk in resp.aiter_text():
                raw_stream_text += chunk
                if '"type": "done"' in chunk:
                    break

            assert "FLEET_STREAM_SUCCESS" in raw_stream_text
            assert '"type": "done"' in raw_stream_text


def test_runner_daemon_argument_parsing():
    """Verify runner.agent argument parsing with flags and default environment variables."""
    args = parse_args([
        "--url", "http://127.0.0.1:8000",
        "--token", "rnt_test_daemon_token_123",
        "--concurrency", "2",
        "--once"
    ])

    assert args.url == "http://127.0.0.1:8000"
    assert args.token == "rnt_test_daemon_token_123"
    assert args.concurrency == 2
    assert args.once is True


@pytest.mark.asyncio
async def test_runner_daemon_payload_execution():
    """Verify standalone runner executes local shell jobs and captures pass/fail status."""
    daemon = RunnerDaemon(
        base_url="http://127.0.0.1:8000",
        token="rnt_mock_runner",
        run_once=True
    )

    # 1. Successful command
    result, logs, err, passed = await daemon.execute_job_payload(
        job_type="custom_command",
        payload={"command": 'python3 -c "print(\'DAEMON_RUN_PASS\')"', "cwd": "."}
    )
    assert passed is True
    assert "DAEMON_RUN_PASS" in logs
    assert err is None
    assert result["exit_code"] == 0

    # 2. Failing command
    fail_result, fail_logs, fail_err, fail_passed = await daemon.execute_job_payload(
        job_type="custom_command",
        payload={"command": 'python3 -c "import sys; sys.exit(42)"', "cwd": "."}
    )
    assert fail_passed is False
    assert fail_result["exit_code"] == 42


def test_antigravity_cloud_bridge_handoff():
    """Verify AntigravityHandoffService generates remote cloud bridge handoff commands."""
    service = AntigravityHandoffService()
    handoff = service.generate_remote_cloud_bridge_command(
        task_id="task_123456789",
        repo_name="Gsoc_pr_tracker",
        branch_name="issue-42-fleet-sandbox"
    )

    assert "agy_command" in handoff
    assert "ssh_tunnel_command" in handoff
    assert "remote_prompt_snippet" in handoff
    
    assert "agy clone-remote" in handoff["agy_command"]
    assert "issue-42-fleet-sandbox" in handoff["agy_command"]
    assert "ssh -N -L" in handoff["ssh_tunnel_command"]
    assert "task_123" in handoff["remote_prompt_snippet"]
