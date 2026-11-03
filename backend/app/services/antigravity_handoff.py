import os
import sys
import shutil
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class AntigravityHandoffService:
    def __init__(self):
        self.app_paths = settings.ANTIGRAVITY_APP_PATHS
        self.cli_path = settings.AGY_CLI_PATH

    def detect_installation(self) -> Dict[str, Any]:
        """Detects whether Antigravity Desktop or agy CLI is installed on this system."""
        found_app = None
        for path_str in self.app_paths:
            p = Path(path_str)
            if p.exists():
                found_app = str(p)
                break
        
        found_cli = None
        if self.cli_path and Path(self.cli_path).exists():
            found_cli = self.cli_path
        else:
            system_cli = shutil.which("agy")
            if system_cli:
                found_cli = system_cli

        return {
            "os": sys.platform,
            "desktop_app_detected": found_app is not None,
            "desktop_app_path": found_app,
            "cli_detected": found_cli is not None,
            "cli_path": found_cli
        }

    async def open_project_in_antigravity(self, worktree_path: str) -> Dict[str, Any]:
        """
        Attempts to open the prepared workspace in Google Antigravity Desktop
        via macOS 'open -a' or agy CLI, and falls back gracefully.
        """
        p = Path(worktree_path)
        if not p.exists():
            return {
                "success": False,
                "method": "none",
                "message": f"Workspace directory does not exist: {worktree_path}",
                "fallback_prompt": None
            }

        detection = self.detect_installation()
        prompt_path = p / ".antigravity" / "PROMPT.txt"
        prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

        # Strategy 1: macOS 'open -a <desktop_app_path> <worktree>'
        if sys.platform == "darwin" and detection["desktop_app_detected"]:
            app_target = detection["desktop_app_path"] or "Antigravity"
            try:
                proc = await asyncio.create_subprocess_exec(
                    "open", "-a", app_target, str(p),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0:
                    return {
                        "success": True,
                        "method": "desktop_app",
                        "message": f"Successfully launched Antigravity desktop app with workspace '{p.name}'.",
                        "workspace_path": str(p),
                        "fallback_prompt": prompt_text
                    }
                else:
                    logger.warning(f"open -a {app_target} returned code {proc.returncode}: {stderr.decode()}")
            except Exception as e:
                logger.error(f"Error invoking desktop app: {e}")

        # Strategy 2: macOS URL Scheme (antigravity://file/<path>)
        if sys.platform == "darwin":
            try:
                url_scheme = f"antigravity://file/{p.resolve()}"
                proc = await asyncio.create_subprocess_exec(
                    "open", url_scheme,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0:
                    return {
                        "success": True,
                        "method": "url_scheme",
                        "message": f"Opened workspace via Antigravity URL scheme.",
                        "workspace_path": str(p),
                        "fallback_prompt": prompt_text
                    }
            except Exception as e:
                logger.debug(f"URL scheme handoff note: {e}")

        # Strategy 3: Graceful fallback
        return {
            "success": False,
            "method": "manual_fallback",
            "message": "Desktop handoff command could not be invoked directly. Please use the workspace path and prompt below.",
            "workspace_path": str(p),
            "fallback_prompt": prompt_text
        }

    def generate_remote_cloud_bridge_command(
        self,
        task_id: str,
        repo_name: str,
        branch_name: str,
        remote_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates remote Antigravity cloud connection commands for developers connecting
        their local Antigravity instance to an ephemeral cloud worktree.
        """
        target_url = remote_url or f"https://github.com/Pushkar-Shahi/{repo_name}.git"
        return {
            "agy_command": f"agy clone-remote {target_url} --branch {branch_name} --task {task_id[:8]}",
            "ssh_tunnel_command": f"ssh -N -L 8000:localhost:8000 runner@cloud-fleet.issuetopr.dev",
            "remote_prompt_snippet": (
                f"Connect to cloud worktree for task {task_id[:8]} (branch: {branch_name}). "
                f"Execute preflight policy checks and report diffs back to the Issue-to-PR coordinator."
            )
        }
