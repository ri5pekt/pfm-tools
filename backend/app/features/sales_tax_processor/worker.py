from ...core.db import SessionLocal
from .service import process_sales_tax_job


def run_sales_tax_job(job_id: int):
    # This wrapper is what RQ will call
    process_sales_tax_job(job_id, db_session_factory=SessionLocal)
