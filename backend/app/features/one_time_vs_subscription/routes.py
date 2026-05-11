import os
from datetime import datetime, timedelta, time as dt_time
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import schemas
from ...dependencies import get_db, get_current_user
from ...core.config import get_settings
from ...jobs.models import Job, ScheduledExport
from ...jobs.queues import enqueue_job, cancel_job_by_id
from .worker import run_one_time_vs_subscription_export_job
from .scheduler_service import schedule_rq_job, unschedule_rq_job

router = APIRouter(
    prefix="/api/app/one-time-vs-subscription",
    tags=["one-time-vs-subscription"],
)

settings = get_settings()

FEATURE = "one_time_vs_subscription"


@router.post("/export", response_model=schemas.OneTimeVsSubscriptionExportResponse)
def create_export(
    request: schemas.OneTimeVsSubscriptionExportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    def parse_date(date_str: str) -> datetime:
        if '.' in date_str and 'Z' in date_str:
            date_str = date_str.split('.')[0] + 'Z'
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))

    try:
        date_from = parse_date(request.date_from)
        date_to = parse_date(request.date_to)
        if date_from > date_to:
            raise HTTPException(status_code=400, detail="date_from must be before or equal to date_to")
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format. Use ISO format: YYYY-MM-DDTHH:MM:SSZ. Error: {e}")

    if not settings.woo_base_url or not settings.woo_consumer_key or not settings.woo_consumer_secret:
        raise HTTPException(status_code=500, detail="WooCommerce credentials not configured")

    job = Job(
        feature=FEATURE,
        status="pending",
        input_filename="",
        options={
            "date_from": request.date_from,
            "date_to": request.date_to,
            "is_manual": request.is_manual,
            "export_to_file": request.export_to_file,
            "export_to_google_sheets": request.export_to_google_sheets,
            "progress": 0,
            "status_message": "Queued for processing",
            "date_from_display": request.date_from_display or request.date_from.split('T')[0],
            "date_to_display": request.date_to_display or request.date_to.split('T')[0],
        }
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    enqueue_job(run_one_time_vs_subscription_export_job, job.id, job_timeout=7200)

    return schemas.OneTimeVsSubscriptionExportResponse(
        job_id=job.id,
        message="Export job created successfully"
    )


@router.get("/jobs", response_model=List[schemas.OneTimeVsSubscriptionJobStatus])
def list_jobs(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    jobs = db.query(Job).filter(Job.feature == FEATURE).order_by(Job.created_at.desc()).limit(100).all()
    return jobs


@router.get("/jobs/{job_id}", response_model=schemas.OneTimeVsSubscriptionJobStatus)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.feature == FEATURE).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/download")
def download_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.feature == FEATURE).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done" or not job.output_filename:
        raise HTTPException(status_code=400, detail="Job is not completed or has no output file")
    if not os.path.exists(job.output_filename):
        raise HTTPException(status_code=404, detail="Output file not found")

    from fastapi.responses import FileResponse
    return FileResponse(
        job.output_filename,
        media_type="text/csv",
        filename=os.path.basename(job.output_filename)
    )


@router.delete("/jobs/{job_id}")
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.feature == FEATURE).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_cancelled = False
    if job.status in ["pending", "running"]:
        job_cancelled = cancel_job_by_id(job_id)

    files_deleted = []
    errors = []
    if job.output_filename and os.path.exists(job.output_filename):
        try:
            os.remove(job.output_filename)
            files_deleted.append("output file")
        except Exception as e:
            errors.append(f"Failed to delete output file: {e}")

    db.delete(job)
    db.commit()

    return {
        "message": "Job deleted successfully",
        "job_cancelled": job_cancelled,
        "files_deleted": files_deleted,
        "errors": errors if errors else None,
    }


