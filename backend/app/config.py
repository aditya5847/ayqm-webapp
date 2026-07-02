from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: Literal["local", "test", "production"] = Field(default="local", alias="AYQM_ENVIRONMENT")
    database_path: Path = Field(default=Path("data/ayqm.duckdb"), alias="AYQM_DATABASE_PATH")
    upload_root: Path = Field(default=Path("data/uploads"), alias="AYQM_UPLOAD_ROOT")
    episode_root: Path = Field(default=Path("data/episodes"), alias="AYQM_EPISODE_ROOT")
    whisper_model: str = Field(default="base", alias="AYQM_WHISPER_MODEL")
    whisper_device: str = Field(default="cpu", alias="AYQM_WHISPER_DEVICE")
    whisper_compute_type: str = Field(default="int8", alias="AYQM_WHISPER_COMPUTE_TYPE")
    whisper_batch_size: int = Field(default=16, alias="AYQM_WHISPER_BATCH_SIZE")
    gemini_model: str | None = Field(default=None, alias="AYQM_GEMINI_MODEL")
    ffmpeg_path: str = Field(default="ffmpeg", alias="AYQM_FFMPEG_PATH")
    admin_password_hash: str | None = Field(default=None, alias="AYQM_ADMIN_PASSWORD_HASH")
    session_secret: str | None = Field(default=None, alias="AYQM_SESSION_SECRET")
    session_cookie_secure: bool = Field(default=False, alias="AYQM_SESSION_COOKIE_SECURE")
    session_max_age_seconds: int = Field(default=604800, alias="AYQM_SESSION_MAX_AGE_SECONDS", ge=60)
    allowed_origins: str = Field(default="http://localhost:5173", alias="AYQM_ALLOWED_ORIGINS")
    external_transcription_worker: bool = Field(default=False, alias="AYQM_EXTERNAL_TRANSCRIPTION_WORKER")
    worker_token: str | None = Field(default=None, alias="AYQM_WORKER_TOKEN")
    worker_lease_seconds: int = Field(default=900, alias="AYQM_WORKER_LEASE_SECONDS", ge=60)
    storage_backend: Literal["local", "r2"] = Field(default="local", alias="AYQM_STORAGE_BACKEND")
    r2_endpoint_url: str | None = Field(default=None, alias="AYQM_R2_ENDPOINT_URL")
    r2_bucket: str | None = Field(default=None, alias="AYQM_R2_BUCKET")
    r2_access_key_id: str | None = Field(default=None, alias="AYQM_R2_ACCESS_KEY_ID")
    r2_secret_access_key: str | None = Field(default=None, alias="AYQM_R2_SECRET_ACCESS_KEY")
    rss_feed_url: str = Field(
        default="https://anchor.fm/s/d7afa960/podcast/rss",
        alias="AYQM_RSS_FEED_URL",
    )
    backup_enabled: bool = Field(default=False, alias="AYQM_BACKUP_ENABLED")
    backup_hour_utc: int = Field(default=2, alias="AYQM_BACKUP_HOUR_UTC", ge=0, le=23)
    gemini_historical_budget_usd: float = Field(default=5.0, alias="AYQM_GEMINI_BUDGET_USD", gt=0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def ensure_storage(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.episode_root.mkdir(parents=True, exist_ok=True)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    def validate_runtime(self) -> None:
        if self.environment != "production":
            return
        missing: list[str] = []
        if not self.admin_password_hash:
            missing.append("AYQM_ADMIN_PASSWORD_HASH")
        if not self.session_secret:
            missing.append("AYQM_SESSION_SECRET")
        if not self.session_cookie_secure:
            missing.append("AYQM_SESSION_COOKIE_SECURE=true")
        if self.external_transcription_worker and not self.worker_token:
            missing.append("AYQM_WORKER_TOKEN")
        if self.storage_backend == "r2":
            for field_name, value in (
                ("AYQM_R2_ENDPOINT_URL", self.r2_endpoint_url),
                ("AYQM_R2_BUCKET", self.r2_bucket),
                ("AYQM_R2_ACCESS_KEY_ID", self.r2_access_key_id),
                ("AYQM_R2_SECRET_ACCESS_KEY", self.r2_secret_access_key),
            ):
                if not value:
                    missing.append(field_name)
        if missing:
            raise RuntimeError(f"Missing production configuration: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
