import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.preference import BookingPreference
from app.models.schemas import (
    ArmTargetRequest,
    PreferenceCreate,
    PreferenceResponse,
    PreflightResponse,
    SetModeRequest,
    TargetSlotEdit,
    TargetSlotFromCard,
)
from app.services.preflight import PreflightEngine
from app.services.scheduler import monitoring_engine, ws_manager

router = APIRouter(prefix="/api/preferences", tags=["Preferences"])

@router.get("/", response_model=List[PreferenceResponse])
async def list_preferences(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BookingPreference).order_by(BookingPreference.id.desc()))
    prefs = result.scalars().all()
    return [p.to_dict() for p in prefs]

@router.post("/", response_model=PreferenceResponse)
async def create_preference(data: PreferenceCreate, db: AsyncSession = Depends(get_db)):
    # Standardize fields between Milestone 1 & Milestone 2
    title = data.event_title or data.title
    if not title:
        raise HTTPException(status_code=400, detail="Event title is required.")

    target_date = data.target_date or data.preferred_date
    preferred_room = data.preferred_room or data.preferred_venue
    preferred_start_time = data.preferred_start_time or data.preferred_time
    preferred_end_time = data.preferred_end_time
    accept_waitlist = data.accept_waitlist if data.allow_waitlist is None else data.allow_waitlist
    monitoring_enabled = data.monitoring_enabled if data.is_active is None else data.is_active

    # Duplicate target prevention
    query = select(BookingPreference).where(
        and_(
            BookingPreference.event_title == title,
            BookingPreference.target_date == target_date,
            BookingPreference.preferred_room == preferred_room,
            BookingPreference.preferred_start_time == preferred_start_time
        )
    )
    existing_res = await db.execute(query)
    if existing_res.scalars().first():
        raise HTTPException(status_code=409, detail="A target slot with this exact title, date, room, and start time already exists.")

    pref = BookingPreference(
        event_title=title,
        target_date=target_date,
        preferred_room=preferred_room,
        preferred_start_time=preferred_start_time,
        preferred_end_time=preferred_end_time,
        alternative_times=",".join(data.alternative_times) if data.alternative_times else None,
        accept_waitlist=accept_waitlist,
        monitoring_enabled=monitoring_enabled,
        max_bookings=data.max_bookings,
        max_attempts=data.max_attempts,
        target_event_id=data.target_event_id
    )
    db.add(pref)
    await db.commit()
    await db.refresh(pref)
    return pref.to_dict()

@router.post("/from-card", response_model=PreferenceResponse)
async def select_card_as_target(data: TargetSlotFromCard, db: AsyncSession = Depends(get_db)):
    """Method A: Direct card selection from dashboard."""
    # Prevent duplicate target
    query = select(BookingPreference).where(
        and_(
            BookingPreference.event_title == data.title,
            BookingPreference.target_date == data.date,
            BookingPreference.preferred_room == data.venue,
            BookingPreference.preferred_start_time == data.start_time
        )
    )
    existing_res = await db.execute(query)
    if existing_res.scalars().first():
        raise HTTPException(status_code=409, detail=f"Target '{data.title}' ({data.venue}, {data.start_time}) is already saved in My Target Slots.")

    pref = BookingPreference(
        event_title=data.title,
        target_date=data.date,
        preferred_room=data.venue,
        preferred_start_time=data.start_time,
        preferred_end_time=data.end_time,
        target_event_id=data.event_id,
        accept_waitlist=data.accept_waitlist,
        monitoring_enabled=data.monitoring_enabled
    )
    db.add(pref)
    await db.commit()
    await db.refresh(pref)
    return pref.to_dict()

@router.put("/{pref_id}", response_model=PreferenceResponse)
async def update_target(pref_id: int, data: TargetSlotEdit, db: AsyncSession = Depends(get_db)):
    """Edit an existing target slot configuration."""
    pref = await db.get(BookingPreference, pref_id)
    if not pref:
        raise HTTPException(status_code=404, detail="Target slot not found.")

    if data.event_title is not None:
        pref.event_title = data.event_title
    if data.target_date is not None:
        pref.target_date = data.target_date
    if data.preferred_room is not None:
        pref.preferred_room = data.preferred_room
    if data.preferred_start_time is not None:
        pref.preferred_start_time = data.preferred_start_time
    if data.preferred_end_time is not None:
        pref.preferred_end_time = data.preferred_end_time
    if data.accept_waitlist is not None:
        pref.accept_waitlist = data.accept_waitlist
    if data.monitoring_enabled is not None:
        pref.monitoring_enabled = data.monitoring_enabled

    await db.commit()
    await db.refresh(pref)
    return pref.to_dict()

@router.delete("/{pref_id}")
async def delete_preference(pref_id: int, db: AsyncSession = Depends(get_db)):
    pref = await db.get(BookingPreference, pref_id)
    if not pref:
        raise HTTPException(status_code=404, detail="Preference not found")
    await db.delete(pref)
    await db.commit()
    return {"success": True, "message": f"Target slot {pref_id} removed."}

@router.put("/{pref_id}/toggle")
async def toggle_preference(pref_id: int, db: AsyncSession = Depends(get_db)):
    pref = await db.get(BookingPreference, pref_id)
    if not pref:
        raise HTTPException(status_code=404, detail="Preference not found")
    pref.monitoring_enabled = not pref.monitoring_enabled
    await db.commit()
    return pref.to_dict()

# Method B Metadata helper endpoints
@router.get("/meta/rooms")
async def get_discovered_rooms(date: Optional[str] = Query(None)):
    """Return rooms discovered from the actual portal."""
    provider = monitoring_engine.provider
    rooms = await provider.get_available_rooms(date)
    return {"rooms": rooms}

