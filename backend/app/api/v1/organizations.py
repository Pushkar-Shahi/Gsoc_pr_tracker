"""
Organizations & Multi-Tenant Workspace Router.
Enables listing, creating, switching, and member management for team organizations.
"""

import re
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.entitlements import require_tier
from app.core.tenant import get_current_tenant, TenantContext
from app.core.security import generate_session_token
from app.db.database import get_db
from app.models.models import (
    User, Organization, Membership, MembershipRole,
    Repository, Issue, Task, PlatformSettings, AuditLog
)
from app.services.github_client import GitHubClient
from app.services.ranking_service import RankingService
from app.services.availability_inspector import AvailabilityInspector

router = APIRouter(prefix="/organizations", tags=["organizations"])


class CreateOrganizationRequest(BaseModel):
    name: str
    slug: Optional[str] = None


class AddMemberRequest(BaseModel):
    username_or_email: str
    role: str = "member"


class UpdateMemberRoleRequest(BaseModel):
    role: str


class SyncPrivateReposRequest(BaseModel):
    repo_full_name: Optional[str] = None
    org_name: Optional[str] = None


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

    # Multi-user seats > 2 require Engineering Team tier when Free Beta is disabled
    org_obj = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    org_tier = (org_obj.billing_tier if org_obj else "starter").lower()
    seat_count = (await db.execute(select(func.count(Membership.id)).where(Membership.org_id == org_id))).scalar() or 1
    if (
        seat_count >= 2
        and not getattr(settings, "FREE_BETA_MODE", False)
        and not getattr(ctx.user, "is_superuser", False)
        and org_tier not in ("team", "enterprise")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Adding 3+ team seats requires the Engineering Team tier.",
                "code": "TIER_UPGRADE_REQUIRED",
                "required_tier": "team",
                "current_tier": org_tier,
            },
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


async def _verify_org_membership(
    db: AsyncSession, user_id: str, org_id: str, require_admin: bool = False
) -> Membership:
    mem = (
        await db.execute(
            select(Membership).where(Membership.user_id == user_id, Membership.org_id == org_id)
        )
    ).scalar_one_or_none()
    if not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organization.")
    if require_admin and mem.role not in (MembershipRole.OWNER.value, MembershipRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners or admins can perform this action."
        )
    return mem


