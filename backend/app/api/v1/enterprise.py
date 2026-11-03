import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, get_current_tenant
from app.db.database import get_db
from app.models.models import AuditLog
from app.schemas.schemas import SSOConfigRead, SSOConfigUpdate, SSOTestResponse
from app.services.enterprise_sso import EnterpriseSSOService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enterprise", tags=["Enterprise Governance & SSO"])


class SSOTestRequest(BaseModel):
    metadata_url: str
    provider: Optional[str] = None


@router.get("/sso", response_model=SSOConfigRead)
async def get_sso_config(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves current SAML 2.0 / OIDC Single Sign-On configuration for the organization."""
    org = ctx.organization
    return SSOConfigRead(
        sso_provider=org.sso_provider,
        sso_metadata_url=org.sso_metadata_url,
        sso_entity_id=org.sso_entity_id,
        sso_enforced=bool(org.sso_enforced),
        sso_configured=bool(org.sso_metadata_url)
    )


@router.post("/sso", response_model=SSOConfigRead)
async def configure_sso(
    req: SSOConfigUpdate,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Configures enterprise SAML 2.0 / OIDC identity provider metadata.
    Enforces tenant admin or owner role.
    """
    if ctx.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners or admins can configure enterprise SSO."
        )

    try:
        await EnterpriseSSOService.configure_sso(
            db=db,
            organization=ctx.organization,
            provider=req.sso_provider,
            metadata_url=req.sso_metadata_url,
            entity_id=req.sso_entity_id,
            enforced=bool(req.sso_enforced)
        )

        audit = AuditLog(
            tenant_id=ctx.organization.id,
            user_id=ctx.user.id,
            action="ENTERPRISE_SSO_CONFIGURED",
            actor=ctx.user.github_username,
            details={
                "provider": req.sso_provider,
                "metadata_url": req.sso_metadata_url,
                "enforced": req.sso_enforced
            }
        )
        db.add(audit)
        await db.commit()

        return SSOConfigRead(
            sso_provider=ctx.organization.sso_provider,
            sso_metadata_url=ctx.organization.sso_metadata_url,
            sso_entity_id=ctx.organization.sso_entity_id,
            sso_enforced=bool(ctx.organization.sso_enforced),
            sso_configured=True
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error configuring SSO: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/sso/test", response_model=SSOTestResponse)
async def test_sso_connection(
    req: SSOTestRequest,
    ctx: TenantContext = Depends(get_current_tenant)
):
    """Tests connection to an enterprise IdP metadata URL and detects SAML/OIDC endpoints."""
    try:
        res = await EnterpriseSSOService.test_connection(req.metadata_url, provider=req.provider)
        return SSOTestResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        return SSOTestResponse(
            status="failed",
            message=f"IdP connection test failed: {str(e)}",
            provider=req.provider or "unknown",
            endpoints_detected={}
        )