@router.get("/meta/sessions")
async def get_discovered_sessions(
    date: str = Query(..., description="Target date (e.g. 2026-11-20 or Nov 20, 2026)"),
    room: str = Query(..., description="Target room (e.g. 1731, 1851, 1852)"),
    title: Optional[str] = Query(None, description="Assessment title")
):
    """Return actual sessions available on the portal for the chosen date and room."""
    provider = monitoring_engine.provider
    sessions = await provider.get_available_sessions_for_room(date, room, title)
    if not sessions:
        return {
            "found": False,
            "sessions": [],
            "message": f"No sessions discovered for Room {room} on {date}."
        }
    return {
        "found": True,
        "sessions": [s.model_dump() for s in sessions],
        "count": len(sessions)
    }

# Milestone 3: Execution Modes, Pre-Arming, and Preflight Endpoints
@router.put("/{pref_id}/mode", response_model=PreferenceResponse)
async def set_target_mode(pref_id: int, data: SetModeRequest, db: AsyncSession = Depends(get_db)):
    """Set booking mode: OBSERVE, ASSIST, or AUTO_BOOK."""
    mode = data.booking_mode.upper()
    if mode not in ("OBSERVE", "ASSIST", "AUTO_BOOK"):
        raise HTTPException(status_code=400, detail="Invalid booking mode. Must be OBSERVE, ASSIST, or AUTO_BOOK.")

    pref = await db.get(BookingPreference, pref_id)
    if not pref:
        raise HTTPException(status_code=404, detail="Target slot not found.")

    pref.booking_mode = mode
    # If switching away from AUTO_BOOK, disarm target
    if mode != "AUTO_BOOK" and pref.is_armed:
        pref.is_armed = False
        pref.execution_status = "IDLE"

    await db.commit()
    await db.refresh(pref)
    return pref.to_dict()

@router.put("/{pref_id}/arm", response_model=Dict[str, Any])
async def arm_target(pref_id: int, data: ArmTargetRequest, db: AsyncSession = Depends(get_db)):
    """
    Pre-arms target for autonomous booking upon window opening.
    Requires user confirmation that automation is authorized.
    Runs preflight checks immediately and returns target and preflight results.
    """
    if not data.user_permitted_automation:
        raise HTTPException(
            status_code=400,
            detail="User authorization is required to enable autonomous booking."
        )

    clean_purpose = data.purpose.strip() if data.purpose else ""
    if not clean_purpose:
        raise HTTPException(status_code=400, detail="Purpose field is required for booking.")
    if len(clean_purpose) > 255:
        raise HTTPException(status_code=400, detail="Purpose exceeds 255 characters limit.")

    pref = await db.get(BookingPreference, pref_id)
    if not pref:
        raise HTTPException(status_code=404, detail="Target slot not found.")

    # Run preflight check
    provider = monitoring_engine.provider
    preflight = await PreflightEngine.run_checks(
        target=pref,
        provider=provider,
        override_purpose=clean_purpose,
        override_armed=True,
        override_automation_permitted=True,
        override_mode="AUTO_BOOK"
    )

    now = datetime.now(timezone.utc)
    pref.booking_mode = "AUTO_BOOK"
    pref.purpose = clean_purpose
    pref.accept_waitlist = data.accept_waitlist
    pref.user_permitted_automation = True
    pref.is_armed = True
    pref.armed_at = now
    pref.execution_status = "ARMED"
    pref.last_preflight_status = "PASSED" if preflight.passed else "FAILED"
    pref.last_preflight_details = json.dumps([c.model_dump() for c in preflight.checks])
    pref.last_preflight_at = now

    await db.commit()
    await db.refresh(pref)

    # Broadcast arming event
    await ws_manager.broadcast({
        "type": "TARGET_ARMED",
        "target_id": pref.id,
        "event_title": pref.event_title,
        "room": pref.preferred_room,
        "time": pref.preferred_start_time,
        "preflight_passed": preflight.passed,
        "armed_at": now.isoformat()
    })

    return {
        "success": True,
        "message": f"Target '{pref.event_title}' (Room {pref.preferred_room}) successfully armed for AUTO_BOOK.",
        "target": pref.to_dict(),
        "preflight": preflight.model_dump()
    }

@router.put("/{pref_id}/disarm", response_model=PreferenceResponse)
async def disarm_target(pref_id: int, db: AsyncSession = Depends(get_db)):
    """Disarms target, disabling autonomous booking execution."""
    pref = await db.get(BookingPreference, pref_id)
    if not pref:
        raise HTTPException(status_code=404, detail="Target slot not found.")

    pref.is_armed = False
    pref.execution_status = "DISARMED"
    await db.commit()
    await db.refresh(pref)

    await ws_manager.broadcast({
        "type": "TARGET_DISARMED",
        "target_id": pref.id,
        "event_title": pref.event_title,
        "room": pref.preferred_room
    })

    return pref.to_dict()

@router.post("/{pref_id}/preflight", response_model=PreflightResponse)
async def run_target_preflight(pref_id: int, db: AsyncSession = Depends(get_db)):
    """Runs live preflight checks on demand for a target slot."""
    pref = await db.get(BookingPreference, pref_id)
    if not pref:
        raise HTTPException(status_code=404, detail="Target slot not found.")

    provider = monitoring_engine.provider
    preflight = await PreflightEngine.run_checks(pref, provider)

    pref.last_preflight_status = "PASSED" if preflight.passed else "FAILED"
    pref.last_preflight_details = json.dumps([c.model_dump() for c in preflight.checks])
    pref.last_preflight_at = datetime.now(timezone.utc)
    await db.commit()

    return preflight
