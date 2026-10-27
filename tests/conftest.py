import os
import sys
from pathlib import Path
import pytest

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

# Direct test suite to an isolated PostgreSQL test database (issuetopr_test)
test_db_url = f"postgresql+asyncpg://{os.getenv('USER', 'shahi')}@localhost:5432/issuetopr_test"
os.environ["DATABASE_URL"] = test_db_url

from app.core.config import settings
settings.DATABASE_URL = test_db_url

from app.db.database import create_tables, init_engine

@pytest.fixture(autouse=True, scope="session")
async def setup_test_db():
    await init_engine()
    await create_tables()
    yield
