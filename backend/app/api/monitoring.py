from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.monitoring import MonitoringJob, NotificationLog
from app.models.schemas import MonitoringJobCreate, MonitoringJobResponse
from app.services.scheduler import monitoring_engine

router = APIRouter(prefix="/api/monitoring", tags=["Monitoring"])

@router.get("/jobs", response_model=List[MonitoringJobResponse])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MonitoringJob).order_by(MonitoringJob.id.desc()))
    jobs = result.scalars().all()
    return [j.to_dict() for j in jobs]

@router.post("/jobs", response_model=MonitoringJobResponse)
async def create_job(data: MonitoringJobCreate, db: AsyncSession = Depends(get_db)):
    job = MonitoringJob(
        name=data.name,
        target_event_id=data.target_event_id,
        filter_term=data.filter_term,
        filter_slot_name=data.filter_slot_name,
        filter_date_from=data.filter_date_from,
        filter_date_to=data.filter_date_to,
        interval_seconds=data.interval_seconds,
        mode=data.mode,
        is_active=True
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Schedule with monitoring engine
    monitoring_engine.schedule_job(job.id, job.interval_seconds)
    return job.to_dict()

@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(MonitoringJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    monitoring_engine.remove_job(job_id)
    await db.delete(job)
    await db.commit()
    return {"success": True, "message": f"Job {job_id} deleted"}

@router.post("/jobs/{job_id}/run")
async def run_job_now(job_id: int):
    """Trigger an immediate check for a specific job."""
    events = await monitoring_engine.run_job_check(job_id)
    return {"success": True, "discovered_count": len(events)}

@router.get("/notifications")
async def list_notifications(limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(NotificationLog).order_by(NotificationLog.id.desc()).limit(limit))
    notifs = result.scalars().all()
    return [n.to_dict() for n in notifs]
