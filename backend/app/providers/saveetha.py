import asyncio
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, Playwright, async_playwright

from app.core.config import settings
from app.models.schemas import EventSchema
from app.providers.base import BaseProvider


class SaveethaProvider(BaseProvider):
    def __init__(self, profile_dir: Optional[str] = None):
        self.profile_dir = profile_dir or settings.SAVEETHA_PROFILE_DIR
        self.base_url = settings.SAVEETHA_BASE_URL
        self.event_url = settings.SAVEETHA_EVENT_URL
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._lock = asyncio.Lock()
        self._submitting_sessions: Set[str] = set()
        self.last_fetch_status: Optional[int] = None
        self.last_fetch_error: Optional[str] = None

    async def connect(self) -> bool:
        """Initialize Playwright persistent context if not already running."""
        async with self._lock:
            if self._context is not None:
                return True
            try:
                os.makedirs(self.profile_dir, exist_ok=True)
                self._playwright = await async_playwright().start()
                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
                return True
            except Exception as e:
                print(f"[SaveethaProvider] Error connecting browser context: {e}")
                return False

    async def check_session(self) -> Dict[str, Any]:
        """Check if current persistent context session is authenticated."""
        connected = await self.connect()
        if not connected or not self._context:
            return {
                "authenticated": False,
                "profile_dir": self.profile_dir,
                "portal_url": self.event_url,
                "message": "Failed to connect to local browser profile.",
                "transient": True
            }

        try:
            response = await self._context.request.get(self.event_url, timeout=15000)
            status = response.status
            url = response.url

            # Explicit login redirect or auth rejection
            if "login" in url or status in (301, 302, 401, 403):
                return {
                    "authenticated": False,
                    "profile_dir": self.profile_dir,
                    "portal_url": self.event_url,
                    "message": "Session expired or not logged in. Manual login required.",
                    "error_type": "SESSION_EXPIRED",
                    "transient": False
                }

            # High-traffic server error / crash (500, 502, 503, 504)
            if status in (500, 502, 503, 504):
                return {
                    "authenticated": True,  # Cookies/session remain intact; server is overloaded
                    "server_crashed": True,
                    "status_code": status,
                    "profile_dir": self.profile_dir,
                    "portal_url": self.event_url,
                    "message": f"Server returned HTTP {status} (temporary portal crash under high traffic). Session preserved.",
                    "error_type": "SERVER_CRASH",
                    "transient": True
                }

            html = await response.text()
            if "booking-term" in html or "Saveetha" in html or "academicevents" in html:
                return {
                    "authenticated": True,
                    "profile_dir": self.profile_dir,
                    "portal_url": self.event_url,
                    "message": "Session active and authenticated."
                }

            return {
                "authenticated": True,  # Preserve session during unexpected portal response
                "server_crashed": True,
                "profile_dir": self.profile_dir,
                "portal_url": self.event_url,
                "message": "Unrecognized portal response (possible load balancer / CDN surge page). Session preserved.",
                "transient": True
            }
        except Exception as e:
            # Network timeout or connection drop under traffic surge
            return {
                "authenticated": True,  # Keep authenticated status; network drop does not expire session cookies
                "server_crashed": True,
                "profile_dir": self.profile_dir,
                "portal_url": self.event_url,
                "message": f"Temporary network timeout / connection drop under high traffic: {str(e)}",
                "error_type": "NETWORK_SURGE_TIMEOUT",
                "transient": True
            }

    async def get_events(self, filters: Optional[Dict[str, Any]] = None) -> List[EventSchema]:
        """Fetch and parse events from the booking portal."""
        connected = await self.connect()
        if not connected or not self._context:
            return []

        query_params = {}
        if filters:
            for k in ("event_term", "date_from", "date_to", "slot_name", "session_time"):
                if filters.get(k):
                    query_params[k] = str(filters[k])

        target_url = self.event_url
        if query_params:
            target_url = f"{self.event_url}?{urlencode(query_params)}"

        try:
            response = await self._context.request.get(target_url, timeout=15000)
            self.last_fetch_status = response.status
            if response.status in (500, 502, 503, 504):
                print(f"[SaveethaProvider] Server error HTTP {response.status} fetching events (high surge).")
                self.last_fetch_error = f"HTTP {response.status} Server Error"
                return []
            if response.status != 200:
                print(f"[SaveethaProvider] Non-200 response: {response.status} for {target_url}")
                self.last_fetch_error = f"HTTP {response.status}"
                return []

            self.last_fetch_error = None
            html = await response.text()
            return self.parse_events_html(html)
        except Exception as e:
            print(f"[SaveethaProvider] Error fetching events (timeout/network): {e}")
            self.last_fetch_status = None
            self.last_fetch_error = str(e)
            return []

    async def apply_filters(self, filters: Dict[str, Any]) -> List[EventSchema]:
        return await self.get_events(filters)

    async def get_available_slots(self, filters: Optional[Dict[str, Any]] = None) -> List[EventSchema]:
        events = await self.get_events(filters)
        return [e for e in events if e.booking_status == "Open" or e.can_book]

    async def get_booking_status(self, event_id: str) -> str:
        events = await self.get_events()
        for e in events:
            if e.event_id == event_id or e.session_id == event_id:
                return e.booking_status
        return "Unknown"

    async def get_event_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fetch view-more details for a session if available."""
        connected = await self.connect()
        if not connected or not self._context:
            return None

        url = f"{self.base_url}/academicevents/event-booking/{session_id}/view-more/"
        try:
            response = await self._context.request.get(url)
            if response.status != 200:
                return None
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            title_el = soup.find("h5") or soup.find("h4")
            title = title_el.get_text(strip=True) if title_el else "Unknown Session"
            return {
                "session_id": session_id,
                "title": title,
                "url": url,
                "status": response.status
            }
        except Exception as e:
            print(f"[SaveethaProvider] Error fetching event details: {e}")
            return None

    async def get_available_rooms(self, date: Optional[str] = None) -> List[str]:
        """Discover unique rooms/venues from actual portal cards."""
        filters = {"date_from": date, "date_to": date} if date else None
        events = await self.get_events(filters)
        rooms = set()
        for e in events:
            if e.venue and e.venue.strip():
                rooms.add(e.venue.strip())
        # Sort with standard numerical rooms first (1731, 1851, 1852)
        sorted_rooms = sorted(list(rooms))
        return sorted_rooms

    async def get_available_sessions_for_room(self, date: str, room: str, title: Optional[str] = None) -> List[EventSchema]:
        """Discover actual available sessions for a given date and room."""
        filters = {"date_from": date, "date_to": date}
        events = await self.get_events(filters)
        matching = []
        for e in events:
            # Check room
            if not e.venue or e.venue.strip().lower() != room.strip().lower():
                continue
            # Check title if provided
            if title:
                t_clean = title.strip().lower()
                e_clean = e.title.strip().lower()
                if t_clean not in e_clean and e_clean not in t_clean:
                    continue
            matching.append(e)

        # Sort by start time
        matching.sort(key=lambda x: x.start_time)
        return matching

    async def prepare_booking(self, event_id: str, purpose: str = "Academic Continuous Assessment") -> Dict[str, Any]:
        """Assist Mode: Inspect and prepare booking payload without submitting."""
        events = await self.get_events()
        target_event = None
        for e in events:
            if e.event_id == event_id or e.session_id == event_id:
                target_event = e
                break

        # Date-specific fallback if not in default view
        if not target_event and event_id.startswith("evt_"):
            m = re.match(r"evt_([a-z]{3})_(\d{1,2})_(\d{4})_", event_id)
            if m:
                month_abbr, day_str, year_str = m.groups()
                try:
                    dt = datetime.strptime(f"{month_abbr} {day_str} {year_str}", "%b %d %Y")
                    date_iso = dt.strftime("%Y-%m-%d")
                    date_events = await self.get_events(filters={"date_from": date_iso, "date_to": date_iso})
                    for e in date_events:
                        if e.event_id == event_id or e.session_id == event_id:
                            target_event = e
                            break
                except Exception:
                    pass

        if not target_event:
            return {
                "success": False,
                "event_id": event_id,
                "message": f"Event {event_id} not found."
            }

        if target_event.booking_status not in ("Open", "Waitlist Open"):
            return {
                "success": False,
                "event_id": event_id,
                "title": target_event.title,
                "status": target_event.booking_status,
                "message": f"Cannot prepare booking. Status is '{target_event.booking_status}'."
            }

        session_id = target_event.session_id or event_id
        action_name = "join_waitlist" if target_event.booking_status == "Waitlist Open" else "book"

        return {
            "success": True,
            "event_id": target_event.event_id,
            "session_id": str(session_id),
            "title": target_event.title,
            "venue": target_event.venue,
            "date": target_event.date,
            "time": f"{target_event.start_time} - {target_event.end_time}",
            "booking_action": action_name,
            "purpose": purpose[:255] if purpose else "Academic Continuous Assessment",
            "ready_to_submit": True,
            "status": target_event.booking_status,
            "message": "Booking prepared in ASSIST MODE. Final submission requires your explicit confirmation."
        }

    async def submit_booking(self, session_id: str, purpose: str, action: str = "book", target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute controlled booking submission with CSRF protection and verify server response.
        Enforces duplicate submission prevention and response verification.
        """
        # Duplicate submission prevention lock
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
            connected = await self.connect()
            if not connected or not self._context:
                return {
                    "success": False,
                    "session_id": session_id,
                    "verified": False,
                    "status": "ERROR",
                    "message": "Browser session not connected."
                }

            page = await self._context.new_page()
            try:
                # 1. Navigate to booking page (with date filtering if target_date provided)
                target_url = self.event_url
                if target_date:
                    target_url = f"{self.event_url}?date_from={target_date}&date_to={target_date}"

                try:
                    resp = await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                    if resp and resp.status in (500, 502, 503, 504):
                        return {
                            "success": False,
                            "session_id": session_id,
                            "verified": False,
                            "status": "SERVER_CRASH",
                            "is_transient": True,
                            "message": f"Saveetha portal returned HTTP {resp.status} (High load / Bad Gateway).",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                except Exception as goto_err:
                    return {
                        "success": False,
                        "session_id": session_id,
                        "verified": False,
                        "status": "SERVER_CRASH",
                        "is_transient": True,
                        "message": f"Portal page load timeout/network drop: {str(goto_err)}",
                        "timestamp": datetime.utcnow().isoformat()
                    }

                # Check if page rendered a server crash screen
                page_text = await page.content()
                is_crash_screen = any(err in page_text.lower() for err in ["502 bad gateway", "504 gateway time-out", "503 service unavailable", "internal server error", "an error occurred."])
                if is_crash_screen:
                    return {
                        "success": False,
                        "session_id": session_id,
                        "verified": False,
                        "status": "SERVER_CRASH",
                        "is_transient": True,
                        "message": "Portal rendered server crash page (HTTP 502/504 Bad Gateway).",
                        "timestamp": datetime.utcnow().isoformat()
                    }

                # 2. Check if already booked before filling form (in case previous attempt completed on backend)
                if any(ind in page_text.lower() for ind in ["already booked", "already registered", "registration successful"]):
                    return {
                        "success": True,
                        "session_id": session_id,
                        "verified": True,
                        "status": "CONFIRMED",
                        "message": "Slot is already registered / booked for your account.",
                        "timestamp": datetime.utcnow().isoformat()
                    }

                # 3. Locate form corresponding to session_id
                form_selector = f'form:has(input[name="session_id"][value="{session_id}"])'
                form = await page.query_selector(form_selector)
                if not form:
                    return {
                        "success": False,
                        "session_id": session_id,
                        "verified": False,
                        "status": "UNAVAILABLE",
                        "is_transient": True,  # Under surge, button might activate seconds late
                        "message": f"Target session {session_id} booking form not yet rendered on page.",
                        "timestamp": datetime.utcnow().isoformat()
                    }

                # 4. Fill required purpose field (max 255 chars)
                purpose_input = await form.query_selector('input[name="purpose"]')
                if purpose_input:
                    clean_purpose = (purpose or "Academic Continuous Assessment")[:255]
                    await purpose_input.fill(clean_purpose)

                # 5. Locate submit button
                submit_btn = await form.query_selector('button[type="submit"]')
                if not submit_btn:
                    return {
                        "success": False,
                        "session_id": session_id,
                        "verified": False,
                        "status": "NO_BUTTON",
                        "is_transient": True,
                        "message": "Booking submit button not found in form.",
                        "timestamp": datetime.utcnow().isoformat()
                    }

                # 6. Submit form and wait for navigation / redirect
                try:
                    async with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
                        await submit_btn.click()
                except Exception as nav_err:
                    print(f"[SaveethaProvider] Navigation wait timed out/completed: {nav_err}")

                # 7. Verify actual server response and post-submission state
                content = await page.content()
                soup = BeautifulSoup(content, "html.parser")

                # Extract Django alert messages
                alerts = []
                for alert_el in soup.find_all(class_=re.compile(r"alert\b")):
                    alert_text = alert_el.get_text(strip=True)
                    if alert_text:
                        alerts.append(alert_text)

                alert_summary = " | ".join(alerts)

                # Check for success indicators in alert messages
                is_success = False
                if any("success" in a.lower() or "confirmed" in a.lower() or "booked" in a.lower() or "waitlist" in a.lower() for a in alerts):
                    is_success = True
                elif "already booked" in alert_summary.lower() or "registered" in alert_summary.lower():
                    is_success = True
                elif "already registered" in content.lower():
                    is_success = True

                # Check if card changed to booked / waitlisted
                card_still_available = soup.find("input", {"name": "session_id", "value": session_id})

                status_code_str = "CONFIRMED" if is_success else ("UNVERIFIED" if card_still_available else "SUBMITTED")

                # If not confirmed and card still available, check if server crashed or returned 502 after submit
                is_transient_failure = False
                if not is_success:
                    if any(err in content.lower() for err in ["502 bad gateway", "504 gateway", "500 internal", "timeout"]):
                        is_transient_failure = True
                    elif card_still_available and not alerts:
                        is_transient_failure = True  # Form still there, no error alert - retry!

                return {
                    "success": is_success,
                    "session_id": session_id,
                    "verified": is_success,
                    "status": status_code_str,
                    "is_transient": is_transient_failure,
                    "message": alert_summary if alert_summary else ("Booking form submitted. Status requires verification." if is_success else "Submission attempt did not confirm booking."),
                    "timestamp": datetime.utcnow().isoformat()
                }
            finally:
                await page.close()
        except Exception as e:
            err_str = str(e).lower()
            is_transient = any(t in err_str for t in ["timeout", "net::", "connection", "reset", "502", "504", "500", "navigation", "disconnected", "target closed"])
            return {
                "success": False,
                "session_id": session_id,
                "verified": False,
                "status": "SERVER_CRASH" if is_transient else "ERROR",
                "is_transient": is_transient,
                "message": f"Submission error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat()
            }
        finally:
            self._submitting_sessions.discard(session_id)

    async def reauthenticate(self) -> bool:
        """Launch visible Chromium window for manual login."""
        await self.close()
        p = await async_playwright().start()
        context = await p.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(self.event_url)

        for _ in range(60):
            await asyncio.sleep(3)
            if "academicevents/event-booking" in page.url and "login" not in page.url:
                await context.close()
                await p.stop()
                return True

        await context.close()
        await p.stop()
        return False

    async def close(self):
        """Close browser context and playwright instance."""
        async with self._lock:
            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass
                self._context = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

    @classmethod
    def parse_events_html(cls, html: str) -> List[EventSchema]:
        """Pure parsing of server-rendered HTML into structured EventSchema objects."""
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_=re.compile(r"card.*shadow-sm.*border-0.*h-100"))
        events: List[EventSchema] = []

        for card in cards:
            try:
                title_el = card.find("h5", class_=re.compile(r"fw-semibold")) or card.find("h5")
                title = title_el.get_text(strip=True) if title_el else "Unknown Event"

                date_str = ""
                start_time_str = ""
                end_time_str = ""
                venue_str = ""
                description_str = ""

                muted_divs = card.find_all("div", class_=re.compile(r"text-muted small|small text-muted"))
                for div in muted_divs:
                    text = div.get_text(strip=True)
                    if "·" in text:
                        parts = [p.strip() for p in text.split("·", 1)]
                        date_str = parts[0]
                        if len(parts) > 1 and "-" in parts[1]:
                            time_parts = parts[1].split("-")
                            start_time_str = cls._normalize_time(time_parts[0])
                            end_time_str = cls._normalize_time(time_parts[1])
                    elif text.startswith("Venue:"):
                        venue_str = text.replace("Venue:", "").strip()

                desc_p = card.find("div", class_=re.compile(r"small mt-1"))
                if desc_p:
                    description_str = desc_p.get_text(strip=True)

                status_el = card.find("span", class_=re.compile(r"badge bg-"))
                booking_status = status_el.get_text(strip=True) if status_el else "Unknown"

                reward_points = 0
                attendance_cluster = None
                all_badges = card.find_all("span", class_="badge")
                for badge in all_badges:
                    b_text = badge.get_text(strip=True)
                    if "Reward Points:" in b_text:
                        m = re.search(r"Reward Points:\s*(\d+)", b_text)
                        if m:
                            reward_points = int(m.group(1))
                    elif "ClassAttendance:" in b_text:
                        attendance_cluster = b_text.replace("ClassAttendance:", "").strip()

                booking_window_start = None
                booking_window_end = None
                cancellation_deadline = None
                capacity_str = None
                waitlist_str = None

                for div in muted_divs:
                    text = div.get_text(strip=True)
                    if text.startswith("Booking Window:"):
                        window_content = text.replace("Booking Window:", "").strip()
                        if "→" in window_content:
                            w_parts = window_content.split("→")
                            booking_window_start = cls._normalize_datetime(w_parts[0])
                            booking_window_end = cls._normalize_datetime(w_parts[1])
                        else:
                            booking_window_start = window_content
                    elif text.startswith("Cancellation Ends:"):
                        cancellation_deadline = cls._normalize_datetime(text.replace("Cancellation Ends:", "").strip())
                    elif text.startswith("Capacity:"):
                        capacity_str = text.replace("Capacity:", "").strip()
                    elif text.startswith("Waitlist:"):
                        waitlist_str = text.replace("Waitlist:", "").strip()

                session_id = None
                session_input = card.find("input", {"name": "session_id"})
                if session_input and session_input.get("value"):
                    session_id = session_input["value"]
                else:
                    view_more_link = card.find("a", href=re.compile(r"/event-booking/(\d+)"))
                    if view_more_link:
                        m = re.search(r"/event-booking/(\d+)", view_more_link["href"])
                        if m:
                            session_id = m.group(1)

                form = card.find("form")
                can_book = False
                has_waitlist = False
                purpose_required = False

                if form:
                    purpose_input = form.find("input", {"name": "purpose"})
                    if purpose_input:
                        purpose_required = purpose_input.has_attr("required")

                    submit_btn = form.find("button", {"type": "submit"})
                    if submit_btn:
                        btn_text = submit_btn.get_text(strip=True).lower()
                        if "book now" in btn_text:
                            can_book = True
                        elif "waitlist" in btn_text:
                            has_waitlist = True

                event_id = session_id if session_id else cls._generate_composite_id(title, date_str, start_time_str, venue_str)

                event = EventSchema(
                    event_id=event_id,
                    session_id=session_id,
                    title=title,
                    date=date_str,
                    start_time=start_time_str,
                    end_time=end_time_str,
                    venue=venue_str,
                    description=description_str,
                    booking_status=booking_status,
                    booking_window_start=booking_window_start,
                    booking_window_end=booking_window_end,
                    cancellation_deadline=cancellation_deadline,
                    capacity=capacity_str,
                    waitlist_capacity=waitlist_str,
                    reward_points=reward_points,
                    attendance_cluster=attendance_cluster,
                    can_book=can_book,
                    has_waitlist=has_waitlist,
                    purpose_required=purpose_required
                )
                events.append(event)
            except Exception as e:
                print(f"[SaveethaParser] Warning: failed to parse card: {e}")
                continue

        return events

    @staticmethod
    def _normalize_time(t_str: str) -> str:
        """Parse '8 a.m.' or '1:15 p.m.' to '08:00' or '13:15'."""
        cleaned = t_str.strip().replace(".", "").lower()
        for fmt in ("%I:%M %p", "%I %p"):
            try:
                return datetime.strptime(cleaned, fmt).strftime("%H:%M")
            except ValueError:
                pass
        return t_str.strip()

    @staticmethod
    def _normalize_datetime(dt_str: str) -> str:
        """Parse 'Nov 18, 2026, 7 p.m.' to ISO formatted string."""
        cleaned = re.sub(r"\b([ap])\.m\.", r"\1m", dt_str.strip(), flags=re.IGNORECASE)
        for fmt in ("%b %d, %Y, %I:%M %p", "%b %d, %Y, %I %p", "%b %d, %Y"):
            try:
                return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass
        return dt_str.strip()

    @staticmethod
    def _generate_composite_id(title: str, date: str, time: str, venue: str) -> str:
        """Deterministic ID when session_id is not yet in the DOM."""
        clean_title = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower()[:30]
        clean_date = re.sub(r"[^a-zA-Z0-9]+", "_", date).strip("_").lower()
        clean_time = re.sub(r"[^a-zA-Z0-9]+", "_", time).strip("_").lower()
        clean_venue = re.sub(r"[^a-zA-Z0-9]+", "_", venue).strip("_").lower()
        return f"evt_{clean_date}_{clean_time}_{clean_venue}_{clean_title}"
