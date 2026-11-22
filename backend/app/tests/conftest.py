import os
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure isolated SQLite test database for pytest runs
TEST_DB_PATH = Path(__file__).resolve().parent.parent.parent / "test_firstshot.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
os.environ["SYNC_DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from app.core.auth import get_current_user
from app.core.config import settings

settings.DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH}"
settings.SYNC_DATABASE_URL = f"sqlite:///{TEST_DB_PATH}"

from app.database import session as db_session
from app.main import app
from app.models.user import User

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

@pytest.fixture(autouse=True)
def default_auth_override():
    """Default authentication override providing Owner context for legacy test suites."""
    owner = User(
        id=1,
        username="owner",
        role="owner",
        profile_dir=settings.SAVEETHA_PROFILE_DIR
    )
    app.dependency_overrides[get_current_user] = lambda: owner
    yield
    app.dependency_overrides.pop(get_current_user, None)
