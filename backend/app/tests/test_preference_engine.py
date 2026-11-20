import pytest

from app.models.preference import BookingPreference
from app.models.schemas import EventSchema
from app.services.preference_engine import PreferenceEngine


@pytest.fixture
def sample_event():
    return EventSchema(
        event_id="evt_test_1",
        session_id="555",
        title="Module Assessment",
        date="Nov 19, 2026",
        start_time="08:00",
        end_time="09:29",
        venue="1731",
        booking_status="Open",
        can_book=True
    )

def test_preference_exact_match(sample_event):
    pref = BookingPreference(
        title="Module Assessment",
        preferred_date="Nov 19, 2026",
        preferred_time="08:00",
        preferred_venue="1731",
        is_active=True
    )
    matched, score, reasons = PreferenceEngine.evaluate_match(sample_event, pref)
    assert matched is True
    assert score == 100
    assert "Exact title match" in reasons

def test_preference_alternative_time_match(sample_event):
    pref = BookingPreference(
        title="Module Assessment",
        preferred_date="Nov 19, 2026",
        preferred_time="09:45",
        alternative_times="08:00, 13:15",
        is_active=True
    )
    matched, score, reasons = PreferenceEngine.evaluate_match(sample_event, pref)
    assert matched is True
    assert any("Alternative time matched" in r for r in reasons)

def test_preference_strict_no_match_unrelated_event():
    pref = BookingPreference(
        title="Physics Lab Assessment",
        is_active=True
    )
    unrelated_event = EventSchema(
        event_id="evt_test_open",
        session_id="999",
        title="Campus Coding Marathon",
        date="Nov 19, 2026",
        start_time="08:00",
        end_time="09:29",
        booking_status="Open",
        can_book=True
    )
    matched, score, reasons = PreferenceEngine.evaluate_match(unrelated_event, pref)
    # Strictly false! Do not select an unrelated event merely because it is marked Open
    assert matched is False
    assert score == 0

def test_preference_waitlist_policy(sample_event):
    sample_event.booking_status = "Waitlist Open"
    sample_event.can_book = False
    sample_event.has_waitlist = True

    pref_no_waitlist = BookingPreference(
        title="Module Assessment",
        allow_waitlist=False,
        is_active=True
    )
    matched, score, reasons = PreferenceEngine.evaluate_match(sample_event, pref_no_waitlist)
    assert matched is False

    pref_allow_waitlist = BookingPreference(
        title="Module Assessment",
        allow_waitlist=True,
        is_active=True
    )
    matched, score, reasons = PreferenceEngine.evaluate_match(sample_event, pref_allow_waitlist)
    assert matched is True
