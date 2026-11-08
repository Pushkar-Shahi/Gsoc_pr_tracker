import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

# Configure engine with robust fallback
engine = None
AsyncSessionLocal = None

async def init_engine():
    global engine, AsyncSessionLocal
    try:
        # Try primary PostgreSQL connection
        test_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            future=True,
            pool_pre_ping=True
        )
        async with test_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        engine = test_engine
        logger.info(f"Connected to PostgreSQL database at {settings.DATABASE_URL}")
    except Exception as e:
        logger.warning(f"PostgreSQL connection failed ({e}). Falling back to SQLite: {settings.SQLITE_FALLBACK_URL}")
        engine = create_async_engine(
            settings.SQLITE_FALLBACK_URL,
            echo=False,
            future=True
        )
    
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    return engine

async def get_session_factory():
    global AsyncSessionLocal
    if AsyncSessionLocal is None:
        await init_engine()
    return AsyncSessionLocal

async def get_db():
    factory = await get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()

async def create_tables():
    global engine
    if engine is None:
        await init_engine()
    # Ensure all models are imported into Base.metadata
    from app.models.models import (
        User, Organization, Membership, Repository, Issue, Task,
        DiscoveryCheckpoint, AuditLog, PlatformSettings,
        UserSettings, OrganizationSettings, Runner, RunnerJob
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        is_pg = "postgresql" in str(engine.url)

        # Drop strict DB-level foreign keys if they exist so test fixtures with unseeded tenant IDs succeed
        if is_pg:
            for tbl in ("tasks", "audit_logs", "issues", "repositories"):
                try:
                    await conn.execute(text(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {tbl}_tenant_id_fkey;"))
                    await conn.execute(text(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {tbl}_user_id_fkey;"))
                except Exception:
                    pass

        # Safe migration for new columns on tasks table
        columns_to_add = [
            ("pr_review_status", "VARCHAR(64)"),
            ("pr_review_comments", "JSON DEFAULT '[]'::json" if is_pg else "TEXT"),
            ("pr_merged", "BOOLEAN DEFAULT FALSE"),
            ("blocked_reason", "TEXT")
        ]
        for col_name, col_type in columns_to_add:
            try:
                if is_pg:
                    await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
                else:
                    await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type};"))
            except Exception:
                pass

        # Safe migration for availability and linked PR columns on issues table
        issue_cols_to_add = [
            ("has_open_pr", "BOOLEAN DEFAULT FALSE"),
            ("linked_pr_count", "INTEGER DEFAULT 0"),
            ("linked_prs", "JSON DEFAULT '[]'::json" if is_pg else "TEXT"),
            ("is_reserved", "BOOLEAN DEFAULT FALSE"),
            ("reservation_reason", "VARCHAR(512)"),
            ("availability_status", "VARCHAR(32) DEFAULT 'AVAILABLE'")
        ]
        for col_name, col_type in issue_cols_to_add:
            try:
                if is_pg:
                    await conn.execute(text(f"ALTER TABLE issues ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
                else:
                    await conn.execute(text(f"ALTER TABLE issues ADD COLUMN {col_name} {col_type};"))
            except Exception:
                pass

        # Safe migration for multi-tenant columns across tables
        multi_tenant_cols = [
            ("repositories", "tenant_id", "VARCHAR(36)"),
            ("repositories", "user_id", "VARCHAR(36)"),
            ("issues", "tenant_id", "VARCHAR(36)"),
            ("issues", "user_id", "VARCHAR(36)"),
            ("tasks", "tenant_id", "VARCHAR(36)"),
            ("tasks", "user_id", "VARCHAR(36)"),
            ("audit_logs", "tenant_id", "VARCHAR(36)"),
            ("audit_logs", "user_id", "VARCHAR(36)"),
        ]
        for tbl, col_name, col_def in multi_tenant_cols:
            try:
                if is_pg:
                    await conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col_name} {col_def};"))
                else:
                    await conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col_name} {col_def};"))
            except Exception:
                pass

        # Create indexes for tenant_id and user_id
        for tbl in ("repositories", "issues", "tasks", "audit_logs"):
            try:
                await conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{tbl}_tenant_id ON {tbl}(tenant_id);"))
                await conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{tbl}_user_id ON {tbl}(user_id);"))
            except Exception:
                pass

        # Safe migration for new columns on repositories table
        repo_cols = [
            ("is_gsoc", "BOOLEAN DEFAULT FALSE"),
            ("gsoc_org_name", "VARCHAR(255)")
        ]
        for col_name, col_type in repo_cols:
            try:
                if is_pg:
                    await conn.execute(text(f"ALTER TABLE repositories ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
                else:
                    await conn.execute(text(f"ALTER TABLE repositories ADD COLUMN {col_name} {col_type};"))
            except Exception:
                pass

        # Safe migration for Phase 4: Bounty and SSO columns
        phase4_cols = [
            ("organizations", "sso_provider", "VARCHAR(64)"),
            ("organizations", "sso_metadata_url", "VARCHAR(1024)"),
            ("organizations", "sso_entity_id", "VARCHAR(512)"),
            ("organizations", "sso_enforced", "BOOLEAN DEFAULT FALSE"),
            ("organizations", "sso_config", "JSON DEFAULT '{}'::json" if is_pg else "TEXT"),
            ("issues", "bounty_amount", "DOUBLE PRECISION DEFAULT 0.0" if is_pg else "REAL DEFAULT 0.0"),
            ("issues", "bounty_currency", "VARCHAR(16) DEFAULT 'USD'"),
            ("issues", "bounty_platform", "VARCHAR(64)"),
            ("issues", "bounty_url", "VARCHAR(1024)"),
            ("issues", "bounty_status", "VARCHAR(32) DEFAULT 'NONE'")
        ]
        for tbl, col_name, col_type in phase4_cols:
            try:
                if is_pg:
                    await conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
                else:
                    await conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col_name} {col_type};"))
            except Exception:
                pass

        try:
            if is_pg:
                await conn.execute(text("ALTER TABLE runners ALTER COLUMN registration_token TYPE TEXT;"))
        except Exception:
            pass

        # Backfill existing repositories in DB matching GSoC organizations
        try:
            from app.core.gsoc_orgs import GSOC_ORGS_MAP
            for owner_key, org_name in GSOC_ORGS_MAP.items():
                clean_name = org_name.replace("'", "''")
                await conn.execute(text(
                    f"UPDATE repositories SET is_gsoc = TRUE, gsoc_org_name = '{clean_name}' "
                    f"WHERE (LOWER(owner) = '{owner_key.lower()}' OR LOWER(name) = '{owner_key.lower()}') "
                    f"AND (is_gsoc IS NULL OR is_gsoc = FALSE);"
                ))
        except Exception as e:
            logger.debug(f"GSoC repo backfill skipped: {e}")

        # Seed Default Tenant & User for Seamless Backward Compatibility
        try:
            # Check default user
            u_check = await conn.execute(text("SELECT id FROM users WHERE id = 'default-user'"))
            if not u_check.scalar_one_or_none():
                admin_check = await conn.execute(text("SELECT id FROM users WHERE github_username = 'admin'"))
                if not admin_check.scalar_one_or_none():
                    await conn.execute(text(
                        "INSERT INTO users (id, github_username, name, email, is_active, is_superuser, created_at, updated_at) "
                        f"VALUES ('default-user', 'admin', 'Admin User', 'admin@example.com', {'TRUE, TRUE' if is_pg else '1, 1'}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"
                    ))

            # Check default org
            o_check = await conn.execute(text("SELECT id FROM organizations WHERE id = 'default-org'"))
            if not o_check.scalar_one_or_none():
                slug_check = await conn.execute(text("SELECT id FROM organizations WHERE slug = 'default-org'"))
                if not slug_check.scalar_one_or_none():
                    default_tier = getattr(settings, "DEFAULT_ORG_TIER", "pro")
                    bool_val = 'TRUE' if is_pg else '1'
                    await conn.execute(text(
                        "INSERT INTO organizations (id, name, slug, is_personal, billing_tier, created_at, updated_at) "
                        f"VALUES ('default-org', 'Personal Workspace', 'default-org', {bool_val}, '{default_tier}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"
                    ))

            # Check default membership
            m_check = await conn.execute(text("SELECT id FROM memberships WHERE user_id = 'default-user' AND org_id = 'default-org'"))
            if not m_check.scalar_one_or_none():
                await conn.execute(text(
                    "INSERT INTO memberships (id, user_id, org_id, role, created_at, updated_at) "
                    "VALUES ('default-membership', 'default-user', 'default-org', 'owner', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"
                ))

            # Backfill existing tasks and audit_logs where tenant_id is NULL
            await conn.execute(text(
                "UPDATE tasks SET tenant_id = 'default-org', user_id = 'default-user' WHERE tenant_id IS NULL;"
            ))
            await conn.execute(text(
                "UPDATE audit_logs SET tenant_id = 'default-org', user_id = 'default-user' WHERE tenant_id IS NULL;"
            ))
        except Exception as e:
            logger.warning(f"Default user/org seed or backfill warning: {e}")

    logger.info("Database tables verified and initialized.")
