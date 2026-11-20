import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.models.schemas import EventSchema
from app.providers.base import BaseProvider

logger = logging.getLogger("firstshot.simulated")

class SimulatedProvider(BaseProvider):
    """Simulated provider for unit testing scheduler, state transitions, and workflows."""

    def __init__(self, fail_network: bool = False, session_valid: bool = True):
        self.fail_network = fail_network
        self.session_valid = session_valid
        self._submitting_sessions: Set[str] = set()
        self.submission_log: List[Dict[str, Any]] = []
        self.crash_failures_remaining: int = 0
        self.events: List[EventSchema] = [
            EventSchema(
                event_id="sim_101",
                session_id="101",
                title="Module Assessment",
                date="2026-11-20",
                start_time="08:00",
                end_time="09:29",
                venue="1731",
                booking_status="Opening Soon",
                booking_window_start="2026-11-19 19:00",
                booking_window_end="2026-11-20 08:00",
                cancellation_deadline="2026-11-20 06:00",
                capacity="0/80",
                waitlist_capacity="0/5",
                reward_points=0,
                can_book=False,
                has_waitlist=False,
                purpose_required=True
            ),
            EventSchema(
                event_id="sim_102",
                session_id="102",
                title="Module Assessment",
                date="2026-11-20",
                start_time="09:45",
                end_time="11:14",
                venue="1731",
                booking_status="Open",
                booking_window_start="2026-11-19 19:00",
                booking_window_end="2026-11-20 09:45",
                cancellation_deadline="2026-11-20 08:30",
                capacity="15/80",
                waitlist_capacity="0/5",
                reward_points=0,
                can_book=True,
                has_waitlist=False,
                purpose_required=True
            ),
            EventSchema(
                event_id="sim_103",
                session_id="103",
                title="Module Assessment",
                date="2026-11-20",
                start_time="08:00",
                end_time="09:29",
                venue="1851",
                booking_status="Open",
                booking_window_start="2026-11-19 19:00",
                booking_window_end="2026-11-20 08:00",
                cancellation_deadline="2026-11-20 06:00",
                capacity="20/60",
                waitlist_capacity="0/5",
                reward_points=0,
                can_book=True,
                has_waitlist=False,
                purpose_required=True
            ),
            EventSchema(
                event_id="sim_104",
                session_id="104",
                title="Module Assessment",
                date="2026-11-20",
                start_time="08:00",
                end_time="09:29",
                venue="1852",
                booking_status="Full",
                booking_window_start="2026-11-19 19:00",
                booking_window_end="2026-11-20 08:00",
                cancellation_deadline="2026-11-20 06:00",
                capacity="60/60",
                waitlist_capacity="5/5",
                reward_points=0,
                can_book=False,
                has_waitlist=False,
                purpose_required=True
            )
        ]

    async def connect(self) -> bool:
        if self.fail_network:
            raise ConnectionError("Simulated network connection failure")
        return True

    async def check_session(self) -> Dict[str, Any]:
        if self.fail_network:
            raise ConnectionError("Simulated network timeout during session check")
        if not self.session_valid:
            return {"authenticated": False, "message": "Session expired simulation"}
        return {"authenticated": True, "message": "Session valid"}

    async def get_events(self, filters: Optional[Dict[str, Any]] = None) -> List[EventSchema]:
        if self.fail_network:
            raise ConnectionError("Simulated network timeout")
        results = self.events
        if filters:
            if filters.get("slot_name"):
                name = filters["slot_name"].lower()
                results = [e for e in results if name in e.title.lower()]
            if filters.get("session_time"):
                t = filters["session_time"]
                results = [e for e in results if e.start_time == t]
            if filters.get("date_from"):
                d = filters["date_from"]
                results = [e for e in results if d in e.date]
        return results

    async def apply_filters(self, filters: Dict[str, Any]) -> List[EventSchema]:
        return await self.get_events(filters)

    async def get_available_slots(self, filters: Optional[Dict[str, Any]] = None) -> List[EventSchema]:
        events = await self.get_events(filters)
        return [e for e in events if e.can_book or e.booking_status == "Open"]

    async def get_booking_status(self, event_id: str) -> str:
        for e in self.events:
            if e.event_id == event_id or e.session_id == event_id:
                return e.booking_status
        return "Unknown"

    async def get_event_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        for e in self.events:
            if e.session_id == session_id:
                return {"session_id": session_id, "title": e.title}
        return None

    async def get_available_rooms(self, date: Optional[str] = None) -> List[str]:
        rooms = set(e.venue for e in self.events if e.venue)
        return sorted(list(rooms))

    async def get_available_sessions_for_room(self, date: str, room: str, title: Optional[str] = None) -> List[EventSchema]:
        matching = []
        for e in self.events:
            if e.venue and e.venue.lower() == room.lower():
                if not title or title.lower() in e.title.lower():
                    matching.append(e)
        matching.sort(key=lambda x: x.start_time)
        return matching

    async def prepare_booking(self, event_id: str, purpose: str = "Academic Continuous Assessment") -> Dict[str, Any]:
        target = None
        for e in self.events:
            if e.event_id == event_id or e.session_id == event_id:
                target = e
                break
        if not target:
            return {"success": False, "message": "Event not found"}

        if target.booking_status not in ("Open", "Waitlist Open"):
            return {
                "success": False,
                "event_id": event_id,
                "title": target.title,
                "status": target.booking_status,
                "message": f"Cannot prepare booking. Status is '{target.booking_status}'."
            }

        return {
            "success": True,
            "event_id": target.event_id,
            "session_id": target.session_id or target.event_id,
            "title": target.title,
            "venue": target.venue,
            "date": target.date,
            "time": f"{target.start_time} - {target.end_time}",
            "booking_action": "book",
            "purpose": purpose[:255],
            "ready_to_submit": True,
            "status": target.booking_status,
            "message": "Booking prepared in ASSIST MODE."
        }

    async def submit_booking(self, session_id: str, purpose: str, action: str = "book", target_date: Optional[str] = None) -> Dict[str, Any]:
        if session_id in self._submitting_sessions:
            return {
                "success": False,
                "session_id": session_id,
                "verified": False,
                "status": "DUPLICATE_ATTEMPT_PREVENTED",
                "message": f"A booking submission is already in progress for session {session_id}."
            }

        self._submitting_sessions.add(session_id)
        try:
            if getattr(self, "crash_failures_remaining", 0) > 0:
                self.crash_failures_remaining -= 1
                return {
                    "success": False,
                    "session_id": session_id,
                    "verified": False,
                    "status": "SERVER_CRASH",
                    "is_transient": True,
                    "message": "Simulated 502 Bad Gateway under surge load.",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

            target = None
            for e in self.events:
                if e.session_id == session_id or e.event_id == session_id:
                    target = e
                    break

            if not target:
                return {
                    "success": False,
                    "session_id": session_id,
                    "verified": False,
                    "status": "NOT_FOUND",
                    "message": "Session not found."
                }

            if target.booking_status not in ("Open", "Waitlist Open"):
                return {
                    "success": False,
                    "session_id": session_id,
                    "verified": False,
                    "status": "UNAVAILABLE",
                    "message": f"Session is currently {target.booking_status}."
                }

            record = {
                "session_id": session_id,
                "purpose": purpose,
                "action": action,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.submission_log.append(record)

            return {
                "success": True,
                "event_id": target.event_id,
                "session_id": session_id,
                "title": target.title,
                "booking_action": action,
                "status": "CONFIRMED",
                "verified": True,
                "message": f"Booking successfully confirmed on simulated provider for {target.title} ({target.venue}).",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        finally:
            self._submitting_sessions.discard(session_id)

    def transition_event_status(self, event_id: str, new_status: str, can_book: bool = False):
        """Simulate status transition e.g. Opening Soon -> Open."""
        for e in self.events:
            if e.event_id == event_id or e.session_id == event_id:
                e.booking_status = new_status
                e.can_book = can_book
                break

    async def close(self):
        pass
