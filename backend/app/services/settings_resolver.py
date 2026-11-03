import os
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.crypto import decrypt_secret
from app.models.models import UserSettings, OrganizationSettings

class SettingsResolver:
    @staticmethod
    async def get_effective_ai_key(
        db: AsyncSession,
        ctx: Optional[TenantContext] = None,
        provider: str = "gemini",
        user_id: Optional[str] = None,
        org_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolves the effective API key for the requested provider with precedence:
        1. If Organization enforce_shared_keys is True: Org Shared Key -> User Key -> Env -> None
        2. Otherwise: User Key -> Org Shared Key -> Env -> None
        """
        prov = (provider or "").lower().strip()
        provider_column_map = {
            "openai": "openai_api_key_encrypted",
            "anthropic": "anthropic_api_key_encrypted",
            "gemini": "gemini_api_key_encrypted",
            "custom": "custom_api_key_encrypted"
        }
        if prov not in provider_column_map:
            return None

        col_name = provider_column_map[prov]
        uid = user_id or (ctx.user.id if ctx and hasattr(ctx, "user") and ctx.user else None)
        oid = org_id or (ctx.organization.id if ctx and hasattr(ctx, "organization") and ctx.organization else None)

        user_sett = None
        org_sett = None

        if uid:
            u_stmt = select(UserSettings).where(UserSettings.user_id == uid)
            user_sett = (await db.execute(u_stmt)).scalar_one_or_none()

        if oid:
            o_stmt = select(OrganizationSettings).where(OrganizationSettings.org_id == oid)
            org_sett = (await db.execute(o_stmt)).scalar_one_or_none()

        enforce_shared = org_sett.enforce_shared_keys if org_sett else False

        user_key = decrypt_secret(getattr(user_sett, col_name, None)) if user_sett else None
        org_key = decrypt_secret(getattr(org_sett, col_name, None)) if org_sett else None

        env_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }
        env_var = env_map.get(prov)
        env_key = os.getenv(env_var) if env_var else None

        if enforce_shared:
            return org_key or user_key or env_key
        else:
            return user_key or org_key or env_key

get_effective_ai_key = SettingsResolver.get_effective_ai_key
