from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DailyOrdersExportRequest(BaseModel):
    date: str  # ISO format: 2025-11-01T00:00:00Z (single date to export)
    is_manual: bool = True  # True for manual runs, False for scheduled
    date_display: str = None  # Original selected date (YYYY-MM-DD) for display
    export_to_file: bool = True  # Export to CSV file
    export_to_google_sheets: bool = True  # Export to Google Sheets


class DailyOrdersExportResponse(BaseModel):
    job_id: int
    message: str


class DailyOrdersJobStatus(BaseModel):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    output_filename: Optional[str] = None
    error_message: Optional[str] = None
    options: Optional[dict] = None


# Scheduled Export Schemas
class ScheduledExportCreate(BaseModel):
    name: str
    period: str  # "minute", "daily", "weekly", "monthly"
    frequency: int = 1  # Frequency: every X minutes/days/weeks/months
    time: Optional[str] = None  # Time in HH:MM format (24-hour) - not needed for minute period
    day_of_week: Optional[int] = None  # 0-6 for weekly (0=Monday, 6=Sunday)
    day_of_month: Optional[int] = None  # 1-31 for monthly
    timezone: str = "UTC"
    enabled: bool = True
    options: Optional[dict] = None


class ScheduledExportUpdate(BaseModel):
    name: Optional[str] = None
    period: Optional[str] = None
    frequency: Optional[int] = None
    time: Optional[str] = None
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None
    options: Optional[dict] = None


class ScheduledExportResponse(BaseModel):
    id: int
    feature: str
    name: str
    period: str
    frequency: int
    time: Optional[str] = None
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    timezone: str
    enabled: bool
    rq_job_id: Optional[str] = None
    options: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

