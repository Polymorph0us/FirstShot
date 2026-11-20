import os
from pathlib import Path

import pytest

# Ensure isolated SQLite test database for pytest runs
TEST_DB_PATH = Path(__file__).resolve().parent.parent.parent / "test_firstshot.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
os.environ["SYNC_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from app.core.config import settings

settings.DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
settings.SYNC_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import session as db_session

# Re-bind test engine to isolated test DB
test_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)
db_session.engine = test_engine
db_session.AsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

@pytest.fixture(scope="session", autouse=True)
def cleanup_test_database():
    yield
    # Teardown: remove test database file after pytest session completes
    if TEST_DB_PATH.exists():
        try:
            TEST_DB_PATH.unlink()
        except Exception:
            pass
