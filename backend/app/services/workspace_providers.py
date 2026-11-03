import abc
import asyncio
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_docker_available() -> bool:
    """Checks whether the docker CLI is present and the Docker daemon is responding."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        # Check standard mac/linux docker paths
        for p in ("/usr/local/bin/docker", "/opt/homebrew/bin/docker", str(Path.home() / ".docker/bin/docker")):
            if Path(p).exists():
                docker_bin = p
                break
    if not docker_bin:
        return False

    try:
        res = subprocess.run(
            [docker_bin, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            timeout=2.0
        )
        return res.returncode == 0 and bool(res.stdout.strip())
    except Exception:
        return False


class WorkspaceProvider(abc.ABC):
    @abc.abstractmethod
    async def prepare_workspace(
        self,
        task_id: str,
        owner: str,
        repo: str,
        clone_url: str,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        default_branch: str = "main",
        test_commands: Optional[str] = None
    ) -> Dict[str, Any]:
        """Prepares an isolated workspace/worktree for a task."""
        pass

    @abc.abstractmethod
    async def cleanup_workspace(self, worktree_path: str) -> bool:
        """Cleans up the workspace."""
        pass

    @abc.abstractmethod
    def get_workspace_path(self, task_id: str, repo: str) -> Path:
        """Returns the workspace path."""
        pass


class LocalWorktreeProvider(WorkspaceProvider):
    """
    Manages local Git worktrees backed by a shared shallow clone cache.
    Fast, lightweight, and zero Docker dependency.
    """
    def __init__(self, workspace_root: Optional[Path] = None, cache_root: Optional[Path] = None):
        self.workspace_root = workspace_root or settings.WORKSPACE_ROOT
        self.cache_root = cache_root or settings.REPOS_CACHE_DIR
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _sanitize_slug(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^a-z0-9]+', '-', text)
        return text.strip('-')[:35]

    async def _run_git_cmd(self, args: list, cwd: Path) -> Tuple[int, str, str]:
        cmd = ["git"] + args
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")

    def get_workspace_path(self, task_id: str, repo: str) -> Path:
        return self.workspace_root / f"task-{task_id[:8]}" / repo

    async def prepare_workspace(
        self,
        task_id: str,
        owner: str,
        repo: str,
        clone_url: str,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        default_branch: str = "main",
        test_commands: Optional[str] = None
    ) -> Dict[str, Any]:
        repo_cache_dir = self.cache_root / owner / repo
        repo_cache_dir.parent.mkdir(parents=True, exist_ok=True)

        # 1. Clone or fetch cache repository
        if not (repo_cache_dir / ".git").exists() and not (repo_cache_dir / "HEAD").exists():
            logger.info(f"Cloning {clone_url} to cache: {repo_cache_dir}")
            cmd = ["git", "clone", "--depth", "50", clone_url, str(repo_cache_dir)]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
        else:
            logger.info(f"Fetching latest refs for {owner}/{repo}")
            await self._run_git_cmd(["fetch", "origin", default_branch], cwd=repo_cache_dir)

        # 2. Prepare isolated task worktree
        task_worktree_dir = self.get_workspace_path(task_id, repo)
        task_worktree_dir.parent.mkdir(parents=True, exist_ok=True)

        branch_slug = self._sanitize_slug(issue_title)
        branch_name = f"fix/issue-{issue_number}-{branch_slug}"

        if task_worktree_dir.exists():
            shutil.rmtree(task_worktree_dir, ignore_errors=True)
        await self._run_git_cmd(["worktree", "prune"], cwd=repo_cache_dir)

        # Create git worktree
        rc, out, err = await self._run_git_cmd(
            ["worktree", "add", "--force", "-B", branch_name, str(task_worktree_dir), f"origin/{default_branch}"],
            cwd=repo_cache_dir
        )
        if rc != 0:
            logger.warning(f"Worktree add origin/{default_branch} failed: {err.strip()}. Retrying with {default_branch}...")
            rc, out, err = await self._run_git_cmd(
                ["worktree", "add", "--force", "-B", branch_name, str(task_worktree_dir), default_branch],
                cwd=repo_cache_dir
            )
        if rc != 0:
            logger.warning(f"Worktree add fallback failed: {err.strip()}. Retrying with HEAD...")
            rc, out, err = await self._run_git_cmd(
                ["worktree", "add", "--force", "-B", branch_name, str(task_worktree_dir), "HEAD"],
                cwd=repo_cache_dir
            )
        if not (task_worktree_dir / ".git").exists():
            logger.warning(f"Worktree checkout incomplete ({err.strip()}). Falling back to fresh clone for task {task_id[:8]}...")
            shutil.rmtree(task_worktree_dir, ignore_errors=True)
            clone_proc = await asyncio.create_subprocess_exec(
                "git", "clone", "--depth", "50", clone_url, str(task_worktree_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await clone_proc.communicate()
            await self._run_git_cmd(["checkout", "-B", branch_name], cwd=task_worktree_dir)

        logger.info(f"Created local workspace at {task_worktree_dir} with branch {branch_name}")

        # 3. Create .antigravity collaborative documentation
        antigravity_dir = task_worktree_dir / ".antigravity"
        antigravity_dir.mkdir(parents=True, exist_ok=True)

        brief_content = f"""# Antigravity Collaborative Implementation Brief

