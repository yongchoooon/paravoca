from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RagSearchRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=10, ge=1, le=50)


class RagIngestResponse(BaseModel):
    source_documents: int
    indexed_documents: int

