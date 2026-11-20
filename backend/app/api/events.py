from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.event import DiscoveredEvent
from app.models.preference import BookingPreference
from app.models.schemas import EventSchema
from app.services.preference_engine import PreferenceEngine
from app.services.scheduler import monitoring_engine

router = APIRouter(prefix="/api/events", tags=["Events"])

# Supported event terms discovered directly from the portal
AVAILABLE_TERMS = [
    {"value": "", "name": "All"},
    {"value": "16", "name": "26-27-EVENTDAY-02"},
    {"value": "15", "name": "26-27-EVENTDAY-01"},
    {"value": "14", "name": "26-27-ODD-EXAMHALL"},
    {"value": "13", "name": "26-27-EVENTS"},
    {"value": "11", "name": "26-27-LEARNING"},
    {"value": "12", "name": "26-27-PLACEMENT"},
    {"value": "10", "name": "26-27-ODD-EXAMCENTRE"},
    {"value": "9", "name": "25-26-EVENTDAY-04"},
    {"value": "8", "name": "25-26-EVEN-EXAMHALL"},
    {"value": "7", "name": "25-26-EVENTS"},
    {"value": "6", "name": "25-26-HOSTEL BOOKING"},
    {"value": "5", "name": "25-26-PLACEMENT"},
    {"value": "4", "name": "25-26 SKILL DEV"},
    {"value": "3", "name": "25-26-EVENTDAY-03"},
    {"value": "2", "name": "25-26-LEARNING"},
    {"value": "1", "name": "25-26-EVEN-EXAMCENTRE"}
]

@router.get("/terms")
async def get_terms():
    """Returns available event terms from the Saveetha portal."""
    return AVAILABLE_TERMS

@router.get("/", response_model=List[EventSchema])
async def list_events(
    event_term: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    slot_name: Optional[str] = Query(None),
    session_time: Optional[str] = Query(None),
    live: bool = Query(True, description="Fetch directly from Saveetha portal"),
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch discovered events with optional filtering.
    When live=True, connects to Saveetha portal via persistent session.
    """
    filters = {}
    if event_term:
        filters["event_term"] = event_term
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    if slot_name:
        filters["slot_name"] = slot_name
    if session_time:
        filters["session_time"] = session_time

    # Fetch active user preferences
    pref_res = await db.execute(select(BookingPreference).where(BookingPreference.is_active == True))
    preferences = pref_res.scalars().all()

    if live:
        provider = monitoring_engine.provider
        events = await provider.get_events(filters)
        # Update cache in background/db
        for evt in events:
            existing = await db.get(DiscoveredEvent, evt.event_id)
            if not existing:
                db.add(DiscoveredEvent(
                    id=evt.event_id,
                    session_id=evt.session_id,
                    title=evt.title,
                    date=evt.date,
                    start_time=evt.start_time,
                    end_time=evt.end_time,
                    venue=evt.venue,
                    description=evt.description,
                    booking_status=evt.booking_status,
                    booking_window_start=evt.booking_window_start,
                    booking_window_end=evt.booking_window_end,
                    cancellation_deadline=evt.cancellation_deadline,
                    capacity=evt.capacity,
                    waitlist_capacity=evt.waitlist_capacity,
                    reward_points=evt.reward_points,
                    attendance_cluster=evt.attendance_cluster,
                    can_book=evt.can_book,
                    has_waitlist=evt.has_waitlist,
                    purpose_required=evt.purpose_required
                ))
            else:
                existing.booking_status = evt.booking_status
                existing.capacity = evt.capacity
                existing.waitlist_capacity = evt.waitlist_capacity
                existing.can_book = evt.can_book
        await db.commit()
    else:
        # Load from database cache
        db_res = await db.execute(select(DiscoveredEvent))
        db_events = db_res.scalars().all()
        events = [
            EventSchema(
                event_id=e.id,
                session_id=e.session_id,
                title=e.title,
                date=e.date,
                start_time=e.start_time,
                end_time=e.end_time,
                venue=e.venue,
                description=e.description,
                booking_status=e.booking_status,
                booking_window_start=e.booking_window_start,
                booking_window_end=e.booking_window_end,
                cancellation_deadline=e.cancellation_deadline,
                capacity=e.capacity,
                waitlist_capacity=e.waitlist_capacity,
                reward_points=e.reward_points or 0,
                attendance_cluster=e.attendance_cluster,
                can_book=e.can_book or False,
                has_waitlist=e.has_waitlist or False,
                purpose_required=e.purpose_required or False
            )
            for e in db_events
        ]

    # Run preference evaluation
    enriched = PreferenceEngine.match_events(events, preferences)
    return enriched

@router.get("/available", response_model=List[EventSchema])
async def list_available_slots(
    slot_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Returns only slots that are Open or available to book."""
    provider = monitoring_engine.provider
    filters = {"slot_name": slot_name} if slot_name else {}
    events = await provider.get_available_slots(filters)

    pref_res = await db.execute(select(BookingPreference).where(BookingPreference.is_active == True))
    preferences = pref_res.scalars().all()
    return PreferenceEngine.match_events(events, preferences)

@router.get("/{event_id}/details")
async def get_event_details(event_id: str):
    """Fetch view-more details for session."""
    provider = monitoring_engine.provider
    details = await provider.get_event_details(event_id)
    if not details:
        raise HTTPException(status_code=404, detail="Session details not found")
    return details
