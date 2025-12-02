import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import schemas
from ...dependencies import get_db, get_current_user
from ...core.config import get_settings
from ...jobs.models import Job
from ...jobs.queues import enqueue_job, cancel_job_by_id
from .worker import run_comparison_job

router = APIRouter(
    prefix="/api/app/order-comparison",
    tags=["order-comparison"],
)

settings = get_settings()

# Maximum file size: 500 MB
MAX_UPLOAD_SIZE = settings.max_upload_size_mb * 1024 * 1024


@router.post("/upload", response_model=schemas.UploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    order_id_header: str = Form(...),
    date_from: str = Form(...),
    date_to: str = Form(...),
    usa_only: str = Form("true"),
    exclude_states: str = Form(""),
    exclude_complyt_states: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

    # Validate date format
    try:
        datetime.fromisoformat(date_from)
        datetime.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")


    os.makedirs(settings.uploads_dir, exist_ok=True)

    # Generate unique filename to avoid conflicts
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    dest_path = os.path.join(settings.uploads_dir, unique_filename)

    # Stream file in chunks to handle large files efficiently
    total_size = 0
    chunk_size = 1024 * 1024  # 1 MB chunks

    try:
        with open(dest_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE:
                    os.remove(dest_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Parse boolean and states
    usa_only_bool = usa_only.lower() == "true"
    # WooCommerce uses state codes (uppercase)
    exclude_states_list = [s.strip().upper() for s in exclude_states.split(",") if s.strip()] if exclude_states else []
    # Complyt CSV uses full state names (preserve original case)
    exclude_complyt_states_list = [s.strip() for s in exclude_complyt_states.split(",") if s.strip()] if exclude_complyt_states else []

    options = {
        "order_id_header": order_id_header,
        "date_from": date_from,
        "date_to": date_to,
        "usa_only": usa_only_bool,
        "exclude_states": exclude_states_list,
        "exclude_complyt_states": exclude_complyt_states_list,
        "original_filename": file.filename,  # Store original filename for display
    }

    job = Job(
        feature="order_comparison",
        status="pending",
        input_filename=dest_path,
        options=options,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue background job with extended timeout for large datasets
    # 4 hours (14400 seconds) to handle very large date ranges and many WooCommerce API calls
    # Large date ranges can require hundreds of API pages, each taking 1-2 seconds
    enqueue_job(run_comparison_job, job.id, job_timeout=14400)

    return {"job_id": job.id}


@router.get("/jobs")
def list_jobs(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    jobs = (
        db.query(Job)
        .filter(Job.feature == "order_comparison")
        .order_by(Job.created_at.desc())
        .all()
    )
    return jobs


@router.get("/job/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/job/{job_id}/download")
def download_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done" or not job.output_filename:
        raise HTTPException(status_code=400, detail="Job not finished")

    if not os.path.exists(job.output_filename):
        raise HTTPException(status_code=404, detail="Report file missing")

    # Determine media type and filename based on file extension
    if job.output_filename.endswith('.zip'):
        media_type = "application/zip"
        # Ensure filename has .zip extension for download
        filename = os.path.basename(job.output_filename)
        if not filename.endswith('.zip'):
            filename = filename.rsplit('.', 1)[0] + '.zip'
    elif job.output_filename.endswith('.pdf'):
        media_type = "application/pdf"
        # Ensure filename has .pdf extension for download
        filename = os.path.basename(job.output_filename)
        if not filename.endswith('.pdf'):
            filename = filename.rsplit('.', 1)[0] + '.pdf'
    else:
        media_type = "text/plain"
        filename = os.path.basename(job.output_filename)

    # FileResponse will set Content-Disposition automatically from filename parameter
    # But we also set it explicitly to ensure it's correct
    return FileResponse(
        path=job.output_filename,
        filename=filename,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.delete("/job/{job_id}")
def delete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Cancel RQ job if it's pending or running
    job_cancelled = False
    if job.status in ["pending", "running"]:
        job_cancelled = cancel_job_by_id(job_id)

    # Delete associated files
    files_deleted = []
    errors = []

    # Delete input file
    if job.input_filename and os.path.exists(job.input_filename):
        try:
            os.remove(job.input_filename)
            files_deleted.append("input file")
        except Exception as e:
            errors.append(f"Failed to delete input file: {str(e)}")

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

