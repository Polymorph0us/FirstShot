import re
from datetime import datetime
from typing import List, Optional, Tuple

from app.models.preference import BookingPreference
from app.models.schemas import AlternativeSession, EventSchema


class PreferenceEngine:
    @classmethod
    def evaluate_match(cls, event: EventSchema, preference: BookingPreference) -> Tuple[bool, int, List[str]]:
        """
        Evaluate whether an event matches a user preference / target.
        Returns (is_matched, score, reasons).
        Strict policy:
        - Never match an unrelated event just because it is Open.
        - Room, date, and start time must match exactly when configured.
        """
        reasons: List[str] = []
        score = 0

        # Direct event_id match (if target slot was selected from a card)
        if preference.target_event_id:
            if event.event_id == preference.target_event_id or (event.session_id and event.session_id == preference.target_event_id):
                score += 50
                reasons.append("Exact event target ID match")

        # 1. Title matching (MANDATORY REQUIREMENT)
        pref_title = (preference.event_title or preference.title or "").strip().lower()
        evt_title = event.title.strip().lower()

        if not pref_title:
            return False, 0, []

        title_matched = False
        if pref_title == evt_title:
            score += 30
            reasons.append("Exact title match")
            title_matched = True
        elif pref_title in evt_title or evt_title in pref_title:
            score += 25
            reasons.append(f"Title contains '{preference.event_title or preference.title}'")
            title_matched = True
        else:
            pref_words = set(re.findall(r"\w+", pref_title))
            evt_words = set(re.findall(r"\w+", evt_title))
            common = pref_words.intersection(evt_words)
            if len(common) >= 2 or (len(pref_words) == 1 and len(common) == 1):
                score += 15
                reasons.append("Partial title keyword match")
                title_matched = True

        if not title_matched:
            # Strict rule: Unrelated events must NEVER match
            return False, 0, []

        # 2. Date matching (Target Date)
        target_date = preference.target_date or preference.preferred_date
        if target_date:
            norm_pref_date = cls._normalize_date(target_date)
            norm_evt_date = cls._normalize_date(event.date)
            if norm_pref_date and norm_evt_date:
                if norm_pref_date == norm_evt_date:
                    score += 25
                    reasons.append(f"Date matched: {event.date}")
                else:
                    return False, 0, [f"Date mismatch (expected {target_date}, got {event.date})"]
            elif target_date.lower() in event.date.lower() or event.date.lower() in target_date.lower():
                score += 20
                reasons.append(f"Date text matched: {event.date}")
            else:
                return False, 0, [f"Date mismatch (expected {target_date}, got {event.date})"]

        # 3. Room / Venue matching (Strict)
        target_room = preference.preferred_room or preference.preferred_venue
        if target_room:
            clean_pref_room = target_room.strip().lower()
            clean_evt_venue = (event.venue or "").strip().lower()
            if clean_pref_room == clean_evt_venue or clean_pref_room in clean_evt_venue:
                score += 25
                reasons.append(f"Room matched: {event.venue}")
            else:
                return False, 0, [f"Room mismatch (expected {target_room}, got {event.venue})"]

        # 4. Session Start Time matching (Strict)
        pref_start_time = preference.preferred_start_time or preference.preferred_time
        if pref_start_time:
            norm_pref_time = cls._normalize_time(pref_start_time)
            norm_evt_time = cls._normalize_time(event.start_time)

            time_matched = False
            if norm_pref_time == norm_evt_time:
                score += 20
                reasons.append(f"Preferred start time matched: {event.start_time}")
                time_matched = True
            elif preference.alternative_times:
                alt_list = [cls._normalize_time(t.strip()) for t in preference.alternative_times.split(",") if t.strip()]
                if norm_evt_time in alt_list:
                    score += 10
                    reasons.append(f"Alternative time matched: {event.start_time}")
                    time_matched = True

            if not time_matched:
                return False, 0, [f"Time mismatch (expected {pref_start_time}, got {event.start_time})"]

        # 5. Waitlist acceptance policy
        waitlist_allowed = preference.accept_waitlist if preference.accept_waitlist is not None else preference.allow_waitlist
        if event.booking_status == "Waitlist Open" and not waitlist_allowed:
            return False, 0, ["Waitlist slot rejected (accept_waitlist is False)"]

        return True, min(score, 100), reasons

    @classmethod
    def match_events(cls, events: List[EventSchema], preferences: List[BookingPreference]) -> List[EventSchema]:
        """Enrich events with matching preference flags and scores."""
        matched_results = []
        for evt in events:
            best_match = False
            best_score = 0
            best_reasons = []

            for pref in preferences:
                is_active = pref.monitoring_enabled if pref.monitoring_enabled is not None else pref.is_active
                if not is_active:
                    continue
                matched, score, reasons = cls.evaluate_match(evt, pref)
                if matched and score > best_score:
                    best_match = True
                    best_score = score
                    best_reasons = reasons

            evt_copy = evt.model_copy()
            evt_copy.matched = best_match
            evt_copy.match_score = best_score
            evt_copy.match_reasons = best_reasons
            matched_results.append(evt_copy)

        return matched_results

    @classmethod
    def find_alternatives(cls, target_pref: BookingPreference, all_events: List[EventSchema]) -> List[AlternativeSession]:
        """
        If the preferred target is unavailable (e.g. Full or Closed),
        discover other available matching sessions (e.g. other rooms or other session times)
        without automatically substituting them.
        """
        alternatives: List[AlternativeSession] = []
        target_title = (target_pref.event_title or target_pref.title or "").strip().lower()
        target_date_norm = cls._normalize_date(target_pref.target_date or target_pref.preferred_date)

        for evt in all_events:
            # Must be same assessment title
            if target_title not in evt.title.strip().lower() and evt.title.strip().lower() not in target_title:
                continue

            # Must be same date
            evt_date_norm = cls._normalize_date(evt.date)
            if target_date_norm and evt_date_norm and target_date_norm != evt_date_norm:
                continue

            # Skip if this is the target itself
            is_target_room = (target_pref.preferred_room or "").strip().lower() == (evt.venue or "").strip().lower()
            is_target_time = cls._normalize_time(target_pref.preferred_start_time or "") == cls._normalize_time(evt.start_time)
            if is_target_room and is_target_time:
                continue

            # Only show alternatives that are Open or Waitlist Open (if waitlist allowed)
            if evt.booking_status == "Open" or (evt.booking_status == "Waitlist Open" and target_pref.accept_waitlist):
                reason = []
                if not is_target_room and evt.venue:
                    reason.append(f"Alternative Room {evt.venue}")
                if not is_target_time:
                    reason.append(f"Alternative Time {evt.start_time}")
                reason_str = " | ".join(reason) if reason else "Alternative session"

                alternatives.append(AlternativeSession(
                    event_id=evt.event_id,
                    title=evt.title,
                    date=evt.date,
                    start_time=evt.start_time,
                    end_time=evt.end_time,
                    venue=evt.venue or "Unknown",
                    booking_status=evt.booking_status,
                    capacity=evt.capacity,
                    waitlist_capacity=evt.waitlist_capacity,
                    can_book=evt.can_book,
                    has_waitlist=evt.has_waitlist,
                    reason=reason_str
                ))

        return alternatives

    @staticmethod
    def _normalize_date(d_str: Optional[str]) -> Optional[str]:
        if not d_str:
            return None
        cleaned = d_str.strip()
        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%d-%m-%Y", "%d/%m/%Y", "%B %d, %Y"):
            try:
                return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None

    @staticmethod
    def _normalize_time(t_str: Optional[str]) -> str:
        if not t_str:
            return ""
        cleaned = t_str.strip().replace(".", "").lower()
        for fmt in ("%H:%M", "%I:%M %p", "%I %p"):
            try:
                return datetime.strptime(cleaned, fmt).strftime("%H:%M")
            except ValueError:
                pass
        return cleaned
