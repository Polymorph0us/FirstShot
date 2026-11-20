from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "FirstShot"
    VERSION: str = "1.0.0"
    TIMEZONE: str = "Asia/Kolkata"

    # Database
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BACKEND_DIR}/firstshot.db"
    SYNC_DATABASE_URL: str = f"sqlite:///{BACKEND_DIR}/firstshot.db"

    # Saveetha Portal URLs & Paths
    SAVEETHA_BASE_URL: str = "https://learner.saveetha.in"
    SAVEETHA_EVENT_URL: str = "https://learner.saveetha.in/academicevents/event-booking/"
    SAVEETHA_PROFILE_DIR: str = str(PROJECT_ROOT / ".local" / "saveetha-profile")

    # Monitoring defaults
    DEFAULT_MONITOR_INTERVAL_SECONDS: int = 60
    DEFAULT_MODE: str = "OBSERVE"  # OBSERVE or ASSIST

    model_config = {
        "env_file": ".env",
        "extra": "allow"
    }

settings = Settings()
