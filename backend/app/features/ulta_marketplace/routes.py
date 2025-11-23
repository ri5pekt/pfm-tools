import os
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from . import schemas
from ...dependencies import get_db, get_current_user
from ...core.config import get_settings
from ...jobs.models import Job
from ...jobs.queues import enqueue_job, cancel_job_by_id
from .worker import run_ulta_export_job
from .scheduler import get_scheduler_status

router = APIRouter(
    prefix="/api/app/ulta-marketplace",
    tags=["ulta-marketplace"],
)

settings = get_settings()


@router.post("/export", response_model=schemas.UltaExportResponse)
def create_export(
    request: schemas.UltaExportRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new Ulta Marketplace export job (manual run).
    """
    # Validate date format (supports both with and without milliseconds)
    def parse_date(date_str: str) -> datetime:
        # Handle milliseconds if present (e.g., 2025-11-22T06:00:00.000Z)
        if '.' in date_str and 'Z' in date_str:
            # Remove milliseconds for parsing: 2025-11-22T06:00:00.000Z -> 2025-11-22T06:00:00Z
            date_str = date_str.split('.')[0] + 'Z'
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))

    try:
        parse_date(request.start_date)
        parse_date(request.end_date)
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format. Use ISO format: YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS.sssZ. Error: {str(e)}")

    # Get API key from environment or settings
    ulta_api_key = os.getenv("ULTA_API_KEY") or settings.ulta_api_key
    if not ulta_api_key:
        raise HTTPException(status_code=500, detail="Ulta API key not configured")

    # Create job record
    job = Job(
        feature="ulta_marketplace",
        status="pending",
        input_filename="",  # No input file for API-based exports
        options={
            "start_date": request.start_date,
            "end_date": request.end_date,
            "is_manual": request.is_manual,
            "ulta_api_key": ulta_api_key,
            "progress": 0,
            "status_message": "Queued for processing",
            "start_date_display": request.start_date_display or request.start_date.split('T')[0],
            "end_date_display": request.end_date_display or request.end_date.split('T')[0]
        }
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue the job
    enqueue_job(
        run_ulta_export_job,
        job.id,
        job_timeout=3600  # 1 hour timeout
    )

    return schemas.UltaExportResponse(
        job_id=job.id,
        message="Export job created successfully"
    )


@router.get("/jobs", response_model=List[schemas.UltaJobStatus])
def list_jobs(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    List all Ulta Marketplace export jobs.
    """
    jobs = db.query(Job).filter(Job.feature == "ulta_marketplace").order_by(Job.created_at.desc()).limit(100).all()
    return jobs


@router.get("/jobs/{job_id}", response_model=schemas.UltaJobStatus)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Get details of a specific job.
    """
    job = db.query(Job).filter(Job.id == job_id, Job.feature == "ulta_marketplace").first()
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
    job = db.query(Job).filter(Job.id == job_id, Job.feature == "ulta_marketplace").first()
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
    Delete an Ulta Marketplace export job and its associated files.
    """
    job = db.query(Job).filter(Job.id == job_id, Job.feature == "ulta_marketplace").first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Cancel RQ job if it's pending or running
    job_cancelled = False
    if job.status in ["pending", "running"]:
        job_cancelled = cancel_job_by_id(job_id)

    # Delete associated files
    files_deleted = []
    errors = []

    # Delete output file (if exists)
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
    current_user=Depends(get_current_user),
):
    """
    Get the status of the scheduled export scheduler.
    Returns next run time and last run time.
    """
    return get_scheduler_status()

