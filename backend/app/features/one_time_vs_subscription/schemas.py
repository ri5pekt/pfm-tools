from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class OneTimeVsSubscriptionExportRequest(BaseModel):
    date_from: str  # ISO format: 2025-11-01T00:00:00Z (start date)
    date_to: str    # ISO format: 2025-11-07T00:00:00Z (end date)
    is_manual: bool = True
    date_from_display: str = None  # YYYY-MM-DD for display
    date_to_display: str = None    # YYYY-MM-DD for display
    export_to_file: bool = True
    export_to_google_sheets: bool = True


class OneTimeVsSubscriptionExportResponse(BaseModel):
    job_id: int
    message: str


class OneTimeVsSubscriptionJobStatus(BaseModel):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    output_filename: Optional[str] = None
    error_message: Optional[str] = None
    options: Optional[dict] = None


class ScheduledExportCreate(BaseModel):
    name: str
    period: str  # "minute", "daily", "weekly", "monthly"
    frequency: int = 1
    time: Optional[str] = None
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
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
