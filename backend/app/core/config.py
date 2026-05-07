from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PARAVOCA AX Agent Studio"
    app_description: str = (
        "AI workflow system for turning public tourism data into launch-ready "
        "travel product drafts with evidence, QA review, and human approval."
    )
    app_version: str = "0.1.0"
    app_env: str = "local"
    database_url: str = "sqlite:///./data/paravoca.db"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )
    vector_db: str = "chroma"
    chroma_path: str = "./data/chroma"
    tourapi_enabled: bool = True
    tourapi_service_key: str | None = None
    tourapi_base_url: str = "https://apis.data.go.kr/B551011/KorService2"
    tourapi_detail_enrichment_limit: int = 5
    kto_photo_contest_enabled: bool = False
    kto_wellness_enabled: bool = False
    kto_pet_enabled: bool = False
    kto_durunubi_enabled: bool = False
    kto_audio_enabled: bool = False
    kto_eco_enabled: bool = False
    kto_tourism_photo_enabled: bool = False
    kto_bigdata_enabled: bool = False
    kto_crowding_enabled: bool = False
    kto_related_places_enabled: bool = False
    allow_medical_api: bool = False
    official_web_search_enabled: bool = False
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
