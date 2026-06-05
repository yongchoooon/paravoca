from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


PosterStylePreset = Literal["editorial_travel", "night_city", "minimal_event"]
PosterIncludedSection = Literal[
    "product_summary",
    "itinerary",
    "marketing_copy",
    "target_segment",
    "key_selling_points",
    "landing_outline",
    "faq_strategy",
    "sns_copy",
    "usable_claims",
    "evidence_summary",
    "claim_limits",
]


class PosterCreateRequest(BaseModel):
    style_preset: PosterStylePreset
    included_sections: list[PosterIncludedSection] = Field(default_factory=list)
    input_images: list[str] = Field(default_factory=list)

    @field_validator("included_sections")
    @classmethod
    def dedupe_sections(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            if item in seen:
                continue
            seen.add(item)
            result.append(item)
        return result

    @field_validator("input_images")
    @classmethod
    def validate_input_images(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        if len(result) > 3:
            raise ValueError("입력 이미지는 최대 3개까지만 제공할 수 있습니다.")
        return result


class PosterStylePresetRead(BaseModel):
    id: str
    label: str
    description: str


class PosterAssetRead(BaseModel):
    id: str
    run_id: str
    product_id: str
    product_title: str
    style_preset: str
    included_sections: list[str]
    input_images: list[str] = Field(default_factory=list)
    prompt: str
    prompt_language: str
    image_model: str
    image_size: str
    image_quality: str
    image_path: str | None = None
    image_url: str | None = None
    provider: str
    provider_response_summary: dict[str, Any]
    cost_usd: float = 0
    latency_ms: int | None = None
    status: str
    error: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PosterStudioOptions(BaseModel):
    style_presets: list[PosterStylePresetRead]
    default_included_sections: list[str]
    image_size: str
    image_quality: str
    image_model: str
    usd_krw_rate: float
    max_posters_per_product: int


class PosterDeleteResult(BaseModel):
    deleted_poster_id: str
    deleted_image_path: str | None = None
