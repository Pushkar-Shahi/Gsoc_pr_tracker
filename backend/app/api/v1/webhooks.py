import json
import logging
import secrets
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Request, Header, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.entitlements import require_tier
from app.core.security import verify_github_webhook_signature
from app.core.tenant import TenantContext, get_current_tenant
from app.db.database import get_db
from app.models.models import WebhookSubscription, AuditLog
from app.services.webhook_service import process_github_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class WebhookSubscriptionCreateRequest(BaseModel):
    repo_full_name: str = Field(..., description="Target repository in owner/repo format")
    events: List[str] = Field(default_factory=lambda: ["issues", "pull_request", "pull_request_review"])


@router.post("/github")
async def github_webhook_endpoint(
    request: Request,
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db)
):
    """
    Ingests and validates GitHub App webhook events via HMAC-SHA256 signature (X-Hub-Signature-256).
    Supports both the platform webhook secret and tenant-level Pro/Team repository subscriptions.
    """
    if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed X-Hub-Signature-256 signature header."
        )

    raw_body = await request.body()
    if not raw_body or not raw_body.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty webhook request body."
        )

    payload: Optional[dict] = None
    json_error: Optional[Exception] = None
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
        if isinstance(parsed, dict):
            payload = parsed
        else:
            json_error = ValueError("Webhook payload must be a JSON object.")
    except Exception as e:
        json_error = e

    matched_sub: Optional[WebhookSubscription] = None
    verified = False

    if verify_github_webhook_signature(raw_body, x_hub_signature_256, settings.GITHUB_WEBHOOK_SECRET):
        verified = True

    if not verified:
        repo_full_name = (payload.get("repository") or {}).get("full_name") if payload else None
        sub_stmt = select(WebhookSubscription).where(WebhookSubscription.is_active.is_(True))
        if repo_full_name:
            sub_stmt = sub_stmt.where(WebhookSubscription.repo_full_name == repo_full_name)
        subs = (await db.execute(sub_stmt)).scalars().all()
        for sub in subs:
            if verify_github_webhook_signature(raw_body, x_hub_signature_256, sub.webhook_secret):
                verified = True
                matched_sub = sub
                break

    if not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC SHA-256 signature."
        )

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed JSON payload: {json_error}"
        )

    event_type = x_github_event or payload.get("event") or "ping"
    tenant_id = matched_sub.tenant_id if matched_sub else None

    if matched_sub:
        matched_sub.deliveries_count += 1
        matched_sub.last_delivery_at = datetime.utcnow()
        matched_sub.updated_at = datetime.utcnow()

    result = await process_github_webhook_event(
        db=db,
        event_type=event_type,
        payload=payload,
        tenant_id=tenant_id,
    )
    if matched_sub:
        await db.commit()
    return result


@router.get("/subscriptions")
async def list_webhook_subscriptions(
    ctx: TenantContext = Depends(require_tier("pro")),
    db: AsyncSession = Depends(get_db),
):
    """Lists per-repository real-time webhook endpoints configured for this workspace (Pro/Team)."""
    stmt = (
        select(WebhookSubscription)
        .where(WebhookSubscription.tenant_id == ctx.organization.id)
        .order_by(desc(WebhookSubscription.created_at))
    )
    subs = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": s.id,
            "repo_full_name": s.repo_full_name,
            "webhook_secret": s.webhook_secret,
            "events": s.events or ["issues", "pull_request", "pull_request_review"],
            "is_active": s.is_active,
            "deliveries_count": s.deliveries_count,
            "last_delivery_at": s.last_delivery_at.isoformat() if s.last_delivery_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in subs
    ]


@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
async def create_webhook_subscription(
    payload: WebhookSubscriptionCreateRequest,
    ctx: TenantContext = Depends(require_tier("pro")),
    db: AsyncSession = Depends(get_db),
):
    """Registers a real-time GitHub repository webhook subscription & HMAC secret (Pro/Team)."""
    repo = payload.repo_full_name.strip().strip("/")
    if repo.startswith("https://github.com/") or repo.startswith("http://github.com/"):
        parts = repo.split("github.com/", 1)[1].split("/")
        repo = "/".join(parts[:2]) if len(parts) >= 2 else repo
    if "/" not in repo or len(repo.split("/")) != 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository must be formatted as 'owner/repo'."
        )

    sub = WebhookSubscription(
        id=str(uuid.uuid4()),
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        repo_full_name=repo,
        webhook_secret=f"whsec_{secrets.token_hex(20)}",
        events=payload.events or ["issues", "pull_request", "pull_request_review"],
        is_active=True,
    )
    db.add(sub)
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="WEBHOOK_SUBSCRIPTION_CREATED",
        actor=ctx.user.github_username,
        details={"repo_full_name": repo, "events": sub.events},
    ))
    await db.commit()
    await db.refresh(sub)
    return {
        "id": sub.id,
        "repo_full_name": sub.repo_full_name,
        "webhook_secret": sub.webhook_secret,
        "events": sub.events,
        "is_active": sub.is_active,
        "deliveries_count": sub.deliveries_count,
        "last_delivery_at": None,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }


@router.delete("/subscriptions/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook_subscription(
    sub_id: str,
    ctx: TenantContext = Depends(require_tier("pro")),
    db: AsyncSession = Depends(get_db),
):
    """Deletes a tenant's repository webhook subscription."""
    stmt = select(WebhookSubscription).where(
        WebhookSubscription.id == sub_id,
        WebhookSubscription.tenant_id == ctx.organization.id,
    )
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook subscription not found.")
    await db.delete(sub)
    await db.commit()
