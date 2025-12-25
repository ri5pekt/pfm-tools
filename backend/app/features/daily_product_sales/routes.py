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
from .worker import run_daily_product_sales_export_job
from .scheduler_service import schedule_rq_job, unschedule_rq_job

router = APIRouter(
    prefix="/api/app/daily-product-sales",
    tags=["daily-product-sales"],
)

settings = get_settings()


@router.post("/export", response_model=schemas.DailyProductSalesExportResponse)
def create_export(
    request: schemas.DailyProductSalesExportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new Daily Product Sales export job (manual run).
    """
    # Validate date format
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
        raise HTTPException(status_code=400, detail=f"Invalid date format. Use ISO format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.sssZ. Error: {str(e)}")

    # Verify WooCommerce credentials
    if not settings.woo_base_url or not settings.woo_consumer_key or not settings.woo_consumer_secret:
        raise HTTPException(status_code=500, detail="WooCommerce credentials not configured")

    # Create job record
    job = Job(
        feature="daily_product_sales",
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
            "date_to_display": request.date_to_display or request.date_to.split('T')[0]
        }
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue the job
    enqueue_job(
        run_daily_product_sales_export_job,
        job.id,
        job_timeout=7200  # 2 hour timeout (longer for date ranges)
    )

    return schemas.DailyProductSalesExportResponse(
        job_id=job.id,
        message="Export job created successfully"
    )


@router.get("/jobs", response_model=List[schemas.DailyProductSalesJobStatus])
def list_jobs(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    List all Daily Product Sales export jobs.
    """
    jobs = db.query(Job).filter(Job.feature == "daily_product_sales").order_by(Job.created_at.desc()).limit(100).all()
    return jobs


@router.get("/jobs/{job_id}", response_model=schemas.DailyProductSalesJobStatus)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get details of a specific job.
    """
    job = db.query(Job).filter(Job.id == job_id, Job.feature == "daily_product_sales").first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/download")
def download_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Download the CSV file for a completed job.
    """
    job = db.query(Job).filter(Job.id == job_id, Job.feature == "daily_product_sales").first()
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
    """
    Delete a Daily Product Sales export job and its associated files.
    """
    job = db.query(Job).filter(Job.id == job_id, Job.feature == "daily_product_sales").first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Cancel RQ job if it's pending or running
    job_cancelled = False
    if job.status in ["pending", "running"]:
        job_cancelled = cancel_job_by_id(job_id)

    # Delete associated files
    files_deleted = []
    errors = []

    if job.output_filename and os.path.exists(job.output_filename):
        try:
            os.remove(job.output_filename)
            files_deleted.append("output file")
        except Exception as e:
            errors.append(f"Failed to delete output file: {str(e)}")

    # Delete job from database
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
    """
    Get the status of the scheduled export scheduler.
    """
    from datetime import datetime, timezone
    from rq_scheduler import Scheduler
    from ...jobs.queues import get_redis_connection

    try:
        # Get first enabled scheduled export
        scheduled_export = db.query(ScheduledExport).filter(
            ScheduledExport.feature == "daily_product_sales",
            ScheduledExport.enabled == True
        ).first()

        if not scheduled_export or not scheduled_export.rq_job_id:
            # Get last scheduled job run
            last_job = db.query(Job).filter(
                Job.feature == "daily_product_sales",
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

        # Get next run time from RQ scheduler
        conn = get_redis_connection()
        scheduler = Scheduler(connection=conn)

        try:
            conn.ping()
            scheduler_connected = True
        except:
            scheduler_connected = False

        next_run = None
        try:
            redis_conn = get_redis_connection()
            scheduled_score = redis_conn.zscore('rq:scheduler:scheduled_jobs', scheduled_export.rq_job_id)
            if scheduled_score:
                next_run = datetime.fromtimestamp(scheduled_score, tz=timezone.utc)
        except Exception as e:
            pass

        # Get last scheduled job run
        last_job = db.query(Job).filter(
            Job.feature == "daily_product_sales",
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
            "error": str(e)
        }


# Scheduled Export CRUD Routes (same as daily_orders_data but with feature="daily_product_sales")
@router.post("/scheduled-exports", response_model=schemas.ScheduledExportResponse)
def create_scheduled_export(
    request: schemas.ScheduledExportCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new scheduled export configuration.
    """
    # Validate frequency
    frequency = request.frequency if request.frequency else 1
    if frequency < 1:
        raise HTTPException(status_code=400, detail="frequency must be at least 1")

    # Validate period-specific fields
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

    # Parse time string to Time object
    time_obj = None
    if request.time:
        try:
            time_parts = request.time.split(':')
            time_obj = dt_time(int(time_parts[0]), int(time_parts[1]) if len(time_parts) > 1 else 0)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {request.time}. Use HH:MM format.")

    # Create scheduled export
    scheduled_export = ScheduledExport(
        feature="daily_product_sales",
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

    # Schedule the RQ job if enabled
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
    """
    List all scheduled export configurations.
    """
    scheduled_exports = db.query(ScheduledExport).filter(
        ScheduledExport.feature == "daily_product_sales"
    ).order_by(ScheduledExport.created_at.desc()).all()

    result = []
    for se in scheduled_exports:
        se_dict = {
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
        result.append(se_dict)

    return result


@router.get("/scheduled-exports/{scheduled_export_id}", response_model=schemas.ScheduledExportResponse)
def get_scheduled_export(
    scheduled_export_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get a specific scheduled export configuration.
    """
    scheduled_export = db.query(ScheduledExport).filter(
        ScheduledExport.id == scheduled_export_id,
        ScheduledExport.feature == "daily_product_sales"
    ).first()

    if not scheduled_export:
        raise HTTPException(status_code=404, detail="Scheduled export not found")

    return {
        "id": scheduled_export.id,
        "feature": scheduled_export.feature,
        "name": scheduled_export.name,
        "period": scheduled_export.period,
        "frequency": scheduled_export.frequency if scheduled_export.frequency else 1,
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


@router.put("/scheduled-exports/{scheduled_export_id}", response_model=schemas.ScheduledExportResponse)
def update_scheduled_export(
    scheduled_export_id: int,
    request: schemas.ScheduledExportUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Update a scheduled export configuration.
    """
    scheduled_export = db.query(ScheduledExport).filter(
        ScheduledExport.id == scheduled_export_id,
        ScheduledExport.feature == "daily_product_sales"
    ).first()

    if not scheduled_export:
        raise HTTPException(status_code=404, detail="Scheduled export not found")

    needs_reschedule = False

    if request.frequency is not None:
        if request.frequency < 1:
            raise HTTPException(status_code=400, detail="frequency must be at least 1")
        scheduled_export.frequency = request.frequency
        needs_reschedule = True

    if request.name is not None:
        scheduled_export.name = request.name
    if request.period is not None:
        scheduled_export.period = request.period
        needs_reschedule = True
    if request.time is not None:
        try:
            time_parts = request.time.split(':')
            scheduled_export.time = dt_time(int(time_parts[0]), int(time_parts[1]) if len(time_parts) > 1 else 0)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid time format: {request.time}. Use HH:MM format.")
        needs_reschedule = True
    if request.day_of_week is not None:
        scheduled_export.day_of_week = request.day_of_week
        needs_reschedule = True
    if request.day_of_month is not None:
        scheduled_export.day_of_month = request.day_of_month
        needs_reschedule = True
    if request.timezone is not None:
        scheduled_export.timezone = request.timezone
        needs_reschedule = True
    if request.enabled is not None:
        scheduled_export.enabled = request.enabled
        needs_reschedule = True
    if request.options is not None:
        scheduled_export.options = request.options

    db.commit()
    db.refresh(scheduled_export)

    # Reschedule if needed
    if needs_reschedule:
        # Unschedule existing job
        if scheduled_export.rq_job_id:
            unschedule_rq_job(db, scheduled_export)

        # Schedule new job if enabled
        if scheduled_export.enabled:
            schedule_rq_job(db, scheduled_export)

    return {
        "id": scheduled_export.id,
        "feature": scheduled_export.feature,
        "name": scheduled_export.name,
        "period": scheduled_export.period,
        "frequency": scheduled_export.frequency if scheduled_export.frequency else 1,
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


@router.delete("/scheduled-exports/{scheduled_export_id}")
def delete_scheduled_export(
    scheduled_export_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Delete a scheduled export configuration.
    """
    scheduled_export = db.query(ScheduledExport).filter(
        ScheduledExport.id == scheduled_export_id,
        ScheduledExport.feature == "daily_product_sales"
    ).first()

    if not scheduled_export:
        raise HTTPException(status_code=404, detail="Scheduled export not found")

    # Unschedule RQ job
    if scheduled_export.rq_job_id:
        unschedule_rq_job(db, scheduled_export)

    # Delete from database
    db.delete(scheduled_export)
    db.commit()

    return {"message": "Scheduled export deleted successfully"}

