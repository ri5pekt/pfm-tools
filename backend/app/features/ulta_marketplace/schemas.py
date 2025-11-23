from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UltaExportRequest(BaseModel):
    start_date: str  # ISO format: 2025-11-01T00:00:00Z
    end_date: str    # ISO format: 2025-11-01T23:59:00Z
    is_manual: bool = True  # True for manual runs, False for scheduled
    start_date_display: str = None  # Original selected start date (YYYY-MM-DD) for display
    end_date_display: str = None    # Original selected end date (YYYY-MM-DD) for display


class UltaExportResponse(BaseModel):
    job_id: int
    message: str


class UltaJobStatus(BaseModel):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    output_filename: Optional[str] = None
    error_message: Optional[str] = None
    options: Optional[dict] = None

