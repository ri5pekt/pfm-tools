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
