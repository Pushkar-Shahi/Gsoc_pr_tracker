import hashlib
import logging
import secrets
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import get_current_tenant, TenantContext, _decode_claims_from_token
from app.db.database import get_db
from app.models.models import Runner, RunnerJob, Task
from app.schemas.schemas import (
    RunnerRegisterRequest,
    RunnerRegisterResponse,
    RunnerHeartbeatRequest,
    RunnerJobRead,
    RunnerJobCompleteRequest,
    RunnerRead,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runners", tags=["runners"])


def _extract_bearer_token(request: Request) -> str:
    """Extracts bearer token from Authorization header or raises HTTP 401."""
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header."
        )
    return auth.split("Bearer ", 1)[1].strip()


@router.post("/register", response_model=RunnerRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_runner(
    payload: RunnerRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Registers a new local runner and pairs it with the authenticated tenant.
    Generates a persistent revokable token starting with 'rnt_'.
    """
    reg_token = payload.registration_token
    if not reg_token:
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            reg_token = auth.split("Bearer ", 1)[1].strip()

    if not reg_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration token is required."
        )

    claims = _decode_claims_from_token(reg_token)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired registration token."
        )

    tenant_id = claims.get("tenant_id") or claims.get("org_id") or "default-org"
    user_id = claims.get("user_id") or claims.get("sub") or "default-user"

    runner_id = str(uuid.uuid4())
    runner_token = f"rnt_{secrets.token_hex(24)}"
    token_hash = hashlib.sha256(runner_token.encode("utf-8")).hexdigest()

    runner = Runner(
        id=runner_id,
        tenant_id=tenant_id,
        user_id=user_id,
        name=payload.name,
        os_info=payload.os_info,
        status="idle",
        runner_token=runner_token,
        token_hash=token_hash,
        registration_token=reg_token,
        system_stats={},
        is_active=True,
        last_heartbeat_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(runner)
    await db.commit()
    await db.refresh(runner)

    logger.info(f"Registered new runner {runner.id} ({runner.name}) for tenant {tenant_id}")
    return RunnerRegisterResponse(runner_id=runner.id, runner_token=runner_token)


@router.post("/{runner_id}/heartbeat")
async def runner_heartbeat(
    runner_id: str,
    payload: RunnerHeartbeatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Updates runner heartbeat timestamp, active status, and reported system stats.
    Rejects revoked or unauthorized runners.
    """
    token = _extract_bearer_token(request)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    stmt = select(Runner).where(Runner.id == runner_id)
    res = await db.execute(stmt)
    runner = res.scalar_one_or_none()

    if not runner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Runner {runner_id} not found."
        )

    if not runner.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Runner access has been revoked."
        )

    if runner.runner_token != token and runner.token_hash != token_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid runner authentication token."
        )

    runner.last_heartbeat_at = datetime.utcnow()
    if payload.status:
        runner.status = payload.status
    if payload.system_stats is not None:
        runner.system_stats = payload.system_stats
    runner.updated_at = datetime.utcnow()

    await db.commit()
    return {"status": "ok"}


@router.get("/jobs/poll", response_model=Optional[RunnerJobRead])
async def poll_runner_jobs(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Polls next available queued job strictly scoped to the runner's paired tenant.
    Returns HTTP 200 with job payload or HTTP 204 No Content.
    """
    token = _extract_bearer_token(request)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    stmt = select(Runner).where(
        or_(Runner.runner_token == token, Runner.token_hash == token_hash)
    )
    res = await db.execute(stmt)
    runner = res.scalar_one_or_none()

    if not runner or not runner.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked runner token."
        )

    runner.last_heartbeat_at = datetime.utcnow()

    # Query oldest queued job strictly scoped to runner's tenant
    job_stmt = (
        select(RunnerJob)
        .where(
            RunnerJob.tenant_id == runner.tenant_id,
            RunnerJob.status == "queued"
        )
        .order_by(RunnerJob.created_at.asc())
        .limit(1)
    )
    job_res = await db.execute(job_stmt)
    job = job_res.scalar_one_or_none()

    if not job:
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    job.status = "running"
    job.runner_id = runner.id
    job.started_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(job)
    return RunnerJobRead.model_validate(job)


@router.post("/jobs/{job_id}/complete")
async def complete_runner_job(
    job_id: str,
    payload: RunnerJobCompleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Acknowledges completion of a runner execution job, updating results and logs.
    """
    token = _extract_bearer_token(request)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    runner_stmt = select(Runner).where(
        or_(Runner.runner_token == token, Runner.token_hash == token_hash)
    )
    runner_res = await db.execute(runner_stmt)
    runner = runner_res.scalar_one_or_none()

    if not runner or not runner.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked runner token."
        )

    job_stmt = select(RunnerJob).where(RunnerJob.id == job_id)
    job_res = await db.execute(job_stmt)
    job = job_res.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Runner job {job_id} not found."
        )

    if job.tenant_id != runner.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant job completion denied."
        )

    job.status = payload.status or "completed"
    if payload.result is not None:
        job.result = payload.result
    if payload.error_message:
        job.error_message = payload.error_message
    if payload.logs:
        job.logs = payload.logs
    job.completed_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()

    await db.commit()
    return {"status": "ok", "job_id": job.id}


@router.delete("/{runner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_runner(
    runner_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Revokes a runner's credentials and disables future heartbeat/polling access.
    """
    stmt = select(Runner).where(Runner.id == runner_id)
    res = await db.execute(stmt)
    runner = res.scalar_one_or_none()

    if not runner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Runner {runner_id} not found."
        )

    if runner.tenant_id != ctx.organization.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Runner {runner_id} not found."
        )

    runner.is_active = False
    runner.status = "revoked"
    runner.updated_at = datetime.utcnow()

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=List[RunnerRead])
async def list_runners(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Lists runners paired with the tenant, computing offline status if last heartbeat > 90s.
    """
    stmt = select(Runner).where(Runner.tenant_id == ctx.organization.id)
    stmt = stmt.order_by(Runner.created_at.desc())

    res = await db.execute(stmt)
    runners = res.scalars().all()

    now = datetime.utcnow()
    output = []
    for r in runners:
        current_status = r.status
        if r.is_active and r.status != "revoked" and r.last_heartbeat_at:
            if (now - r.last_heartbeat_at).total_seconds() > 90:
                current_status = "offline"

        output.append(RunnerRead(
            id=r.id,
            name=r.name,
            os_info=r.os_info,
            status=current_status,
            system_stats=r.system_stats,
            last_heartbeat_at=r.last_heartbeat_at,
            is_active=r.is_active,
            created_at=r.created_at
        ))

    return output
