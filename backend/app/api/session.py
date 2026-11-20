from fastapi import APIRouter

from app.models.schemas import SessionStatusResponse
from app.services.scheduler import monitoring_engine

router = APIRouter(prefix="/api/session", tags=["Session"])

@router.get("/status", response_model=SessionStatusResponse)
async def get_session_status():
    """Check whether local browser profile has an active Saveetha session."""
    provider = monitoring_engine.provider
    status = await provider.check_session()
    return SessionStatusResponse(
        authenticated=status.get("authenticated", False),
        profile_dir=provider.profile_dir,
        portal_url=provider.event_url,
        message=status.get("message", "Unknown status")
    )

@router.post("/reauthenticate")
async def trigger_reauthenticate():
    """Launch visible browser on local screen to allow user to log in."""
    provider = monitoring_engine.provider
    success = await provider.reauthenticate()
    return {
        "success": success,
        "message": "Reauthentication completed." if success else "Reauthentication timed out or cancelled."
    }
