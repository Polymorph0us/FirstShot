import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select

from app.database.session import AsyncSessionLocal
from app.models.booking_attempt import BookingAttempt
from app.models.preference import BookingPreference
from app.models.schemas import PreflightCheckItem, PreflightResponse
from app.providers.base import BaseProvider
from app.services.preference_engine import PreferenceEngine

logger = logging.getLogger("firstshot.preflight")

class PreflightEngine:
    @staticmethod
    async def run_checks(
        target: BookingPreference,
        provider: BaseProvider,
        override_purpose: Optional[str] = None,
        override_armed: Optional[bool] = None,
        override_automation_permitted: Optional[bool] = None,
        override_mode: Optional[str] = None
    ) -> PreflightResponse:
        """
        Executes comprehensive preflight checks for an autonomous booking target.
        Returns a PreflightResponse containing itemized check results.
        """
        checks: List[PreflightCheckItem] = []
        now_str = datetime.now(timezone.utc).isoformat()

        purpose_to_check = override_purpose if override_purpose is not None else (target.purpose or "")
        is_armed_to_check = override_armed if override_armed is not None else target.is_armed
        is_permitted_to_check = override_automation_permitted if override_automation_permitted is not None else target.user_permitted_automation
        mode_to_check = override_mode if override_mode is not None else target.booking_mode

        # 1. Session Authentication Check
        sess_status = await provider.check_session()
        is_auth = sess_status.get("authenticated", False)
        checks.append(PreflightCheckItem(
            name="Session Authentication",
            passed=is_auth,
            critical=True,
            detail="Portal session is active and authenticated." if is_auth else f"Session not authenticated: {sess_status.get('message', 'Expired or disconnected.')}"
        ))

        # 2. Portal Events Retrieval & Target Existence Check
        matched_event = None
        portal_events = []
        try:
            target_date = target.target_date or target.preferred_date
            portal_events = await provider.get_events(filters={"date_from": target_date, "date_to": target_date})
            for evt in portal_events:
                matched, score, reasons = PreferenceEngine.evaluate_match(evt, target)
                if matched and score >= 60:
                    matched_event = evt
                    break
        except Exception as e:
            logger.error(f"Error fetching events for preflight check: {e}")

        checks.append(PreflightCheckItem(
            name="Target Existence on Portal",
            passed=(matched_event is not None),
            critical=True,
            detail=(
                f"Target session verified on live portal: '{matched_event.title}' on {matched_event.date}."
                if matched_event else
                f"Target slot could not be located on college portal for date {target.target_date}."
            )
        ))

        # 3. Exact Room, Date & Time Verification
        room_date_time_ok = False
        room_detail = "Target session not found on portal."
        if matched_event:
            room_matches = (matched_event.venue or "").strip().lower() == (target.preferred_room or "").strip().lower()
            start_matches = (matched_event.start_time or "").strip() == (target.preferred_start_time or "").strip()
            room_date_time_ok = room_matches and start_matches
            room_detail = (
                f"Verified: Room {matched_event.venue}, {matched_event.start_time} - {matched_event.end_time} on {matched_event.date}."
                if room_date_time_ok else
                f"Room/Time discrepancy: Expected Room {target.preferred_room} at {target.preferred_start_time}, found Room {matched_event.venue} at {matched_event.start_time}."
            )

        checks.append(PreflightCheckItem(
            name="Room, Date & Time Verification",
            passed=room_date_time_ok,
            critical=True,
            detail=room_detail
        ))

        # 4. Session Identifier Verification
        id_ok = False
        id_detail = "Identifier unavailable."
        if matched_event:
            # When Opening Soon, identifier is deterministic; when Open, numeric session_id is available
            event_id = matched_event.session_id or matched_event.event_id
            id_ok = bool(event_id)
            id_detail = f"Portal identifier verified: {event_id} (Status: {matched_event.booking_status})."

        checks.append(PreflightCheckItem(
            name="Session Identifier Verification",
            passed=id_ok,
            critical=True,
            detail=id_detail
        ))

        # 5. Purpose Field Validation
        clean_purpose = purpose_to_check.strip()
        purpose_ok = bool(clean_purpose) and len(clean_purpose) <= 255
        checks.append(PreflightCheckItem(
            name="Purpose Field Validation",
            passed=purpose_ok,
            critical=True,
            detail=(
                f"Purpose validated: '{clean_purpose[:40]}...' ({len(clean_purpose)} chars)."
                if purpose_ok else
                "Purpose is required and must not exceed 255 characters."
            )
        ))

        # 6. AUTO_BOOK Armed & Automation Permission Check
        armed_ok = bool(is_armed_to_check) and (mode_to_check == "AUTO_BOOK") and bool(is_permitted_to_check)
        checks.append(PreflightCheckItem(
            name="AUTO_BOOK Pre-Armed Authorization",
            passed=armed_ok,
            critical=True,
            detail=(
                "Target is authorized and armed for autonomous execution."
                if armed_ok else
                "Target is not armed for AUTO_BOOK or user permission has not been confirmed."
            )
        ))

        # 7. Target Not Already Booked Check
        already_booked = False
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(BookingAttempt).where(
                    BookingAttempt.preference_id == target.id,
                    BookingAttempt.status == "CONFIRMED"
                )
            )
            confirmed_attempts = res.scalars().all()
            if confirmed_attempts:
                already_booked = True

        if matched_event and matched_event.booking_status in ("Booked", "Registered"):
            already_booked = True

        checks.append(PreflightCheckItem(
            name="Already Booked Protection",
            passed=(not already_booked),
            critical=True,
            detail=(
                "Session has not been previously booked. Slot is eligible for execution."
                if not already_booked else
                "Session is already booked or registered."
            )
        ))

        # 8. Monitoring System Operational Check
        monitoring_ok = bool(target.monitoring_enabled)
        checks.append(PreflightCheckItem(
            name="Monitoring System Operational",
            passed=monitoring_ok,
            critical=False,
            detail="Monitoring is active and will track availability changes." if monitoring_ok else "Monitoring is currently paused for this target."
        ))

        all_critical_passed = all(c.passed for c in checks if c.critical)
        summary = (
            "ALL PREFLIGHT CHECKS PASSED: Target is verified, authorized, and pre-armed for autonomous execution upon window opening."
            if all_critical_passed else
            "PREFLIGHT CHECK FAILED: One or more critical checks did not pass. Autonomous submission is blocked."
        )

        return PreflightResponse(
            target_id=target.id,
            target_title=target.event_title,
            target_room=target.preferred_room,
            target_date=target.target_date,
            target_time=f"{target.preferred_start_time} - {target.preferred_end_time or ''}".strip(" -"),
            passed=all_critical_passed,
            timestamp=now_str,
            checks=checks,
            summary=summary
        )
