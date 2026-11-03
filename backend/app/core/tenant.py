import base64
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import User, Organization, Membership, MembershipRole

logger = logging.getLogger(__name__)

@dataclass
class TenantContext:
    user: User
    organization: Organization
    membership: Membership
    role: str

def _decode_claims_from_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes token payload, falling back to local decoding if decode_session_token is not yet implemented in security."""
    try:
        from app.core.security import decode_session_token
        decoded = decode_session_token(token)
        if decoded is not None:
            return decoded
    except (ImportError, AttributeError):
        pass

    try:
        from app.core.security import verify_session_token
        if not verify_session_token(token):
            return None
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload = parts[0]
        payload_bytes = base64.urlsafe_b64decode(b64_payload + "=" * (-len(b64_payload) % 4))
        return json.loads(payload_bytes.decode('utf-8'))
    except Exception as e:
        logger.debug(f"Failed to decode token payload: {e}")
        return None

async def get_current_tenant(
    authorization: Optional[str] = Header(None),
    x_organization_id: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> TenantContext:
    """
    FastAPI dependency that enforces tenant isolation.
    Extracts Bearer session token, identifies user and organization, and verifies membership.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication header."
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    payload = _decode_claims_from_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid."
        )

    user_claim = payload.get("user_id") or payload.get("sub") or "default-user"
    username_claim = payload.get("username") or user_claim
    claim_tenant_id = payload.get("tenant_id") or payload.get("org_id")
    claim_role = payload.get("role", "owner")
    claim_tier = payload.get("tier", "starter")

    # Fallback to default-user for legacy tokens ("admin", "user")
    if user_claim in ("admin", "user", "default-user"):
        user_claim = "default-user"
        username_claim = "admin"
        if not claim_tenant_id:
            claim_tenant_id = "default-org"

    # Query user by ID only (no username fallback to prevent cross-tenant aliasing)
    user_stmt = select(User).where(User.id == user_claim)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    # JIT provision User if not in DB
    if not user:
        assigned_username = username_claim
        chk_stmt = select(User).where(User.github_username == assigned_username)
        chk_res = await db.execute(chk_stmt)
        if chk_res.scalar_one_or_none():
            assigned_username = f"{username_claim}_{user_claim[:8]}"

        user = User(
            id=user_claim,
            github_username=assigned_username,
            name=username_claim,
            email=f"{assigned_username}@example.com",
            is_active=True,
            is_superuser=(user_claim == "default-user")
        )
        db.add(user)
        await db.flush()

    # JIT provision Organization and Membership for claim_tenant_id if provided
    if claim_tenant_id:
        org_stmt = select(Organization).where(Organization.id == claim_tenant_id)
        org_res = await db.execute(org_stmt)
        claimed_org = org_res.scalar_one_or_none()
        if not claimed_org:
            claimed_org = Organization(
                id=claim_tenant_id,
                name=payload.get("org_name", claim_tenant_id),
                slug=payload.get("org_slug", claim_tenant_id),
                is_personal=True,
                billing_tier=claim_tier
            )
            db.add(claimed_org)
            await db.flush()

        mem_stmt = select(Membership).where(
            Membership.user_id == user.id,
            Membership.org_id == claim_tenant_id
        )
        mem_res = await db.execute(mem_stmt)
        claimed_mem = mem_res.scalar_one_or_none()
        if not claimed_mem:
            import uuid
            claimed_mem = Membership(
                id=f"mem-{uuid.uuid4().hex[:8]}",
                user_id=user.id,
                org_id=claim_tenant_id,
                role=claim_role
            )
            db.add(claimed_mem)
            await db.flush()

    # Determine requested organization
    requested_org_id = x_organization_id or claim_tenant_id

    if requested_org_id:
        mem_stmt = select(Membership).where(
            Membership.user_id == user.id,
            Membership.org_id == requested_org_id
        )
        mem_res = await db.execute(mem_stmt)
        membership = mem_res.scalar_one_or_none()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Not a member of the requested organization."
            )
        org_stmt = select(Organization).where(Organization.id == requested_org_id)
        org_res = await db.execute(org_stmt)
        organization = org_res.scalar_one_or_none()
        if not organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found."
            )
    else:
        # Default to user's first available organization membership
        mem_stmt = select(Membership).where(
            Membership.user_id == user.id
        ).order_by(Membership.created_at)
        mem_res = await db.execute(mem_stmt)
        membership = mem_res.scalars().first()

        # If default-user has no membership yet, wire to default-org
        if not membership and user.id == "default-user":
            org_stmt = select(Organization).where(Organization.id == "default-org")
            org_res = await db.execute(org_stmt)
            organization = org_res.scalar_one_or_none()
            if not organization:
                organization = Organization(
                    id="default-org",
                    name="Personal Workspace",
                    slug="default-org",
                    is_personal=True,
                    billing_tier="starter"
                )
                db.add(organization)
                await db.flush()

            membership = Membership(
                id="default-membership",
                user_id=user.id,
                org_id=organization.id,
                role=MembershipRole.OWNER.value
            )
            db.add(membership)
            await db.flush()
        elif not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to any active organization."
            )
        else:
            org_stmt = select(Organization).where(Organization.id == membership.org_id)
            org_res = await db.execute(org_stmt)
            organization = org_res.scalar_one_or_none()
            if not organization:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Organization not found."
                )

    await db.commit()

    return TenantContext(
        user=user,
        organization=organization,
        membership=membership,
        role=membership.role
    )
