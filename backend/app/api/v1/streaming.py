import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenant import TenantContext, get_current_tenant
from app.db.database import get_db
from app.models.models import Task, Issue, RunnerJob
from app.services.sandbox_executor import SandboxedExecutionEngine
from app.services.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/streaming", tags=["Streaming & Logs"])


@router.get("/tasks/{task_id}/validation")
async def stream_task_validation(
    task_id: str,
    custom_command: Optional[str] = Query(None),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Server-Sent Events (SSE) endpoint streaming real-time test execution output line-by-line.
    Content-Type: text/event-stream
    """
    stmt = (
        select(Task)
        .options(selectinload(Task.issue).selectinload(Issue.repository))
        .where(Task.id == task_id, Task.tenant_id == ctx.organization.id)
    )
    res = await db.execute(stmt)
    task = res.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found."
        )

    # Auto-prepare workspace if missing
    worktree_path = task.worktree_path
    if not worktree_path or not Path(worktree_path).exists():
        wm = WorkspaceManager()
        prep_res = await wm.prepare_workspace(
            task_id=task.id,
            owner=task.issue.repository.owner,
            repo=task.issue.repository.name,
            clone_url=task.issue.repository.html_url,
            issue_number=task.issue.issue_number,
            issue_title=task.issue.title,
            issue_body=task.issue.body or "",
            default_branch=task.issue.repository.default_branch or "main"
        )
        task.worktree_path = prep_res["worktree_path"]
        task.branch_name = prep_res["branch_name"]
        await db.commit()
        await db.refresh(task)
        worktree_path = task.worktree_path

    p = Path(worktree_path)

    # Determine command
    cmd_to_run = custom_command
    if not cmd_to_run and task.implementation_brief and isinstance(task.implementation_brief, dict):
        cmd_to_run = task.implementation_brief.get("test_strategy", {}).get("command")

    if not cmd_to_run:
        if (p / "pyproject.toml").exists() or (p / "setup.py").exists() or (p / "requirements.txt").exists():
            cmd_to_run = "pytest -q --tb=short || python3 -m unittest discover -s . -p '*test*.py' || python3 -m compileall -q ."
        elif (p / "package.json").exists():
            cmd_to_run = "npm test --if-present"
        elif (p / "Cargo.toml").exists():
            cmd_to_run = "cargo test"
        elif (p / "go.mod").exists():
            cmd_to_run = "go test ./..."
        else:
            cmd_to_run = "git status"

    logger.info(f"Opening live SSE validation stream for task {task_id}: {cmd_to_run}")

    return StreamingResponse(
        SandboxedExecutionEngine.stream_command(cmd_to_run, p, timeout_sec=120.0),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/runners/jobs/{job_id}")
async def stream_runner_job_logs(
    job_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Streams live execution logs for an active or completed runner job via SSE."""
    stmt = select(RunnerJob).where(
        RunnerJob.id == job_id,
        RunnerJob.tenant_id == ctx.organization.id
    )
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Runner job {job_id} not found."
        )

    async def _job_log_generator():
        yield f"data: {json.dumps({'type': 'job_info', 'job_id': job.id, 'status': job.status, 'job_type': job.job_type})}\n\n"
        if job.logs:
            for line in job.logs.splitlines():
                yield f"data: {json.dumps({'type': 'stdout', 'text': line})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'status': job.status, 'has_error': bool(job.error_message)})}\n\n"

    return StreamingResponse(
        _job_log_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
