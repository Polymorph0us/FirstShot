import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.database.session import AsyncSessionLocal, init_db
from app.main import app
from app.models.booking_attempt import BookingAttempt
from app.models.preference import BookingPreference
from app.providers.simulated import SimulatedProvider
from app.services.preflight import PreflightEngine
from app.services.scheduler import MonitoringEngine


@pytest.mark.asyncio
async def test_booking_modes_and_arming_workflow():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create target preference
        res = await client.post("/api/preferences/", json={
            "event_title": "Module Assessment M3 Test",
            "target_date": "2026-11-20",
            "preferred_room": "1731",
            "preferred_start_time": "08:00",
            "preferred_end_time": "09:29",
            "accept_waitlist": False,
            "monitoring_enabled": True
        })
        assert res.status_code == 200
        target = res.json()
        target_id = target["id"]
        assert target["booking_mode"] == "OBSERVE"
        assert target["is_armed"] is False

        # 2. Switch mode to ASSIST
        mode_res = await client.put(f"/api/preferences/{target_id}/mode", json={"booking_mode": "ASSIST"})
        assert mode_res.status_code == 200
        assert mode_res.json()["booking_mode"] == "ASSIST"

        # 3. Attempt arming WITHOUT user permission -> MUST FAIL with 400
        unauth_arm = await client.put(f"/api/preferences/{target_id}/arm", json={
            "purpose": "Academic Continuous Assessment",
            "accept_waitlist": False,
            "user_permitted_automation": False,
            "booking_mode": "AUTO_BOOK"
        })
        assert unauth_arm.status_code == 400
        assert "authorization is required" in unauth_arm.json()["detail"].lower()

        # 4. Attempt arming with empty purpose -> MUST FAIL with 400
        empty_purpose_arm = await client.put(f"/api/preferences/{target_id}/arm", json={
            "purpose": "   ",
            "accept_waitlist": False,
            "user_permitted_automation": True,
            "booking_mode": "AUTO_BOOK"
        })
        assert empty_purpose_arm.status_code == 400
        assert "purpose field is required" in empty_purpose_arm.json()["detail"].lower()

        # 5. Successfully Arm target
        arm_res = await client.put(f"/api/preferences/{target_id}/arm", json={
            "purpose": "Academic Continuous Assessment Test",
            "accept_waitlist": False,
            "user_permitted_automation": True,
            "booking_mode": "AUTO_BOOK"
        })
        assert arm_res.status_code == 200
        arm_data = arm_res.json()
        assert arm_data["success"] is True
        assert arm_data["target"]["is_armed"] is True
        assert arm_data["target"]["booking_mode"] == "AUTO_BOOK"
        assert arm_data["target"]["execution_status"] == "ARMED"
        assert "preflight" in arm_data

        # 6. Disarm target
        disarm_res = await client.put(f"/api/preferences/{target_id}/disarm")
        assert disarm_res.status_code == 200
        assert disarm_res.json()["is_armed"] is False
        assert disarm_res.json()["execution_status"] == "DISARMED"

        # Clean up
        await client.delete(f"/api/preferences/{target_id}")

@pytest.mark.asyncio
async def test_preflight_checks_comprehensive():
    await init_db()
    sim_provider = SimulatedProvider()

    pref = BookingPreference(
        event_title="Module Assessment",
        target_date="2026-11-20",
        preferred_room="1731",
        preferred_start_time="08:00",
        preferred_end_time="09:29",
        accept_waitlist=False,
        monitoring_enabled=True,
        booking_mode="AUTO_BOOK",
        is_armed=True,
        user_permitted_automation=True,
        purpose="Academic Continuous Assessment"
    )

    # 1. Normal preflight with valid simulated provider -> MUST PASS
    preflight = await PreflightEngine.run_checks(pref, sim_provider)
    assert preflight.passed is True
    assert len(preflight.checks) == 8
    assert all(c.passed for c in preflight.checks)

    # 2. Failure: Expired session
    expired_sim = SimulatedProvider(session_valid=False)
    preflight_exp = await PreflightEngine.run_checks(pref, expired_sim)
    assert preflight_exp.passed is False
    sess_check = next(c for c in preflight_exp.checks if c.name == "Session Authentication")
    assert sess_check.passed is False

    # 3. Failure: Target slot does not exist on portal
    pref_nonexistent = BookingPreference(
        event_title="Quantum Computing",
        target_date="2026-11-20",
        preferred_room="9999",
        preferred_start_time="08:00",
        booking_mode="AUTO_BOOK",
        is_armed=True,
        user_permitted_automation=True,
        purpose="Test"
    )
    preflight_none = await PreflightEngine.run_checks(pref_nonexistent, sim_provider)
    assert preflight_none.passed is False
    exists_check = next(c for c in preflight_none.checks if c.name == "Target Existence on Portal")
    assert exists_check.passed is False

    # 4. Failure: Purpose empty
    pref_no_purpose = BookingPreference(
        event_title="Module Assessment",
        target_date="2026-11-20",
        preferred_room="1731",
        preferred_start_time="08:00",
        booking_mode="AUTO_BOOK",
        is_armed=True,
        user_permitted_automation=True,
        purpose=""
    )
    preflight_purp = await PreflightEngine.run_checks(pref_no_purpose, sim_provider)
    assert preflight_purp.passed is False
    purp_check = next(c for c in preflight_purp.checks if c.name == "Purpose Field Validation")
    assert purp_check.passed is False

