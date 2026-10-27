from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.models import PlatformSettings, AuditLog
from app.schemas.schemas import PlatformSettingsRead, PlatformSettingsUpdate
from app.services.antigravity_handoff import AntigravityHandoffService
from app.core.config import settings as app_settings

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("", response_model=PlatformSettingsRead)
async def get_settings(db: AsyncSession = Depends(get_db)):
    stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    res = await db.execute(stmt)
    s = res.scalar_one_or_none()
    
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
        await db.commit()
        await db.refresh(s)

    handoff = AntigravityHandoffService()
    detection = handoff.detect_installation()

    return PlatformSettingsRead(
        github_token_configured=bool(s.github_token and s.github_token.strip()),
        github_username=s.github_username,
        auto_publish_pr=s.auto_publish_pr,
        workspace_root=s.workspace_root or str(app_settings.WORKSPACE_ROOT),
        antigravity_app_path=s.antigravity_app_path,
        skills_profile=s.skills_profile or app_settings.DEFAULT_SKILLS,
        discovery_filters=s.discovery_filters or {},
        detected_antigravity_installed=detection["desktop_app_detected"],
        detected_agy_cli=detection["cli_detected"]
    )

@router.put("", response_model=PlatformSettingsRead)
async def update_settings(payload: PlatformSettingsUpdate, db: AsyncSession = Depends(get_db)):
    stmt = select(PlatformSettings).where(PlatformSettings.id == 1)
    res = await db.execute(stmt)
    s = res.scalar_one_or_none()

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
        action="SETTINGS_UPDATED",
        actor="USER",
        details={
            "auto_publish_pr": s.auto_publish_pr,
            "github_token_set": bool(s.github_token),
            "skills_count": len(s.skills_profile or [])
        }
    )
    db.add(audit)
    await db.commit()
    await db.refresh(s)

    handoff = AntigravityHandoffService()
    detection = handoff.detect_installation()

    return PlatformSettingsRead(
        github_token_configured=bool(s.github_token and s.github_token.strip()),
        github_username=s.github_username,
        auto_publish_pr=s.auto_publish_pr,
        workspace_root=s.workspace_root or str(app_settings.WORKSPACE_ROOT),
        antigravity_app_path=s.antigravity_app_path,
        skills_profile=s.skills_profile or app_settings.DEFAULT_SKILLS,
        discovery_filters=s.discovery_filters or {},
        detected_antigravity_installed=detection["desktop_app_detected"],
        detected_agy_cli=detection["cli_detected"]
    )
