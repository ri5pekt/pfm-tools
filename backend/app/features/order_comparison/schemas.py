from pydantic import BaseModel
from typing import Optional


class UploadResponse(BaseModel):
    job_id: int


class ComparisonOptions(BaseModel):
    order_id_header: str
    date_from: str
    date_to: str