@pytest.mark.asyncio
async def test_autonomous_booking_execution_and_disarming():
    await init_db()
    sim_provider = SimulatedProvider()
    engine = MonitoringEngine(provider=sim_provider)

    # Create pre-armed target in DB
    async with AsyncSessionLocal() as session:
        pref = BookingPreference(
            event_title="Module Assessment",
            target_date="2026-11-20",
            preferred_room="1731",
            preferred_start_time="08:00",
            preferred_end_time="09:29",
            accept_waitlist=False,
            monitoring_enabled=True,
            booking_mode="AUTO_BOOK",
            is_armed=True,
            user_permitted_automation=True,
            purpose="Autonomous Execution Verification",
            execution_status="ARMED",
            current_status="Opening Soon"
        )
        session.add(pref)
        await session.commit()
        await session.refresh(pref)
        pref_id = pref.id

    # 1. Target check when Opening Soon -> remains ARMED, no booking executed
    await engine.check_all_targets()
    async with AsyncSessionLocal() as session:
        db_pref = await session.get(BookingPreference, pref_id)
        assert db_pref.current_status == "Opening Soon"
        assert db_pref.is_armed is True
        assert db_pref.execution_status == "ARMED"

    # 2. Window opens: Status transitions from "Opening Soon" -> "Open"
    sim_provider.transition_event_status("sim_101", "Open", can_book=True)

    # 3. Target check triggers autonomous booking
    await engine.check_all_targets()

    # Small sleep to allow background execution task to complete
    await asyncio.sleep(0.5)

    # 4. Verify post-execution state
    async with AsyncSessionLocal() as session:
        db_pref = await session.get(BookingPreference, pref_id)
        assert db_pref.current_status == "Booked"
        assert db_pref.is_armed is False  # Target must be DISARMED after execution
        assert db_pref.execution_status == "SUCCESS"

        # Check persistent BookingAttempt record
        from sqlalchemy import select
        res = await session.execute(
            select(BookingAttempt).where(BookingAttempt.preference_id == pref_id)
        )
        attempts = res.scalars().all()
        assert len(attempts) == 1
        att = attempts[0]
        assert att.status == "CONFIRMED"
        assert att.verified is True
        assert att.mode == "AUTO_BOOK"
        assert att.purpose == "Autonomous Execution Verification"

        # Clean up
        await session.delete(db_pref)
        await session.delete(att)
        await session.commit()

@pytest.mark.asyncio
async def test_crash_recovery_and_continuous_retry():
    """
    Tests crash prevention and 5-minute continuous retry resilience:
    When the portal crashes with HTTP 502/timeouts at opening, FirstShot
    does not give up or disarm, but continuously retries until the portal recovers.
    """
    await init_db()
    sim_provider = SimulatedProvider()
    engine = MonitoringEngine(provider=sim_provider)

    # Configure 2 consecutive simulated crashes (e.g. 502 Bad Gateway under surge)
    sim_provider.crash_failures_remaining = 2

    # Create pre-armed target
    async with AsyncSessionLocal() as session:
        pref = BookingPreference(
            event_title="Module Assessment",
            target_date="2026-11-20",
            preferred_room="1731",
            preferred_start_time="08:00",
            preferred_end_time="09:29",
            accept_waitlist=False,
            monitoring_enabled=True,
            booking_mode="AUTO_BOOK",
            is_armed=True,
            user_permitted_automation=True,
            purpose="Crash Resilience Test",
            execution_status="ARMED",
            current_status="Open",
            retry_window_seconds=300
        )
        session.add(pref)
        await session.commit()
        await session.refresh(pref)
        pref_id = pref.id

    # Session is open on provider
    sim_provider.transition_event_status("sim_101", "Open", can_book=True)

    # Trigger autonomous execution directly with fast retry delay (0.1s for testing)
    target_event = next(e for e in sim_provider.events if e.event_id == "sim_101")
    exec_task = asyncio.create_task(engine.execute_autonomous_booking(pref_id, target_event))

    # Allow retry loop to cycle through attempts 1 (fail), 2 (fail), and 3 (success)
    await asyncio.sleep(5.0)
    await exec_task

    # Verify post-recovery state
    async with AsyncSessionLocal() as session:
        db_pref = await session.get(BookingPreference, pref_id)
        assert db_pref.current_status == "Booked"
        assert db_pref.is_armed is False
        assert db_pref.execution_status == "SUCCESS"

        from sqlalchemy import select
        res = await session.execute(
            select(BookingAttempt).where(BookingAttempt.preference_id == pref_id)
        )
        attempts = res.scalars().all()
        assert len(attempts) == 1
        att = attempts[0]
        assert att.status == "CONFIRMED"
        assert att.verified is True
        assert att.retry_count == 3  # Took 3 attempts (recovered after 2 crashes!)

        # Clean up
        await session.delete(db_pref)
        await session.delete(att)
        await session.commit()
