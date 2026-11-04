"""
Preflight & Production Health Verification Engine.
Validates database connectivity, runs schema migrations, checks secret entropy,
and inspects configuration before application startup.
"""

import asyncio
import logging
import os
import sys
from typing import Dict, Any, List

from sqlalchemy import text
from app.core.config import settings
from app.db.database import init_engine, create_tables

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("preflight")


async def run_preflight_checks() -> Dict[str, Any]:
    """
    Executes comprehensive preflight checks:
    1. Database connectivity and schema migration.
    2. Secret entropy validation.
    3. Storage permissions.
    4. Integration credentials readiness.
    """
    report: Dict[str, Any] = {
        "status": "healthy",
        "checks": {},
        "warnings": [],
        "errors": []
    }

    # 1. Database Connectivity & Migration Check
    try:
        engine = await init_engine()
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            assert res.scalar() == 1
        await create_tables()
        db_type = "PostgreSQL" if "postgresql" in str(engine.url) else "SQLite Fallback"
        report["checks"]["database"] = {
            "status": "ok",
            "type": db_type,
            "url": str(engine.url).split("@")[-1] if "@" in str(engine.url) else str(engine.url)
        }
    except Exception as e:
        report["status"] = "error"
        err_msg = f"Database connection or migration failed: {str(e)}"
        report["errors"].append(err_msg)
        report["checks"]["database"] = {"status": "error", "error": str(e)}

    # 2. Secret Key Entropy Check
    secret = settings.SECRET_KEY or ""
    is_prod = os.getenv("ENVIRONMENT", "development").lower() in ("production", "prod")
    default_secret = "issuetopr_secure_jwt_secret_mwps_2026"

    if secret == default_secret or len(secret) < 32:
        if is_prod:
            report["status"] = "error"
            report["errors"].append("SECRET_KEY must be a unique, cryptographically random string (min 32 chars) in production.")
        else:
            report["warnings"].append("SECRET_KEY is using development default. Set a strong SECRET_KEY in production.")
        report["checks"]["secret_key"] = {"status": "warning" if not is_prod else "error", "length": len(secret)}
    else:
        report["checks"]["secret_key"] = {"status": "ok", "length": len(secret)}

    # 3. Storage Permissions Check
    try:
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        test_file = settings.DATA_DIR / ".preflight_write_test"
        test_file.write_text("ok")
        test_file.unlink()
        report["checks"]["storage"] = {
            "status": "ok",
            "data_dir": str(settings.DATA_DIR),
            "workspace_root": str(settings.WORKSPACE_ROOT)
        }
    except Exception as e:
        report["status"] = "error"
        report["errors"].append(f"Storage directory write check failed: {e}")
        report["checks"]["storage"] = {"status": "error", "error": str(e)}

    # 4. Stripe Integration Check
    stripe_key = settings.STRIPE_SECRET_KEY or ""
    if stripe_key.startswith("sk_live_"):
        stripe_mode = "live"
    elif stripe_key.startswith("sk_test_"):
        stripe_mode = "test"
    else:
        stripe_mode = "simulation"
    report["checks"]["stripe"] = {
        "status": "ok",
        "mode": stripe_mode,
        "webhook_configured": bool(settings.STRIPE_WEBHOOK_SECRET)
    }

    # 5. GitHub Integration Check
    has_github_auth = bool(settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET)
    has_github_token = bool(settings.GITHUB_TOKEN)
    report["checks"]["github"] = {
        "status": "ok",
        "oauth_configured": has_github_auth,
        "fallback_token_present": has_github_token
    }

    # 6. Task Queue & Sandboxing Provider Check
    redis_configured = bool(getattr(settings, "REDIS_URL", None))
    workspace_provider = getattr(settings, "WORKSPACE_PROVIDER", "local")
    report["checks"]["runtime"] = {
        "queue_backend": "redis" if redis_configured else "in_memory_async",
        "workspace_provider": workspace_provider,
        "e2b_configured": bool(getattr(settings, "E2B_API_KEY", None))
    }

    if report["errors"]:
        report["status"] = "error"
    elif report["warnings"] and report["status"] == "healthy":
        report["status"] = "warning"

    return report


def main():
    """CLI Entry point for preflight check."""
    logger.info("Starting Issue-to-PR Platform Preflight Health Verification...")
    report = asyncio.run(run_preflight_checks())

    print("\n================ PREFLIGHT HEALTH REPORT ================")
    print(f"Overall Status: {report['status'].upper()}")
    for check_name, check_data in report["checks"].items():
        sub_status = check_data.get("status", "ok").upper()
        print(f" - {check_name:15}: [{sub_status}] {check_data}")

    if report["warnings"]:
        print("\nWarnings:")
        for w in report["warnings"]:
            print(f"  [!] {w}")

    if report["errors"]:
        print("\nErrors:")
        for e in report["errors"]:
            print(f"  [X] {e}")
        print("=========================================================\n")
        sys.exit(1)

    print("=========================================================\n")
    sys.exit(0)


if __name__ == "__main__":
    main()

