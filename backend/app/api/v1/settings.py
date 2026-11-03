from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import PlatformSettings, UserSettings, OrganizationSettings, AuditLog
from app.schemas.schemas import PlatformSettingsRead, PlatformSettingsUpdate
from app.services.antigravity_handoff import AntigravityHandoffService
from app.core.config import settings as app_settings
from app.core.tenant import TenantContext, get_current_tenant
from app.core.crypto import encrypt_secret, decrypt_secret, mask_api_key

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("", response_model=PlatformSettingsRead)
async def get_settings(
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    # 1. Fetch or create UserSettings for ctx.user.id
    u_stmt = select(UserSettings).where(UserSettings.user_id == ctx.user.id)
    u_sett = (await db.execute(u_stmt)).scalar_one_or_none()
    if not u_sett:
        u_sett = UserSettings(user_id=ctx.user.id)
        db.add(u_sett)
        await db.flush()

    # 2. Fetch or create OrganizationSettings for ctx.organization.id
    o_stmt = select(OrganizationSettings).where(OrganizationSettings.org_id == ctx.organization.id)
    o_sett = (await db.execute(o_stmt)).scalar_one_or_none()
    if not o_sett:
        o_sett = OrganizationSettings(org_id=ctx.organization.id)
        db.add(o_sett)
        await db.flush()

    # 3. Base platform settings for fallback defaults
    p_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    s = (await db.execute(p_stmt)).scalar_one_or_none()
    if not s:
        s = PlatformSettings(
            id=1,
            github_token=app_settings.GITHUB_TOKEN,
            auto_publish_pr=False,
            workspace_root=str(app_settings.WORKSPACE_ROOT),
            antigravity_app_path=app_settings.ANTIGRAVITY_APP_PATHS[0],
            skills_profile=app_settings.DEFAULT_SKILLS,
            discovery_filters={"languages": app_settings.DISCOVERY_LANGUAGES}
        )
        db.add(s)
        await db.flush()

    await db.commit()

    handoff = AntigravityHandoffService()
    detection = handoff.detect_installation()

    has_openai = bool(u_sett.openai_api_key_encrypted or o_sett.openai_api_key_encrypted)
    has_anthropic = bool(u_sett.anthropic_api_key_encrypted or o_sett.anthropic_api_key_encrypted)
    has_gemini = bool(u_sett.gemini_api_key_encrypted or o_sett.gemini_api_key_encrypted)
    has_custom = bool(u_sett.custom_api_key_encrypted or o_sett.custom_api_key_encrypted)

    has_org_openai = bool(o_sett.openai_api_key_encrypted)
    has_org_anthropic = bool(o_sett.anthropic_api_key_encrypted)
    has_org_gemini = bool(o_sett.gemini_api_key_encrypted)
    has_org_custom = bool(o_sett.custom_api_key_encrypted)

    openai_dec = decrypt_secret(u_sett.openai_api_key_encrypted) or decrypt_secret(o_sett.openai_api_key_encrypted)
    anthropic_dec = decrypt_secret(u_sett.anthropic_api_key_encrypted) or decrypt_secret(o_sett.anthropic_api_key_encrypted)
    gemini_dec = decrypt_secret(u_sett.gemini_api_key_encrypted) or decrypt_secret(o_sett.gemini_api_key_encrypted)
    custom_dec = decrypt_secret(u_sett.custom_api_key_encrypted) or decrypt_secret(o_sett.custom_api_key_encrypted)

    org_openai_dec = decrypt_secret(o_sett.openai_api_key_encrypted)
    org_anthropic_dec = decrypt_secret(o_sett.anthropic_api_key_encrypted)
    org_gemini_dec = decrypt_secret(o_sett.gemini_api_key_encrypted)
    org_custom_dec = decrypt_secret(o_sett.custom_api_key_encrypted)

    return PlatformSettingsRead(
        github_token_configured=bool(s.github_token and s.github_token.strip()),
        github_username=s.github_username,
        auto_publish_pr=u_sett.auto_publish_pr if u_sett.auto_publish_pr is not None else s.auto_publish_pr,
        workspace_root=u_sett.workspace_root or s.workspace_root or str(app_settings.WORKSPACE_ROOT),
        antigravity_app_path=u_sett.antigravity_app_path or s.antigravity_app_path,
        skills_profile=u_sett.skills_profile or s.skills_profile or app_settings.DEFAULT_SKILLS,
        discovery_filters=u_sett.discovery_filters or s.discovery_filters or {},
        detected_antigravity_installed=detection["desktop_app_detected"],
        detected_agy_cli=detection["cli_detected"],
        has_openai_key=has_openai,
        has_anthropic_key=has_anthropic,
        has_gemini_key=has_gemini,
        has_custom_key=has_custom,
        has_org_openai_key=has_org_openai,
        has_org_anthropic_key=has_org_anthropic,
        has_org_gemini_key=has_org_gemini,
        has_org_custom_key=has_org_custom,
        openai_api_key=mask_api_key(openai_dec),
        anthropic_api_key=mask_api_key(anthropic_dec),
        gemini_api_key=mask_api_key(gemini_dec),
        custom_api_key=mask_api_key(custom_dec),
        org_openai_api_key=mask_api_key(org_openai_dec),
        org_anthropic_api_key=mask_api_key(org_anthropic_dec),
        org_gemini_api_key=mask_api_key(org_gemini_dec),
        org_custom_api_key=mask_api_key(org_custom_dec),
        enforce_shared_keys=o_sett.enforce_shared_keys,
        preferred_ai_provider=u_sett.preferred_ai_provider or "gemini"
    )

@router.put("", response_model=PlatformSettingsRead)
async def update_settings(
    payload: PlatformSettingsUpdate,
    ctx: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    # Enforce RBAC: regular member cannot modify organization-level shared settings
    is_org_scope = payload.scope in ("organization", "org")
    has_org_keys = any(
        k is not None
        for k in (
            payload.org_openai_api_key,
            payload.org_anthropic_api_key,
            payload.org_gemini_api_key,
            payload.org_custom_api_key,
        )
    )
    if ctx.role == "member" and (payload.enforce_shared_keys is not None or is_org_scope or has_org_keys):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only organization owners and admins can modify organization settings."
        )

    # 1. Fetch or create UserSettings
    u_stmt = select(UserSettings).where(UserSettings.user_id == ctx.user.id)
    u_sett = (await db.execute(u_stmt)).scalar_one_or_none()
    if not u_sett:
        u_sett = UserSettings(user_id=ctx.user.id)
        db.add(u_sett)
        await db.flush()

    # 2. Fetch or create OrganizationSettings
    o_stmt = select(OrganizationSettings).where(OrganizationSettings.org_id == ctx.organization.id)
    o_sett = (await db.execute(o_stmt)).scalar_one_or_none()
    if not o_sett:
        o_sett = OrganizationSettings(org_id=ctx.organization.id)
        db.add(o_sett)
        await db.flush()

    def _process_key(val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        cleaned = val.strip()
        if not cleaned:
            return ""  # indicates clearing the key
        return encrypt_secret(cleaned)

    # Org-level explicit keys
    if ctx.role in ("owner", "admin"):
        if payload.org_openai_api_key is not None:
            res = _process_key(payload.org_openai_api_key)
            o_sett.openai_api_key_encrypted = None if res == "" else res
        if payload.org_anthropic_api_key is not None:
            res = _process_key(payload.org_anthropic_api_key)
            o_sett.anthropic_api_key_encrypted = None if res == "" else res
        if payload.org_gemini_api_key is not None:
            res = _process_key(payload.org_gemini_api_key)
            o_sett.gemini_api_key_encrypted = None if res == "" else res
        if payload.org_custom_api_key is not None:
            res = _process_key(payload.org_custom_api_key)
            o_sett.custom_api_key_encrypted = None if res == "" else res

    if is_org_scope and ctx.role in ("owner", "admin"):
        if payload.openai_api_key is not None:
            res = _process_key(payload.openai_api_key)
            o_sett.openai_api_key_encrypted = None if res == "" else res
        if payload.anthropic_api_key is not None:
            res = _process_key(payload.anthropic_api_key)
            o_sett.anthropic_api_key_encrypted = None if res == "" else res
        if payload.gemini_api_key is not None:
            res = _process_key(payload.gemini_api_key)
            o_sett.gemini_api_key_encrypted = None if res == "" else res
        if payload.custom_api_key is not None:
            res = _process_key(payload.custom_api_key)
            o_sett.custom_api_key_encrypted = None if res == "" else res
        if payload.preferred_ai_provider is not None:
            o_sett.preferred_ai_provider = payload.preferred_ai_provider
    else:
        if payload.openai_api_key is not None:
            res = _process_key(payload.openai_api_key)
            u_sett.openai_api_key_encrypted = None if res == "" else res
        if payload.anthropic_api_key is not None:
            res = _process_key(payload.anthropic_api_key)
            u_sett.anthropic_api_key_encrypted = None if res == "" else res
        if payload.gemini_api_key is not None:
            res = _process_key(payload.gemini_api_key)
            u_sett.gemini_api_key_encrypted = None if res == "" else res
        if payload.custom_api_key is not None:
            res = _process_key(payload.custom_api_key)
            u_sett.custom_api_key_encrypted = None if res == "" else res

    if payload.enforce_shared_keys is not None and ctx.role in ("owner", "admin"):
        o_sett.enforce_shared_keys = payload.enforce_shared_keys

    if payload.auto_publish_pr is not None:
        u_sett.auto_publish_pr = payload.auto_publish_pr
    if payload.workspace_root is not None:
        u_sett.workspace_root = payload.workspace_root.strip()
    if payload.antigravity_app_path is not None:
        u_sett.antigravity_app_path = payload.antigravity_app_path.strip()
    if payload.skills_profile is not None:
        u_sett.skills_profile = payload.skills_profile
    if payload.discovery_filters is not None:
        u_sett.discovery_filters = payload.discovery_filters
    if payload.preferred_ai_provider is not None:
        u_sett.preferred_ai_provider = payload.preferred_ai_provider

    # Also update platform settings for workspace defaults
    p_stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    s = (await db.execute(p_stmt)).scalar_one_or_none()
    if not s:
        s = PlatformSettings(id=1)
        db.add(s)

    if payload.github_token is not None:
        s.github_token = payload.github_token.strip() if payload.github_token.strip() else None
    if payload.github_username is not None:
        s.github_username = payload.github_username.strip()
    if payload.auto_publish_pr is not None:
        s.auto_publish_pr = payload.auto_publish_pr
    if payload.workspace_root is not None:
        s.workspace_root = payload.workspace_root.strip()
    if payload.antigravity_app_path is not None:
        s.antigravity_app_path = payload.antigravity_app_path.strip()
    if payload.skills_profile is not None:
        s.skills_profile = payload.skills_profile
    if payload.discovery_filters is not None:
        s.discovery_filters = payload.discovery_filters

    audit = AuditLog(
        tenant_id=ctx.organization.id,
        user_id=ctx.user.id,
        action="SETTINGS_UPDATED",
        actor="USER",
        details={
            "auto_publish_pr": u_sett.auto_publish_pr,
            "has_openai_key": bool(u_sett.openai_api_key_encrypted),
            "enforce_shared_keys": o_sett.enforce_shared_keys
        }
    )
    db.add(audit)
    await db.commit()

    handoff = AntigravityHandoffService()
    detection = handoff.detect_installation()

    has_openai = bool(u_sett.openai_api_key_encrypted or o_sett.openai_api_key_encrypted)
    has_anthropic = bool(u_sett.anthropic_api_key_encrypted or o_sett.anthropic_api_key_encrypted)
    has_gemini = bool(u_sett.gemini_api_key_encrypted or o_sett.gemini_api_key_encrypted)
    has_custom = bool(u_sett.custom_api_key_encrypted or o_sett.custom_api_key_encrypted)

    has_org_openai = bool(o_sett.openai_api_key_encrypted)
    has_org_anthropic = bool(o_sett.anthropic_api_key_encrypted)
    has_org_gemini = bool(o_sett.gemini_api_key_encrypted)
    has_org_custom = bool(o_sett.custom_api_key_encrypted)

    openai_dec = decrypt_secret(u_sett.openai_api_key_encrypted) or decrypt_secret(o_sett.openai_api_key_encrypted)
    anthropic_dec = decrypt_secret(u_sett.anthropic_api_key_encrypted) or decrypt_secret(o_sett.anthropic_api_key_encrypted)
    gemini_dec = decrypt_secret(u_sett.gemini_api_key_encrypted) or decrypt_secret(o_sett.gemini_api_key_encrypted)
    custom_dec = decrypt_secret(u_sett.custom_api_key_encrypted) or decrypt_secret(o_sett.custom_api_key_encrypted)

    org_openai_dec = decrypt_secret(o_sett.openai_api_key_encrypted)
    org_anthropic_dec = decrypt_secret(o_sett.anthropic_api_key_encrypted)
    org_gemini_dec = decrypt_secret(o_sett.gemini_api_key_encrypted)
    org_custom_dec = decrypt_secret(o_sett.custom_api_key_encrypted)

    return PlatformSettingsRead(
        github_token_configured=bool(s.github_token and s.github_token.strip()),
        github_username=s.github_username,
        auto_publish_pr=u_sett.auto_publish_pr if u_sett.auto_publish_pr is not None else s.auto_publish_pr,
        workspace_root=u_sett.workspace_root or s.workspace_root or str(app_settings.WORKSPACE_ROOT),
        antigravity_app_path=u_sett.antigravity_app_path or s.antigravity_app_path,
        skills_profile=u_sett.skills_profile or s.skills_profile or app_settings.DEFAULT_SKILLS,
        discovery_filters=u_sett.discovery_filters or s.discovery_filters or {},
        detected_antigravity_installed=detection["desktop_app_detected"],
        detected_agy_cli=detection["cli_detected"],
        has_openai_key=has_openai,
        has_anthropic_key=has_anthropic,
        has_gemini_key=has_gemini,
        has_custom_key=has_custom,
        has_org_openai_key=has_org_openai,
        has_org_anthropic_key=has_org_anthropic,
        has_org_gemini_key=has_org_gemini,
        has_org_custom_key=has_org_custom,
        openai_api_key=mask_api_key(openai_dec),
        anthropic_api_key=mask_api_key(anthropic_dec),
        gemini_api_key=mask_api_key(gemini_dec),
        custom_api_key=mask_api_key(custom_dec),
        org_openai_api_key=mask_api_key(org_openai_dec),
        org_anthropic_api_key=mask_api_key(org_anthropic_dec),
        org_gemini_api_key=mask_api_key(org_gemini_dec),
        org_custom_api_key=mask_api_key(org_custom_dec),
        enforce_shared_keys=o_sett.enforce_shared_keys,
        preferred_ai_provider=u_sett.preferred_ai_provider or "gemini"
    )
