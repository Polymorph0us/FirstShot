import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    from app.core.auth import hash_password
    from app.models.user import User, UserSession  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def migrate_columns(connection):
            cursor = connection.connection.cursor()

            # Ensure owner user exists
            cursor.execute("SELECT id FROM users WHERE id = 1 OR role = 'owner'")
            owner_row = cursor.fetchone()
            if not owner_row:
                initial_pwd = os.environ.get("FIRSTSHOT_OWNER_PASSWORD", "firstshot_owner_2026")
                pwd_hash = hash_password(initial_pwd)
                cursor.execute(
                    "INSERT INTO users (id, username, password_hash, role, profile_dir) VALUES (?, ?, ?, ?, ?)",
                    (1, "owner", pwd_hash, "owner", settings.SAVEETHA_PROFILE_DIR)
                )

            cursor.execute("PRAGMA table_info(booking_preferences)")
            existing = {row[1] for row in cursor.fetchall()}
            cols_to_add = [
                ("user_id", "INTEGER DEFAULT 1"),
                ("booking_mode", "VARCHAR(20) DEFAULT 'OBSERVE'"),
                ("is_armed", "BOOLEAN DEFAULT 0"),
                ("armed_at", "DATETIME"),
                ("purpose", "VARCHAR(255) DEFAULT 'Academic Continuous Assessment'"),
                ("user_permitted_automation", "BOOLEAN DEFAULT 0"),
                ("execution_status", "VARCHAR(50) DEFAULT 'IDLE'"),
                ("retry_window_seconds", "INTEGER DEFAULT 300"),
                ("last_preflight_status", "VARCHAR(50)"),
                ("last_preflight_details", "TEXT"),
                ("last_preflight_at", "DATETIME"),
            ]
            for col_name, col_type in cols_to_add:
                if col_name not in existing:
                    cursor.execute(f"ALTER TABLE booking_preferences ADD COLUMN {col_name} {col_type}")

            # Migrate booking_attempts table
            cursor.execute("PRAGMA table_info(booking_attempts)")
            existing_attempts = {row[1] for row in cursor.fetchall()}
            if "user_id" not in existing_attempts:
                cursor.execute("ALTER TABLE booking_attempts ADD COLUMN user_id INTEGER DEFAULT 1")
            if "retry_count" not in existing_attempts:
                cursor.execute("ALTER TABLE booking_attempts ADD COLUMN retry_count INTEGER DEFAULT 0")

            # Guarantee all existing targets and attempts belong to owner (id=1)
            cursor.execute("UPDATE booking_preferences SET user_id = 1 WHERE user_id IS NULL")
            cursor.execute("UPDATE booking_attempts SET user_id = 1 WHERE user_id IS NULL")

        await conn.run_sync(migrate_columns)
