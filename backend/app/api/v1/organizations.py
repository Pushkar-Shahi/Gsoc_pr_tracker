"""
Organizations & Multi-Tenant Workspace Router.
Enables listing, creating, switching, and member management for team organizations.
"""

import re
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.tenant import get_current_tenant, TenantContext
from app.core.security import generate_session_token
from app.db.database import get_db
from app.models.models import User, Organization, Membership, MembershipRole

router = APIRouter(prefix="/organizations", tags=["organizations"])


class CreateOrganizationRequest(BaseModel):
    name: str
    slug: Optional[str] = None


class AddMemberRequest(BaseModel):
    username_or_email: str
    role: str = "member"


class OrganizationRead(BaseModel):
    id: str
    name: str
    slug: str
    is_personal: bool
    billing_tier: str
    role: str
    is_active: bool
    member_count: int = 1


class MemberRead(BaseModel):
    id: str
    user_id: str
    username: str
    name: Optional[str] = None
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str


def _slugify(text: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', text).strip('-').lower()
    return slug[:40] or "workspace"


@router.get("", response_model=List[OrganizationRead])
async def list_user_organizations(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns all organizations that the current authenticated user belongs to.
    """
    stmt = (
        select(Membership)
        .options(selectinload(Membership.organization))
        .where(Membership.user_id == ctx.user.id)
    )
    res = await db.execute(stmt)
    memberships = res.scalars().all()

    org_list = []
    for mem in memberships:
        org = mem.organization
        if not org:
            continue

        # Count total members
        count_stmt = select(func.count(Membership.id)).where(Membership.org_id == org.id)
        count_res = await db.execute(count_stmt)
        member_count = count_res.scalar() or 1

        org_list.append(
            OrganizationRead(
                id=org.id,
                name=org.name,
                slug=org.slug,
                is_personal=org.is_personal,
                billing_tier=org.billing_tier or "starter",
                role=mem.role,
                is_active=(org.id == ctx.organization.id),
                member_count=member_count
            )
        )

    return org_list


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    req: CreateOrganizationRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new organization, sets the current user as Owner, and returns the workspace.
    """
    name = req.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization name is required."
        )

    base_slug = _slugify(req.slug or name)
    slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

    org_id = f"org-{uuid.uuid4().hex[:12]}"
    org = Organization(
        id=org_id,
        name=name,
        slug=slug,
        is_personal=False,
        billing_tier="starter"
    )
    db.add(org)
    await db.flush()

    membership = Membership(
        id=f"mem-{uuid.uuid4().hex[:8]}",
        user_id=ctx.user.id,
        org_id=org.id,
        role=MembershipRole.OWNER.value
    )
    db.add(membership)
    await db.commit()
    await db.refresh(org)

    return OrganizationRead(
        id=org.id,
        name=org.name,
        slug=org.slug,
        is_personal=org.is_personal,
        billing_tier=org.billing_tier,
        role=MembershipRole.OWNER.value,
        is_active=False,
        member_count=1
    )


@router.post("/{org_id}/switch")
async def switch_organization(
    org_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Switches active organization context and issues an updated JWT session token.
    """
    stmt = (
        select(Membership)
        .options(selectinload(Membership.organization))
        .where(Membership.user_id == ctx.user.id, Membership.org_id == org_id)
    )
    res = await db.execute(stmt)
    mem = res.scalar_one_or_none()

    if not mem or not mem.organization:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization."
        )

    org = mem.organization
    claims = {
        "user_id": ctx.user.id,
        "username": ctx.user.github_username,
        "tenant_id": org.id,
        "role": mem.role,
        "tier": org.billing_tier or "starter"
    }
    new_token = generate_session_token(subject=ctx.user.id, claims=claims)

    return {
        "token": new_token,
        "token_type": "bearer",
        "organization": {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "is_personal": org.is_personal,
            "billing_tier": org.billing_tier
        },
        "role": mem.role
    }


@router.get("/{org_id}/members", response_model=List[MemberRead])
async def list_organization_members(
    org_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Lists all members belonging to the specified organization.
    """
    # Verify current user is member of org_id
    verify_stmt = select(Membership).where(
        Membership.user_id == ctx.user.id,
        Membership.org_id == org_id
    )
    v_res = await db.execute(verify_stmt)
    if not v_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to organization members."
        )

    stmt = (
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.org_id == org_id)
    )
    res = await db.execute(stmt)
    memberships = res.scalars().all()

    members = []
    for m in memberships:
        u = m.user
        if u:
            members.append(
                MemberRead(
                    id=m.id,
                    user_id=u.id,
                    username=u.github_username,
                    name=u.name,
                    email=u.email,
                    avatar_url=u.avatar_url,
                    role=m.role
                )
            )

    return members


@router.post("/{org_id}/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def add_organization_member(
    org_id: str,
    req: AddMemberRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Invites or adds a user to the organization by username or email.
    Only Owner or Admin can add members.
    """
    # Verify user has owner/admin role in org
    verify_stmt = select(Membership).where(
        Membership.user_id == ctx.user.id,
        Membership.org_id == org_id
    )
    v_res = await db.execute(verify_stmt)
    my_mem = v_res.scalar_one_or_none()

    if not my_mem or my_mem.role not in (MembershipRole.OWNER.value, MembershipRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners or admins can invite new members."
        )

    identifier = req.username_or_email.strip()
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email is required."
        )

    # Find existing user or provision a placeholder member
    u_stmt = select(User).where(
        (User.github_username == identifier) | (User.email == identifier)
    )
    u_res = await db.execute(u_stmt)
    target_user = u_res.scalar_one_or_none()

    if not target_user:
        target_user = User(
            id=f"usr-{uuid.uuid4().hex[:12]}",
            github_username=identifier,
            email=identifier if "@" in identifier else f"{identifier}@platform.dev",
            name=identifier,
            avatar_url=f"https://github.com/{identifier}.png"
        )
        db.add(target_user)
        await db.flush()

    # Check if already a member
    existing_mem_stmt = select(Membership).where(
        Membership.user_id == target_user.id,
        Membership.org_id == org_id
    )
    ex_res = await db.execute(existing_mem_stmt)
    if ex_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User '{identifier}' is already a member of this organization."
        )

    target_role = req.role.lower() if req.role.lower() in ("owner", "admin", "member") else "member"
    new_mem = Membership(
        id=f"mem-{uuid.uuid4().hex[:8]}",
        user_id=target_user.id,
        org_id=org_id,
        role=target_role
    )
    db.add(new_mem)
    await db.commit()
    await db.refresh(new_mem)

    return MemberRead(
        id=new_mem.id,
        user_id=target_user.id,
        username=target_user.github_username,
        name=target_user.name,
        email=target_user.email,
        avatar_url=target_user.avatar_url,
        role=new_mem.role
    )

