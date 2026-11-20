import pytest

from app.providers.saveetha import SaveethaProvider


@pytest.mark.asyncio
async def test_real_saveetha_provider_session_and_events():
    """Read-only test against live Saveetha portal session."""
    provider = SaveethaProvider()

    # 1. Check session
    session_status = await provider.check_session()
    assert "authenticated" in session_status
    print("Live session status:", session_status)
    assert session_status["authenticated"] is True, "Expected persistent session to be authenticated"

    # 2. Fetch live events without modification
    events = await provider.get_events()
    assert isinstance(events, list)
    assert len(events) > 0
    print(f"Discovered {len(events)} live events from portal.")

    first = events[0]
    assert first.title != ""
    assert first.date != ""
    assert first.booking_status in (
        "Open",
        "Waitlist Open",
        "Opening Soon",
        "Booking Closed",
        "Full",
        "Booked",
        "Registered",
    )

    # 3. Test filtering with real query parameters
    filtered = await provider.apply_filters({"slot_name": "Module"})
    assert isinstance(filtered, list)
    print(f"Discovered {len(filtered)} Module Assessment sessions.")
    for evt in filtered:
        assert "module" in evt.title.lower()

    # Clean up browser context
    await provider.close()