@router.get("/scheduler/status")
def get_scheduler_status_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from datetime import timezone
    from rq_scheduler import Scheduler
    from ...jobs.queues import get_redis_connection

    try:
        scheduled_export = db.query(ScheduledExport).filter(
            ScheduledExport.feature == FEATURE,
            ScheduledExport.enabled == True
        ).first()

        if not scheduled_export or not scheduled_export.rq_job_id:
            last_job = db.query(Job).filter(
                Job.feature == FEATURE,
                Job.options['is_manual'].astext == 'false'
            ).order_by(Job.created_at.desc()).first()

            last_run = None
            if last_job and last_job.created_at:
                last_run = last_job.created_at
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=timezone.utc)

            return {
                "scheduler_running": False,
                "next_run": None,
                "last_run": last_run.isoformat() if last_run else None,
            }

        conn = get_redis_connection()

        try:
            conn.ping()
            scheduler_connected = True
        except Exception:
            scheduler_connected = False

        next_run = None
        try:
            scheduled_score = conn.zscore('rq:scheduler:scheduled_jobs', scheduled_export.rq_job_id)
            if scheduled_score:
                next_run = datetime.fromtimestamp(scheduled_score, tz=timezone.utc)
        except Exception:
            pass

        last_job = db.query(Job).filter(
            Job.feature == FEATURE,
            Job.options['is_manual'].astext == 'false'
        ).order_by(Job.created_at.desc()).first()

        last_run = None
        if last_job and last_job.created_at:
            last_run = last_job.created_at
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)

        return {
            "scheduler_running": scheduler_connected,
            "next_run": next_run.isoformat() if next_run else None,
            "last_run": last_run.isoformat() if last_run else None,
        }
    except Exception as e:
        return {
            "scheduler_running": False,
            "next_run": None,
            "last_run": None,
            "error": str(e),
        }


