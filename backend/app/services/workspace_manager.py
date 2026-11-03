import logging
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.config import settings
from app.services.workspace_providers import (
    WorkspaceProvider,
    LocalWorktreeProvider,
    EphemeralDockerSandboxProvider,
    WorkspaceProviderFactory,
    is_docker_available
)

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """
    Facade maintaining backward compatibility while delegating to the pluggable
    WorkspaceProvider architecture.
    """
    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        cache_root: Optional[Path] = None,
        provider: Optional[WorkspaceProvider] = None
    ):
        self.workspace_root = workspace_root or settings.WORKSPACE_ROOT
        self.cache_root = cache_root or settings.REPOS_CACHE_DIR
        self.provider = provider or WorkspaceProviderFactory.get_provider()

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
        return await self.provider.prepare_workspace(
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

    async def cleanup_workspace(self, worktree_path: str) -> bool:
        return await self.provider.cleanup_workspace(worktree_path)

    def get_workspace_path(self, task_id: str, repo: str) -> Path:
        return self.provider.get_workspace_path(task_id, repo)
