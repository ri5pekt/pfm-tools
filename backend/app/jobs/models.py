from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text
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
