import pytest
from httpx import ASGITransport, AsyncClient

from app.database.session import AsyncSessionLocal, init_db
from app.main import app
from app.models.preference import BookingPreference
from app.models.schemas import EventSchema
from app.providers.simulated import SimulatedProvider
from app.services.preference_engine import PreferenceEngine
from app.services.scheduler import MonitoringEngine


@pytest.mark.asyncio
async def test_exact_room_date_time_matching():
    await init_db()
    # Target preference with room 1731 at 08:00
    pref = BookingPreference(
        event_title="Module Assessment",
        target_date="2026-11-20",
        preferred_room="1731",
        preferred_start_time="08:00",
        accept_waitlist=False,
        monitoring_enabled=True
    )

    # 1. Exact match
    event_exact = EventSchema(
        event_id="evt_1",
        title="Module Assessment",
        date="2026-11-20",
        start_time="08:00",
        end_time="09:29",
        venue="1731",
        booking_status="Opening Soon"
    )
    matched, score, reasons = PreferenceEngine.evaluate_match(event_exact, pref)
    assert matched is True
    assert score == 100
    assert any("Room matched" in r for r in reasons)

    # 2. Room mismatch (Room 1851 instead of 1731)
    event_diff_room = EventSchema(
        event_id="evt_2",
        title="Module Assessment",
        date="2026-11-20",
        start_time="08:00",
        end_time="09:29",
        venue="1851",
        booking_status="Open"
    )
    matched, score, reasons = PreferenceEngine.evaluate_match(event_diff_room, pref)
    assert matched is False
    assert any("Room mismatch" in r for r in reasons)

    # 3. Time mismatch (09:45 instead of 08:00)
    event_diff_time = EventSchema(
        event_id="evt_3",
        title="Module Assessment",
        date="2026-11-20",
        start_time="09:45",
        end_time="11:14",
        venue="1731",
        booking_status="Open"
    )
    matched, score, reasons = PreferenceEngine.evaluate_match(event_diff_time, pref)
    assert matched is False
    assert any("Time mismatch" in r for r in reasons)

    # 4. Date mismatch (2026-11-21 instead of 2026-11-20)
    event_diff_date = EventSchema(
        event_id="evt_4",
        title="Module Assessment",
        date="2026-11-21",
        start_time="08:00",
        end_time="09:29",
        venue="1731",
        booking_status="Open"
    )
    matched, score, reasons = PreferenceEngine.evaluate_match(event_diff_date, pref)
    assert matched is False
    assert any("Date mismatch" in r for r in reasons)

