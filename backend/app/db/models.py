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
