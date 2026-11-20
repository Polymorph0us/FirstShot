import pytest
from httpx import ASGITransport, AsyncClient

from app.database.session import init_db
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["application"] == "FirstShot"
        assert data["provider"] == "Saveetha"

@pytest.mark.asyncio
async def test_terms_endpoint():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/events/terms")
        assert res.status_code == 200
        terms = res.json()
        assert isinstance(terms, list)
        assert len(terms) > 0
        assert any(t["name"] == "26-27-EVENTDAY-02" for t in terms)

@pytest.mark.asyncio
async def test_preferences_api_crud():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create
        create_res = await client.post("/api/preferences/", json={
            "title": "API Test Preference Unique",
            "preferred_date": "2026-11-20",
            "preferred_time": "08:00",
            "alternative_times": ["09:45"],
            "allow_waitlist": True
        })
        assert create_res.status_code == 200
        pref = create_res.json()
        pref_id = pref["id"]
        assert pref["event_title"] == "API Test Preference Unique"

        # List
        list_res = await client.get("/api/preferences/")
        assert list_res.status_code == 200
        prefs = list_res.json()
        assert any(p["id"] == pref_id for p in prefs)

        # Delete
        del_res = await client.delete(f"/api/preferences/{pref_id}")
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

@pytest.mark.asyncio
async def test_assist_mode_booking_safety():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Preparing a non-existent or un-bookable event should fail gracefully
        res = await client.post("/api/booking/prepare", json={
            "event_id": "non_existent_99999",
            "purpose": "Testing safety"
        })
        assert res.status_code == 400
