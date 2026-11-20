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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def migrate_columns(connection):
            cursor = connection.connection.cursor()
            cursor.execute("PRAGMA table_info(booking_preferences)")
            existing = {row[1] for row in cursor.fetchall()}
            cols_to_add = [
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
            if "retry_count" not in existing_attempts:
                cursor.execute("ALTER TABLE booking_attempts ADD COLUMN retry_count INTEGER DEFAULT 0")

        await conn.run_sync(migrate_columns)
