# backend/app/core/config.py

from functools import lru_cache
from typing import Any, List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator


class Settings(BaseSettings):
    # Required
    secret_key: str
    database_url: str
    redis_url: str

    # CORS origins can be:
    # - comma-separated string
    # - JSON list string
    # - actual list
    backend_cors_origins: Optional[List[AnyHttpUrl]] | Optional[List[str]] = None

    # Auth config
    access_token_expires_minutes: int = 60 * 24  # 24 hours
    algorithm: str = "HS256"  # JWT algorithm

    # File storage paths
    data_dir: str = "/data"
    uploads_dir: str = "/data/uploads"
    processed_dir: str = "/data/processed"

    # File upload limits
    max_upload_size_mb: int = 500  # Maximum file size in MB

    # Redis Queue config
    rq_default_queue: str = "pfmtools"  # Default RQ queue name

    # WooCommerce API config (optional)
    woo_base_url: Optional[str] = None
    woo_consumer_key: Optional[str] = None
    woo_consumer_secret: Optional[str] = None

    # Braintree API config (optional)
    braintree_merchant_id: Optional[str] = None
    braintree_public_key: Optional[str] = None
    braintree_private_key: Optional[str] = None
    braintree_environment: str = "production"  # "production" or "sandbox"

    # AfterShip API config (optional)
    aftership_username: Optional[str] = None
    aftership_password: Optional[str] = None
    aftership_base_url: Optional[str] = None

    # Ulta Marketplace API config (optional)
    ulta_api_key: Optional[str] = None

    # TikTok Marketplace API config (optional)
    tiktok_api_key: Optional[str] = None

    # Order Desk API config (for TikTok Marketplace integration)
    orderdesk_store_id: Optional[str] = None
    orderdesk_api_key: Optional[str] = None
    orderdesk_base_url: str = "https://app.orderdesk.me/api/v2"

    # Zenventory API config (optional)
    zenventory_klb_username: Optional[str] = None
    zenventory_klb_password: Optional[str] = None
    zenventory_klb_base_url: Optional[str] = "https://app.zenventory.com/rest/inventory"

    # Shipbob API config (optional)
    shipbob_api_key: Optional[str] = None
    shipbob_base_url: Optional[str] = "https://api.shipbob.com/2025-07"

    # Google Sheets API config (optional)
    # OAuth 2.0 credentials (for organization projects that don't allow service account keys)
    google_sheets_oauth_credentials_path: Optional[str] = None  # Path to OAuth client credentials JSON file
    google_sheets_oauth_token_path: Optional[str] = None  # Path to saved OAuth token (created by setup script)
    # Service account (alternative - if your org allows service account keys)
    google_sheets_service_account_path: Optional[str] = None  # Path to service account JSON file
    # Spreadsheet settings (supports both GOOGLE_SHEETS_* and ULTA_GOOGLE_SHEETS_* prefixes)
    google_sheets_spreadsheet_id: Optional[str] = None  # Google Sheets spreadsheet ID
    google_sheets_sheet_name: Optional[str] = "Ulta Exports"  # Default sheet name
    # Alternative naming with ULTA_ prefix (for backward compatibility)
    ulta_google_sheets_spreadsheet_id: Optional[str] = None  # Alternative: ULTA_GOOGLE_SHEETS_SPREADSHEET_ID
    ulta_google_sheets_sheet_name: Optional[str] = None  # Alternative: ULTA_GOOGLE_SHEETS_SHEET_NAME
    # Inventory Data specific spreadsheet ID
    inventory_google_sheets_spreadsheet_id: Optional[str] = None  # Inventory Data Google Sheets spreadsheet ID
    # Daily Orders Data specific spreadsheet ID
    daily_orders_google_sheets_spreadsheet_id: Optional[str] = None  # Daily Orders Data Google Sheets spreadsheet ID
    # TikTok Marketplace specific spreadsheet ID
    tiktok_google_sheets_spreadsheet_id: Optional[str] = None  # TikTok Marketplace Google Sheets spreadsheet ID
    tiktok_google_sheets_sheet_name: Optional[str] = "TikTok Exports"  # TikTok Marketplace Google Sheets sheet name

    # Where to read env vars from
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> Optional[List[str]]:
        """
        Accept:
        - 'http://a,http://b'
        - '["http://a", "http://b"]'
        - list(...)
        """
        if v is None or v == "":
            return None

        if isinstance(v, list):
            return [str(i) for i in v]

        if isinstance(v, str):
            v = v.strip()
            # JSON-style list
            if v.startswith("[") and v.endswith("]"):
                import json

                try:
                    data = json.loads(v)
                    return [str(i) for i in data]
                except Exception:
                    # fall through to comma parsing
                    pass

            # Comma-separated string
            return [i.strip() for i in v.split(",") if i.strip()]

        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
