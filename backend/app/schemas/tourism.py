from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TourismSearchQuery(BaseModel):
    region: str | None = None
    region_code: str | None = None
    keyword: str | None = None
    content_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    run_id: str | None = None
    limit: int = Field(default=20, ge=1, le=50)


class TourismItemRead(BaseModel):
    id: str
    source: str
    content_id: str
    content_type: str
    title: str
    region_code: str
    sigungu_code: str | None = None
    address: str | None = None
    map_x: float | None = None
    map_y: float | None = None
    tel: str | None = None
    homepage: str | None = None
    overview: str | None = None
    image_url: str | None = None
    license_type: str | None = None
    event_start_date: str | None = None
    event_end_date: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class TourismEntityRead(BaseModel):
    id: str
    canonical_name: str
    entity_type: str
    region_code: str | None = None
    sigungu_code: str | None = None
    address: str | None = None
    map_x: float | None = None
    map_y: float | None = None
    primary_source_item_id: str | None = None
    match_confidence: float | None = None
    entity_metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class TourismVisualAssetRead(BaseModel):
    id: str
    entity_id: str | None = None
    source_family: str
    source_item_id: str | None = None
    title: str | None = None
    image_url: str
    thumbnail_url: str | None = None
    shooting_place: str | None = None
    shooting_date: str | None = None
    photographer: str | None = None
    keywords: list[str] = Field(default_factory=list)
    license_type: str | None = None
    license_note: str | None = None
    usage_status: str
    raw: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class TourismDetailEnrichmentRequest(BaseModel):
    item_ids: list[str] = Field(default_factory=list)
    content_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class TourismDetailEnrichmentResult(BaseModel):
    items: list[TourismItemRead]
    entities: list[TourismEntityRead]
    visual_assets: list[TourismVisualAssetRead]
    source_documents: int
    indexed_documents: int
    summary: dict[str, Any]
