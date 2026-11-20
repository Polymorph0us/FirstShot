
import pytest

from app.database.session import AsyncSessionLocal, init_db
from app.models.monitoring import MonitoringJob
from app.providers.simulated import SimulatedProvider
from app.services.scheduler import MonitoringEngine


@pytest.mark.asyncio
async def test_scheduler_monitoring_and_status_transition():
    await init_db()

    # Create simulated provider
    sim_provider = SimulatedProvider()
    engine = MonitoringEngine(provider=sim_provider)

    # Set up test job in DB
    async with AsyncSessionLocal() as session:
        job = MonitoringJob(
            name="Test Sim Job",
            filter_slot_name="Module",
            interval_seconds=10,
            is_active=True
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    # 1. Run first check
    events1 = await engine.run_job_check(job_id)
    assert len(events1) >= 1
    target_event = next((e for e in events1 if e.event_id == "sim_102"), None)
    assert target_event is not None
    assert target_event.title == "Module Assessment"
    assert target_event.booking_status == "Open"
    assert engine.last_known_statuses["sim_102"] == "Open"

    # 2. Simulate status change: "Open" -> "Full"
    sim_provider.transition_event_status("sim_102", "Full", can_book=False)

    events2 = await engine.run_job_check(job_id)
    assert len(events2) >= 1
    target_event2 = next((e for e in events2 if e.event_id == "sim_102"), None)
    assert target_event2.booking_status == "Full"
    assert engine.last_known_statuses["sim_102"] == "Full"

    # 3. Simulate identical subsequent run (avoid duplicate notification)
    _ = await engine.run_job_check(job_id)
    assert engine.last_known_statuses["sim_102"] == "Full"

@pytest.mark.asyncio
async def test_scheduler_session_expiration_handling():
    await init_db()
    # Provider with expired session
    expired_provider = SimulatedProvider(session_valid=False)
    engine = MonitoringEngine(provider=expired_provider)

    async with AsyncSessionLocal() as session:
        job = MonitoringJob(
            name="Test Expired Session Job",
            is_active=True
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    events = await engine.run_job_check(job_id)
    assert events == []

    async with AsyncSessionLocal() as session:
        updated_job = await session.get(MonitoringJob, job_id)
        assert updated_job.last_status == "SESSION_EXPIRED"

@pytest.mark.asyncio
async def test_scheduler_network_failure_recovery():
    await init_db()
    # Provider with simulated network failure
    failing_provider = SimulatedProvider(fail_network=True)
    engine = MonitoringEngine(provider=failing_provider)

    async with AsyncSessionLocal() as session:
        job = MonitoringJob(
            name="Test Network Failure Job",
            is_active=True
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id

    # Should recover gracefully without crashing
    events = await engine.run_job_check(job_id)
    assert events == []

    async with AsyncSessionLocal() as session:
        updated_job = await session.get(MonitoringJob, job_id)
        assert "NETWORK_ERROR" in updated_job.last_status or "ERROR" in updated_job.last_status
