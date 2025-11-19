from pydantic import BaseModel


class SalesTaxOptions(BaseModel):
    woo: bool = True
    braintree: bool = True
    tax_diff: bool = True
    totals_diff: bool = True


class UploadResponse(BaseModel):
    job_id: int