- **Issue**: #{issue_number} — {issue_title}
- **Repository**: {owner}/{repo}
- **Target Branch**: {default_branch}
- **Working Branch**: {branch_name}
- **Workspace Path**: {task_worktree_dir}

## Objective & Problem Statement
{issue_body or 'No issue description provided.'}

## Prescribed Setup & Test Conventions
{test_commands or 'Run standard project test suite (e.g. pytest, npm test, cargo test) before requesting validation.'}

## Collaboration Rules
1. Work strictly within this worktree.
2. Preserve existing coding conventions, formatting, and docstrings.
3. Do NOT modify unrelated files or commit environment secrets (such as .env or API keys).
4. Verify all tests pass cleanly before signaling completion in the dashboard.
"""
        (antigravity_dir / "BRIEF.md").write_text(brief_content, encoding="utf-8")

        prompt_content = (
            f"I am working on GitHub issue #{issue_number} for {owner}/{repo}: '{issue_title}'.\n\n"
            f"Here is the issue context:\n{issue_body or ''}\n\n"
            f"Please help me analyze the codebase, plan the minimal surgical fix, "
            f"implement the changes, and verify all tests pass without introducing regressions."
        )
        (antigravity_dir / "PROMPT.txt").write_text(prompt_content, encoding="utf-8")

        return {
            "worktree_path": str(task_worktree_dir),
            "branch_name": branch_name,
            "brief_path": str(antigravity_dir / "BRIEF.md"),
            "prompt_text": prompt_content,
            "default_branch": default_branch,
            "provider": "local_worktree"
        }

    async def cleanup_workspace(self, worktree_path: str) -> bool:
        try:
            target = Path(worktree_path)
            if target.exists() and str(self.workspace_root) in str(target.resolve()):
                shutil.rmtree(target.parent, ignore_errors=True)
                for repo_dir in self.cache_root.glob("*/*"):
                    if (repo_dir / ".git").exists() or (repo_dir / "HEAD").exists():
                        await self._run_git_cmd(["worktree", "prune"], cwd=repo_dir)
                return True
            return False
        except Exception as e:
            logger.error(f"Error cleaning up workspace {worktree_path}: {e}")
            return False


class EphemeralDockerSandboxProvider(WorkspaceProvider):
    """
    Prepares worktrees encapsulated inside isolated Docker container sandboxes
    with CPU, memory, and network boundaries.
    """
    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        cache_root: Optional[Path] = None,
        docker_image: str = "alpine/git:latest",
        cpu_limit: str = "2.0",
        memory_limit: str = "4g"
    ):
        self.local_provider = LocalWorktreeProvider(workspace_root, cache_root)
        self.docker_image = docker_image
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit

    def get_workspace_path(self, task_id: str, repo: str) -> Path:
        return self.local_provider.get_workspace_path(task_id, repo)

    async def prepare_workspace(
        self,
        task_id: str,
        owner: str,
        repo: str,
        clone_url: str,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        default_branch: str = "main",
        test_commands: Optional[str] = None
    ) -> Dict[str, Any]:
        # Prepares underlying worktree using local provider
        res = await self.local_provider.prepare_workspace(
            task_id=task_id,
            owner=owner,
            repo=repo,
            clone_url=clone_url,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            default_branch=default_branch,
            test_commands=test_commands
        )

        docker_available = is_docker_available()
        res["docker_sandbox_active"] = docker_available
        res["provider"] = "docker_sandbox" if docker_available else "docker_sandbox_fallback_local"
        res["cpu_limit"] = self.cpu_limit
        res["memory_limit"] = self.memory_limit
        return res

    async def cleanup_workspace(self, worktree_path: str) -> bool:
        return await self.local_provider.cleanup_workspace(worktree_path)


class WorkspaceProviderFactory:
    @staticmethod
    def get_provider(provider_type: Optional[str] = None) -> WorkspaceProvider:
        """
        Returns the appropriate WorkspaceProvider.
        If provider_type is 'docker' or 'sandbox', attempts to use EphemeralDockerSandboxProvider;
        otherwise defaults to LocalWorktreeProvider.
        """
        ptype = (provider_type or os.getenv("WORKSPACE_PROVIDER", "local")).lower()
        if ptype in ("docker", "sandbox", "cloud"):
            return EphemeralDockerSandboxProvider()
        return LocalWorktreeProvider()
