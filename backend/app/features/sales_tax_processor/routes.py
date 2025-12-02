import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import schemas
from ...dependencies import get_db, get_current_user
from ...core.config import get_settings
from ...jobs.models import Job
from ...jobs.queues import enqueue_job, cancel_job_by_id
from .worker import run_sales_tax_job

router = APIRouter(
    prefix="/api/app/sales-tax-processor",
    tags=["sales-tax-processor"],
)

settings = get_settings()

# Maximum file size: 500 MB
MAX_UPLOAD_SIZE = settings.max_upload_size_mb * 1024 * 1024


@router.post("/upload", response_model=schemas.UploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    order_id_header: str = Form(...),
    woo: bool = Form(True),
    braintree: bool = Form(True),
    tax_diff: bool = Form(True),
    totals_diff: bool = Form(True),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

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

    options = {
        "order_id_header": order_id_header,
        "woo": woo,
        "braintree": braintree,
        "tax_diff": tax_diff,
        "totals_diff": totals_diff,
    }

    job = Job(
        feature="sales_tax_processor",
        status="pending",
        input_filename=dest_path,
        options=options,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue background job with extended timeout for large files
    # 8 hours timeout (28800 seconds) to handle very large CSV files
    enqueue_job(run_sales_tax_job, job.id, job_timeout=28800)

    return {"job_id": job.id}


@router.get("/jobs")
def list_jobs(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    jobs = (
        db.query(Job)
        .filter(Job.feature == "sales_tax_processor")
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
        raise HTTPException(status_code=404, detail="Processed file missing")

    return FileResponse(
        path=job.output_filename,
        filename=os.path.basename(job.output_filename),
        media_type="text/csv",
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
        # Update status to indicate cancellation attempt
        if job.status == "running":
            # For running jobs, we can't immediately stop them,
            # but deleting the DB record will cause the worker to fail gracefully
            pass

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
