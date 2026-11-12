import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func

from app.core.config import settings
from app.core.security import verify_session_token
from app.db.database import create_tables, get_session_factory
from app.models.models import Issue, Repository, PlatformSettings
from app.api.v1.auth import router as auth_router
from app.api.v1.issues import router as issues_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.tracker import router as tracker_router
from app.api.v1.settings import router as settings_router
from app.api.v1.discovery import router as discovery_router
from app.api.v1.audit import router as audit_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.runners import router as runners_router
from app.api.v1.billing import router as billing_router
from app.api.v1.streaming import router as streaming_router
from app.api.v1.bounties import router as bounties_router
from app.api.v1.enterprise import router as enterprise_router
from app.api.v1.organizations import router as organizations_router
from app.services.ranking_service import RankingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

async def seed_initial_data_if_needed():
    """Populates default settings and discovers live open unassigned issues if database is fresh."""
    session_factory = await get_session_factory()
    async with session_factory() as session:
        # Default Platform Settings if not already present
        sett_res = await session.execute(select(PlatformSettings).where(PlatformSettings.id == 1))
        if not sett_res.scalar_one_or_none():
            settings_obj = PlatformSettings(
                id=1,
                github_token=None,
                github_username="",
                auto_publish_pr=False,
                workspace_root=str(settings.WORKSPACE_ROOT),
                antigravity_app_path=settings.ANTIGRAVITY_APP_PATHS[0],
                skills_profile=settings.DEFAULT_SKILLS,
                discovery_filters={"languages": settings.DISCOVERY_LANGUAGES}
            )
            session.add(settings_obj)
            await session.commit()

        logger.info("Platform settings verified. Ready for PR & Contribution tracking.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Issue-to-PR backend application...")
    await create_tables()
    await seed_initial_data_if_needed()
    
    session_factory = await get_session_factory()
    # Phase 5: Reconcile interrupted tasks non-blockingly so the server binds and passes healthchecks instantly
    from app.services.background_worker import (
        reconcile_tasks_on_startup,
        BackgroundWorkerService,
        set_background_worker,
    )
    asyncio.create_task(reconcile_tasks_on_startup(session_factory))

    # Start background worker for PR sync and 2-hour discovery cron
    worker_service = BackgroundWorkerService(
        session_factory=session_factory,
        discovery_interval_sec=7200,
        pr_poll_interval_sec=60
    )
    set_background_worker(worker_service)
    worker_service.start()

    yield

    logger.info("Shutting down Issue-to-PR backend application...")
    await worker_service.stop()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Enable automatic GZip response compression for payloads > 1000 bytes
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def enforce_auth_middleware(request: Request, call_next):
    # Allow CORS preflight requests
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    # Protect all /api/v1/* endpoints except auth login, biometric authentication, and health checks
    PUBLIC_AUTH_PATHS = {
        "/api/v1/billing/webhook",
        "/api/v1/billing/plans",
        "/api/v1/billing/upi/config",
        "/api/v1/health",
    }
    if path.startswith("/api/v1"):
        is_public_auth = path.startswith("/api/v1/auth/") and path != "/api/v1/auth/me"
        if (
            is_public_auth
            or path in PUBLIC_AUTH_PATHS
            or path == "/api/v1/webhooks/github"
            or path.startswith("/api/v1/runners")
        ):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required. Please enter platform password."}
            )
        token = auth_header.split("Bearer ", 1)[1].strip()
        if not verify_session_token(token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Session expired or invalid. Please re-authenticate."}
            )

    return await call_next(request)

# Include API Routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(tracker_router, prefix=settings.API_V1_STR)
app.include_router(issues_router, prefix=settings.API_V1_STR)
app.include_router(tasks_router, prefix=settings.API_V1_STR)
app.include_router(settings_router, prefix=settings.API_V1_STR)
app.include_router(discovery_router, prefix=settings.API_V1_STR)
app.include_router(audit_router, prefix=settings.API_V1_STR)
app.include_router(webhooks_router, prefix=settings.API_V1_STR)
app.include_router(runners_router, prefix=settings.API_V1_STR)
app.include_router(billing_router, prefix=settings.API_V1_STR)
app.include_router(streaming_router, prefix=settings.API_V1_STR)
app.include_router(bounties_router, prefix=settings.API_V1_STR)
app.include_router(enterprise_router, prefix=settings.API_V1_STR)
app.include_router(organizations_router, prefix=settings.API_V1_STR)

@app.get("/health")
@app.get("/api/health")
@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }

# Unified Frontend static bundle serving for PWA
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api"):
        return JSONResponse(status_code=404, content={"detail": "API endpoint not found"})
    target = frontend_dist / full_path
    if target.exists() and target.is_file():
        # Immutable caching for hashed assets (never re-fetched unnecessarily)
        if "assets/" in full_path:
            return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable"})
        # Never cache sw.js, manifest, or index.html so mobile clients always get latest deployment
        if full_path in ("sw.js", "manifest.webmanifest", "index.html"):
            return FileResponse(
                target,
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
        return FileResponse(target)
    index_file = frontend_dist / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse(status_code=404, content={"detail": "Frontend bundle not found. Run npm run build."})
