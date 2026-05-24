from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, Time
from sqlalchemy.dialects.postgresql import JSONB  # if using Postgres
from ..core.db import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    feature = Column(String(100), nullable=False)  # e.g. "sales_tax_processor"
    status = Column(String(50), default="pending")  # pending, running, done, error
    input_filename = Column(String(255), nullable=False)
    output_filename = Column(String(255), nullable=True)
    options = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScheduledExport(Base):
    __tablename__ = "scheduled_exports"

    id = Column(Integer, primary_key=True, index=True)
    feature = Column(String(100), nullable=False)  # e.g. "inventory_data"
    name = Column(String(255), nullable=False)  # User-friendly name for the scheduled export
    period = Column(String(50), nullable=False)  # "minute", "daily", "weekly", "monthly"
    frequency = Column(Integer, default=1)  # Frequency: every X minutes/days/weeks/months
    time = Column(Time, nullable=True)  # Time of day (for daily/weekly/monthly, not needed for minute)
    day_of_week = Column(Integer, nullable=True)  # 0-6 for weekly (0=Monday, 6=Sunday)
    day_of_month = Column(Integer, nullable=True)  # 1-31 for monthly
    timezone = Column(String(100), default="UTC")  # Timezone for the schedule
    enabled = Column(Boolean, default=True)  # Whether the schedule is active
    rq_job_id = Column(String(255), nullable=True)  # RQ Scheduler job ID for tracking
    options = Column(JSONB, nullable=True)  # Additional options (e.g., export settings)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LowStockAlert(Base):
    __tablename__ = "low_stock_alerts"

    id = Column(Integer, primary_key=True, index=True)
    feature = Column(String(100), nullable=False, default="inventory_data")
    name = Column(String(255), nullable=False)
    period = Column(String(50), nullable=False)  # "minute", "daily", "weekly", "monthly"
    frequency = Column(Integer, default=1)
    time = Column(Time, nullable=True)
    day_of_week = Column(Integer, nullable=True)  # 0-6 for weekly (0=Monday, 6=Sunday)
    day_of_month = Column(Integer, nullable=True)  # 1-31 for monthly
    timezone = Column(String(100), default="UTC")
    enabled = Column(Boolean, default=True)
    rq_job_id = Column(String(255), nullable=True)
    rq_job_ids = Column(JSONB, nullable=True)  # RQ Scheduler job IDs (multiple for daily times)
    threshold = Column(Integer, nullable=False, default=0)  # Legacy fallback
    klb_threshold = Column(Integer, nullable=True)
    shipbob_threshold = Column(Integer, nullable=True)
    slack_webhook_url = Column(String(500), nullable=False)
    excluded_skus = Column(JSONB, nullable=True)  # List of SKU strings to skip
    times = Column(JSONB, nullable=True)  # Daily run times, e.g. ["09:00", "18:00"]

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
