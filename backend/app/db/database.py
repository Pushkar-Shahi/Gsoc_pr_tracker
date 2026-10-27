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
    # Ensure models are loaded into Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe migration for new columns on tasks table
        columns_to_add = [
            ("pr_review_status", "VARCHAR(64)"),
            ("pr_review_comments", "JSON DEFAULT '[]'::json"),
            ("pr_merged", "BOOLEAN DEFAULT FALSE"),
            ("blocked_reason", "TEXT")
        ]
        for col_name, col_type in columns_to_add:
            try:
                if "postgresql" in str(engine.url):
                    await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
                else:
                    await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type};"))
            except Exception:
                pass

        # Safe migration for new columns on repositories table
        repo_cols = [
            ("is_gsoc", "BOOLEAN DEFAULT FALSE"),
            ("gsoc_org_name", "VARCHAR(255)")
        ]
        for col_name, col_type in repo_cols:
            try:
                if "postgresql" in str(engine.url):
                    await conn.execute(text(f"ALTER TABLE repositories ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
                else:
                    await conn.execute(text(f"ALTER TABLE repositories ADD COLUMN {col_name} {col_type};"))
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

    logger.info("Database tables verified and initialized.")
