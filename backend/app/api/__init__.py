from app.api.auth import router as auth_router
from app.api.booking import router as booking_router
from app.api.events import router as events_router
from app.api.monitoring import router as monitoring_router
from app.api.preferences import router as preferences_router
from app.api.session import router as session_router

__all__ = [
    "auth_router",
    "events_router",
    "preferences_router",
    "monitoring_router",
    "session_router",
    "booking_router"
]
