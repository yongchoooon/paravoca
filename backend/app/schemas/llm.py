from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LLMKeyCheckRequest(BaseModel):
    providers: list[Literal["openai", "gemini"]] = Field(
        default_factory=lambda: ["gemini"]
    )
    max_output_tokens: int = Field(default=16, ge=1, le=32)
