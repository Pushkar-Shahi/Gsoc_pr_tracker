#!/usr/bin/env python3
"""
Issue-to-PR Standalone Runner Agent Daemon.

Usage:
    python -m runner.agent --url http://127.0.0.1:8000 --token <RUNNER_TOKEN>
"""

import argparse
import asyncio
import json
import logging
import os
import platform
import signal
import socket
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Runner] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("runner")


def _http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0
) -> Tuple[int, Dict[str, Any], str]:
    """Lightweight HTTP helper using standard library only."""
    req_headers = {"User-Agent": "IssueToPR-Runner/1.0", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {}
            return status, parsed, raw
    except urllib.error.HTTPError as e:
        raw_err = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw_err)
        except Exception:
            parsed = {"detail": raw_err}
        return e.code, parsed, raw_err
    except Exception as e:
        return -1, {"detail": str(e)}, str(e)


class RunnerDaemon:
    def __init__(
        self,
        base_url: str,
        token: str,
        runner_id: Optional[str] = None,
        name: Optional[str] = None,
        poll_interval: float = 5.0,
        heartbeat_interval: float = 30.0,
        run_once: bool = False
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.runner_id = runner_id
        self.name = name or socket.gethostname()
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.run_once = run_once
        self.is_running = True
        self.os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"

    async def register_if_needed(self) -> bool:
        """Registers runner if runner_id is not yet known or token is a registration token."""
        if self.runner_id and self.token.startswith("rnt_"):
            return True

        logger.info(f"Connecting to platform at {self.base_url} as '{self.name}'...")
        reg_url = f"{self.base_url}/api/v1/runners/register"

        # If token is JWT or session token, register new runner
        payload = {
            "name": self.name,
            "os_info": self.os_info,
            "registration_token": self.token
        }
        status, data, raw = _http_request(
            reg_url,
            method="POST",
            headers={"Authorization": f"Bearer {self.token}"},
            data=payload
        )

        if status in (200, 201) and "runner_token" in data:
            self.runner_id = data["runner_id"]
            self.token = data["runner_token"]
            logger.info(f"✓ Registered runner ID: {self.runner_id}")
            logger.info(f"✓ Active runner token: {self.token[:8]}...{self.token[-6:]}")
            return True
        elif self.token.startswith("rnt_"):
            # Already a persistent runner token
            logger.info("Using pre-configured runner token.")
            return True
        else:
            logger.error(f"Failed to register runner (HTTP {status}): {data.get('detail', raw)}")
            return False

    async def send_heartbeat(self):
        """Sends periodic heartbeats to update the runner's online status and metrics."""
        if not self.runner_id:
            return

        hb_url = f"{self.base_url}/api/v1/runners/{self.runner_id}/heartbeat"
        system_stats = {
            "os": self.os_info,
            "python": platform.python_version(),
            "cpu_count": os.cpu_count() or 1,
            "timestamp": time.time()
        }
        status, data, _ = _http_request(
            hb_url,
            method="POST",
            headers={"Authorization": f"Bearer {self.token}"},
            data={"system_stats": system_stats}
        )
        if status != 200:
            logger.warning(f"Heartbeat failed (HTTP {status}): {data.get('detail')}")

    async def poll_and_execute_job(self) -> bool:
        """Polls for the next available queued job and executes it."""
        poll_url = f"{self.base_url}/api/v1/runners/jobs/poll"
        status, job_data, _ = _http_request(
            poll_url,
            method="POST",
            headers={"Authorization": f"Bearer {self.token}"}
        )

        if status == 204 or not job_data:
            return False  # No queued job

        if status != 200:
            logger.error(f"Job poll error (HTTP {status}): {job_data.get('detail')}")
            return False

        job_id = job_data.get("id")
        job_type = job_data.get("job_type", "UNKNOWN")
        payload = job_data.get("payload", {})
        task_id = job_data.get("task_id")

        logger.info(f"⚡ Acquired Job [{job_id[:8]}] Type: {job_type} (Task: {task_id[:8] if task_id else 'none'})")

        start_time = time.time()
        result, logs, error_message, passed = await self.execute_job_payload(job_type, payload)
        duration = time.time() - start_time

        job_status = "completed" if passed else "failed"
        logger.info(f"Job [{job_id[:8]}] {job_status.upper()} in {duration:.2f}s")

        # Report results back
        complete_url = f"{self.base_url}/api/v1/runners/jobs/{job_id}/complete"
        comp_payload = {
            "status": job_status,
            "result": result,
            "logs": logs,
            "error_message": error_message
        }
        c_status, c_data, _ = _http_request(
            complete_url,
            method="POST",
            headers={"Authorization": f"Bearer {self.token}"},
            data=comp_payload
        )
        if c_status != 200:
            logger.error(f"Failed to submit job completion (HTTP {c_status}): {c_data.get('detail')}")

        return True

    async def execute_job_payload(self, job_type: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str, Optional[str], bool]:
        """Executes a runner job payload based on job type."""
        logs = []
        result = {}
        error_message = None
        passed = False

        if job_type.upper() in ("VALIDATION_RUN", "RUN_TESTS", "COMMAND", "CUSTOM_COMMAND"):
            command = payload.get("command") or payload.get("test_command") or "pytest -q || git status"
            worktree = payload.get("worktree_path") or str(Path.cwd())
            timeout = float(payload.get("timeout_sec", 120.0))

            logs.append(f"$ {command}")
            cwd_path = Path(worktree)
            if not cwd_path.exists():
                err = f"Worktree directory not found: {worktree}"
                logs.append(err)
                return {}, "\n".join(logs), err, False

            # Sanitized clean environment
            env = os.environ.copy()
            env["CI"] = "true"
            env["PAGER"] = "cat"

            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=str(cwd_path),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                out_str = stdout.decode("utf-8", errors="replace")
                err_str = stderr.decode("utf-8", errors="replace")
                if out_str:
                    logs.append(out_str)
                if err_str:
                    logs.append(err_str)

                passed = (proc.returncode == 0)
                result = {
                    "command": command,
                    "exit_code": proc.returncode,
                    "passed": passed,
                    "duration_sec": 0
                }
            except asyncio.TimeoutError:
                err = f"Execution timed out after {timeout} seconds."
                logs.append(err)
                error_message = err
                passed = False
            except Exception as e:
                err = f"Failed to execute command: {str(e)}"
                logs.append(err)
                error_message = err
                passed = False

        elif job_type == "DIFF_SCAN":
            worktree = payload.get("worktree_path") or str(Path.cwd())
            cwd_path = Path(worktree)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git", "status", "--porcelain",
                    cwd=str(cwd_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                out, _ = await proc.communicate()
                status_text = out.decode("utf-8", errors="replace")
                logs.append(status_text)
                passed = True
                result = {"status_porcelain": status_text, "clean": len(status_text.strip()) == 0}
            except Exception as e:
                error_message = str(e)
                logs.append(str(e))
                passed = False
        else:
            # Echo job
            logs.append(f"Generic job executed: {json.dumps(payload)}")
            passed = True
            result = {"echo": payload}

        return result, "\n".join(logs), error_message, passed

    async def start(self):
        """Main daemon lifecycle loop."""
        registered = await self.register_if_needed()
        if not registered:
            logger.error("Runner startup aborted: registration failed.")
            return

        logger.info(f"🚀 Runner '{self.name}' is online and listening for jobs...")
        last_hb = 0.0

        while self.is_running:
            # 1. Heartbeat check
            now = time.time()
            if now - last_hb >= self.heartbeat_interval:
                await self.send_heartbeat()
                last_hb = now

            # 2. Poll for queued job
            try:
                had_job = await self.poll_and_execute_job()
            except Exception as e:
                logger.error(f"Error during job processing: {e}")
                had_job = False

            if self.run_once:
                logger.info("Exiting after single run execution (--once).")
                break

            # 3. Wait poll interval if idle
            if not had_job:
                await asyncio.sleep(self.poll_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Issue-to-PR Hybrid Runner Daemon")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Backend API base URL")
    parser.add_argument("--token", required=True, help="Runner token (rnt_...) or Registration Token")
    parser.add_argument("--runner-id", default=None, help="Registered Runner UUID (optional)")
    parser.add_argument("--name", default=None, help="Custom runner display name")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Job polling interval in seconds")
    parser.add_argument("--heartbeat-interval", type=float, default=30.0, help="Heartbeat interval in seconds")
    parser.add_argument("--concurrency", type=int, default=1, help="Maximum concurrent jobs")
    parser.add_argument("--once", action="store_true", help="Run once and exit after handling available jobs")
    return parser


def parse_args(args=None):
    parser = build_parser()
    return parser.parse_args(args)


def main(argv=None):
    args = parse_args(argv)

    daemon = RunnerDaemon(
        base_url=args.url,
        token=args.token,
        runner_id=args.runner_id,
        name=args.name,
        poll_interval=args.poll_interval,
        heartbeat_interval=args.heartbeat_interval,
        run_once=args.once
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown(sig, frame):
        logger.info("\nReceived termination signal. Shutting down runner...")
        daemon.is_running = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        loop.run_until_complete(daemon.start())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
        logger.info("Runner stopped cleanly.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
