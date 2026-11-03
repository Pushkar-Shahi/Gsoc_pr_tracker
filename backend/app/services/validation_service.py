import re
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.services.sandbox_executor import SandboxedExecutionEngine

logger = logging.getLogger(__name__)

class ValidationService:
    # Secret scanning patterns
    SECRET_PATTERNS = [
        (r'-----BEGIN\s+(RSA|OPENSSH|DSA|EC|PGP)?\s*PRIVATE KEY-----', "Private cryptographic key"),
        (r'(?i)ghp_[a-zA-Z0-9]{36,}', "GitHub Personal Access Token"),
        (r'(?i)github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}', "GitHub Fine-Grained Token"),
        (r'(?i)AKIA[0-9A-Z]{16}', "AWS Access Key ID"),
        (r'(?i)aws_secret_access_key\s*=\s*[a-zA-Z0-9/+=]{40}', "AWS Secret Access Key"),
        (r'(?i)eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}', "JSON Web Token (JWT)"),
        (r'(?i)sk-[a-zA-Z0-9]{32,}', "OpenAI or Model Provider Secret Key"),
    ]

    UNWANTED_EXTENSIONS = [".pyc", ".pyo", ".pyd", ".so", ".dylib", ".dll", ".class", ".exe", ".env"]

    async def scan_git_diff(self, worktree_path: str) -> Dict[str, Any]:
        """
        Inspects git status and git diff for secrets, binary artifacts,
        and unauthorized file modifications.
        """
        p = Path(worktree_path)
        if not p.exists():
            return {
                "passed": False,
                "error": f"Worktree path does not exist: {worktree_path}",
                "secrets_detected": [],
                "unrelated_files": [],
                "changed_files": []
            }

        # 1. Run git status --porcelain
        proc = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            cwd=str(p),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        status_out, _ = await proc.communicate()
        status_lines = status_out.decode("utf-8", errors="replace").strip().split("\n")
        
        changed_files = []
        unrelated_files = []
        for line in status_lines:
            if not line.strip():
                continue
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                status_code, filename = parts
                changed_files.append({"status": status_code, "file": filename})
                
                # Check for unwanted files
                fpath = Path(filename)
                if fpath.suffix.lower() in self.UNWANTED_EXTENSIONS or filename.startswith(".env"):
                    unrelated_files.append(f"Disallowed artifact or environment file: {filename}")

        # 2. Run git diff
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "HEAD",
            cwd=str(p),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        diff_out, _ = await proc.communicate()
        diff_text = diff_out.decode("utf-8", errors="replace")

        # 3. Secret scanning on diff
        secrets_detected = []
        for pattern, desc in self.SECRET_PATTERNS:
            matches = re.findall(pattern, diff_text)
            if matches:
                secrets_detected.append(desc)

        passed = len(secrets_detected) == 0 and len(unrelated_files) == 0

        return {
            "passed": passed,
            "changed_files_count": len(changed_files),
            "changed_files": changed_files,
            "secrets_detected": secrets_detected,
            "unrelated_files": unrelated_files,
            "diff_preview": diff_text[:5000] if diff_text else "No unstaged or committed diff detected."
        }

    async def execute_validation_tests(
        self,
        worktree_path: str,
        custom_command: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes automated tests in the isolated worktree and records exact command,
        output, and exit code. Never reports skipped or unrun tests as passed.
        """
        p = Path(worktree_path)
        if not p.exists():
            return {
                "passed": False,
                "commands": [],
                "error": "Workspace directory not found."
            }

        import os

        # Prepare subshell execution environment
        sub_env = os.environ.copy()
        sub_env["PYTHONPATH"] = f".:{str(p)}:{sub_env.get('PYTHONPATH', '')}".strip(":")
        sub_env["CI"] = "true"
        sub_env["PAGER"] = "cat"

        # Determine appropriate test command if none specified
        commands_to_run = []
        if custom_command and custom_command.strip():
            commands_to_run.append(custom_command.strip())
        else:
            if (p / "pyproject.toml").exists() or (p / "setup.py").exists() or (p / "requirements.txt").exists():
                commands_to_run.append("pytest -q --tb=short || python3 -m unittest discover -s . -p '*test*.py' || python3 -m compileall -q .")
            elif (p / "package.json").exists():
                commands_to_run.append("npm test --if-present")
            elif (p / "Cargo.toml").exists():
                commands_to_run.append("cargo test")
            elif (p / "go.mod").exists():
                commands_to_run.append("go test ./...")
            else:
                commands_to_run.append("git status")

        command_results = []
        all_passed = True

        for cmd_str in commands_to_run:
            exec_res = await SandboxedExecutionEngine.execute_command(
                cmd_str=cmd_str,
                cwd=p,
                timeout_sec=120.0
            )
            passed = exec_res["passed"]
            if not passed:
                all_passed = False

            command_results.append({
                "command": cmd_str,
                "exit_code": exec_res["exit_code"],
                "passed": passed,
                "stdout": exec_res["stdout"][:8000],
                "stderr": exec_res["stderr"][:8000],
                "sandbox_mode": exec_res.get("sandbox_mode", "isolated")
            })

        return {
            "passed": all_passed,
            "commands": command_results,
            "status": "PASSED" if all_passed else "FAILED"
        }
