from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TravelOps AX Agent Studio"
    app_description: str = (
        "AI workflow system for turning public tourism data into launch-ready "
        "travel product drafts with evidence, QA review, and human approval."
    )
    app_version: str = "0.1.0"
    app_env: str = "local"
    database_url: str = "sqlite:///./data/travelops.db"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )
    vector_db: str = "chroma"
    chroma_path: str = "./data/chroma"
    tourapi_service_key: str | None = None
    tourapi_base_url: str = "https://apis.data.go.kr/B551011/KorService2"
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_check_model: str = "gpt-4.1-nano"
    gemini_check_model: str = "gemini-2.5-flash-lite"
    gemini_generation_model: str = "gemini-2.5-flash-lite"
    gemini_max_retries: int = 3
    gemini_json_max_retries: int = 2
    gemini_retry_base_seconds: float = 1.5
    gemini_retry_max_seconds: float = 12.0
    llm_enabled: bool = False
    llm_usage_log_dir: str = "logs"
    app_log_dir: str = "logs"
    usd_krw_rate: float = 1400

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlite_path(self) -> Path | None:
        if not self.database_url.startswith("sqlite:///"):
            return None
        raw_path = self.database_url.replace("sqlite:///", "", 1)
        return Path(raw_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