@router.patch("/{org_id}/members/{member_id}", response_model=MemberRead)
async def update_organization_member_role(
    org_id: str,
    member_id: str,
    req: UpdateMemberRoleRequest,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Updates an organization member's RBAC role (owner / admin / member)."""
    await _verify_org_membership(db, ctx.user.id, org_id, require_admin=True)
    target_role = req.role.lower().strip()
    if target_role not in ("owner", "admin", "member"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be owner, admin, or member.")

    mem = (
        await db.execute(
            select(Membership).options(selectinload(Membership.user)).where(
                Membership.id == member_id,
                Membership.org_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if not mem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if mem.role == MembershipRole.OWNER.value and target_role != MembershipRole.OWNER.value:
        owners_count = (
            await db.execute(
                select(func.count(Membership.id)).where(
                    Membership.org_id == org_id,
                    Membership.role == MembershipRole.OWNER.value,
                )
            )
        ).scalar() or 0
        if owners_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the sole remaining organization owner."
            )

    mem.role = target_role
    mem.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(mem)
    u = mem.user
    return MemberRead(
        id=mem.id,
        user_id=mem.user_id,
        username=u.github_username if u else "member",
        name=u.name if u else None,
        email=u.email if u else None,
        avatar_url=u.avatar_url if u else None,
        role=mem.role,
    )


@router.delete("/{org_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_organization_member(
    org_id: str,
    member_id: str,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Removes a seat from the organization while preserving the last owner."""
    await _verify_org_membership(db, ctx.user.id, org_id, require_admin=True)
    mem = (
        await db.execute(
            select(Membership).where(Membership.id == member_id, Membership.org_id == org_id)
        )
    ).scalar_one_or_none()
    if not mem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if mem.role == MembershipRole.OWNER.value:
        owners_count = (
            await db.execute(
                select(func.count(Membership.id)).where(
                    Membership.org_id == org_id,
                    Membership.role == MembershipRole.OWNER.value,
                )
            )
        ).scalar() or 0
        if owners_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the sole remaining organization owner."
            )

    await db.delete(mem)
    await db.commit()


@router.get("/{org_id}/private-repos")
async def list_org_private_repositories(
    org_id: str,
    ctx: TenantContext = Depends(require_tier("team")),
    db: AsyncSession = Depends(get_db),
):
    """Lists private GitHub repositories connected to this Engineering Team organization."""
    await _verify_org_membership(db, ctx.user.id, org_id, require_admin=False)
    stmt = (
        select(Repository)
        .where(Repository.tenant_id == org_id, Repository.is_private.is_(True))
        .order_by(desc(Repository.updated_at))
    )
    repos = (await db.execute(stmt)).scalars().all()
    out = []
    for r in repos:
        open_count = (
            await db.execute(
                select(func.count(Issue.id)).where(
                    Issue.repository_id == r.id,
                    Issue.state == "open",
                    Issue.is_eligible.is_(True),
                )
            )
        ).scalar() or 0
        out.append({
            "id": r.id,
            "full_name": r.full_name,
            "html_url": r.html_url,
            "primary_language": r.primary_language,
            "stars_count": r.stars_count,
            "open_issues_count": open_count,
            "last_inspected_at": r.last_inspected_at.isoformat() if r.last_inspected_at else None,
        })
    return out


@router.post("/{org_id}/private-repos/sync")
async def sync_org_private_repositories(
    org_id: str,
    payload: Optional[SyncPrivateReposRequest] = None,
    ctx: TenantContext = Depends(require_tier("team")),
    db: AsyncSession = Depends(get_db),
):
    """
    Syncs private GitHub repositories & open issues strictly scoped to this Team organization.
    """
    await _verify_org_membership(db, ctx.user.id, org_id, require_admin=True)

    p_sett = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))).scalar_one_or_none()
    gh = GitHubClient(token=p_sett.github_token if p_sett else None)
    ranking_svc = RankingService()

    repo_payloads: List[Dict[str, Any]] = []
    target_repo = (payload.repo_full_name or "").strip().strip("/") if payload else ""
    target_org = (payload.org_name or "").strip() if payload else ""

    if target_repo and "/" in target_repo:
        owner, name = target_repo.split("/", 1)
        data = await gh.get_repository(owner, name)
        if not data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository '{target_repo}' not found or token lacks 'repo' private access."
            )
        repo_payloads.append(data)
    elif target_org:
        repo_payloads = await gh.list_org_private_repos(target_org)
    else:
        repo_payloads = await gh.list_user_private_repos()

    synced_repos = 0
    synced_issues = 0
    for r_data in repo_payloads:
        full_name = r_data.get("full_name")
        if not full_name or "/" not in full_name:
            continue
        owner, name = full_name.split("/", 1)
        is_priv = bool(r_data.get("private", True))
        repo_obj = (
            await db.execute(select(Repository).where(Repository.full_name == full_name))
        ).scalar_one_or_none()
        if not repo_obj:
            repo_obj = Repository(
                id=f"repo-{uuid.uuid4().hex[:8]}",
                tenant_id=org_id if is_priv else None,
                user_id=ctx.user.id,
                owner=owner,
                name=name,
                full_name=full_name,
                html_url=r_data.get("html_url") or f"https://github.com/{full_name}",
                default_branch=r_data.get("default_branch", "main"),
                primary_language=r_data.get("language"),
                stars_count=r_data.get("stargazers_count", 0),
                open_issues_count=r_data.get("open_issues_count", 0),
                is_private=is_priv,
                is_gsoc=not is_priv,
                last_inspected_at=datetime.utcnow(),
            )
            db.add(repo_obj)
            await db.flush()
        else:
            if is_priv:
                repo_obj.tenant_id = org_id
                repo_obj.is_private = True
            repo_obj.last_inspected_at = datetime.utcnow()
        synced_repos += 1

        raw_issues = await gh.get_repo_issues(owner, name, state="open", assignee="none", per_page=15)
        for item in raw_issues:
            gh_id = item.get("id")
            iss_num = item.get("number")
            if not gh_id or not iss_num:
                continue
            existing_iss = (
                await db.execute(select(Issue).where(Issue.github_id == gh_id))
            ).scalar_one_or_none()
            labels = item.get("labels", [])
            is_res, res_reason = AvailabilityInspector.detect_maintainer_reservation(
                item.get("title", ""), item.get("body", "")
            )
            eval_res = ranking_svc.evaluate_issue(
                title=item.get("title", ""),
                body=item.get("body", ""),
                labels=labels,
                repo_language=r_data.get("language") or "",
                repo_stars=r_data.get("stargazers_count", 0),
            )
            if not existing_iss:
                db.add(Issue(
                    id=f"iss-{uuid.uuid4().hex[:8]}",
                    tenant_id=org_id,
                    user_id=ctx.user.id,
                    repository_id=repo_obj.id,
                    github_id=gh_id,
                    issue_number=iss_num,
                    title=item.get("title", "Untitled"),
                    body=item.get("body", ""),
                    author=(item.get("user") or {}).get("login"),
                    html_url=item.get("html_url") or f"https://github.com/{full_name}/issues/{iss_num}",
                    state="open",
                    labels=labels,
                    assignees=item.get("assignees", []),
                    comments_count=item.get("comments", 0),
                    is_eligible=not is_res,
                    is_reserved=is_res,
                    reservation_reason=res_reason,
                    availability_status="RESERVED" if is_res else "AVAILABLE",
                    ranking_score=eval_res["ranking_score"],
                    difficulty_estimate=eval_res["difficulty_estimate"],
                    estimated_effort_hours=eval_res["estimated_effort_hours"],
                    ranking_breakdown=eval_res["ranking_breakdown"],
                    ai_summary=eval_res["ai_summary"],
                    last_verified_at=datetime.utcnow(),
                ))
                synced_issues += 1

    db.add(AuditLog(
        id=str(uuid.uuid4()),
        tenant_id=org_id,
        user_id=ctx.user.id,
        action="PRIVATE_REPOS_SYNCED",
        actor=ctx.user.github_username,
        details={"synced_repos": synced_repos, "synced_issues": synced_issues, "target": target_repo or target_org or "user_private"},
    ))
    await db.commit()
    return {
        "status": "synced",
        "synced_repos": synced_repos,
        "synced_issues": synced_issues,
    }


@router.get("/{org_id}/velocity")
async def get_team_pr_velocity(
    org_id: str,
    ctx: TenantContext = Depends(require_tier("team")),
    db: AsyncSession = Depends(get_db),
):
    """Returns centralized PR velocity, CI health, merge rates, and contributor breakdown for a Team org."""
    await _verify_org_membership(db, ctx.user.id, org_id, require_admin=False)

    tasks_stmt = (
        select(Task)
        .options(selectinload(Task.issue).selectinload(Issue.repository))
        .where(Task.tenant_id == org_id)
        .order_by(desc(Task.updated_at))
    )
    tasks = (await db.execute(tasks_stmt)).scalars().all()

    mem_stmt = (
        select(Membership)
        .options(selectinload(Membership.user))
        .where(Membership.org_id == org_id)
    )
    memberships = (await db.execute(mem_stmt)).scalars().all()

    member_stats: Dict[str, Dict[str, Any]] = {}
    for m in memberships:
        u = m.user
        uid = m.user_id
        member_stats[uid] = {
            "user_id": uid,
            "username": u.github_username if u else "member",
            "avatar_url": u.avatar_url if u else None,
            "role": m.role,
            "tasks_count": 0,
            "prs_opened": 0,
            "prs_merged": 0,
            "ci_passing": 0,
        }

    total_tasks = len(tasks)
    pr_tasks = [t for t in tasks if (t.pr_number or t.pr_url)]
    total_prs = len(pr_tasks)
    merged_prs = [t for t in pr_tasks if t.pr_merged]
    open_prs = [t for t in pr_tasks if not t.pr_merged and t.pr_state != "closed"]
    changes_requested = [t for t in pr_tasks if t.pr_review_status == "CHANGES_REQUESTED"]
    ci_evaluated = [t for t in pr_tasks if t.pr_ci_status in ("success", "failure")]
    ci_passing = [t for t in ci_evaluated if t.pr_ci_status == "success"]

    lead_hours: List[float] = []
    for t in tasks:
        uid = t.user_id or "unassigned"
        if uid not in member_stats:
            member_stats[uid] = {
                "user_id": uid,
                "username": "contributor",
                "avatar_url": None,
                "role": "member",
                "tasks_count": 0,
                "prs_opened": 0,
                "prs_merged": 0,
                "ci_passing": 0,
            }
        member_stats[uid]["tasks_count"] += 1
        if t.pr_number or t.pr_url:
            member_stats[uid]["prs_opened"] += 1
            if t.pr_merged:
                member_stats[uid]["prs_merged"] += 1
            if t.pr_ci_status == "success":
                member_stats[uid]["ci_passing"] += 1
            if t.created_at and t.updated_at and t.updated_at >= t.created_at:
                lead_hours.append((t.updated_at - t.created_at).total_seconds() / 3600.0)

    avg_cycle_hours = round(sum(lead_hours) / len(lead_hours), 1) if lead_hours else 0.0
    merge_rate_pct = round((len(merged_prs) / total_prs) * 100.0, 1) if total_prs > 0 else 0.0
    ci_pass_rate_pct = round((len(ci_passing) / len(ci_evaluated)) * 100.0, 1) if ci_evaluated else 100.0

    contributors = sorted(
        member_stats.values(),
        key=lambda c: (c["prs_merged"], c["prs_opened"], c["tasks_count"]),
        reverse=True,
    )

    recent_merges = [
        {
            "task_id": t.id,
            "pr_number": t.pr_number,
            "pr_url": t.pr_url,
            "repo": t.issue.repository.full_name if (t.issue and t.issue.repository) else "repository",
            "title": t.issue.title if t.issue else f"PR #{t.pr_number}",
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in merged_prs[:5]
    ]

    return {
        "organization_id": org_id,
        "total_tasks": total_tasks,
        "total_prs": total_prs,
        "open_prs": len(open_prs),
        "merged_prs": len(merged_prs),
        "changes_requested_prs": len(changes_requested),
        "merge_rate_pct": merge_rate_pct,
        "ci_pass_rate_pct": ci_pass_rate_pct,
        "avg_cycle_hours": avg_cycle_hours,
        "seat_count": len(memberships),
        "contributors": contributors,
        "recent_merges": recent_merges,
    }

