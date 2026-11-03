import csv
import io
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy import select, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import AuditLog
from app.schemas.schemas import AuditLogRead
from app.core.tenant import TenantContext, get_current_tenant

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get("/export")
async def export_audit_logs(
    format: str = Query("csv", description="csv or json / siem"),
    limit: int = Query(1000, ge=1, le=5000),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Exports immutable audit trail logs for enterprise SIEM ingestion (Splunk, Datadog)
    or corporate compliance auditing. Formats: CSV (RFC 4180) or NDJSON.
    """
    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == ctx.organization.id)
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
    )
    res = await db.execute(stmt)
    logs = res.scalars().all()

    slug = ctx.organization.slug or "default"

    if format.lower() == "csv":
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["id", "created_at", "actor", "action", "task_id", "issue_id", "details"])
        for l in logs:
            writer.writerow([
                l.id,
                l.created_at.isoformat() if l.created_at else "",
                l.actor,
                l.action,
                l.task_id or "",
                l.issue_id or "",
                json.dumps(l.details or {})
            ])
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="audit_logs_{slug}.csv"'}
        )
    else:
        # SIEM JSON / NDJSON export
        records = []
        for l in logs:
            records.append({
                "id": l.id,
                "tenant_id": l.tenant_id,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "actor": l.actor,
                "action": l.action,
                "task_id": l.task_id,
                "issue_id": l.issue_id,
                "details": l.details or {}
            })
        json_content = json.dumps(records, indent=2)
        return Response(
            content=json_content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="audit_logs_{slug}_siem.json"'}
        )


@router.get("", response_model=List[AuditLogRead])
async def list_audit_logs(
    task_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(AuditLog).where(
        AuditLog.tenant_id == ctx.organization.id
    ).order_by(desc(AuditLog.created_at))
    if task_id:
        stmt = stmt.where(AuditLog.task_id == task_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.delete("")
async def clear_all_audit_logs(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Clear all audit logs / notification history for the current tenant."""
    stmt = delete(AuditLog).where(AuditLog.tenant_id == ctx.organization.id)
    result = await db.execute(stmt)
    await db.commit()
    return {"status": "success", "cleared": result.rowcount}

@router.delete("/{log_id}")
async def delete_audit_log(
    log_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Delete a single audit log notification within the current tenant."""
    stmt = delete(AuditLog).where(
        AuditLog.id == log_id,
        AuditLog.tenant_id == ctx.organization.id
    )
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "success", "deleted_id": log_id}

