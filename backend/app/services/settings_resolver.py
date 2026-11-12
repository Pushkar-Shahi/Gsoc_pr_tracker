import os
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext
from app.core.crypto import decrypt_secret
from app.models.models import UserSettings, OrganizationSettings

ENV_VAR_MAP = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

PROVIDER_COLUMN_MAP = {
    "openai": "openai_api_key_encrypted",
    "anthropic": "anthropic_api_key_encrypted",
    "gemini": "gemini_api_key_encrypted",
    "custom": "custom_api_key_encrypted",
}


class SettingsResolver:
    @staticmethod
    async def resolve_effective_ai_config(
        db: AsyncSession,
        ctx: Optional[TenantContext] = None,
        provider: Optional[str] = None,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolves the active AI provider, decrypted API key, source precedence,
        custom endpoint, and organization triage policy.
        """
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

        prov = (
            provider
            or (user_sett.preferred_ai_provider if user_sett and user_sett.preferred_ai_provider else None)
            or "gemini"
        ).lower().strip()

        enforce_shared = bool(org_sett.enforce_shared_keys) if org_sett else False
        triage_policy = dict(org_sett.triage_policy or {}) if org_sett and isinstance(org_sett.triage_policy, dict) else {}

        col_name = PROVIDER_COLUMN_MAP.get(prov)
        user_key = decrypt_secret(getattr(user_sett, col_name, None)) if (user_sett and col_name) else None
        org_key = decrypt_secret(getattr(org_sett, col_name, None)) if (org_sett and col_name) else None
        env_var = ENV_VAR_MAP.get(prov)
        env_key = os.getenv(env_var) if env_var else None

        api_key = None
        key_source = None
        if enforce_shared:
            if org_key:
                api_key, key_source = org_key, "organization"
            elif user_key:
                api_key, key_source = user_key, "personal"
            elif env_key:
                api_key, key_source = env_key, "env"
        else:
            if user_key:
                api_key, key_source = user_key, "personal"
            elif org_key:
                api_key, key_source = org_key, "organization"
            elif env_key:
                api_key, key_source = env_key, "env"

        custom_endpoint = None
        if enforce_shared:
            custom_endpoint = (org_sett.custom_endpoint if org_sett else None) or (user_sett.custom_endpoint if user_sett else None)
        else:
            custom_endpoint = (user_sett.custom_endpoint if user_sett else None) or (org_sett.custom_endpoint if org_sett else None)

        return {
            "provider": prov,
            "api_key": api_key,
            "key_source": key_source,
            "custom_endpoint": custom_endpoint,
            "enforce_shared_keys": enforce_shared,
            "triage_policy": triage_policy,
        }

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
        if (provider or "").lower().strip() not in PROVIDER_COLUMN_MAP:
            return None
        resolved = await SettingsResolver.resolve_effective_ai_config(
            db=db, ctx=ctx, provider=provider, user_id=user_id, org_id=org_id
        )
        return resolved.get("api_key")

get_effective_ai_key = SettingsResolver.get_effective_ai_key
