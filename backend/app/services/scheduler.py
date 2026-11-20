import asyncio
import json
import logging
import zoneinfo
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models.booking_attempt import BookingAttempt
from app.models.event import DiscoveredEvent
from app.models.monitoring import MonitoringJob, NotificationLog
from app.models.preference import BookingPreference
from app.models.schemas import EventSchema
from app.providers.base import BaseProvider
from app.providers.saveetha import SaveethaProvider
from app.services.preference_engine import PreferenceEngine
from app.services.preflight import PreflightEngine

logger = logging.getLogger("firstshot.scheduler")
IST = zoneinfo.ZoneInfo("Asia/Kolkata")

class WebSocketManager:
    """Manages active WebSocket connections for live real-time dashboard updates."""
    def __init__(self):
        self.active_connections: Set[Any] = set()

    async def connect(self, websocket: Any):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: Any):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = WebSocketManager()

class MonitoringEngine:
    def __init__(self, provider: Optional[BaseProvider] = None):
        self.provider = provider or SaveethaProvider()
        self.scheduler = AsyncIOScheduler(timezone=IST)
        self.last_known_statuses: Dict[str, str] = {}         # event_id -> status
        self.target_last_statuses: Dict[int, str] = {}        # target_id -> status
        self.is_running = False
        self._current_interval = settings.DEFAULT_MONITOR_INTERVAL_SECONDS
        self._executing_targets: Set[int] = set()             # Target mutex to prevent duplicate concurrent runs

    def start(self):
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            logger.info("FirstShot Monitoring Engine started with timezone Asia/Kolkata.")
            # Add standing periodic check for all active target slots every 60s
            self.scheduler.add_job(
                self.check_all_targets,
                trigger=IntervalTrigger(seconds=settings.DEFAULT_MONITOR_INTERVAL_SECONDS, timezone=IST),
                id="check_all_targets_job",
                replace_existing=True
            )

    def shutdown(self):
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("FirstShot Monitoring Engine stopped.")

    async def check_all_jobs(self):
        """Executed periodically: runs checks for all active monitoring jobs."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MonitoringJob).where(MonitoringJob.is_active == True))
            jobs = result.scalars().all()

        for job in jobs:
            try:
                await self.run_job_check(job.id)
            except Exception as e:
                logger.error(f"Error checking monitoring job {job.id}: {e}")

    async def check_all_targets(self):
        """Check availability and status transitions specifically for all active user target slots."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BookingPreference).where(
                    (BookingPreference.monitoring_enabled == True) | (BookingPreference.is_active == True)
                )
            )
            targets = result.scalars().all()

        if not targets:
            return

        # Dynamic interval adaptation near 7:00 PM IST opening window
        now_ist = datetime.now(IST)
        any_armed = any(getattr(t, "is_armed", False) and getattr(t, "booking_mode", "") == "AUTO_BOOK" for t in targets)
        is_blitz_window = (now_ist.hour == 18 and now_ist.minute == 59 and now_ist.second >= 45) or (now_ist.hour == 19 and now_ist.minute <= 5)
        is_near_window = (now_ist.hour == 18 and now_ist.minute >= 45) or (now_ist.hour == 19 and now_ist.minute <= 15)

        if any_armed and is_blitz_window:
            target_interval = 2
        elif any_armed and is_near_window:
            target_interval = 5
        else:
            target_interval = settings.DEFAULT_MONITOR_INTERVAL_SECONDS

        if self._current_interval != target_interval:
            try:
                self._current_interval = target_interval
                self.scheduler.reschedule_job("check_all_targets_job", trigger=IntervalTrigger(seconds=target_interval, timezone=IST))
                logger.info(f"Scheduler interval dynamically adjusted to {target_interval}s (blitz={is_blitz_window}, near={is_near_window}, armed={any_armed}).")
            except Exception as e:
                logger.debug(f"Could not reschedule monitor job: {e}")

        try:
            # Pre-connect / warm up session
            sess_status = await self.provider.check_session()
            if sess_status.get("server_crashed"):
                logger.warning(f"Portal experiencing traffic surge / temporary crash: {sess_status.get('message')}. Retaining active monitoring.")
                await ws_manager.broadcast({
                    "type": "PORTAL_SURGE_DETECTED",
                    "message": "Saveetha portal is experiencing high traffic (HTTP 502/timeout). Continuous monitoring active...",
                    "timestamp": datetime.now(IST).isoformat()
                })
            elif not sess_status.get("authenticated"):
                await ws_manager.broadcast({
                    "type": "SESSION_EXPIRED",
                    "message": "Saveetha portal session expired during target monitoring. Please log in."
                })
                return

            # Query events targeted by date if targets have explicit target dates
            unique_dates = {t.target_date or t.preferred_date for t in targets if (t.target_date or t.preferred_date)}
            events_by_date = {}
            raw_events = []

            if unique_dates:
                for udate in unique_dates:
                    try:
                        d_events = await self.provider.get_events(filters={"date_from": udate, "date_to": udate})
                        events_by_date[udate] = d_events
                        raw_events.extend(d_events)
                    except Exception as err:
                        logger.error(f"Error fetching portal events for target date {udate}: {err}")
            else:
                raw_events = await self.provider.get_events()

            now = datetime.now(IST)

            for target in targets:
                # Find exact matching event from date-specific candidates
                t_date = target.target_date or target.preferred_date
                candidates = events_by_date.get(t_date, raw_events)
                exact_match = None
                for evt in candidates:
                    matched, score, reasons = PreferenceEngine.evaluate_match(evt, target)
                    if matched and score >= 60:
                        exact_match = evt
                        break

                async with AsyncSessionLocal() as session:
                    db_target = await session.get(BookingPreference, target.id)
                    if not db_target:
                        continue

                    old_status = self.target_last_statuses.get(target.id) or db_target.current_status

                    if exact_match:
                        new_status = exact_match.booking_status
                        db_target.current_status = new_status
                        db_target.capacity = exact_match.capacity
                        db_target.waitlist_capacity = exact_match.waitlist_capacity
                        db_target.target_event_id = exact_match.event_id
                        db_target.last_checked_at = now

                        # Status transition detection
                        if old_status is not None and old_status != new_status:
                            notif_msg = (
                                f"Target '{db_target.event_title}' (Room {db_target.preferred_room}, "
                                f"{exact_match.start_time}) changed: '{old_status}' → '{new_status}'!"
                            )
                            logger.info(notif_msg)

                            notif = NotificationLog(
                                event_id=exact_match.event_id,
                                title=exact_match.title,
                                status_from=old_status,
                                status_to=new_status,
                                message=notif_msg,
                                created_at=datetime.now(timezone.utc)
                            )
                            session.add(notif)

                            # Booking Trigger or Assist Preparation
                            is_target_open = (new_status == "Open") or (new_status == "Waitlist Open" and db_target.accept_waitlist)
                            prepared_payload = None

                            if is_target_open:
                                if db_target.booking_mode == "AUTO_BOOK" and db_target.is_armed and db_target.user_permitted_automation:
                                    if db_target.id not in self._executing_targets and db_target.execution_status in ("ARMED", "IDLE"):
                                        logger.info(f"Target {db_target.id} verified OPEN & pre-armed for AUTO_BOOK. Executing autonomous booking!")
                                        asyncio.create_task(self.execute_autonomous_booking(db_target.id, exact_match))
                                elif db_target.booking_mode == "ASSIST":
                                    try:
                                        prepared_payload = await self.provider.prepare_booking(exact_match.event_id)
                                    except Exception as err:
                                        logger.error(f"Error preparing booking for target {target.id}: {err}")

                            await ws_manager.broadcast({
                                "type": "TARGET_STATUS_CHANGED",
                                "target_id": db_target.id,
                                "event_title": db_target.event_title,
                                "room": db_target.preferred_room,
                                "date": db_target.target_date,
                                "time": exact_match.start_time,
                                "old_status": old_status,
                                "new_status": new_status,
                                "prepared_booking": prepared_payload,
                                "notification": notif_msg,
                                "timestamp": now.isoformat()
                            })

                        # Even if status didn't transition this tick, check if open target is pre-armed and unexecuted
                        is_target_open = (new_status == "Open") or (new_status == "Waitlist Open" and db_target.accept_waitlist)
                        if is_target_open and db_target.booking_mode == "AUTO_BOOK" and db_target.is_armed and db_target.user_permitted_automation:
                            if db_target.id not in self._executing_targets and db_target.execution_status in ("ARMED", "IDLE"):
                                logger.info(f"Target {db_target.id} is verified OPEN and pre-armed. Executing autonomous booking...")
                                asyncio.create_task(self.execute_autonomous_booking(db_target.id, exact_match))

                        # If target became Full or Closed, check for alternatives in other rooms/times
                        if new_status in ("Full", "Booking Closed"):
                            alternatives = PreferenceEngine.find_alternatives(db_target, raw_events)
                            if alternatives:
                                await ws_manager.broadcast({
                                    "type": "TARGET_UNAVAILABLE_ALTERNATIVES",
                                    "target_id": db_target.id,
                                    "target_title": db_target.event_title,
                                    "target_room": db_target.preferred_room,
                                    "target_status": new_status,
                                    "alternatives": [a.model_dump() for a in alternatives]
                                })

                        self.target_last_statuses[target.id] = new_status
                    else:
                        is_fetch_crash = getattr(self.provider, "last_fetch_status", None) in (500, 502, 503, 504) or getattr(self.provider, "last_fetch_error", None) is not None
                        if is_fetch_crash:
                            logger.warning(f"Target #{target.id}: Portal error/timeout during event fetch. Retaining status '{old_status}'.")
                            db_target.last_checked_at = now
                        else:
                            db_target.last_checked_at = now
                            db_target.current_status = "Not Scheduled / Unknown"

                    await session.commit()

            # Broadcast target update
            await ws_manager.broadcast({
                "type": "TARGETS_UPDATED",
                "timestamp": now.isoformat()
            })

        except Exception as e:
            logger.error(f"Error during check_all_targets: {e}")

    async def execute_autonomous_booking(self, target_id: int, matched_event: EventSchema) -> Dict[str, Any]:
        """
        Executes a pre-authorized, pre-armed autonomous booking attempt.
        Strictly enforces preflight verification, persistent attempt recording,
        duplicate protection, and post-submission verification.
        """
        if target_id in self._executing_targets:
            logger.warning(f"Target {target_id} execution already in progress. Ignoring duplicate trigger.")
            return {"success": False, "message": "Execution already in progress."}

        self._executing_targets.add(target_id)
        try:
            async with AsyncSessionLocal() as session:
                target = await session.get(BookingPreference, target_id)
                if not target:
                    return {"success": False, "message": "Target not found."}

                if not target.is_armed or target.booking_mode != "AUTO_BOOK" or not target.user_permitted_automation:
                    logger.warning(f"Target {target_id} is not armed for AUTO_BOOK or user permission not confirmed. Aborting.")
                    return {"success": False, "message": "Target not armed."}

                # 1. Check existing confirmed or in-progress attempts
                res = await session.execute(
                    select(BookingAttempt).where(
                        BookingAttempt.preference_id == target_id,
                        BookingAttempt.status == "CONFIRMED"
                    )
                )
                if res.scalars().first():
                    logger.info(f"Target {target_id} has already been confirmed. Skipping.")
                    target.is_armed = False
                    target.execution_status = "SUCCESS"
                    await session.commit()
                    return {"success": True, "message": "Already confirmed."}

                # 2. Preflight checks before submission
                preflight = await PreflightEngine.run_checks(target, self.provider)
                target.last_preflight_status = "PASSED" if preflight.passed else "FAILED"
                target.last_preflight_details = json.dumps([c.model_dump() for c in preflight.checks])
                target.last_preflight_at = datetime.now(timezone.utc)

                if not preflight.passed:
                    fail_msg = f"Autonomous booking preflight checks failed: {preflight.summary}"
                    logger.error(fail_msg)

                    failed_attempt = BookingAttempt(
                        preference_id=target.id,
                        target_event_id=matched_event.event_id,
                        session_id=matched_event.session_id or matched_event.event_id,
                        mode="AUTO_BOOK",
                        purpose=target.purpose,
                        status="PREFLIGHT_FAILED",
                        verified=False,
                        response_message=fail_msg,
                        attempted_at=datetime.now(timezone.utc)
                    )
                    session.add(failed_attempt)
                    target.execution_status = "PREFLIGHT_FAILED"
                    target.is_armed = False  # Disarm on preflight failure to alert user
                    await session.commit()

                    await ws_manager.broadcast({
                        "type": "AUTO_BOOKING_PREFLIGHT_FAILED",
                        "target_id": target.id,
                        "event_title": target.event_title,
                        "summary": preflight.summary,
                        "checks": [c.model_dump() for c in preflight.checks]
                    })
                    return {"success": False, "message": fail_msg}

                # 3. Record attempt before submission
                session_id_to_submit = matched_event.session_id or matched_event.event_id
                action = "join_waitlist" if matched_event.booking_status == "Waitlist Open" else "book"

                attempt = BookingAttempt(
                    preference_id=target.id,
                    target_event_id=matched_event.event_id,
                    session_id=str(session_id_to_submit),
                    mode="AUTO_BOOK",
                    purpose=target.purpose,
                    status="INITIATED",
                    verified=False,
                    attempted_at=datetime.now(timezone.utc)
                )
                session.add(attempt)
                target.execution_status = "EXECUTING"
                await session.commit()
                await session.refresh(attempt)
                attempt_id = attempt.id

                await ws_manager.broadcast({
                    "type": "AUTO_BOOKING_INITIATED",
                    "target_id": target.id,
                    "event_title": target.event_title,
                    "session_id": str(session_id_to_submit),
                    "room": target.preferred_room,
                    "time": matched_event.start_time,
                    "message": f"Executing pre-authorized autonomous booking for '{target.event_title}' (Room {target.preferred_room})."
                })

            # 4. Continuous Submission Loop (Retries up to retry_window_seconds / 5 mins on transient crash/502/timeout)
            max_duration = getattr(target, "retry_window_seconds", 300) or 300
            start_time = asyncio.get_event_loop().time()
            attempt_num = 0
            final_result = None
            duration_ms = 0

            while (asyncio.get_event_loop().time() - start_time) < max_duration:
                attempt_num += 1
                elapsed_sec = int(asyncio.get_event_loop().time() - start_time)
                remaining_sec = max(0, max_duration - elapsed_sec)

                logger.info(
                    f"[AUTONOMOUS_ENGINE] Target #{target_id}: Submission attempt #{attempt_num} "
                    f"(Elapsed: {elapsed_sec}s, Remaining: {remaining_sec}s)..."
                )

                # Update attempt record with attempt count
                async with AsyncSessionLocal() as session:
                    cur_attempt = await session.get(BookingAttempt, attempt_id)
                    if cur_attempt:
                        cur_attempt.retry_count = attempt_num
                        await session.commit()

                # Broadcast live attempt notification
                await ws_manager.broadcast({
                    "type": "AUTO_BOOKING_ATTEMPT",
                    "target_id": target_id,
                    "event_title": target.event_title,
                    "room": target.preferred_room,
                    "attempt_count": attempt_num,
                    "elapsed_seconds": elapsed_sec,
                    "remaining_seconds": remaining_sec,
                    "message": f"Autonomous booking submission attempt #{attempt_num} ({remaining_sec}s left in 5-min surge window)..."
                })

                t0 = datetime.now(timezone.utc)
                try:
                    submit_result = await self.provider.submit_booking(
                        session_id=str(session_id_to_submit),
                        purpose=target.purpose,
                        action=action,
                        target_date=target.target_date
                    )
                    duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
                except Exception as e:
                    submit_result = {
                        "success": False,
                        "status": "SERVER_CRASH",
                        "is_transient": True,
                        "message": f"Submission exception under load: {str(e)}",
                        "verified": False
                    }
                    duration_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)

                final_result = submit_result
                is_success = submit_result.get("success", False)

                if is_success:
                    logger.info(f"Target #{target_id}: Booking CONFIRMED on attempt #{attempt_num}!")
                    break

                # Check if transient error / portal crash
                is_transient = submit_result.get("is_transient", True)
                if is_transient and (asyncio.get_event_loop().time() - start_time) < max_duration:
                    err_msg = submit_result.get("message", "Temporary portal crash / 502 / timeout")
                    logger.warning(
                        f"Target #{target_id}: Attempt #{attempt_num} encountered crash/timeout ({err_msg}). "
                        f"Retrying continuously in 2s ({remaining_sec}s remaining in 5-min window)..."
                    )

                    async with AsyncSessionLocal() as session:
                        cur_attempt = await session.get(BookingAttempt, attempt_id)
                        if cur_attempt:
                            cur_attempt.status = "RETRYING"
                            cur_attempt.response_message = f"Attempt #{attempt_num} crash/timeout: {err_msg}"
                            await session.commit()

                    await ws_manager.broadcast({
                        "type": "PORTAL_CRASH_RETRY",
                        "target_id": target_id,
                        "event_title": target.event_title,
                        "room": target.preferred_room,
                        "attempt_count": attempt_num,
                        "elapsed_seconds": elapsed_sec,
                        "remaining_seconds": remaining_sec,
                        "error_message": err_msg,
                        "message": f"⚡ Portal experiencing high-load crash/timeout. FirstShot is retrying continuously (Attempt #{attempt_num}, {remaining_sec}s remaining)..."
                    })

                    await asyncio.sleep(2.0)
                    continue
                else:
                    # Non-transient fatal error
                    logger.error(f"Target #{target_id}: Non-transient failure on attempt #{attempt_num}: {submit_result.get('message')}")
                    break

            # 5. Verify server response & finalize persistent records
            async with AsyncSessionLocal() as session:
                target = await session.get(BookingPreference, target_id)
                attempt = await session.get(BookingAttempt, attempt_id)
                is_success = final_result.get("success", False) if final_result else False

                if attempt:
                    attempt.status = "CONFIRMED" if is_success else "FAILED"
                    attempt.verified = final_result.get("verified", False) if final_result else False
                    attempt.response_message = final_result.get("message", "") if final_result else "No result."
                    attempt.execution_duration_ms = duration_ms
                    attempt.retry_count = attempt_num

                if target:
                    target.is_armed = False  # Disarm after confirmed success or after 5-minute window expires
                    target.execution_status = "SUCCESS" if is_success else "FAILED"
                    if is_success:
                        target.current_status = "Booked"

                    notif = NotificationLog(
                        event_id=matched_event.event_id,
                        title=target.event_title,
                        status_from="Open",
                        status_to="Booked" if is_success else "Booking Failed",
                        message=(
                            f"Autonomous booking CONFIRMED for '{target.event_title}' in Room {target.preferred_room} on attempt #{attempt_num}!"
                            if is_success else
                            f"Autonomous booking FAILED after {attempt_num} attempts in 5-min surge window: {final_result.get('message') if final_result else 'Timeout'}"
                        ),
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(notif)

                await session.commit()

                # Broadcast final execution result
                broadcast_type = "AUTO_BOOKING_SUCCESS" if is_success else "AUTO_BOOKING_FAILED"
                await ws_manager.broadcast({
                    "type": broadcast_type,
                    "target_id": target_id,
                    "event_title": target.event_title if target else "",
                    "room": target.preferred_room if target else "",
                    "status": "CONFIRMED" if is_success else "FAILED",
                    "verified": final_result.get("verified", False) if final_result else False,
                    "attempt_count": attempt_num,
                    "message": final_result.get("message", "") if final_result else "",
                    "duration_ms": duration_ms
                })

                return final_result or {"success": False, "message": "No submission result."}
        finally:
            self._executing_targets.discard(target_id)

    async def run_job_check(self, job_id: int) -> List[EventSchema]:
        """Runs availability check for a specific job."""
        async with AsyncSessionLocal() as session:
            job = await session.get(MonitoringJob, job_id)
            if not job or not job.is_active:
                return []

            # Check provider session
            try:
                sess_status = await self.provider.check_session()
            except Exception as e:
                logger.error(f"Network or connection error during session check: {e}")
                job.last_status = f"NETWORK_ERROR: {str(e)}"
                job.last_checked_at = datetime.now(IST)
                await session.commit()
                return []

            if not sess_status.get("authenticated"):
                logger.warning(f"Session expired or invalid during job {job_id} check.")
                await ws_manager.broadcast({
                    "type": "SESSION_EXPIRED",
                    "message": "Saveetha portal session expired. Please re-authenticate."
                })
                job.last_status = "SESSION_EXPIRED"
                job.last_checked_at = datetime.now(IST)
                await session.commit()
                return []

            # Fetch active preferences
            pref_result = await session.execute(
                select(BookingPreference).where(
                    (BookingPreference.monitoring_enabled == True) | (BookingPreference.is_active == True)
                )
            )
            preferences = pref_result.scalars().all()

            # Build query filter
            filters = {}
            if job.filter_term:
                filters["event_term"] = job.filter_term
            if job.filter_slot_name:
                filters["slot_name"] = job.filter_slot_name
            if job.filter_date_from:
                filters["date_from"] = job.filter_date_from
            if job.filter_date_to:
                filters["date_to"] = job.filter_date_to

            try:
                raw_events = await self.provider.get_events(filters)
            except Exception as e:
                logger.error(f"Network or provider failure during check: {e}")
                job.last_status = f"ERROR: {str(e)}"
                job.last_checked_at = datetime.now(IST)
                await session.commit()
                await ws_manager.broadcast({
                    "type": "MONITORING_ERROR",
                    "job_id": job_id,
                    "error": str(e)
                })
                return []

            # Filter for specific target event if configured
            if job.target_event_id:
                raw_events = [e for e in raw_events if e.event_id == job.target_event_id or e.session_id == job.target_event_id]

            # Run preference engine
            enriched_events = PreferenceEngine.match_events(raw_events, preferences)

            # Detect status changes & save events to cache
            now = datetime.now(IST)
            for evt in enriched_events:
                old_status = self.last_known_statuses.get(evt.event_id)
                new_status = evt.booking_status

                # Status change detection
                if old_status is not None and old_status != new_status:
                    notif_msg = f"Status changed from '{old_status}' to '{new_status}' for '{evt.title}' ({evt.date} {evt.start_time})"
                    logger.info(notif_msg)

                    notif = NotificationLog(
                        event_id=evt.event_id,
                        title=evt.title,
                        status_from=old_status,
                        status_to=new_status,
                        message=notif_msg,
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(notif)

                    await ws_manager.broadcast({
                        "type": "STATUS_CHANGED",
                        "event": evt.model_dump(),
                        "previous_status": old_status,
                        "new_status": new_status,
                        "notification": notif_msg
                    })

                self.last_known_statuses[evt.event_id] = new_status

                # Upsert into DiscoveredEvent table
                existing = await session.get(DiscoveredEvent, evt.event_id)
                if not existing:
                    existing = DiscoveredEvent(
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
                        purpose_required=evt.purpose_required,
                        last_seen_at=datetime.now(timezone.utc)
                    )
                    session.add(existing)
                else:
                    existing.booking_status = evt.booking_status
                    existing.capacity = evt.capacity
                    existing.waitlist_capacity = evt.waitlist_capacity
                    existing.can_book = evt.can_book
                    existing.has_waitlist = evt.has_waitlist
                    existing.last_seen_at = datetime.now(timezone.utc)

            job.last_checked_at = now
            job.last_status = f"OK ({len(enriched_events)} events discovered)"
            await session.commit()

            # Broadcast live update
            await ws_manager.broadcast({
                "type": "EVENTS_UPDATED",
                "job_id": job_id,
                "count": len(enriched_events),
                "timestamp": now.isoformat(),
                "events": [e.model_dump() for e in enriched_events[:30]]
            })

            return enriched_events

    def schedule_job(self, job_id: int, interval_seconds: int = 60):
        """Schedule an individual job with APScheduler."""
        job_key = f"monitor_job_{job_id}"
        self.scheduler.add_job(
            self.run_job_check,
            trigger=IntervalTrigger(seconds=interval_seconds, timezone=IST),
            args=[job_id],
            id=job_key,
            replace_existing=True
        )
        logger.info(f"Scheduled job {job_key} every {interval_seconds}s (Asia/Kolkata).")

    def remove_job(self, job_id: int):
        job_key = f"monitor_job_{job_id}"
        if self.scheduler.get_job(job_key):
            self.scheduler.remove_job(job_key)
            logger.info(f"Removed job {job_key}.")

# Global engine instance
monitoring_engine = MonitoringEngine()