@pytest.mark.asyncio
async def test_card_selection_and_duplicate_prevention():
    await init_db()
    import uuid
    rand_id = uuid.uuid4().hex[:6]
    test_title = f"Module Assessment {rand_id}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Method A: Select card as target
        payload = {
            "event_id": f"card_test_{rand_id}",
            "title": test_title,
            "date": "2026-11-20",
            "start_time": "08:00",
            "end_time": "09:29",
            "venue": "1731",
            "accept_waitlist": False,
            "monitoring_enabled": True
        }

        res = await client.post("/api/preferences/from-card", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["event_title"] == test_title
        assert data["preferred_room"] == "1731"
        assert data["preferred_start_time"] == "08:00"

        # Attempt duplicate target selection
        res_dup = await client.post("/api/preferences/from-card", json=payload)
        assert res_dup.status_code == 409
        assert "already saved" in res_dup.json()["detail"].lower()

        # Clean up
        del_res = await client.delete(f"/api/preferences/{data['id']}")
        assert del_res.status_code == 200

@pytest.mark.asyncio
async def test_manual_preference_configuration_and_duplicate():
    await init_db()
    import uuid
    rand_id = uuid.uuid4().hex[:6]
    test_title = f"VIVA {rand_id}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Method B: Manual preference creation
        manual_payload = {
            "event_title": test_title,
            "target_date": "2026-11-22",
            "preferred_room": "1851",
            "preferred_start_time": "13:15",
            "preferred_end_time": "14:44",
            "accept_waitlist": True,
            "monitoring_enabled": True
        }

        res = await client.post("/api/preferences/", json=manual_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["event_title"] == test_title
        assert data["preferred_room"] == "1851"

        # Duplicate check on manual
        res_dup = await client.post("/api/preferences/", json=manual_payload)
        assert res_dup.status_code == 409

        # Clean up
        del_res = await client.delete(f"/api/preferences/{data['id']}")
        assert del_res.status_code == 200

@pytest.mark.asyncio
async def test_target_status_transition_and_alternatives():
    await init_db()
    sim_provider = SimulatedProvider()
    engine = MonitoringEngine(provider=sim_provider)

    # 1. Target in Room 1731 at 08:00 (initially Opening Soon)
    async with AsyncSessionLocal() as session:
        pref = BookingPreference(
            event_title="Module Assessment",
            target_date="2026-11-20",
            preferred_room="1731",
            preferred_start_time="08:00",
            accept_waitlist=False,
            monitoring_enabled=True,
            current_status="Opening Soon"
        )
        session.add(pref)
        await session.commit()
        await session.refresh(pref)
        pref_id = pref.id

    # 2. Run target check when Opening Soon
    await engine.check_all_targets()
    async with AsyncSessionLocal() as session:
        updated = await session.get(BookingPreference, pref_id)
        assert updated.current_status == "Opening Soon"

    # 3. Simulate portal transition: Opening Soon -> Open
    sim_provider.transition_event_status("sim_101", "Open", can_book=True)

    await engine.check_all_targets()
    async with AsyncSessionLocal() as session:
        updated = await session.get(BookingPreference, pref_id)
        assert updated.current_status == "Open"

    # 4. Simulate target becoming Full
    sim_provider.transition_event_status("sim_101", "Full", can_book=False)
    all_events = await sim_provider.get_events()
    alternatives = PreferenceEngine.find_alternatives(updated, all_events)
    # Room 1851 has an Open Module Assessment at 08:00!
    assert len(alternatives) > 0
    assert any(a.venue == "1851" for a in alternatives)
    assert any("Alternative Room 1851" in a.reason for a in alternatives)

    # Clean up
    async with AsyncSessionLocal() as session:
        to_del = await session.get(BookingPreference, pref_id)
        if to_del:
            await session.delete(to_del)
            await session.commit()

@pytest.mark.asyncio
async def test_controlled_booking_confirmation_and_duplicate_prevention():
    await init_db()
    sim_provider = SimulatedProvider()

    # 1. Prepare booking
    prep = await sim_provider.prepare_booking("sim_102", "Continuous Assessment")
    assert prep["success"] is True
    assert prep["ready_to_submit"] is True

    # 2. Test explicit user confirmation requirement
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unconfirmed_res = await client.post("/api/booking/confirm", json={
            "event_id": "sim_102",
            "session_id": "102",
            "purpose": "Academic Continuous Assessment",
            "booking_action": "book",
            "user_confirmed": False
        })
        assert unconfirmed_res.status_code == 400
        assert "explicit user confirmation" in unconfirmed_res.json()["detail"].lower()

    # 3. Test submission directly with provider
    sub_res = await sim_provider.submit_booking(
        session_id="102",
        purpose="Continuous Assessment",
        action="book"
    )
    assert sub_res["success"] is True
    assert sub_res["status"] == "CONFIRMED"
    assert sub_res["verified"] is True
    assert len(sim_provider.submission_log) == 1

    # 4. Test duplicate submission prevention
    sim_provider._submitting_sessions.add("102")
    dup_res = await sim_provider.submit_booking(
        session_id="102",
        purpose="Continuous Assessment",
        action="book"
    )
    assert dup_res["success"] is False
    assert dup_res["status"] == "DUPLICATE_ATTEMPT_PREVENTED"
    sim_provider._submitting_sessions.discard("102")
