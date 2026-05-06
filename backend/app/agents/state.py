from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    run_id: str
    user_request: dict[str, Any]
    normalized_request: dict[str, Any]
    plan: list[dict[str, Any]]
    source_items: list[dict[str, Any]]
    retrieved_documents: list[dict[str, Any]]
    research_summary: dict[str, Any]
    product_ideas: list[dict[str, Any]]
    marketing_assets: list[dict[str, Any]]
    qa_report: dict[str, Any]
    approval: dict[str, Any] | None
    final_report: dict[str, Any] | None
    errors: list[dict[str, Any]]
    cost_summary: dict[str, Any]
    agent_execution: list[dict[str, Any]]
