import pytest
from httpx import ASGITransport, AsyncClient

from app.database.session import init_db
from app.main import app
from app.providers.simulated import SimulatedProvider


@pytest.mark.asyncio
async def test_single_pristine_target_and_no_duplicates():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a test preference
        create_res = await client.post("/api/preferences/", json={
            "event_title": "Module Assessment Test Audit",
            "target_date": "2026-11-20",
            "preferred_room": "1731",
            "preferred_start_time": "08:00",
            "preferred_end_time": "09:29",
            "accept_waitlist": False,
            "monitoring_enabled": True
        })
        assert create_res.status_code == 200
        data = create_res.json()
        target_id = data["id"]

        # Attempt to insert exact duplicate
        dup_res = await client.post("/api/preferences/", json={
            "event_title": "Module Assessment Test Audit",
            "target_date": "2026-11-20",
            "preferred_room": "1731",
            "preferred_start_time": "08:00",
            "preferred_end_time": "09:29",
            "accept_waitlist": False,
            "monitoring_enabled": True
        })
        assert dup_res.status_code == 409
        assert "already exists" in dup_res.json()["detail"].lower()

        # Clean up
        del_res = await client.delete(f"/api/preferences/{target_id}")
        assert del_res.status_code == 200

@pytest.mark.asyncio
async def test_booking_preparation_blocked_for_opening_soon_target():
    await init_db()
    sim = SimulatedProvider()
    # Opening Soon event
    res = await sim.prepare_booking("sim_101")
    assert res["success"] is False
    assert "Opening Soon" in res["status"]
    assert "Cannot prepare booking" in res["message"]

@pytest.mark.asyncio
async def test_user_confirmation_mandatory_for_booking():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unconfirmed attempt -> MUST fail with 400
        unconfirmed_res = await client.post("/api/booking/confirm", json={
            "event_id": "sim_102",
            "session_id": "102",
            "purpose": "Academic Continuous Assessment",
            "booking_action": "book",
            "user_confirmed": False
        })
        assert unconfirmed_res.status_code == 400
        assert "explicit user confirmation" in unconfirmed_res.json()["detail"].lower()

        # 2. Empty purpose -> MUST fail with 400
        no_purpose_res = await client.post("/api/booking/confirm", json={
            "event_id": "sim_102",
            "session_id": "102",
            "purpose": "   ",
            "booking_action": "book",
            "user_confirmed": True
        })
        assert no_purpose_res.status_code == 400
        assert "purpose field is required" in no_purpose_res.json()["detail"].lower()