@router.post("/scheduled-exports", response_model=schemas.ScheduledExportResponse)
def create_scheduled_export(
    request: schemas.ScheduledExportCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    frequency = request.frequency if request.frequency else 1
    if frequency < 1:
        raise HTTPException(status_code=400, detail="frequency must be at least 1")

    if request.period == "minute":
        pass
    elif request.period == "weekly":
        if request.day_of_week is None:
            raise HTTPException(status_code=400, detail="day_of_week is required for weekly period")
        if request.time is None:
            raise HTTPException(status_code=400, detail="time is required for weekly period")
    elif request.period == "monthly":
        if request.day_of_month is None:
            raise HTTPException(status_code=400, detail="day_of_month is required for monthly period")
        if request.time is None:
            raise HTTPException(status_code=400, detail="time is required for monthly period")
    elif request.period == "daily":
        if request.time is None:
            raise HTTPException(status_code=400, detail="time is required for daily period")
    else:
        raise HTTPException(status_code=400, detail=f"Unknown period: {request.period}")

    time_obj = None
    if request.time:
        try:
            time_parts = request.time.split(':')
            time_obj = dt_time(int(time_parts[0]), int(time_parts[1]) if len(time_parts) > 1 else 0)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {request.time}. Use HH:MM format.")

    scheduled_export = ScheduledExport(
        feature=FEATURE,
        name=request.name,
        period=request.period,
        frequency=frequency,
        time=time_obj,
        day_of_week=request.day_of_week,
        day_of_month=request.day_of_month,
        timezone=request.timezone,
        enabled=request.enabled,
        options=request.options or {}
    )
    db.add(scheduled_export)
    db.commit()
    db.refresh(scheduled_export)

    if scheduled_export.enabled:
        schedule_rq_job(db, scheduled_export)

    return {
        "id": scheduled_export.id,
        "feature": scheduled_export.feature,
        "name": scheduled_export.name,
        "period": scheduled_export.period,
        "frequency": scheduled_export.frequency,
        "time": scheduled_export.time.strftime("%H:%M") if scheduled_export.time else None,
        "day_of_week": scheduled_export.day_of_week,
        "day_of_month": scheduled_export.day_of_month,
        "timezone": scheduled_export.timezone,
        "enabled": scheduled_export.enabled,
        "rq_job_id": scheduled_export.rq_job_id,
        "options": scheduled_export.options,
        "created_at": scheduled_export.created_at,
        "updated_at": scheduled_export.updated_at,
    }


@router.get("/scheduled-exports", response_model=List[schemas.ScheduledExportResponse])
def list_scheduled_exports(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    scheduled_exports = db.query(ScheduledExport).filter(
        ScheduledExport.feature == FEATURE
    ).order_by(ScheduledExport.created_at.desc()).all()

    result = []
    for se in scheduled_exports:
        result.append({
            "id": se.id,
            "feature": se.feature,
            "name": se.name,
            "period": se.period,
            "frequency": se.frequency if se.frequency else 1,
            "time": se.time.strftime("%H:%M") if se.time else None,
            "day_of_week": se.day_of_week,
            "day_of_month": se.day_of_month,
            "timezone": se.timezone,
            "enabled": se.enabled,
            "rq_job_id": se.rq_job_id,
            "options": se.options,
            "created_at": se.created_at,
            "updated_at": se.updated_at,
        })
    return result


@router.get("/scheduled-exports/{scheduled_export_id}", response_model=schemas.ScheduledExportResponse)
def get_scheduled_export(
    scheduled_export_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    se = db.query(ScheduledExport).filter(
        ScheduledExport.id == scheduled_export_id,
        ScheduledExport.feature == FEATURE
    ).first()

    if not se:
        raise HTTPException(status_code=404, detail="Scheduled export not found")

    return {
        "id": se.id,
        "feature": se.feature,
        "name": se.name,
        "period": se.period,
        "frequency": se.frequency if se.frequency else 1,
        "time": se.time.strftime("%H:%M") if se.time else None,
        "day_of_week": se.day_of_week,
        "day_of_month": se.day_of_month,
        "timezone": se.timezone,
        "enabled": se.enabled,
        "rq_job_id": se.rq_job_id,
        "options": se.options,
        "created_at": se.created_at,
        "updated_at": se.updated_at,
    }


@router.put("/scheduled-exports/{scheduled_export_id}", response_model=schemas.ScheduledExportResponse)
def update_scheduled_export(
    scheduled_export_id: int,
    request: schemas.ScheduledExportUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    se = db.query(ScheduledExport).filter(
        ScheduledExport.id == scheduled_export_id,
        ScheduledExport.feature == FEATURE
    ).first()

    if not se:
        raise HTTPException(status_code=404, detail="Scheduled export not found")

    needs_reschedule = False

    if request.frequency is not None:
        if request.frequency < 1:
            raise HTTPException(status_code=400, detail="frequency must be at least 1")
        se.frequency = request.frequency
        needs_reschedule = True
    if request.name is not None:
        se.name = request.name
    if request.period is not None:
        se.period = request.period
        needs_reschedule = True
    if request.time is not None:
        try:
            time_parts = request.time.split(':')
            se.time = dt_time(int(time_parts[0]), int(time_parts[1]) if len(time_parts) > 1 else 0)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {request.time}. Use HH:MM format.")
        needs_reschedule = True
    if request.day_of_week is not None:
        se.day_of_week = request.day_of_week
        needs_reschedule = True
    if request.day_of_month is not None:
        se.day_of_month = request.day_of_month
        needs_reschedule = True
    if request.timezone is not None:
        se.timezone = request.timezone
        needs_reschedule = True
    if request.enabled is not None:
        se.enabled = request.enabled
        needs_reschedule = True
    if request.options is not None:
        se.options = request.options

    db.commit()
    db.refresh(se)

    if needs_reschedule:
        if se.rq_job_id:
            unschedule_rq_job(db, se)
        if se.enabled:
            schedule_rq_job(db, se)

    return {
        "id": se.id,
        "feature": se.feature,
        "name": se.name,
        "period": se.period,
        "frequency": se.frequency if se.frequency else 1,
        "time": se.time.strftime("%H:%M") if se.time else None,
        "day_of_week": se.day_of_week,
        "day_of_month": se.day_of_month,
        "timezone": se.timezone,
        "enabled": se.enabled,
        "rq_job_id": se.rq_job_id,
        "options": se.options,
        "created_at": se.created_at,
        "updated_at": se.updated_at,
    }


@router.delete("/scheduled-exports/{scheduled_export_id}")
def delete_scheduled_export(
    scheduled_export_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    se = db.query(ScheduledExport).filter(
        ScheduledExport.id == scheduled_export_id,
        ScheduledExport.feature == FEATURE
    ).first()

    if not se:
        raise HTTPException(status_code=404, detail="Scheduled export not found")

    if se.rq_job_id:
        unschedule_rq_job(db, se)

    db.delete(se)
    db.commit()

    return {"message": "Scheduled export deleted successfully"}
