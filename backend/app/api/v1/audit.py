from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import AuditLog
from app.schemas.schemas import AuditLogRead

router = APIRouter(prefix="/audit-logs", tags=["Audit"])

@router.get("", response_model=List[AuditLogRead])
async def list_audit_logs(
    task_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(AuditLog).order_by(desc(AuditLog.created_at))
    if task_id:
        stmt = stmt.where(AuditLog.task_id == task_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.delete("")
async def clear_all_audit_logs(
    db: AsyncSession = Depends(get_db)
):
    """Clear all audit logs / notification history."""
    stmt = delete(AuditLog)
    result = await db.execute(stmt)
    await db.commit()
    return {"status": "success", "cleared": result.rowcount}

@router.delete("/{log_id}")
async def delete_audit_log(
    log_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a single audit log notification."""
    stmt = delete(AuditLog).where(AuditLog.id == log_id)
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "success", "deleted_id": log_id}

