import asyncio
import logging
import os
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
from app.api.v1.admin import router as admin_router
from app.services.ranking_service import RankingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

async def seed_initial_data_if_needed():
    """Populates default settings and discovers live open unassigned issues if database is fresh."""
    session_factory = await get_session_factory()
    async with session_factory() as session:
        # Default Platform Settings if not already present
        sett_res = await session.execute(select(PlatformSettings).where(PlatformSettings.id == 1))
        existing_sett = sett_res.scalar_one_or_none()
        if not existing_sett:
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
        elif (
            not os.getenv("PYTEST_CURRENT_TEST")
            and os.getenv("ENVIRONMENT") != "testing"
            and isinstance(existing_sett.discovery_filters, dict)
            and "_admin_runtime" in existing_sett.discovery_filters
        ):
            settings.apply_runtime_overrides(existing_sett.discovery_filters.get("_admin_runtime") or {})

        logger.info("Platform settings verified. Ready for PR & Contribution tracking.")

        # Seed new requested organizations (Zulip, Learning Equality, Rocket.Chat, CircuitVerse, Wikimedia)
        try:
            from datetime import datetime
            new_org_repos = [
                {
                    "owner": "zulip", "name": "zulip", "full_name": "zulip/zulip",
                    "html_url": "https://github.com/zulip/zulip", "primary_language": "Python",
                    "license_spdx": "Apache-2.0", "stars_count": 21000, "gsoc_org_name": "Zulip",
                    "issue": {
                        "github_id": 6420284631, "issue_number": 40708,
                        "title": "Scheduled messages are sent to the old topic after the topic is resolved or renamed",
                        "body": "When a topic is renamed or marked as resolved, scheduled messages queued previously should route to the updated topic title.",
                        "html_url": "https://github.com/zulip/zulip/issues/40708",
                        "labels": [{"name": "area: scheduled messages", "color": "e11d48"}, {"name": "bug", "color": "d73a4a"}],
                        "ranking_score": 92.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 3,
                    }
                },
                {
                    "owner": "learningequality", "name": "kolibri", "full_name": "learningequality/kolibri",
                    "html_url": "https://github.com/learningequality/kolibri", "primary_language": "Python",
                    "license_spdx": "MIT", "stars_count": 3200, "gsoc_org_name": "Learning Equality",
                    "issue": {
                        "github_id": 6433233795, "issue_number": 15916,
                        "title": "kolibri-server source package build aborts on `tests/`, which the orig tarball excludes",
                        "body": "Source package build fails when searching for tests directory excluded from original release archive.",
                        "html_url": "https://github.com/learningequality/kolibri/issues/15916",
                        "labels": [{"name": "build", "color": "0284c7"}, {"name": "good first issue", "color": "10b981"}],
                        "ranking_score": 94.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 4,
                    }
                },
                {
                    "owner": "learningequality", "name": "studio", "full_name": "learningequality/studio",
                    "html_url": "https://github.com/learningequality/studio", "primary_language": "Python",
                    "license_spdx": "MIT", "stars_count": 800, "gsoc_org_name": "Learning Equality",
                },
                {
                    "owner": "learningequality", "name": "kolibri-design-system", "full_name": "learningequality/kolibri-design-system",
                    "html_url": "https://github.com/learningequality/kolibri-design-system", "primary_language": "JavaScript",
                    "license_spdx": "MIT", "stars_count": 350, "gsoc_org_name": "Learning Equality",
                },
                {
                    "owner": "RocketChat", "name": "Rocket.Chat", "full_name": "RocketChat/Rocket.Chat",
                    "html_url": "https://github.com/rocketchat/rocket.chat", "primary_language": "TypeScript",
                    "license_spdx": "GPL-3.0", "stars_count": 41000, "gsoc_org_name": "Rocket.Chat",
                    "issue": {
                        "github_id": 6432954219, "issue_number": 43767,
                        "title": "Navigation sidebar accessibility and theme variations",
                        "body": "Allow side navigation variations to respect compact view mode and high contrast accessibility settings.",
                        "html_url": "https://github.com/rocketchat/rocket.chat/issues/43767",
                        "labels": [{"name": "ui/ux", "color": "8b5cf6"}, {"name": "accessibility", "color": "f59e0b"}],
                        "ranking_score": 89.0, "difficulty_estimate": "intermediate", "estimated_effort_hours": 6,
                    }
                },
                {
                    "owner": "RocketChat", "name": "EmbeddedChat", "full_name": "RocketChat/EmbeddedChat",
                    "html_url": "https://github.com/RocketChat/EmbeddedChat", "primary_language": "TypeScript",
                    "license_spdx": "MIT", "stars_count": 950, "gsoc_org_name": "Rocket.Chat",
                    "issue": {
                        "github_id": 6411254188, "issue_number": 1433,
                        "title": "bug(layout-editor): theme refinements like 'change it to dark' are ignored with AI providers",
                        "body": "Ensure theme toggle refinement commands are parsed properly when streaming LLM responses in layout editor.",
                        "html_url": "https://github.com/RocketChat/EmbeddedChat/issues/1433",
                        "labels": [{"name": "bug", "color": "d73a4a"}, {"name": "good first issue", "color": "10b981"}],
                        "ranking_score": 96.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 3,
                    }
                },
                {
                    "owner": "CircuitVerse", "name": "CircuitVerse", "full_name": "CircuitVerse/CircuitVerse",
                    "html_url": "https://github.com/circuitverse/circuitverse", "primary_language": "Ruby",
                    "license_spdx": "GPL-3.0", "stars_count": 2300, "gsoc_org_name": "CircuitVerse.org",
                    "issue": {
                        "github_id": 6422610048, "issue_number": 8189,
                        "title": "ActiveRecord::QueryCanceled statement timeout optimization on simulator circuits index",
                        "body": "Optimize heavy query joins when retrieving public circuits with multiple component tags.",
                        "html_url": "https://github.com/circuitverse/circuitverse/issues/8189",
                        "labels": [{"name": "performance", "color": "e11d48"}, {"name": "backend", "color": "2563eb"}],
                        "ranking_score": 91.0, "difficulty_estimate": "intermediate", "estimated_effort_hours": 5,
                    }
                },
                {
                    "owner": "CircuitVerse", "name": "cv-frontend-vue", "full_name": "CircuitVerse/cv-frontend-vue",
                    "html_url": "https://github.com/CircuitVerse/cv-frontend-vue", "primary_language": "JavaScript",
                    "license_spdx": "GPL-3.0", "stars_count": 600, "gsoc_org_name": "CircuitVerse.org",
                    "issue": {
                        "github_id": 6422411851, "issue_number": 1542,
                        "title": "Fix typo in PropertiesPanel prop name panleBodyData across desktop and child components",
                        "body": "Standardize prop naming to panelBodyData across desktop views and circuit canvas.",
                        "html_url": "https://github.com/CircuitVerse/cv-frontend-vue/issues/1542",
                        "labels": [{"name": "bug", "color": "d73a4a"}, {"name": "good first issue", "color": "10b981"}],
                        "ranking_score": 97.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 2,
                    }
                },
                {
                    "owner": "WikiEducationFoundation", "name": "WikiEduDashboard", "full_name": "WikiEducationFoundation/WikiEduDashboard",
                    "html_url": "https://github.com/WikiEducationFoundation/WikiEduDashboard", "primary_language": "Ruby",
                    "license_spdx": "MIT", "stars_count": 1800, "gsoc_org_name": "Wikimedia Foundation",
                    "issue": {
                        "github_id": 6363715530, "issue_number": 7279,
                        "title": "Improve Sidekiq worker concurrency and job monitoring documentation",
                        "body": "Add setup instructions for Sidekiq worker pools and healthcheck endpoints in development.",
                        "html_url": "https://github.com/WikiEducationFoundation/WikiEduDashboard/issues/7279",
                        "labels": [{"name": "documentation", "color": "0284c7"}, {"name": "good first issue", "color": "10b981"}],
                        "ranking_score": 95.0, "difficulty_estimate": "beginner", "estimated_effort_hours": 2,
                    }
                },
                {
                    "owner": "wikimedia", "name": "mediawiki-extensions-Wikisource", "full_name": "wikimedia/mediawiki-extensions-Wikisource",
                    "html_url": "https://github.com/wikimedia/mediawiki-extensions-Wikisource", "primary_language": "PHP",
                    "license_spdx": "GPL-2.0", "stars_count": 350, "gsoc_org_name": "Wikimedia Foundation",
                },
                {
                    "owner": "Open-Knowledge-Impact-Foundation", "name": "campwiz-nxt-frontend2", "full_name": "Open-Knowledge-Impact-Foundation/campwiz-nxt-frontend2",
                    "html_url": "https://github.com/Open-Knowledge-Impact-Foundation/campwiz-nxt-frontend2", "primary_language": "JavaScript",
                    "license_spdx": "MIT", "stars_count": 120, "gsoc_org_name": "Wikimedia Foundation",
                },
                {
                    "owner": "hatnote", "name": "montage", "full_name": "hatnote/montage",
                    "html_url": "https://github.com/hatnote/montage", "primary_language": "Python",
                    "license_spdx": "MIT", "stars_count": 280, "gsoc_org_name": "Wikimedia Foundation",
                },
            ]

            for entry in new_org_repos:
                fn = entry["full_name"]
                r_stmt = select(Repository).where(Repository.full_name == fn)
                existing_r = (await session.execute(r_stmt)).scalar_one_or_none()
                if not existing_r:
                    repo_obj = Repository(
                        owner=entry["owner"],
                        name=entry["name"],
                        full_name=fn,
                        html_url=entry["html_url"],
                        default_branch="main",
                        primary_language=entry.get("primary_language", "Python"),
                        license_spdx=entry.get("license_spdx", "MIT"),
                        stars_count=entry.get("stars_count", 100),
                        is_gsoc=True,
                        gsoc_org_name=entry.get("gsoc_org_name"),
                        last_inspected_at=datetime.utcnow()
                    )
                    session.add(repo_obj)
                    await session.flush()
                else:
                    repo_obj = existing_r
                    repo_obj.is_gsoc = True
                    repo_obj.gsoc_org_name = entry.get("gsoc_org_name")
                    await session.flush()

                iss_data = entry.get("issue")
                if iss_data:
                    i_stmt = select(Issue).where(Issue.github_id == iss_data["github_id"])
                    existing_i = (await session.execute(i_stmt)).scalar_one_or_none()
                    if not existing_i:
                        new_iss = Issue(
                            repository_id=repo_obj.id,
                            github_id=iss_data["github_id"],
                            issue_number=iss_data["issue_number"],
                            title=iss_data["title"],
                            body=iss_data["body"],
                            html_url=iss_data["html_url"],
                            state="open",
                            labels=iss_data.get("labels", []),
                            assignees=[],
                            is_eligible=True,
                            license_status="VERIFIED_OSI",
                            policy_status="READY_TO_WORK",
                            ranking_score=iss_data.get("ranking_score", 90.0),
                            difficulty_estimate=iss_data.get("difficulty_estimate", "beginner"),
                            estimated_effort_hours=iss_data.get("estimated_effort_hours", 4),
                            last_verified_at=datetime.utcnow()
                        )
                        session.add(new_iss)

            await session.commit()
            logger.info("New organizations and repositories seeded successfully.")
        except Exception as seed_err:
            logger.warning(f"Error seeding new organizations: {seed_err}")

        # Purge unselected issues belonging to older showcase orgs (NumFOCUS, PSF, DeepChem, Kornia)
        try:
            from app.models.models import Task, AuditLog
            from sqlalchemy import delete, update
            other_org_owners = [
                "numfocus", "numpy", "scipy", "pandas-dev", "matplotlib",
                "scikit-learn", "scikit-image", "sympy", "networkx", "astropy",
                "jupyter", "jupyterlab", "dask", "xarray", "zarr-developers", "statsmodels",
                "psf", "python", "pallets", "pypa", "celery", "pylint-dev",
                "deepchem", "kornia"
            ]
            selected_subquery = select(Task.issue_id).where(Task.issue_id.is_not(None)).distinct()
            unselected_other_issues_subq = (
                select(Issue.id)
                .join(Repository, Issue.repository_id == Repository.id)
                .where(func.lower(Repository.owner).in_(other_org_owners))
                .where(Issue.id.not_in(selected_subquery))
            )
            await session.execute(
                update(AuditLog)
                .where(AuditLog.issue_id.in_(unselected_other_issues_subq))
                .values(issue_id=None)
            )
            await session.execute(
                delete(Issue)
                .where(Issue.id.in_(unselected_other_issues_subq))
            )
            await session.commit()
            logger.info("Purged unselected legacy showcase issues successfully.")
        except Exception as purge_err:
            logger.warning(f"Error purging unselected legacy showcase issues: {purge_err}")

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

    # Start background worker for PR sync and 24/7 continuous discovery cron (5-minute interval)
    worker_service = BackgroundWorkerService(
        session_factory=session_factory,
        discovery_interval_sec=300,
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
app.include_router(admin_router, prefix=settings.API_V1_STR)

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
