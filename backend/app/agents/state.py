from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    run_id: str
    user_request: dict[str, Any]
    normalized_request: dict[str, Any]
    geo_scope: dict[str, Any]
    plan: list[dict[str, Any]]
    source_items: list[dict[str, Any]]
    candidate_pool_summary: dict[str, Any]
    retrieved_documents: list[dict[str, Any]]
    data_gap_report: dict[str, Any]
    capability_routing: dict[str, Any]
    enrichment_plan_fragments: list[dict[str, Any]]
    enrichment_plan: dict[str, Any]
    enrichment_summary: dict[str, Any]
    evidence_profile: dict[str, Any]
    productization_advice: dict[str, Any]
    data_coverage: dict[str, Any]
    unresolved_gaps: list[dict[str, Any]]
    source_confidence: float
    ui_highlights: list[dict[str, Any]]
    research_summary: dict[str, Any]
    product_ideas: list[dict[str, Any]]
    marketing_assets: list[dict[str, Any]]
    qa_report: dict[str, Any]
    approval: dict[str, Any] | None
    final_report: dict[str, Any] | None
    run_status: str
    errors: list[dict[str, Any]]
    cost_summary: dict[str, Any]
    agent_execution: list[dict[str, Any]]
