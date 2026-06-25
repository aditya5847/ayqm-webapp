from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_path: Path = Field(default=Path("data/ayqm.duckdb"), alias="AYQM_DATABASE_PATH")
    upload_root: Path = Field(default=Path("data/uploads"), alias="AYQM_UPLOAD_ROOT")
    episode_root: Path = Field(default=Path("data/episodes"), alias="AYQM_EPISODE_ROOT")
    whisper_model: str = Field(default="base", alias="AYQM_WHISPER_MODEL")
    whisper_device: str = Field(default="cpu", alias="AYQM_WHISPER_DEVICE")
    whisper_compute_type: str = Field(default="int8", alias="AYQM_WHISPER_COMPUTE_TYPE")
    whisper_batch_size: int = Field(default=16, alias="AYQM_WHISPER_BATCH_SIZE")
    gemini_model: str | None = Field(default=None, alias="AYQM_GEMINI_MODEL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def ensure_storage(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.episode_root.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()

