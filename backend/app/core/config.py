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
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32
    tourapi_enabled: bool = True
    tourapi_service_key: str | None = None
    tourapi_base_url: str = "https://apis.data.go.kr/B551011/KorService2"
    tourapi_timeout_seconds: float = 20.0
    tourapi_max_retries: int = 2
    tourapi_retry_base_seconds: float = 0.8
    tourapi_retry_max_seconds: float = 4.0
    tourapi_detail_enrichment_limit: int = 5
    tourapi_candidate_shortlist_limit: int = 20
    enrichment_max_call_budget: int = 6
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
    kto_regional_tourism_demand_enabled: bool = False
    allow_medical_api: bool = False
    official_web_search_enabled: bool = False
    openai_api_key: str | None = None
    poster_asset_dir: str = "data/poster_assets"
    poster_image_model: str = "gpt-image-2"
    poster_image_size: str = "1024x1536"
    poster_image_quality: str = "medium"
    poster_image_timeout_seconds: float = 120.0
    poster_image_estimated_cost_usd: float = 0
    poster_text_input_cost_per_million_tokens_usd: float = 5.0
    poster_text_cached_input_cost_per_million_tokens_usd: float = 1.25
    poster_image_input_cost_per_million_tokens_usd: float = 8.0
    poster_image_cached_input_cost_per_million_tokens_usd: float = 2.0
    poster_image_output_cost_per_million_tokens_usd: float = 30.0
    poster_usage_log_dir: str = "logs"
    poster_prompt_log_dir: str = "logs/poster_prompts"
    gemini_api_key: str | None = None
    openai_check_model: str = "gpt-4.1-nano"
    gemini_check_model: str = "gemini-2.5-flash-lite"
    gemini_generation_model: str = "gemini-2.5-flash-lite"
    gemini_timeout_seconds: float = 60.0
    gemini_max_retries: int = 5
    gemini_json_max_retries: int = 2
    gemini_retry_base_seconds: float = 2.0
    gemini_retry_max_seconds: float = 30.0
    llm_usage_log_dir: str = "logs"
    llm_prompt_debug_log_enabled: bool = False
    llm_prompt_debug_log_dir: str = "logs/prompt_debug"
    app_log_dir: str = "logs"
    evaluation_report_dir: str = "reports/evaluations"
    usd_krw_rate: float = 1490

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
