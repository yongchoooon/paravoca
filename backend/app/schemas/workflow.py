from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class WorkflowRunInput(BaseModel):
    message: str
    region: str | None = None
    period: str | None = None
    target_customer: str | None = None
    product_count: int = Field(default=3, ge=1, le=20)
    preferences: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    output_language: Literal["ko", "en"] = "ko"

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            return None
        if not PERIOD_PATTERN.fullmatch(normalized):
            raise ValueError("period must use YYYY-MM format")
        return normalized


class WorkflowRunCreate(BaseModel):
    template_id: str = "default_product_planning"
    input: WorkflowRunInput


class WorkflowRevisionCreate(BaseModel):
    revision_mode: Literal["manual_save", "manual_edit", "llm_partial_rewrite", "qa_only"]
    comment: str | None = Field(default=None, max_length=2000)
    requested_changes: list[str] = Field(default_factory=list)
    qa_issues: list[dict[str, Any]] = Field(default_factory=list)
    qa_settings: dict[str, Any] = Field(default_factory=dict)
    products: list[dict[str, Any]] | None = None
    marketing_assets: list[dict[str, Any]] | None = None


class QAIssueDeleteRequest(BaseModel):
    issue_indices: list[int] = Field(default_factory=list)


class WorkflowRunDeleteRequest(BaseModel):
    run_ids: list[str] = Field(default_factory=list, min_length=1)


class WorkflowRunDeleteResult(BaseModel):
    deleted_run_ids: list[str]
    deleted_count: int


class WorkflowTemplateRead(BaseModel):
    id: str
    name: str
    description: str
    version: int
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunRead(BaseModel):
    id: str
    template_id: str
    parent_run_id: str | None = None
    revision_number: int = 0
    revision_mode: str | None = None
    status: str
    input: dict[str, Any]
    normalized_input: dict[str, Any] | None = None
    final_output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    cost_total_usd: float = 0
    latency_ms: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class AgentStepRead(BaseModel):
    id: str
    run_id: str
    agent_name: str
    step_type: str
    status: str
    input: Any
    output: Any | None = None
    error: dict[str, Any] | None = None
    prompt_version: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class ToolCallRead(BaseModel):
    id: str
    run_id: str
    step_id: str | None = None
    tool_name: str
    status: str
    arguments: dict[str, Any]
    response_summary: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    source: str | None = None
    latency_ms: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LLMCallRead(BaseModel):
    id: str
    run_id: str
    step_id: str | None = None
    provider: str
    model: str
    purpose: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float = 0
    latency_ms: int | None = None
    cache_hit: bool
    request_hash: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalActionRequest(BaseModel):
    reviewer: str = Field(default="operator", min_length=1, max_length=120)
    comment: str | None = Field(default=None, max_length=2000)
    high_risk_override: bool = False
    requested_changes: list[str] = Field(default_factory=list)


class ApprovalRead(BaseModel):
    id: str
    run_id: str
    decision: str
    reviewer: str
    comment: str | None = None
    approval_metadata: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
