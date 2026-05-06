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

