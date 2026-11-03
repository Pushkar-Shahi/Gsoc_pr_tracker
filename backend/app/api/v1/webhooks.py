import json
import logging
from typing import Optional
from fastapi import APIRouter, Request, Header, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import verify_github_webhook_signature
from app.db.database import get_db
from app.services.webhook_service import process_github_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

@router.post("/github")
async def github_webhook_endpoint(
    request: Request,
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db)
):
    """
    Ingests and validates GitHub App webhook events via HMAC-SHA256 signature (X-Hub-Signature-256).
    Dispatches verified payloads to the WebhookService state synchronization handlers.
    """
    # 1. Verify HMAC Signature Header presence and prefix
    if not x_hub_signature_256 or not x_hub_signature_256.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed X-Hub-Signature-256 signature header."
        )

    # 2. Read raw request payload bytes
    raw_body = await request.body()

    # 3. Cryptographically verify signature against secret
    secret = settings.GITHUB_WEBHOOK_SECRET
    if not verify_github_webhook_signature(raw_body, x_hub_signature_256, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC SHA-256 signature."
        )

    # 4. Check for empty payload
    if not raw_body or not raw_body.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty webhook request body."
        )

    # 5. Parse JSON payload
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed JSON payload: {e}"
        )

    event_type = x_github_event or payload.get("event") or "ping"

    # 6. Dispatch to webhook service
    result = await process_github_webhook_event(db=db, event_type=event_type, payload=payload)
    return result
