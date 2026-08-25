from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FasTicket FastAPI Backend"
    app_env: str = "local"

    database_url: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    password_reset_token_expire_minutes: int = 60

    cors_allowed_origins: list[str] = ["*"]

    pagination_limit: int = 15
    # per_page=-1 ("give me everything") is clamped to this instead of being truly unbounded —
    # at a million-row table, no limit at all means loading every row into memory in one request.
    pagination_max_limit: int = 1000

    redis_url: str = "redis://127.0.0.1:6379/0"

    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    mail_from_address: str = "no-reply@fasticket.test"
    mail_from_name: str = "FasTicket"

    frontend_url: str = "http://localhost:3000"

    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    aws_root: str = ""
    aws_bucket: str = ""
    aws_bucket_private: str = ""
    s3_endpoint_url: str = ""
    presigned_upload_url_expire_seconds: int = 300
    presigned_download_url_expire_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
