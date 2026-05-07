from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.timezone import now_kst_naive


def utcnow() -> datetime:
    return now_kst_naive()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    nodes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    edges: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="template")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(
        String(120), primary_key=True, default=lambda: new_id("run")
    )
    template_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("workflow_templates.id"), nullable=False
    )
    parent_run_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("workflow_runs.id"), nullable=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revision_mode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    input: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    normalized_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_total_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    template: Mapped[WorkflowTemplate] = relationship(back_populates="runs")
    steps: Mapped[list["AgentStep"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    llm_calls: Mapped[list["LLMCall"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    enrichment_runs: Mapped[list["EnrichmentRun"]] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan"
    )
    web_evidence_documents: Mapped[list["WebEvidenceDocument"]] = relationship(
        back_populates="workflow_run", cascade="all, delete-orphan"
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"

    id: Mapped[str] = mapped_column(
        String(120), primary_key=True, default=lambda: new_id("step")
    )
    run_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("workflow_runs.id"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    step_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    input: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped[WorkflowRun] = relationship(back_populates="steps")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(
        String(120), primary_key=True, default=lambda: new_id("tool")
    )
    run_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("workflow_runs.id"), nullable=False
    )
    step_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("agent_steps.id"), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="started", nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    response_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    run: Mapped[WorkflowRun] = relationship(back_populates="tool_calls")


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(
        String(120), primary_key=True, default=lambda: new_id("llm")
    )
    run_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("workflow_runs.id"), nullable=False
    )
    step_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("agent_steps.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(80), default="rule_based", nullable=False)
    model: Mapped[str] = mapped_column(String(160), default="rule-based-v1", nullable=False)
    purpose: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    run: Mapped[WorkflowRun] = relationship(back_populates="llm_calls")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(
        String(120), primary_key=True, default=lambda: new_id("approval")
    )
    run_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("workflow_runs.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(120), default="operator", nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    run: Mapped[WorkflowRun] = relationship(back_populates="approvals")


class TourismItem(Base):
    __tablename__ = "tourism_items"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    content_id: Mapped[str] = mapped_column(String(120), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    region_code: Mapped[str] = mapped_column(String(40), nullable=False)
    sigungu_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    map_x: Mapped[float | None] = mapped_column(Numeric(12, 7), nullable=True)
    map_y: Mapped[float | None] = mapped_column(Numeric(12, 7), nullable=True)
    tel: Mapped[str | None] = mapped_column(String(120), nullable=True)
    homepage: Mapped[str | None] = mapped_column(Text, nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    event_end_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    document_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    embedding_status: Mapped[str] = mapped_column(
        String(40), default="pending", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class TourismEntity(Base):
    __tablename__ = "tourism_entities"

    id: Mapped[str] = mapped_column(
        String(160), primary_key=True, default=lambda: new_id("entity")
    )
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sigungu_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    map_x: Mapped[float | None] = mapped_column(Numeric(12, 7), nullable=True)
    map_y: Mapped[float | None] = mapped_column(Numeric(12, 7), nullable=True)
    primary_source_item_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    entity_metadata: Mapped[dict] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    visual_assets: Mapped[list["TourismVisualAsset"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    route_assets: Mapped[list["TourismRouteAsset"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    signal_records: Mapped[list["TourismSignalRecord"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    web_evidence_documents: Mapped[list["WebEvidenceDocument"]] = relationship(
        back_populates="entity"
    )


class TourismVisualAsset(Base):
    __tablename__ = "tourism_visual_assets"

    id: Mapped[str] = mapped_column(
        String(160), primary_key=True, default=lambda: new_id("visual")
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(160), ForeignKey("tourism_entities.id"), nullable=True
    )
    source_family: Mapped[str] = mapped_column(String(120), nullable=False)
    source_item_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    shooting_place: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shooting_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    photographer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    license_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    license_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_status: Mapped[str] = mapped_column(
        String(60), default="candidate", nullable=False
    )
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    entity: Mapped[TourismEntity | None] = relationship(back_populates="visual_assets")


class TourismRouteAsset(Base):
    __tablename__ = "tourism_route_assets"

    id: Mapped[str] = mapped_column(
        String(160), primary_key=True, default=lambda: new_id("route")
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(160), ForeignKey("tourism_entities.id"), nullable=True
    )
    source_family: Mapped[str] = mapped_column(String(120), nullable=False)
    course_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    path_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gpx_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Numeric(8, 3), nullable=True)
    estimated_duration: Mapped[str | None] = mapped_column(String(120), nullable=True)
    start_point: Mapped[str | None] = mapped_column(String(255), nullable=True)
    end_point: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nearby_places: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    safety_notes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    entity: Mapped[TourismEntity | None] = relationship(back_populates="route_assets")


class TourismSignalRecord(Base):
    __tablename__ = "tourism_signal_records"

    id: Mapped[str] = mapped_column(
        String(160), primary_key=True, default=lambda: new_id("signal")
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(160), ForeignKey("tourism_entities.id"), nullable=True
    )
    region_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sigungu_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_family: Mapped[str] = mapped_column(String(120), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[str | None] = mapped_column(String(40), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(40), nullable=True)
    value: Mapped[dict] = mapped_column("value_json", JSON, default=dict, nullable=False)
    interpretation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    entity: Mapped[TourismEntity | None] = relationship(back_populates="signal_records")


class EnrichmentRun(Base):
    __tablename__ = "enrichment_runs"

    id: Mapped[str] = mapped_column(
        String(160), primary_key=True, default=lambda: new_id("enrich")
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("workflow_runs.id"), nullable=True
    )
    trigger_type: Mapped[str] = mapped_column(String(80), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="planned", nullable=False)
    gap_report: Mapped[dict] = mapped_column("gap_report_json", JSON, default=dict, nullable=False)
    plan: Mapped[dict] = mapped_column("plan_json", JSON, default=dict, nullable=False)
    result_summary: Mapped[dict] = mapped_column(
        "result_summary_json", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workflow_run: Mapped[WorkflowRun | None] = relationship(back_populates="enrichment_runs")
    tool_calls: Mapped[list["EnrichmentToolCall"]] = relationship(
        back_populates="enrichment_run", cascade="all, delete-orphan"
    )


class EnrichmentToolCall(Base):
    __tablename__ = "enrichment_tool_calls"

    id: Mapped[str] = mapped_column(
        String(160), primary_key=True, default=lambda: new_id("enrich_tool")
    )
    enrichment_run_id: Mapped[str | None] = mapped_column(
        String(160), ForeignKey("enrichment_runs.id"), nullable=True
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("workflow_runs.id"), nullable=True
    )
    plan_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_family: Mapped[str] = mapped_column(String(120), nullable=False)
    arguments: Mapped[dict] = mapped_column("arguments_json", JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="planned", nullable=False)
    response_summary: Mapped[dict | None] = mapped_column(
        "response_summary_json", JSON, nullable=True
    )
    error: Mapped[dict | None] = mapped_column("error_json", JSON, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    enrichment_run: Mapped[EnrichmentRun | None] = relationship(back_populates="tool_calls")


class WebEvidenceDocument(Base):
    __tablename__ = "web_evidence_documents"

    id: Mapped[str] = mapped_column(
        String(160), primary_key=True, default=lambda: new_id("web_ev")
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(120), ForeignKey("workflow_runs.id"), nullable=True
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(160), ForeignKey("tourism_entities.id"), nullable=True
    )
    field_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="candidate", nullable=False)
    source_type: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    raw: Mapped[dict] = mapped_column("raw_json", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    workflow_run: Mapped[WorkflowRun | None] = relationship(
        back_populates="web_evidence_documents"
    )
    entity: Mapped[TourismEntity | None] = relationship(
        back_populates="web_evidence_documents"
    )
