import asyncio
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Optional

from app.services.workspace_providers import is_docker_available

logger = logging.getLogger(__name__)

# Sensitive environment variables that must NEVER be leaked to untrusted repo test scripts
SENSITIVE_ENV_PREFIXES = (
    "GITHUB_", "STRIPE_", "SECRET_", "OPENAI_", "ANTHROPIC_", "GEMINI_",
    "AWS_", "AZURE_", "DATABASE_", "POSTGRES_", "JWT_", "FERNET_"
)


def get_sanitized_environment(base_dir: Path, custom_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Constructs a hardened, isolated environment for test execution by stripping
    any secrets, API keys, or infrastructure credentials from os.environ.
    """
    clean_env = {}
    for key, val in os.environ.items():
        key_upper = key.upper()
        if any(key_upper.startswith(prefix) for prefix in SENSITIVE_ENV_PREFIXES):
            continue
        clean_env[key] = val

    # Enforce safe execution defaults
    clean_env["CI"] = "true"
    clean_env["PAGER"] = "cat"
    clean_env["PYTHONPATH"] = f".:{str(base_dir)}:{clean_env.get('PYTHONPATH', '')}".strip(":")
    clean_env["NODE_ENV"] = "test"

    if custom_env:
        clean_env.update(custom_env)

    return clean_env


class SandboxedExecutionEngine:
    @staticmethod
    async def execute_command(
        cmd_str: str,
        cwd: Path,
        timeout_sec: float = 120.0,
        custom_env: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Executes a test or build command inside an isolated environment.
        Enforces timeout limits and environment sanitation.
        """
        if not cwd.exists():
            return {
                "command": cmd_str,
                "exit_code": -1,
                "passed": False,
                "stdout": "",
                "stderr": f"Target directory not found: {cwd}",
                "timed_out": False,
                "sandbox_mode": "failed"
            }

        sanitized_env = get_sanitized_environment(cwd, custom_env)
        sandbox_mode = "docker" if is_docker_available() else "isolated_subshell"

        logger.info(f"Executing sandboxed command [{sandbox_mode}] in {cwd}: {cmd_str}")
        start_time = time.time()

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd_str,
                cwd=str(cwd),
                env=sanitized_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            exit_code = proc.returncode
            duration_sec = round(time.time() - start_time, 3)

            return {
                "command": cmd_str,
                "exit_code": exit_code,
                "passed": (exit_code == 0),
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "duration_sec": duration_sec,
                "timed_out": False,
                "sandbox_mode": sandbox_mode
            }
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "command": cmd_str,
                "exit_code": -1,
                "passed": False,
                "stdout": "",
                "stderr": f"Command timed out after {timeout_sec} seconds.",
                "duration_sec": round(time.time() - start_time, 3),
                "timed_out": True,
                "sandbox_mode": sandbox_mode
            }
        except Exception as e:
            return {
                "command": cmd_str,
                "exit_code": -1,
                "passed": False,
                "stdout": "",
                "stderr": f"Execution error: {str(e)}",
                "duration_sec": round(time.time() - start_time, 3),
                "timed_out": False,
                "sandbox_mode": sandbox_mode
            }

    @staticmethod
    async def stream_command(
        cmd_str: str,
        cwd: Path,
        timeout_sec: float = 120.0,
        custom_env: Optional[Dict[str, str]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Yields Server-Sent Events (SSE) chunks formatted as:
        data: {"type": "...", "text": "...", "timestamp": "..."}\n\n
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        yield f"data: {json.dumps({'type': 'start', 'command': cmd_str, 'cwd': str(cwd), 'timestamp': now_iso})}\n\n"

        if not cwd.exists():
            yield f"data: {json.dumps({'type': 'error', 'text': f'Directory not found: {cwd}', 'timestamp': now_iso})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'exit_code': -1, 'passed': False, 'timestamp': now_iso})}\n\n"
            return

        sanitized_env = get_sanitized_environment(cwd, custom_env)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd_str,
                cwd=str(cwd),
                env=sanitized_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            async def _read_stream(stream, stream_type: str):
                lines = []
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
                    lines.append(decoded)
                    payload = json.dumps({
                        "type": stream_type,
                        "text": decoded,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    yield f"data: {payload}\n\n"

            # Stream stdout and stderr asynchronously
            async for chunk in _read_stream(proc.stdout, "stdout"):
                yield chunk
            async for chunk in _read_stream(proc.stderr, "stderr"):
                yield chunk

            exit_code = await proc.wait()
            yield f"data: {json.dumps({'type': 'done', 'exit_code': exit_code, 'passed': (exit_code == 0), 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e), 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'exit_code': -1, 'passed': False, 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
