from __future__ import annotations

import json
import logging
import hashlib
import re
import time
from contextlib import contextmanager
from datetime import date
from typing import Any

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.agents.geo_resolver import load_ldong_catalog, resolve_geo_scope, save_geo_resolution
from app.agents.state import GraphState
from app.agents.data_enrichment import (
    API_CAPABILITY_ROUTING_RESPONSE_SCHEMA,
    DATA_GAP_PROFILE_REF_RESPONSE_SCHEMA,
    DATA_GAP_PROFILE_RESPONSE_SCHEMA,
    EVIDENCE_FUSION_RESPONSE_SCHEMA,
    API_FAMILY_PLANNER_RESPONSE_SCHEMA,
    ROUTE_SIGNAL_SOURCE_FAMILIES,
    THEME_SOURCE_FAMILIES,
    TOURAPI_DETAIL_PLANNER_RESPONSE_SCHEMA,
    VISUAL_SOURCE_FAMILIES,
    build_api_capability_router_prompt,
    build_api_family_planner_prompt,
    build_data_gap_profile_prompt,
    build_evidence_fusion_prompt,
    build_gap_inventory,
    build_tourapi_detail_planner_prompt,
    capability_brief_for_prompt,
    capability_matrix_for_prompt,
    count_tourapi_detail_targets,
    create_enrichment_run,
    execute_enrichment_plan,
    fuse_evidence,
    normalize_evidence_fusion_payload,
    normalize_family_planner_payload,
    normalize_family_routing_payload,
    normalize_gap_profile_payload,
    normalize_tourapi_detail_planner_payload,
    merge_enrichment_plan_fragments,
    select_enrichment_candidate_items,
    summarize_candidate_pool,
    PLANNER_DEFINITIONS,
)
from app.core.config import get_settings
from app.db import models
from app.llm.gemini_gateway import GeminiGatewayError, GeminiJsonResult, call_gemini_json
from app.rag.chroma_store import index_source_documents, search_source_documents_with_diagnostics
from app.rag.source_documents import SOURCE_ROLE_RUNTIME, upsert_source_documents_from_items
from app.tools.tourism import get_tourism_provider, log_tool_call, upsert_tourism_items
from app.agents.run_cancellation import clear_run_cancellation, is_run_cancellation_requested


logger = logging.getLogger("uvicorn.error")

MAX_PRODUCT_COUNT = 20

REMOVED_MARKETING_STRATEGY_FIELDS = {
    "reasons_to_believe",
    "recommended_sales_angle",
    "experience_story",
    "conversion_cta",
    "needs_confirmation",
    "avoid_phrasing",
    "safe_alternatives",
}

MARKETING_FIELD_PARENT_PATCHES = {
    "faq",
    "search_keywords",
    "sales_copy.sections",
    "marketing_strategy.key_selling_points",
    "marketing_strategy.customer_objections",
    "marketing_strategy.operation_checklist",
    "landing_page_outline.why_this_product",
    "landing_page_outline.evidence_backed_points",
    "landing_page_outline.practical_info",
    "faq_strategy.buyer_faq",
    "faq_strategy.operation_faq",
    "sns_campaign.campaign_angles",
    "sns_campaign.posts",
    "sns_campaign.visual_direction",
    "claim_strategy.usable_claims",
    "claim_strategy.caution_phrasing",
}


class WorkflowCancelled(RuntimeError):
    pass


def run_product_planning_workflow(db: Session, run_id: str) -> dict[str, Any]:
    run = _get_workflow_run(db, run_id)
    started = _start_run(db, run)
    graph = _build_graph(db)
    state = _initial_workflow_state(run)
    try:
        _raise_if_cancelled(db, run.id)
        final_state = graph.invoke(state)
    except WorkflowCancelled as exc:
        _cancel_run(db, run, started, exc)
        clear_run_cancellation(run.id)
        return run.final_output or {}
    except Exception as exc:
        if _is_run_cancelled(db, run.id):
            _cancel_run(db, run, started, WorkflowCancelled("사용자가 workflow 실행 중지를 요청했습니다."))
            clear_run_cancellation(run.id)
            return run.final_output or {}
        _fail_run(db, run, started, exc)
        clear_run_cancellation(run.id)
        raise
    final_report = _complete_run(db, run, started, final_state)
    clear_run_cancellation(run.id)
    return final_report


def run_revision_workflow(db: Session, run_id: str) -> dict[str, Any]:
    run = _get_workflow_run(db, run_id)
    context = _revision_context_from_run(run)
    mode = context["revision_mode"]
    started = _start_run(db, run)

    try:
        _raise_if_cancelled(db, run.id)
        if mode == "manual_save":
            final_state = _run_manual_save_revision(db, run, context)
        elif mode in {"manual_edit", "qa_only"}:
            final_state = _run_qa_only_revision(db, run, context)
        elif mode == "llm_partial_rewrite":
            final_state = _run_llm_partial_revision(db, run, context)
        else:
            raise ValueError(f"Unsupported revision_mode: {mode}")
    except WorkflowCancelled as exc:
        _cancel_run(db, run, started, exc)
        clear_run_cancellation(run.id)
        return run.final_output or {}
    except Exception as exc:
        if _is_run_cancelled(db, run.id):
            _cancel_run(db, run, started, WorkflowCancelled("사용자가 workflow 실행 중지를 요청했습니다."))
            clear_run_cancellation(run.id)
            return run.final_output or {}
        _fail_run(db, run, started, exc)
        clear_run_cancellation(run.id)
        raise
    final_report = _complete_run(db, run, started, final_state)
    clear_run_cancellation(run.id)
    return final_report


def _get_workflow_run(db: Session, run_id: str) -> models.WorkflowRun:
    run = db.get(models.WorkflowRun, run_id)
    if not run:
        raise ValueError(f"Workflow run not found: {run_id}")
    return run


def _start_run(db: Session, run: models.WorkflowRun) -> float:
    started = time.perf_counter()
    if run.status in {"cancelling", "cancelled"} or is_run_cancellation_requested(run.id):
        return started
    run.status = "running"
    run.started_at = models.utcnow()
    db.commit()
    return started


def _initial_workflow_state(run: models.WorkflowRun) -> GraphState:
    return {
        "run_id": run.id,
        "user_request": run.input,
        "errors": [],
        "agent_execution": [],
        "cost_summary": {"estimated_cost_usd": 0.0, "mode": "gemini"},
    }


def _fail_run(
    db: Session,
    run: models.WorkflowRun,
    started: float,
    exc: Exception,
) -> None:
    if _is_run_cancelled(db, run.id):
        _cancel_run(db, run, started, WorkflowCancelled("사용자가 workflow 실행 중지를 요청했습니다."))
        return
    run.status = "failed"
    run.error = {"type": exc.__class__.__name__, "message": str(exc)}
    _finish_run(db, run, started)


def _cancel_run(
    db: Session,
    run: models.WorkflowRun,
    started: float,
    exc: Exception,
) -> None:
    message = str(exc) or "사용자가 workflow 실행 중지를 요청했습니다."
    db.refresh(run)
    if run.status == "cancelled" and run.final_output:
        return
    run.status = "cancelled"
    run.error = {"type": exc.__class__.__name__, "message": message}
    if not run.final_output:
        run.final_output = {
            "status": "cancelled",
            "run_status": "cancelled",
            "reason": "user_cancelled",
            "normalized_request": run.normalized_input or {},
            "geo_scope": (run.normalized_input or {}).get("geo_scope") or {},
            "user_message": {
                "title": "실행이 중지되었습니다",
                "message": message,
                "detail": "이미 완료된 단계의 로그는 Developer 탭에서 확인할 수 있습니다.",
            },
            "source_items": [],
            "retrieved_documents": [],
            "products": [],
            "marketing_assets": [],
            "qa_report": {
                "overall_status": "not_run",
                "summary": "사용자 요청으로 실행이 중지되어 QA 검수를 실행하지 않았습니다.",
                "issues": [],
                "pass_count": 0,
                "needs_review_count": 0,
                "fail_count": 0,
            },
            "agent_execution": [],
            "cost_summary": _cost_summary(db, run.id),
            "approval": {
                "required": False,
                "status": "not_required",
                "message": message,
            },
        }
    db.add(
        models.AgentStep(
            run_id=run.id,
            agent_name="System",
            step_type="workflow_cancelled",
            status="succeeded",
            input={"run_id": run.id},
            output={"message": message},
            latency_ms=0,
            started_at=models.utcnow(),
            finished_at=models.utcnow(),
        )
    )
    _finish_run(db, run, started)


def _complete_run(
    db: Session,
    run: models.WorkflowRun,
    started: float,
    final_state: GraphState,
) -> dict[str, Any]:
    if _is_run_cancelled(db, run.id):
        db.refresh(run)
        return run.final_output or {}
    final_report = final_state.get("final_report") or {}
    run.status = str(final_state.get("run_status") or final_report.get("run_status") or "awaiting_approval")
    run.normalized_input = final_state.get("normalized_request")
    run.final_output = final_report
    _finish_run(db, run, started)
    return final_report


def _finish_run(db: Session, run: models.WorkflowRun, started: float) -> None:
    run.latency_ms = int((time.perf_counter() - started) * 1000)
    run.cost_total_usd = _cost_summary(db, run.id)["estimated_cost_usd"]
    run.finished_at = models.utcnow()
    db.commit()


def _run_qa_only_revision(
    db: Session,
    run: models.WorkflowRun,
    context: dict[str, Any],
) -> GraphState:
    source_output = context["source_final_output"]
    products = context.get("manual_products") or source_output.get("products") or []
    marketing_assets = context.get("manual_marketing_assets") or source_output.get("marketing_assets") or []
    if not products or not marketing_assets:
        raise ValueError("manual_edit/qa_only revision requires products and marketing_assets")

    state = _base_revision_state(run, context)
    products, source_stability = _preserve_revision_source_state(
        context,
        products,
        mode=str(context.get("revision_mode") or ""),
    )
    state.update(
        {
            "product_ideas": products,
            "marketing_assets": marketing_assets,
            "source_stability": source_stability,
        }
    )
    _revision_context_step(db, state, context)
    _raise_if_cancelled(db, run.id)
    if context.get("qa_issues"):
        state.update(targeted_revision_qa_agent(db, state))
    else:
        state.update(qa_agent(db, state))
    state.update(_revision_qa_diff_state(state))
    _raise_if_cancelled(db, run.id)
    state.update(human_approval_node(db, state))
    return state


def _run_manual_save_revision(
    db: Session,
    run: models.WorkflowRun,
    context: dict[str, Any],
) -> GraphState:
    source_output = context["source_final_output"]
    products = context.get("manual_products") or source_output.get("products") or []
    marketing_assets = context.get("manual_marketing_assets") or source_output.get("marketing_assets") or []
    if not products or not marketing_assets:
        raise ValueError("manual_save revision requires products and marketing_assets")

    state = _base_revision_state(run, context)
    products, source_stability = _preserve_revision_source_state(
        context,
        products,
        mode=str(context.get("revision_mode") or ""),
    )
    state.update(
        {
            "product_ideas": products,
            "marketing_assets": marketing_assets,
            "qa_report": source_output.get("qa_report") or {},
            "source_stability": source_stability,
        }
    )
    _revision_context_step(db, state, context)
    _raise_if_cancelled(db, run.id)
    state.update(human_approval_node(db, state))
    return state


def _run_llm_partial_revision(
    db: Session,
    run: models.WorkflowRun,
    context: dict[str, Any],
) -> GraphState:
    state = _base_revision_state(run, context)
    _revision_context_step(db, state, context)
    _raise_if_cancelled(db, run.id)
    state.update(revision_patch_agent(db, state))
    products, source_stability = _preserve_revision_source_state(
        context,
        state.get("product_ideas", []),
        mode="llm_partial_rewrite",
    )
    state.update({"product_ideas": products, "source_stability": source_stability})
    _raise_if_cancelled(db, run.id)
    if context.get("qa_issues"):
        state.update(targeted_revision_qa_agent(db, state))
    else:
        state.update(qa_agent(db, state))
    state.update(_revision_qa_diff_state(state))
    _raise_if_cancelled(db, run.id)
    state.update(human_approval_node(db, state))
    return state


def _base_revision_state(run: models.WorkflowRun, context: dict[str, Any]) -> GraphState:
    source_output = context["source_final_output"]
    normalized = dict(source_output.get("normalized_request") or {})
    normalized["revision_context"] = {
        "source_run_id": context["source_run_id"],
        "root_run_id": context.get("root_run_id") or context["source_run_id"],
        "revision_mode": context["revision_mode"],
        "revision_number": context["revision_number"],
        "requested_changes": context.get("requested_changes", []),
        "qa_issues": context.get("qa_issues", []),
        "qa_settings": context.get("qa_settings", {}),
        "review_comment": context.get("comment"),
        "approval_history": context.get("approval_history", []),
        "previous_products": source_output.get("products", []),
        "previous_marketing_assets": source_output.get("marketing_assets", []),
    }
    return {
        "run_id": run.id,
        "user_request": run.input,
        "normalized_request": normalized,
        "source_items": source_output.get("source_items", []),
        "candidate_pool_summary": source_output.get("candidate_pool_summary", {}),
        "retrieved_documents": source_output.get("retrieved_documents", []),
        "data_gap_report": source_output.get("data_gap_report", {}),
        "capability_routing": source_output.get("capability_routing", {}),
        "enrichment_plan_fragments": source_output.get("enrichment_plan_fragments", []),
        "enrichment_plan": source_output.get("enrichment_plan", {}),
        "enrichment_summary": source_output.get("enrichment_summary", {}),
        "evidence_profile": source_output.get("evidence_profile", {}),
        "productization_advice": source_output.get("productization_advice", {}),
        "data_coverage": source_output.get("data_coverage", {}),
        "unresolved_gaps": source_output.get("unresolved_gaps", []),
        "source_confidence": source_output.get("source_confidence", 0.0),
        "ui_highlights": source_output.get("ui_highlights", []),
        "research_summary": source_output.get("research_summary", {}),
        "errors": [],
        "agent_execution": [],
        "cost_summary": {"estimated_cost_usd": 0.0, "mode": "gemini"},
        "revision_context": context,
    }


def _revision_context_step(db: Session, state: GraphState, context: dict[str, Any]) -> None:
    with step_log(db, state["run_id"], "RevisionContextAgent", "revision_context", context) as step:
        output = {
            "source_run_id": context["source_run_id"],
            "root_run_id": context.get("root_run_id") or context["source_run_id"],
            "revision_mode": context["revision_mode"],
            "revision_number": context["revision_number"],
            "requested_changes": context.get("requested_changes", []),
            "qa_issues": context.get("qa_issues", []),
            "qa_settings": context.get("qa_settings", {}),
            "manual_products": bool(context.get("manual_products")),
            "manual_marketing_assets": bool(context.get("manual_marketing_assets")),
        }
        step.output = output


def _revision_context_from_run(run: models.WorkflowRun) -> dict[str, Any]:
    context = (run.input or {}).get("revision_context")
    if not isinstance(context, dict):
        raise ValueError("Revision run is missing revision_context")
    source_output = context.get("source_final_output")
    if not isinstance(source_output, dict):
        raise ValueError("Revision run is missing source_final_output")
    return context


def _run_revision_metadata(db: Session, run_id: str, state: GraphState) -> dict[str, Any]:
    run = db.get(models.WorkflowRun, run_id)
    if not run:
        return {}
    context = state.get("revision_context")
    revision_mode = run.revision_mode or (context.get("revision_mode") if isinstance(context, dict) else None)
    return {
        "root_run_id": context.get("root_run_id") if isinstance(context, dict) else run.parent_run_id,
        "parent_run_id": run.parent_run_id,
        "revision_number": run.revision_number,
        "revision_mode": revision_mode,
        "qa_recheck_mode": _revision_qa_recheck_mode(revision_mode),
        "qa_diff_summary": state.get("qa_diff_summary") or {},
        "source_run_id": context.get("source_run_id") if isinstance(context, dict) else run.parent_run_id,
        "requested_changes": context.get("requested_changes", []) if isinstance(context, dict) else [],
        "qa_settings": context.get("qa_settings", {}) if isinstance(context, dict) else {},
        "comment": context.get("comment") if isinstance(context, dict) else None,
        "approval_history": context.get("approval_history", []) if isinstance(context, dict) else [],
        "source_stability": state.get("source_stability") or {},
        "change_review": _build_ai_revision_change_review(context, state, revision_mode),
    }


def _preserve_revision_source_state(
    context: dict[str, Any],
    products: list[dict[str, Any]],
    *,
    mode: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_output = context.get("source_final_output") if isinstance(context, dict) else {}
    source_output = source_output if isinstance(source_output, dict) else {}
    source_products = [
        product for product in source_output.get("products", [])
        if isinstance(product, dict)
    ]
    source_by_id = {str(product.get("id") or ""): product for product in source_products}
    preserved_products = json.loads(json.dumps(products or [], ensure_ascii=False))
    product_reports: list[dict[str, Any]] = []
    changed_fields: list[str] = []

    for product in preserved_products:
        if not isinstance(product, dict):
            continue
        product_id = str(product.get("id") or "")
        source_product = source_by_id.get(product_id)
        if not source_product:
            product_reports.append(
                {
                    "product_id": product_id,
                    "status": "source_product_missing",
                    "preserved_fields": [],
                    "changed_fields": [],
                    "reason": "부모 run에서 같은 product id를 찾지 못해 source fields를 보존하지 못했습니다.",
                }
            )
            continue
        preserved_fields = []
        product_changed_fields = []
        for field in ["source_ids", "evidence_summary"]:
            source_value = json.loads(json.dumps(source_product.get(field), ensure_ascii=False))
            if product.get(field) != source_value:
                product_changed_fields.append(field)
                changed_fields.append(f"products[{product_id}].{field}")
            product[field] = source_value
            preserved_fields.append(field)
        if _preserve_itinerary_source_ids(product, source_product):
            preserved_fields.append("itinerary[].source_id")
            product_changed_fields.append("itinerary[].source_id")
            changed_fields.append(f"products[{product_id}].itinerary[].source_id")
        product_reports.append(
            {
                "product_id": product_id,
                "status": "preserved",
                "preserved_fields": preserved_fields,
                "changed_fields": product_changed_fields,
                "source_ids": product.get("source_ids", []),
            }
        )

    source_fields_preserved = [
        "products[].source_ids",
        "products[].evidence_summary",
        "products[].itinerary[].source_id",
        "retrieved_documents",
        "evidence_profile",
        "productization_advice",
        "data_coverage",
        "unresolved_gaps",
        "source_confidence",
        "ui_highlights",
    ]
    return preserved_products, {
        "source_stability_mode": _source_stability_mode_for_revision(mode),
        "source_fields_preserved": source_fields_preserved,
        "source_fields_changed": _dedupe_texts(changed_fields),
        "evidence_recomputed": False,
        "reason": "Revision은 source/evidence 수정 기능이 아니므로 부모 run의 근거 연결을 유지했습니다.",
        "product_source_preservation": product_reports,
        "invalid_source_id_diagnostics": _invalid_source_id_diagnostics_from_products(preserved_products),
    }


def _preserve_itinerary_source_ids(product: dict[str, Any], source_product: dict[str, Any]) -> bool:
    itinerary = product.get("itinerary")
    source_itinerary = source_product.get("itinerary")
    if not isinstance(itinerary, list) or not isinstance(source_itinerary, list):
        return False
    changed = False
    for index, item in enumerate(itinerary):
        if not isinstance(item, dict) or index >= len(source_itinerary):
            continue
        source_item = source_itinerary[index]
        if not isinstance(source_item, dict):
            continue
        source_id = source_item.get("source_id")
        if item.get("source_id") != source_id:
            item["source_id"] = source_id
            changed = True
    return changed


def _source_stability_mode_for_revision(mode: str) -> str:
    if mode == "llm_partial_rewrite":
        return "preserve_parent_sources_after_ai_patch"
    if mode == "manual_edit":
        return "preserve_parent_sources_after_manual_edit"
    if mode == "manual_save":
        return "preserve_parent_sources_after_manual_save"
    if mode == "qa_only":
        return "preserve_parent_sources_for_qa_only"
    return "preserve_parent_sources"


def _build_ai_revision_change_review(
    context: Any,
    state: GraphState,
    revision_mode: Any,
) -> dict[str, Any]:
    if str(revision_mode or "") != "llm_partial_rewrite" or not isinstance(context, dict):
        return {"enabled": False, "items": [], "pending_count": 0}
    source_output = context.get("source_final_output")
    if not isinstance(source_output, dict):
        return {"enabled": False, "items": [], "pending_count": 0}
    source_products = [item for item in source_output.get("products", []) or [] if isinstance(item, dict)]
    current_products = [item for item in state.get("product_ideas", []) or [] if isinstance(item, dict)]
    source_assets = [item for item in source_output.get("marketing_assets", []) or [] if isinstance(item, dict)]
    current_assets = [item for item in state.get("marketing_assets", []) or [] if isinstance(item, dict)]
    selected_issues = [item for item in context.get("qa_issues", []) or [] if isinstance(item, dict)]

    items: list[dict[str, Any]] = []
    source_products_by_id = {str(item.get("id") or ""): item for item in source_products}
    source_assets_by_id = {str(item.get("product_id") or ""): item for item in source_assets}

    for product in current_products:
        product_id = str(product.get("id") or "")
        before = source_products_by_id.get(product_id)
        if not before:
            continue
        items.extend(
            _revision_change_items_for_record(
                product_id=product_id,
                entity="product",
                before=before,
                after=product,
                selected_issues=selected_issues,
            )
        )

    for asset in current_assets:
        product_id = str(asset.get("product_id") or "")
        before = source_assets_by_id.get(product_id)
        if not before:
            continue
        items.extend(
            _revision_change_items_for_record(
                product_id=product_id,
                entity="marketing",
                before=before,
                after=asset,
                selected_issues=selected_issues,
            )
        )

    return {
        "enabled": True,
        "mode": "ai_revision_change_review",
        "status": "pending" if items else "no_changes",
        "items": items,
        "pending_count": sum(1 for item in items if item.get("status") == "pending"),
    }


def _revision_change_items_for_record(
    *,
    product_id: str,
    entity: str,
    before: dict[str, Any],
    after: dict[str, Any],
    selected_issues: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in _revision_review_paths(entity, before, after):
        before_value = _get_nested_value(before, path)
        after_value = _get_nested_value(after, path)
        if _json_normalized(before_value) == _json_normalized(after_value):
            continue
        issue = _matching_revision_change_issue(product_id, path, selected_issues)
        change_id = _revision_change_id(entity, product_id, path)
        items.append(
            {
                "id": change_id,
                "entity": entity,
                "product_id": product_id,
                "field_path": path,
                "field_label": _revision_change_field_label(path),
                "before": before_value,
                "after": after_value,
                "status": "pending",
                "qa_issue": json.loads(json.dumps(issue, ensure_ascii=False)) if issue else None,
            }
        )
    return items


def _revision_review_paths(entity: str, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    if entity == "product":
        paths = [
            "title",
            "one_liner",
            "target_customer",
            "core_value",
            "estimated_duration",
            "operation_difficulty",
            "assumptions",
            "not_to_claim",
        ]
        max_itinerary = max(
            len(before.get("itinerary") or []) if isinstance(before.get("itinerary"), list) else 0,
            len(after.get("itinerary") or []) if isinstance(after.get("itinerary"), list) else 0,
        )
        for index in range(max_itinerary):
            paths.extend(
                [
                    f"itinerary[{index}].name",
                    f"itinerary[{index}].description",
                    f"itinerary[{index}].duration",
                ]
            )
        return paths

    sales_paths = [
        "sales_copy.headline",
        "sales_copy.subheadline",
        "sales_copy.disclaimer",
    ]
    before_sections = _get_nested_value(before, "sales_copy.sections")
    after_sections = _get_nested_value(after, "sales_copy.sections")
    max_sections = max(
        len(before_sections) if isinstance(before_sections, list) else 0,
        len(after_sections) if isinstance(after_sections, list) else 0,
    )
    for index in range(max_sections):
        sales_paths.extend([f"sales_copy.sections[{index}].title", f"sales_copy.sections[{index}].body"])
    before_faq = before.get("faq")
    after_faq = after.get("faq")
    max_faq = max(
        len(before_faq) if isinstance(before_faq, list) else 0,
        len(after_faq) if isinstance(after_faq, list) else 0,
    )
    for index in range(max_faq):
        sales_paths.extend([f"faq[{index}].question", f"faq[{index}].answer"])
    sales_paths.extend(["search_keywords"])
    sales_paths.extend(_marketing_strategy_review_paths(before, after))
    return sales_paths


def _marketing_strategy_review_paths(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    paths = [
        "marketing_strategy.target_segment.primary",
        "marketing_strategy.target_segment.foreigner_context",
        "marketing_strategy.product_positioning.summary",
        "marketing_strategy.product_positioning.differentiation",
        "landing_page_outline.hero.headline",
        "landing_page_outline.hero.subheadline",
        "landing_page_outline.hero.hook",
    ]

    def max_len(path: str) -> int:
        before_value = _get_nested_value(before, path)
        after_value = _get_nested_value(after, path)
        return max(
            len(before_value) if isinstance(before_value, list) else 0,
            len(after_value) if isinstance(after_value, list) else 0,
        )

    for index in range(max_len("marketing_strategy.target_segment.secondary")):
        paths.append(f"marketing_strategy.target_segment.secondary[{index}]")
    for index in range(max_len("marketing_strategy.key_selling_points")):
        paths.extend(
            [
                f"marketing_strategy.key_selling_points[{index}].point",
                f"marketing_strategy.key_selling_points[{index}].evidence_basis",
                f"marketing_strategy.key_selling_points[{index}].usage_note",
            ]
        )
    for index in range(max_len("marketing_strategy.customer_objections")):
        paths.extend(
            [
                f"marketing_strategy.customer_objections[{index}].objection",
                f"marketing_strategy.customer_objections[{index}].response",
                f"marketing_strategy.customer_objections[{index}].requires_confirmation",
            ]
        )
    for index in range(max_len("marketing_strategy.operation_checklist")):
        paths.extend(
            [
                f"marketing_strategy.operation_checklist[{index}].item",
                f"marketing_strategy.operation_checklist[{index}].reason",
            ]
        )
    for index in range(max_len("landing_page_outline.why_this_product")):
        paths.append(f"landing_page_outline.why_this_product[{index}]")
    for index in range(max_len("landing_page_outline.evidence_backed_points")):
        paths.extend(
            [
                f"landing_page_outline.evidence_backed_points[{index}].point",
                f"landing_page_outline.evidence_backed_points[{index}].evidence_basis",
            ]
        )
    for index in range(max_len("landing_page_outline.practical_info")):
        paths.append(f"landing_page_outline.practical_info[{index}]")
    for group in ["buyer_faq", "operation_faq"]:
        for index in range(max_len(f"faq_strategy.{group}")):
            paths.extend([f"faq_strategy.{group}[{index}].question", f"faq_strategy.{group}[{index}].answer"])
    for index in range(max_len("sns_campaign.campaign_angles")):
        paths.extend([f"sns_campaign.campaign_angles[{index}].angle", f"sns_campaign.campaign_angles[{index}].rationale"])
    for index in range(max_len("sns_campaign.posts")):
        paths.extend([f"sns_campaign.posts[{index}].format", f"sns_campaign.posts[{index}].hook", f"sns_campaign.posts[{index}].body"])
        for tag_index in range(max_len(f"sns_campaign.posts[{index}].hashtags")):
            paths.append(f"sns_campaign.posts[{index}].hashtags[{tag_index}]")
    for index in range(max_len("sns_campaign.visual_direction")):
        paths.append(f"sns_campaign.visual_direction[{index}]")
    for index in range(max_len("claim_strategy.usable_claims")):
        paths.extend([f"claim_strategy.usable_claims[{index}].claim", f"claim_strategy.usable_claims[{index}].evidence_basis"])
    for index in range(max_len("claim_strategy.caution_phrasing")):
        paths.extend([f"claim_strategy.caution_phrasing[{index}].phrase", f"claim_strategy.caution_phrasing[{index}].reason"])
    return paths


def _revision_change_id(entity: str, product_id: str, path: str) -> str:
    digest = hashlib.sha256(f"{entity}:{product_id}:{path}".encode("utf-8")).hexdigest()[:16]
    return f"change_{digest}"


def _json_normalized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _get_nested_value(record: dict[str, Any], path: str) -> Any:
    current: Any = record
    for token in _path_tokens(path):
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return None
            current = current[token]
        else:
            if not isinstance(current, dict):
                return None
            current = current.get(token)
    return current


def _set_nested_value(record: dict[str, Any], path: str, value: Any) -> bool:
    tokens = _path_tokens(path)
    if not tokens:
        return False
    current: Any = record
    for token in tokens[:-1]:
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return False
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return False
            current = current[token]
    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(current, list) or last >= len(current):
            return False
        current[last] = value
        return True
    if not isinstance(current, dict):
        return False
    current[last] = value
    return True


def _path_tokens(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    for part in path.split("."):
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?", part)
        if not match:
            return []
        tokens.append(match.group(1))
        if match.group(2) is not None:
            tokens.append(int(match.group(2)))
    return tokens


def _matching_revision_change_issue(
    product_id: str,
    path: str,
    selected_issues: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for issue in selected_issues:
        if str(issue.get("product_id") or "") != product_id:
            continue
        issue_path = str(issue.get("field_path") or "").strip()
        if not issue_path:
            continue
        if issue_path == path:
            return issue
        if issue_path in {"faq", "search_keywords"} and path.startswith(issue_path):
            return issue
        if issue_path == "sales_copy.sections" and path.startswith("sales_copy.sections"):
            return issue
        if issue_path in MARKETING_FIELD_PARENT_PATCHES and path.startswith(issue_path):
            return issue
        if path.startswith(f"{issue_path}.") or path.startswith(f"{issue_path}["):
            return issue
    return None


def _revision_change_field_label(path: str) -> str:
    if path == "title":
        return "상품명"
    if path == "one_liner":
        return "한 줄 소개"
    if path == "target_customer":
        return "대상 고객"
    if path == "core_value":
        return "핵심 가치"
    if path == "estimated_duration":
        return "예상 소요 시간"
    if path == "operation_difficulty":
        return "운영 난이도"
    if path == "assumptions":
        return "운영 가정"
    if path == "not_to_claim":
        return "단정 금지 항목"
    if path.startswith("itinerary["):
        return "일정"
    if path == "sales_copy.headline":
        return "홍보 제목"
    if path == "sales_copy.subheadline":
        return "홍보 부제목"
    if path == "sales_copy.disclaimer":
        return "유의 문구"
    section_match = re.fullmatch(r"sales_copy\.sections\[(\d+)\]\.(title|body)", path)
    if section_match:
        return f"상세 설명 {int(section_match.group(1)) + 1}"
    faq_match = re.fullmatch(r"faq\[(\d+)\]\.(question|answer)", path)
    if faq_match:
        return f"FAQ {int(faq_match.group(1)) + 1}"
    if path == "search_keywords":
        return "검색 키워드"
    strategy_label = _marketing_strategy_field_label(path)
    if strategy_label:
        return strategy_label
    return _field_path_label(path)


def _marketing_strategy_field_label(path: str) -> str | None:
    normalized = path.lower()
    if normalized.startswith("marketing_strategy.target_segment"):
        return "판매 대상"
    if normalized.startswith("marketing_strategy.product_positioning"):
        return "포지셔닝"
    if normalized.startswith("marketing_strategy.key_selling_points"):
        return "핵심 Selling Point"
    if normalized.startswith("marketing_strategy.customer_objections"):
        return "고객 망설임 대응"
    if normalized.startswith("marketing_strategy.operation_checklist"):
        return "운영 체크리스트"
    if normalized.startswith("landing_page_outline.hero"):
        return "상세페이지 첫 화면"
    if normalized.startswith("landing_page_outline.why_this_product"):
        return "상세페이지 선택 이유"
    if normalized.startswith("landing_page_outline.evidence_backed_points"):
        return "근거 기반 상세페이지 포인트"
    if normalized.startswith("landing_page_outline.practical_info"):
        return "상세페이지 확인 정보"
    if normalized.startswith("faq_strategy.buyer_faq"):
        return "구매 전환 FAQ 답변" if normalized.endswith(".answer") else "구매 전환 FAQ"
    if normalized.startswith("faq_strategy.operation_faq"):
        return "운영 확인 FAQ 답변" if normalized.endswith(".answer") else "운영 확인 FAQ"
    if normalized.startswith("sns_campaign.campaign_angles"):
        return "SNS 각도"
    if normalized.startswith("sns_campaign.posts"):
        return "SNS 포스트"
    if normalized.startswith("sns_campaign.visual_direction"):
        return "SNS 비주얼 방향"
    if normalized.startswith("claim_strategy.usable_claims"):
        return "활용 가능한 주장"
    if normalized.startswith("claim_strategy.caution_phrasing"):
        return "주의 표현"
    return None


def _invalid_source_id_diagnostics_from_products(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        for item in product.get("internal_diagnostics", []) or []:
            if isinstance(item, dict) and item.get("category") == "source_id_guardrail":
                diagnostics.append(item)
    return diagnostics


def _revision_qa_recheck_mode(revision_mode: Any) -> str | None:
    mode = str(revision_mode or "").strip()
    if mode in {"manual_edit", "qa_only"}:
        return "qa_only_recheck"
    if mode == "llm_partial_rewrite":
        return "ai_partial_rewrite_recheck"
    if mode == "manual_save":
        return "not_rechecked"
    return None


def _revision_qa_diff_state(state: GraphState) -> GraphState:
    context = state.get("revision_context")
    if not isinstance(context, dict):
        return {}
    source_output = context.get("source_final_output")
    if not isinstance(source_output, dict):
        return {}
    qa_report = state.get("qa_report")
    if not isinstance(qa_report, dict):
        return {}
    if qa_report.get("targeted_recheck") is True:
        return {
            "qa_diff_summary": _build_targeted_revision_qa_diff_summary(
                context.get("qa_issues", []) if isinstance(context.get("qa_issues"), list) else [],
                qa_report,
                revision_mode=context.get("revision_mode"),
            )
        }
    return {
        "qa_diff_summary": _build_revision_qa_diff_summary(
            source_output,
            qa_report,
            revision_mode=context.get("revision_mode"),
        )
    }


def _build_targeted_revision_qa_diff_summary(
    selected_issues: list[Any],
    qa_report: dict[str, Any],
    *,
    revision_mode: Any = None,
) -> dict[str, Any]:
    results = qa_report.get("revision_issue_results") if isinstance(qa_report.get("revision_issue_results"), list) else []
    carryover_issues = [
        issue for issue in qa_report.get("issues", [])
        if isinstance(issue, dict) and issue.get("revision_carryover") is True
    ]
    items: list[dict[str, Any]] = []
    counts = {"resolved": 0, "still_open": len(carryover_issues)}
    for index, issue in enumerate(selected_issues):
        if not isinstance(issue, dict):
            continue
        result = results[index] if index < len(results) and isinstance(results[index], dict) else {}
        status = "still_open" if result.get("status") == "still_open" else "resolved"
        counts[status] += 1
        items.append(
            {
                "status": status,
                "product_id": issue.get("product_id"),
                "original_type": issue.get("type"),
                "original_message": _normalize_revision_issue_text(issue),
                "current_message": result.get("message"),
            }
        )
    for issue in carryover_issues:
        items.append(
            {
                "status": "still_open",
                "product_id": issue.get("product_id"),
                "original_type": issue.get("type"),
                "original_message": _normalize_revision_issue_text(issue),
                "carryover": True,
            }
        )
    return {
        "revision_mode": str(revision_mode or ""),
        "qa_recheck_mode": _revision_qa_recheck_mode(revision_mode),
        "scope": "selected_qa_issues_only",
        "counts": counts,
        "items": items,
    }


def _build_revision_qa_diff_summary(
    source_output: dict[str, Any],
    qa_report: dict[str, Any],
    *,
    revision_mode: Any = None,
) -> dict[str, Any]:
    original_report = source_output.get("qa_report") if isinstance(source_output.get("qa_report"), dict) else {}
    original_issues = [
        issue for issue in original_report.get("issues", []) if isinstance(issue, dict)
    ]
    current_issues = [
        issue for issue in qa_report.get("issues", []) if isinstance(issue, dict)
    ]
    pre_existing_notes = _pre_existing_gap_texts(source_output)
    matched_current: set[int] = set()
    items: list[dict[str, Any]] = []

    for original in original_issues:
        match_index, match_status = _find_matching_revision_issue(original, current_issues, matched_current)
        if match_index is None:
            items.append(
                {
                    "status": "resolved",
                    "product_id": original.get("product_id"),
                    "original_type": original.get("type"),
                    "original_message": _normalize_revision_issue_text(original),
                }
            )
            continue
        matched_current.add(match_index)
        current = current_issues[match_index]
        items.append(
            {
                "status": match_status,
                "product_id": current.get("product_id") or original.get("product_id"),
                "original_type": original.get("type"),
                "current_type": current.get("type"),
                "original_message": _normalize_revision_issue_text(original),
                "current_message": _normalize_revision_issue_text(current),
            }
        )

    for index, current in enumerate(current_issues):
        if index in matched_current:
            continue
        current_text = _normalize_revision_issue_text(current)
        status = "pre_existing_gap" if _matches_pre_existing_gap(current_text, pre_existing_notes) else "new_issue"
        items.append(
            {
                "status": status,
                "product_id": current.get("product_id"),
                "current_type": current.get("type"),
                "current_message": current_text,
            }
        )

    counts = {key: 0 for key in ["resolved", "still_open", "new_issue", "pre_existing_gap", "changed_wording", "needs_followup"]}
    for item in items:
        status = str(item.get("status") or "needs_followup")
        counts[status] = counts.get(status, 0) + 1

    return {
        "revision_mode": str(revision_mode or ""),
        "qa_recheck_mode": _revision_qa_recheck_mode(revision_mode),
        "counts": counts,
        "items": items,
    }


def _find_matching_revision_issue(
    original: dict[str, Any],
    current_issues: list[dict[str, Any]],
    matched_current: set[int],
) -> tuple[int | None, str]:
    for index, current in enumerate(current_issues):
        if index in matched_current:
            continue
        if _revision_issues_same(original, current, strict=True):
            return index, "still_open"
    for index, current in enumerate(current_issues):
        if index in matched_current:
            continue
        if _revision_issues_same(original, current, strict=False):
            return index, "changed_wording"
    return None, "resolved"


def _revision_issues_same(original: dict[str, Any], current: dict[str, Any], *, strict: bool) -> bool:
    if str(original.get("product_id") or "") != str(current.get("product_id") or ""):
        return False
    original_type = str(original.get("issue_category") or original.get("type") or "")
    current_type = str(current.get("issue_category") or current.get("type") or "")
    original_text = _normalize_revision_issue_text(original)
    current_text = _normalize_revision_issue_text(current)
    if strict:
        return original_type == current_type and original_text == current_text
    if original_type and current_type and original_type == current_type:
        return True
    return _text_similarity_token_overlap(original_text, current_text) >= 0.55


def _normalize_revision_issue_text(issue: dict[str, Any]) -> str:
    text = f"{issue.get('message') or ''} {issue.get('suggested_fix') or ''}"
    text = _strip_internal_field_paths(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def _text_similarity_token_overlap(left: str, right: str) -> float:
    left_tokens = {token for token in re.split(r"[\s,.'\"()]+", left) if len(token) >= 2}
    right_tokens = {token for token in re.split(r"[\s,.'\"()]+", right) if len(token) >= 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def _pre_existing_gap_texts(source_output: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for product in source_output.get("products", []) or []:
        if not isinstance(product, dict):
            continue
        texts.extend(_string_list(product.get("needs_review")))
        texts.extend(_string_list(product.get("internal_diagnostics")))
        texts.extend(_string_list(product.get("review_notes")))
    qa_report = source_output.get("qa_report") if isinstance(source_output.get("qa_report"), dict) else {}
    for issue in qa_report.get("internal_diagnostics", []) or []:
        if isinstance(issue, dict):
            texts.append(_normalize_revision_issue_text(issue))
    return [_strip_internal_field_paths(text) for text in texts if str(text or "").strip()]


def _matches_pre_existing_gap(current_text: str, gap_texts: list[str]) -> bool:
    internal_gap_terms = ["반려동물", "운영자 확인", "근거 연결", "근거 문서", "확인 필요"]
    if any(term in current_text for term in internal_gap_terms):
        for gap_text in gap_texts:
            if any(term in current_text and term in gap_text for term in internal_gap_terms):
                return True
            if _text_similarity_token_overlap(current_text, gap_text) >= 0.25:
                return True
    return False


def _build_graph(db: Session):
    graph = StateGraph(GraphState)
    graph.add_node("planner", _cancellable_node(db, lambda state: planner_agent(db, state)))
    graph.add_node("geo_resolver", _cancellable_node(db, lambda state: geo_resolver_agent(db, state)))
    graph.add_node("geo_exit", _cancellable_node(db, lambda state: geo_exit_node(db, state)))
    graph.add_node("baseline_data", _cancellable_node(db, lambda state: baseline_data_agent(db, state)))
    graph.add_node("data_gap_profiler", _cancellable_node(db, lambda state: data_gap_profiler_agent(db, state)))
    graph.add_node("api_capability_router", _cancellable_node(db, lambda state: api_capability_router_agent(db, state)))
    graph.add_node("tourapi_detail_planner", _cancellable_node(db, lambda state: tourapi_detail_planner_agent(db, state)))
    graph.add_node("visual_data_planner", _cancellable_node(db, lambda state: visual_data_planner_agent(db, state)))
    graph.add_node("route_signal_planner", _cancellable_node(db, lambda state: route_signal_planner_agent(db, state)))
    graph.add_node("theme_data_planner", _cancellable_node(db, lambda state: theme_data_planner_agent(db, state)))
    graph.add_node("data_enrichment", _cancellable_node(db, lambda state: data_enrichment_agent(db, state)))
    graph.add_node("evidence_fusion", _cancellable_node(db, lambda state: evidence_fusion_agent(db, state)))
    graph.add_node("research", _cancellable_node(db, lambda state: research_agent(db, state)))
    graph.add_node("product", _cancellable_node(db, lambda state: product_agent(db, state)))
    graph.add_node("marketing", _cancellable_node(db, lambda state: marketing_agent(db, state)))
    graph.add_node("qa", _cancellable_node(db, lambda state: qa_agent(db, state)))
    graph.add_node("human_approval", _cancellable_node(db, lambda state: human_approval_node(db, state)))

    graph.set_entry_point("planner")
    graph.add_edge("planner", "geo_resolver")
    graph.add_conditional_edges(
        "geo_resolver",
        _route_after_geo_resolution,
        {
            "geo_exit": "geo_exit",
            "data": "baseline_data",
        },
    )
    graph.add_edge("geo_exit", END)
    graph.add_conditional_edges(
        "baseline_data",
        _route_after_baseline_data,
        {
            "end": END,
            "continue": "data_gap_profiler",
        },
    )
    graph.add_conditional_edges(
        "data_gap_profiler",
        _route_after_gap_profile,
        {
            "enrich": "api_capability_router",
            "research": "research",
        },
    )
    graph.add_edge("api_capability_router", "tourapi_detail_planner")
    graph.add_edge("tourapi_detail_planner", "visual_data_planner")
    graph.add_edge("visual_data_planner", "route_signal_planner")
    graph.add_edge("route_signal_planner", "theme_data_planner")
    graph.add_edge("theme_data_planner", "data_enrichment")
    graph.add_edge("data_enrichment", "evidence_fusion")
    graph.add_edge("evidence_fusion", "research")
    graph.add_edge("research", "product")
    graph.add_edge("product", "marketing")
    graph.add_edge("marketing", "qa")
    graph.add_edge("qa", "human_approval")
    graph.add_edge("human_approval", END)
    return graph.compile()


def _cancellable_node(db: Session, func):
    def runner(state: GraphState) -> GraphState:
        _raise_if_cancelled(db, state["run_id"])
        output = func(state)
        _raise_if_cancelled(db, state["run_id"])
        return output

    return runner


def _raise_if_cancelled(db: Session, run_id: str) -> None:
    if is_run_cancellation_requested(run_id):
        raise WorkflowCancelled("사용자가 workflow 실행 중지를 요청했습니다.")
    status = (
        db.query(models.WorkflowRun.status)
        .filter(models.WorkflowRun.id == run_id)
        .scalar()
    )
    if status in {"cancelling", "cancelled"}:
        raise WorkflowCancelled("사용자가 workflow 실행 중지를 요청했습니다.")


def _is_run_cancelled(db: Session, run_id: str) -> bool:
    status = (
        db.query(models.WorkflowRun.status)
        .filter(models.WorkflowRun.id == run_id)
        .scalar()
    )
    return status in {"cancelling", "cancelled"} or is_run_cancellation_requested(run_id)


def _route_after_geo_resolution(state: GraphState) -> str:
    geo_scope = state.get("geo_scope") or (state.get("normalized_request") or {}).get("geo_scope") or {}
    if (
        geo_scope.get("status") == "unsupported"
        or geo_scope.get("mode") == "unsupported_region"
        or geo_scope.get("needs_clarification")
    ):
        return "geo_exit"
    return "data"


def _route_after_baseline_data(state: GraphState) -> str:
    return "end" if state.get("final_report") else "continue"


def _route_after_gap_profile(state: GraphState) -> str:
    gap_report = state.get("data_gap_report") or {}
    gaps = gap_report.get("gaps") if isinstance(gap_report.get("gaps"), list) else []
    return "enrich" if gaps else "research"


def _default_workflow_plan() -> list[dict[str, Any]]:
    return [
        {"id": "resolve_geo_scope", "agent": "GeoResolverAgent"},
        {"id": "baseline_tourapi_collection", "executor": "BaselineDataCollection"},
        {"id": "profile_data_gaps", "agent": "DataGapProfilerAgent"},
        {"id": "route_data_capabilities", "agent": "ApiCapabilityRouterAgent"},
        {"id": "plan_tourapi_detail", "agent": "TourApiDetailPlannerAgent"},
        {"id": "plan_visual_data", "agent": "VisualDataPlannerAgent"},
        {"id": "plan_route_signal", "agent": "RouteSignalPlannerAgent"},
        {"id": "plan_theme_data", "agent": "ThemeDataPlannerAgent"},
        {"id": "execute_selected_enrichment", "executor": "EnrichmentExecutor"},
        {"id": "fuse_evidence", "agent": "EvidenceFusionAgent"},
        {"id": "synthesize_research", "agent": "ResearchSynthesisAgent"},
        {"id": "generate_products", "agent": "ProductAgent"},
        {"id": "generate_marketing", "agent": "MarketingAgent"},
        {"id": "qa_review", "agent": "QAComplianceAgent"},
        {"id": "human_approval", "node": "HumanApprovalNode"},
    ]


def _default_normalized_request(request: dict[str, Any]) -> dict[str, Any]:
    product_count = _coerce_product_count(request.get("product_count"), fallback=3)
    return {
        "user_intent": str(request.get("message") or "관광 상품 기획").strip(),
        "request_type": "tourism_product_generation",
        "region_name": request.get("region"),
        "start_date": _period_start(request.get("period")),
        "end_date": _period_end(request.get("period")),
        "period": request.get("period"),
        "target_customer": request.get("target_customer") or "외국인",
        "product_count": product_count,
        "preferred_themes": _string_list(request.get("preferences")) or ["야간 관광", "축제"],
        "avoid": _string_list(request.get("avoid")),
        "output_language": request.get("output_language") or "ko",
        "product_generation_constraints": [
            f"상품 개수는 최대 {MAX_PRODUCT_COUNT}개입니다.",
            "지역 코드는 GeoResolverAgent가 확정합니다.",
            "근거 없는 운영시간, 가격, 예약 가능 여부는 단정하지 않습니다.",
        ],
        "evidence_requirements": [
            "각 상품은 최소 1개 이상의 실제 근거 문서와 연결되어야 합니다.",
            "부족한 정보는 needs_review 또는 claim_limits로 분리해야 합니다.",
        ],
    }


def _coerce_product_count(value: Any, fallback: int) -> int:
    try:
        count = int(value or fallback)
    except (TypeError, ValueError):
        count = fallback
    return max(1, min(MAX_PRODUCT_COUNT, count))


def planner_agent(db: Session, state: GraphState) -> GraphState:
    with step_log(db, state["run_id"], "PlannerAgent", "planner", state.get("user_request")) as step:
        request = state["user_request"]
        settings = get_settings()
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose="planner",
            prompt=_planner_prompt(request),
            response_schema=PLANNER_RESPONSE_SCHEMA,
            max_output_tokens=4096,
            temperature=0.1,
            settings=settings,
        )
        normalized = validate_planner_output(gemini_result.data, request)
        meta = _gemini_generation_meta("PlannerAgent", "planner", gemini_result)
        step.model = gemini_result.model
        plan = _default_workflow_plan()
        output = {"normalized_request": normalized, "plan": plan, "generation": meta}
        step.output = output
        return {
            "normalized_request": normalized,
            "plan": plan,
            "agent_execution": _append_agent_execution(state, meta),
        }


def geo_resolver_agent(db: Session, state: GraphState) -> GraphState:
    normalized = dict(state["normalized_request"])
    request = state["user_request"]
    resolver_input = {
        "message": request.get("message"),
        "region_hint": request.get("region"),
    }
    with step_log(db, state["run_id"], "GeoResolverAgent", "geo_resolution", resolver_input) as step:
        settings = get_settings()
        llm_hints: dict[str, Any] | None = None
        catalog = load_ldong_catalog(db)
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose="geo_resolution",
            prompt=_geo_resolution_prompt(resolver_input, catalog_options=_geo_catalog_options_for_prompt(catalog)),
            response_schema=GEO_RESOLUTION_RESPONSE_SCHEMA,
            max_output_tokens=2048,
            temperature=0.05,
            settings=settings,
        )
        llm_hints = validate_geo_resolution_hints(gemini_result.data)
        meta = _gemini_generation_meta("GeoResolverAgent", "geo_resolution", gemini_result)
        step.model = gemini_result.model
        geo_scope = resolve_geo_scope(
            db,
            message=request.get("message"),
            region=request.get("region"),
            llm_hints=llm_hints,
        )
        record = save_geo_resolution(db, run_id=state["run_id"], geo_scope=geo_scope)
        geo_scope["resolution_id"] = record.id
        normalized["geo_scope"] = geo_scope
        if geo_scope.get("locations"):
            first_location = geo_scope["locations"][0]
            normalized["region_name"] = first_location.get("name")
            normalized["ldong_regn_cd"] = first_location.get("ldong_regn_cd")
            normalized["ldong_signgu_cd"] = first_location.get("ldong_signgu_cd")
        normalized["allow_nationwide"] = bool(geo_scope.get("allow_nationwide"))
        step.output = {
            "geo_scope": geo_scope,
            "normalized_request": normalized,
            "geo_intent": llm_hints,
            "generation": meta,
        }
        return {
            "normalized_request": normalized,
            "geo_scope": geo_scope,
            "agent_execution": _append_agent_execution(state, meta),
        }


def geo_exit_node(db: Session, state: GraphState) -> GraphState:
    normalized = state.get("normalized_request") or {}
    geo_scope = state.get("geo_scope") or normalized.get("geo_scope") or {}
    is_clarification = bool(geo_scope.get("needs_clarification"))
    status = "failed" if is_clarification else "unsupported"
    run_status = status
    if is_clarification:
        is_multi_region = (
            geo_scope.get("mode") == "unsupported_multi_region"
            or geo_scope.get("resolution_strategy") == "unsupported_multi_region"
        )
        if is_multi_region:
            message = str(
                geo_scope.get("clarification_question")
                or "현재 PARAVOCA는 한 번에 하나의 지역만 지원합니다. 후보 중 하나만 포함해 다시 요청해 주세요."
            )
            title = "단일 지역만 지원합니다"
            detail = "지역 이동형 코스나 복수 지역을 한 번에 연결하는 요청은 아직 지원하지 않습니다."
            qa_summary = "복수 지역 요청이라 QA 검수를 실행하지 않았습니다."
        else:
            message = str(
                geo_scope.get("clarification_question")
                or "지역을 하나로 확정할 수 없습니다. 후보 중 원하는 지역을 선택해 주세요."
            )
            title = "지역을 하나로 좁혀 주세요"
            detail = "아래 후보 중 원하는 지역명을 포함해서 다시 요청하면 검색과 상품 기획을 진행합니다."
            qa_summary = "지역 확인이 필요해 QA 검수를 실행하지 않았습니다."
    else:
        message = str(
            geo_scope.get("unsupported_reason")
            or "PARAVOCA는 현재 국내 관광 데이터만 지원합니다."
        )
        title = "지원 범위 안내"
        detail = "국내 지역을 포함해 다시 요청하면 관광 데이터 수집과 상품 기획을 진행할 수 있습니다."
        qa_summary = "지원 범위 밖 요청이라 QA 검수를 실행하지 않았습니다."
    with step_log(db, state["run_id"], "GeoResolverAgent", "geo_scope_exit", geo_scope) as step:
        report = {
            "status": status,
            "run_status": run_status,
            "normalized_request": normalized,
            "geo_scope": geo_scope,
            "user_message": {
                "title": title,
                "message": message,
                "detail": detail,
            },
            "source_items": [],
            "retrieved_documents": [],
            "research_summary": {},
            "products": [],
            "marketing_assets": [],
            "qa_report": {
                "overall_status": "not_run",
                "summary": qa_summary,
                "issues": [],
                "pass_count": 0,
                "needs_review_count": 0,
                "fail_count": 0,
            },
            "agent_execution": state.get("agent_execution", []),
            "cost_summary": _cost_summary(db, state["run_id"]),
            "revision": _run_revision_metadata(db, state["run_id"], state),
            "approval": {
                "required": False,
                "status": "not_required",
                "message": message,
            },
        }
        step.output = report
        return {
            "run_status": run_status,
            "final_report": report,
            "approval": report["approval"],
        }


def baseline_data_agent(db: Session, state: GraphState) -> GraphState:
    normalized = state["normalized_request"]
    with step_log(db, state["run_id"], "BaselineDataAgent", "baseline_data_collection", normalized) as step:
        provider = get_tourism_provider()
        provider_source = "tourapi"
        run_id = state["run_id"]
        geo_scope = state.get("geo_scope") or normalized.get("geo_scope") or {}
        if geo_scope.get("status") == "unsupported" or geo_scope.get("mode") == "unsupported_region":
            raise RuntimeError(
                str(geo_scope.get("unsupported_reason") or "PARAVOCA는 현재 국내 관광 데이터만 지원합니다.")
            )
        if geo_scope.get("needs_clarification"):
            raise RuntimeError(
                "Geo scope needs clarification before TourAPI search: "
                f"{geo_scope.get('clarification_question') or geo_scope.get('unresolved_locations')}"
            )

        search_geo_scope = _geo_scope_with_tourapi_child_locations(db, geo_scope)
        locations = _locations_for_tourapi_search(search_geo_scope)
        if not locations and not geo_scope.get("allow_nationwide"):
            raise RuntimeError("Geo scope was not resolved. Nationwide fallback is disabled.")

        all_items: list[Any] = []
        diagnostics: dict[str, Any] = {
            "reason": None,
            "tourapi_raw_collected_count": 0,
            "tourapi_deduped_item_count": 0,
            "geo_filtered_item_count": 0,
            "source_document_upsert_count": 0,
            "indexed_document_count": 0,
            "vector_search_filter": {},
            "vector_search_result_count": 0,
            "post_geo_filter_result_count": 0,
            "tourapi_expanded_locations": [
                {
                    "name": location.get("name"),
                    "ldong_regn_cd": location.get("ldong_regn_cd"),
                    "ldong_signgu_cd": location.get("ldong_signgu_cd"),
                    "expanded_from": location.get("expanded_from_name"),
                }
                for location in locations
                if location.get("expanded_from_name")
            ],
        }
        primary_keyword = _rag_query_for_request(normalized, search_geo_scope)
        for location in locations:
            geo_kwargs = _tourapi_geo_kwargs(location)
            keyword_queries = _tourapi_keyword_queries(normalized, search_geo_scope, location)
            arguments_base = {
                **geo_kwargs,
                "geo_role": location.get("role") if location else None,
                "location_name": location.get("name") if location else "nationwide",
            }
            attractions: list[Any] = []
            for keyword in keyword_queries:
                attractions.extend(
                    log_tool_call(
                        db=db,
                        run_id=run_id,
                        step_id=step.id,
                        tool_name="tourapi_search_keyword",
                        arguments={**arguments_base, "query": keyword, "limit": 20},
                        source=provider_source,
                        call=lambda keyword=keyword, geo_kwargs=geo_kwargs: provider.search_keyword(
                            query=keyword,
                            limit=20,
                            **geo_kwargs,
                        ),
                    )
                )
            area_attractions = log_tool_call(
                db=db,
                run_id=run_id,
                step_id=step.id,
                tool_name="tourapi_area_based_list",
                arguments={**arguments_base, "content_type": "12", "limit": 20},
                source=provider_source,
                call=lambda geo_kwargs=geo_kwargs: provider.area_based_list(
                    content_type="12",
                    limit=20,
                    **geo_kwargs,
                ),
            )
            area_leisure = log_tool_call(
                db=db,
                run_id=run_id,
                step_id=step.id,
                tool_name="tourapi_area_based_list",
                arguments={**arguments_base, "content_type": "28", "limit": 20},
                source=provider_source,
                call=lambda geo_kwargs=geo_kwargs: provider.area_based_list(
                    content_type="28",
                    limit=20,
                    **geo_kwargs,
                ),
            )
            events = log_tool_call(
                db=db,
                run_id=run_id,
                step_id=step.id,
                tool_name="tourapi_search_festival",
                arguments={
                    **arguments_base,
                    "start_date": normalized.get("start_date"),
                    "end_date": normalized.get("end_date"),
                    "limit": 20,
                },
                source=provider_source,
                call=lambda geo_kwargs=geo_kwargs: provider.search_festival(
                    start_date=date.fromisoformat(normalized["start_date"]),
                    end_date=date.fromisoformat(normalized["end_date"]),
                    limit=20,
                    **geo_kwargs,
                ),
            )
            stays = log_tool_call(
                db=db,
                run_id=run_id,
                step_id=step.id,
                tool_name="tourapi_search_stay",
                arguments={**arguments_base, "limit": 10},
                source=provider_source,
                call=lambda geo_kwargs=geo_kwargs: provider.search_stay(limit=10, **geo_kwargs),
            )
            all_items.extend([*attractions, *area_attractions, *area_leisure, *events, *stays])

        diagnostics["tourapi_raw_collected_count"] = len(all_items)
        items = _dedupe_items(all_items)
        diagnostics["tourapi_deduped_item_count"] = len(items)
        items = _filter_items_by_geo_scope(items, geo_scope=search_geo_scope, run_id=run_id)
        diagnostics["geo_filtered_item_count"] = len(items)
        if not items:
            diagnostics["reason"] = "tourapi_empty_for_resolved_geo_scope"
            report = _insufficient_source_data_report(
                db=db,
                state=state,
                geo_scope=geo_scope,
                diagnostics=diagnostics,
                detail=(
                    "해석된 지역 범위로 TourAPI를 조회했지만 상품 기획에 사용할 관광 후보를 찾지 못했습니다."
                ),
            )
            step.output = report
            return {
                "run_status": "failed",
                "final_report": report,
                "approval": report["approval"],
            }
        upsert_tourism_items(db, items)
        source_documents = upsert_source_documents_from_items(
            db,
            items,
            run_id=run_id,
            source_role=SOURCE_ROLE_RUNTIME,
            ingestion_method="workflow_baseline_tourapi",
        )
        diagnostics["source_document_upsert_count"] = len(source_documents)
        indexed_count = index_source_documents(db, source_documents)
        diagnostics["indexed_document_count"] = indexed_count
        vector_filters = _vector_filters_for_geo_scope(
            search_geo_scope,
            source=provider_source,
            normalized=normalized,
        )
        diagnostics["vector_search_filter"] = vector_filters
        vector_result = log_tool_call(
            db=db,
            run_id=run_id,
            step_id=step.id,
            tool_name="vector_search",
            arguments={
                "query": primary_keyword,
                "top_k": 10,
                "filters": vector_filters,
                "search_context": _rag_search_context(normalized, search_geo_scope),
            },
            source="chroma",
            call=lambda: search_source_documents_with_diagnostics(
                query=primary_keyword,
                top_k=10,
                filters=vector_filters,
                search_context=_rag_search_context(normalized, search_geo_scope),
            ),
        )
        retrieved = vector_result.get("results", []) if isinstance(vector_result, dict) else []
        diagnostics["vector_search"] = (
            vector_result.get("retrieval_diagnostics", {}) if isinstance(vector_result, dict) else {}
        )
        diagnostics["vector_search_result_count"] = len(retrieved)
        retrieved = _filter_retrieved_documents_by_geo_scope(
            retrieved,
            geo_scope=search_geo_scope,
            run_id=run_id,
        )
        diagnostics["post_geo_filter_result_count"] = len(retrieved)
        diagnostics["retrieved_document_reasons"] = _retrieved_document_reasons(retrieved)
        if not retrieved:
            diagnostics["reason"] = "vector_search_empty_for_resolved_geo_scope"
            report = _insufficient_source_data_report(
                db=db,
                state=state,
                geo_scope=geo_scope,
                diagnostics=diagnostics,
                detail=(
                    "TourAPI 후보는 수집했지만 현재 검색 조건으로 상품 기획에 사용할 근거 문서를 찾지 못했습니다."
                ),
            )
            step.output = report
            return {
                "run_status": "failed",
                "final_report": report,
                "approval": report["approval"],
            }
        raw_source_items = [_tourism_item_to_dict(item) for item in items]
        source_items = select_enrichment_candidate_items(
            source_items=raw_source_items,
            retrieved_documents=retrieved,
            normalized_request=normalized,
            limit=int(get_settings().tourapi_candidate_shortlist_limit),
        )
        candidate_pool_summary = summarize_candidate_pool(
            raw_source_items=raw_source_items,
            selected_items=source_items,
        )
        output = {
            "geo_scope": geo_scope,
            "source_items": source_items,
            "candidate_pool_summary": candidate_pool_summary,
            "retrieved_documents": retrieved,
            "indexed_documents": indexed_count,
            "retrieval_diagnostics": diagnostics,
            "detail_enrichment": {
                "status": "deferred_to_enrichment_executor",
                "message": "Phase 10부터 상세/이미지 보강은 gap profiling 이후 선택적으로 실행합니다.",
            },
        }
        step.output = output
        return {
            "geo_scope": geo_scope,
            "source_items": output["source_items"],
            "candidate_pool_summary": candidate_pool_summary,
            "retrieved_documents": retrieved,
            "retrieval_diagnostics": diagnostics,
        }


def _insufficient_source_data_report(
    *,
    db: Session,
    state: GraphState,
    geo_scope: dict[str, Any],
    diagnostics: dict[str, Any],
    detail: str,
) -> dict[str, Any]:
    normalized = state.get("normalized_request") or {}
    region_label = _resolved_geo_scope_label(geo_scope)
    message = (
        f"{region_label} 기준으로 TourAPI 데이터를 확인했지만, "
        "상품 기획에 사용할 수 있는 관광 근거를 충분히 찾지 못했습니다."
    )
    suggested_next_requests = _insufficient_source_data_suggestions(
        normalized=normalized,
        geo_scope=geo_scope,
        region_label=region_label,
    )
    return {
        "status": "insufficient_source_data",
        "run_status": "failed",
        "reason": "insufficient_source_data",
        "normalized_request": normalized,
        "geo_scope": geo_scope,
        "user_message": {
            "title": "관광 근거 데이터가 부족합니다",
            "message": message,
            "detail": detail,
            "suggestions": suggested_next_requests,
        },
        "source_items": [],
        "candidate_pool_summary": {
            "status": "insufficient_source_data",
            "raw_collected_count": diagnostics.get("tourapi_raw_collected_count", 0),
            "geo_filtered_item_count": diagnostics.get("geo_filtered_item_count", 0),
            "selected_count": 0,
        },
        "retrieved_documents": [],
        "retrieval_diagnostics": diagnostics,
        "suggested_next_requests": suggested_next_requests,
        "data_gap_report": {
            "gaps": [],
            "coverage": {
                "status": "insufficient_source_data",
                "summary": "상품 생성에 필요한 최소 근거가 부족해 gap profiling을 실행하지 않았습니다.",
            },
            "reasoning_summary": "Baseline TourAPI/RAG retrieval 단계에서 충분한 근거 문서를 찾지 못했습니다.",
            "needs_review": [],
        },
        "enrichment_plan": {"planned_calls": [], "skipped_calls": [], "reason": "insufficient_source_data"},
        "enrichment_summary": {},
        "evidence_profile": {"entities": [], "reason": "insufficient_source_data"},
        "productization_advice": {
            "usable_claims": [],
            "restricted_claims": ["충분한 지역 근거 없이 상품 본문을 생성하지 않습니다."],
            "needs_review": ["지역 범위, 테마, 기간을 조정해 다시 요청해야 합니다."],
        },
        "data_coverage": {
            "status": "insufficient",
            "summary": "상품 초안을 만들 만큼의 근거 문서가 부족합니다.",
            "retrieval_diagnostics": diagnostics,
        },
        "unresolved_gaps": [
            {
                "gap_type": "insufficient_source_data",
                "severity": "high",
                "reason": message,
            }
        ],
        "source_confidence": 0.0,
        "ui_highlights": [
            {
                "type": "insufficient_source_data",
                "title": "데이터 부족",
                "message": message,
            }
        ],
        "research_summary": {},
        "products": [],
        "marketing_assets": [],
        "qa_report": {
            "overall_status": "not_run",
            "summary": "관광 근거 데이터가 부족해 상품 생성과 QA 검수를 실행하지 않았습니다.",
            "issues": [],
            "pass_count": 0,
            "needs_review_count": 0,
            "fail_count": 0,
        },
        "agent_execution": state.get("agent_execution", []),
        "cost_summary": _cost_summary(db, state["run_id"]),
        "revision": _run_revision_metadata(db, state["run_id"], state),
        "approval": {
            "required": False,
            "status": "not_required",
            "message": message,
        },
    }


def _resolved_geo_scope_label(geo_scope: dict[str, Any]) -> str:
    if geo_scope.get("allow_nationwide"):
        return "전국"
    locations = geo_scope.get("locations") if isinstance(geo_scope.get("locations"), list) else []
    names = [str(location.get("name") or "").strip() for location in locations if isinstance(location, dict)]
    return " → ".join(name for name in names if name) or "요청 지역"


def _insufficient_source_data_suggestions(
    *,
    normalized: dict[str, Any],
    geo_scope: dict[str, Any],
    region_label: str,
) -> list[str]:
    target = str(normalized.get("target_customer") or "외국인").strip() or "외국인"
    product_count = _desired_product_count(normalized, fallback=3)
    themes = [str(theme).strip() for theme in _string_list(normalized.get("preferred_themes")) if str(theme).strip()]
    theme_text = f" {themes[0]}" if themes else ""
    suggestions = [
        f"{region_label}에서 {target} 대상{theme_text} 관광 상품 {product_count}개를 다른 테마로 기획해줘.",
        f"{region_label}에서 {target} 대상 관광 상품 {product_count}개를 다른 기간 기준으로 기획해줘.",
    ]
    locations = geo_scope.get("locations") if isinstance(geo_scope.get("locations"), list) else []
    if len(locations) == 1 and isinstance(locations[0], dict):
        broader = str(locations[0].get("ldong_regn_nm") or "").strip()
        if broader and broader not in region_label:
            suggestions.insert(
                0,
                f"{broader} 전체에서 {target} 대상{theme_text} 관광 상품 {product_count}개를 기획해줘.",
            )
        elif broader:
            suggestions.insert(
                0,
                f"{broader} 전체 범위로 넓혀서 {target} 대상{theme_text} 관광 상품 {product_count}개를 기획해줘.",
            )
    return _dedupe_texts(suggestions)[:3]


def data_agent(db: Session, state: GraphState) -> GraphState:
    return baseline_data_agent(db, state)


def data_gap_profiler_agent(db: Session, state: GraphState) -> GraphState:
    settings = get_settings()
    capability_brief = capability_brief_for_prompt(settings)
    gap_inventory = build_gap_inventory(
        source_items=state.get("source_items", []),
        retrieved_documents=state.get("retrieved_documents", []),
        normalized_request=state.get("normalized_request", {}),
    )
    input_payload = {
        "source_item_count": len(state.get("source_items", [])),
        "retrieved_document_count": len(state.get("retrieved_documents", [])),
        "gap_inventory_count": len(gap_inventory.get("gaps") or []),
        "gap_inventory_counts": (gap_inventory.get("coverage") or {}).get("gap_counts") or {},
        "normalized_request": state.get("normalized_request", {}),
        "candidate_pool_summary": state.get("candidate_pool_summary", {}),
    }
    with step_log(db, state["run_id"], "DataGapProfilerAgent", "data_gap_profile", input_payload) as step:
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose="data_gap_profile",
            prompt=build_data_gap_profile_prompt(
                source_items=state.get("source_items", []),
                retrieved_documents=state.get("retrieved_documents", []),
                normalized_request=state.get("normalized_request", {}),
                capability_brief=capability_brief,
                candidate_pool_summary=state.get("candidate_pool_summary", {}),
                gap_inventory=gap_inventory,
            ),
            response_schema=DATA_GAP_PROFILE_REF_RESPONSE_SCHEMA,
            max_output_tokens=8192,
            temperature=0.1,
            settings=settings,
        )
        gap_report = normalize_gap_profile_payload(
            gemini_result.data,
            source_items=state.get("source_items", []),
            retrieved_documents=state.get("retrieved_documents", []),
            normalized_request=state.get("normalized_request", {}),
            gap_inventory=gap_inventory,
        )
        meta = _gemini_generation_meta("DataGapProfilerAgent", "data_gap_profile", gemini_result)
        step.model = gemini_result.model
        step.output = {"gap_report": gap_report, "generation": meta}
        return {
            "data_gap_report": gap_report,
            "data_coverage": gap_report.get("coverage") or {},
            "unresolved_gaps": gap_report.get("gaps") or [],
            "agent_execution": _append_agent_execution(state, meta),
        }


def api_capability_router_agent(db: Session, state: GraphState) -> GraphState:
    gap_report = state.get("data_gap_report") or {"gaps": []}
    settings = get_settings()
    max_call_budget = int(settings.enrichment_max_call_budget)
    capabilities = capability_matrix_for_prompt(settings)
    with step_log(db, state["run_id"], "ApiCapabilityRouterAgent", "api_capability_routing", gap_report) as step:
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose="api_capability_routing",
            prompt=build_api_capability_router_prompt(
                gap_report=gap_report,
                capabilities=capabilities,
                settings=settings,
                max_call_budget=max_call_budget,
            ),
            response_schema=API_CAPABILITY_ROUTING_RESPONSE_SCHEMA,
            max_output_tokens=2048,
            temperature=0.05,
            settings=settings,
        )
        capability_routing = normalize_family_routing_payload(
            gemini_result.data,
            gap_report=gap_report,
            settings=settings,
        )
        meta = _gemini_generation_meta("ApiCapabilityRouterAgent", "api_capability_routing", gemini_result)
        step.model = gemini_result.model
        step.output = {"capability_routing": capability_routing, "generation": meta}
        return {
            "capability_routing": capability_routing,
            "enrichment_plan_fragments": [],
            "agent_execution": _append_agent_execution(state, meta),
        }


def tourapi_detail_planner_agent(db: Session, state: GraphState) -> GraphState:
    return api_family_planner_agent(db, state, "tourapi_detail")


def visual_data_planner_agent(db: Session, state: GraphState) -> GraphState:
    return api_family_planner_agent(db, state, "visual_data")


def route_signal_planner_agent(db: Session, state: GraphState) -> GraphState:
    return api_family_planner_agent(db, state, "route_signal")


def theme_data_planner_agent(db: Session, state: GraphState) -> GraphState:
    return api_family_planner_agent(db, state, "theme_data")


def api_family_planner_agent(db: Session, state: GraphState, planner_key: str) -> GraphState:
    definition = PLANNER_DEFINITIONS[planner_key]
    settings = get_settings()
    existing_fragments = state.get("enrichment_plan_fragments") or []
    existing_planned_count = sum(len(fragment.get("planned_calls") or []) for fragment in existing_fragments)
    # Each enrichment lane owns its own call budget. The final merged plan can
    # contain calls from several lanes; earlier detail calls must not starve
    # route/signal or theme calls explicitly requested by the user.
    lane_existing_planned_count = existing_planned_count if planner_key == "tourapi_detail" else 0
    capability_routing = state.get("capability_routing") or {"family_routes": []}
    gap_report = state.get("data_gap_report") or {"gaps": []}
    max_call_budget = int(settings.enrichment_max_call_budget)
    if planner_key == "tourapi_detail":
        max_call_budget = max(
            max_call_budget,
            existing_planned_count + count_tourapi_detail_targets(capability_routing, gap_report),
        )
    route = next(
        (route for route in capability_routing.get("family_routes") or [] if route.get("planner") == planner_key),
        None,
    )
    assigned_gap_ids = route.get("gap_ids") if isinstance(route, dict) else []
    assigned_gap_count = len(assigned_gap_ids or [])
    if assigned_gap_count == 0:
        result: GraphState = {"enrichment_plan_fragments": existing_fragments}
        if planner_key == "theme_data":
            result["enrichment_plan"] = merge_enrichment_plan_fragments(
                existing_fragments,
                max_call_budget=max(max_call_budget, existing_planned_count),
            )
        return result

    input_payload = {
        "planner": planner_key,
        "assigned_gap_count": assigned_gap_count,
        "existing_planned_count": existing_planned_count,
        "lane_existing_planned_count": lane_existing_planned_count,
    }
    with step_log(db, state["run_id"], definition["agent_name"], definition["purpose"], input_payload) as step:
        if planner_key == "tourapi_detail":
            planner_prompt = build_tourapi_detail_planner_prompt(
                capability_routing=capability_routing,
                gap_report=gap_report,
                max_call_budget=max_call_budget,
                existing_planned_count=lane_existing_planned_count,
            )
            planner_schema = TOURAPI_DETAIL_PLANNER_RESPONSE_SCHEMA
            planner_max_output_tokens = 8192
        else:
            planner_prompt = build_api_family_planner_prompt(
                planner_key=planner_key,
                capability_routing=capability_routing,
                gap_report=gap_report,
                capabilities=capability_matrix_for_prompt(settings),
                settings=settings,
                max_call_budget=max_call_budget,
                existing_planned_count=lane_existing_planned_count,
            )
            planner_schema = API_FAMILY_PLANNER_RESPONSE_SCHEMA
            planner_max_output_tokens = 2048
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose=definition["purpose"],
            prompt=planner_prompt,
            response_schema=planner_schema,
            max_output_tokens=planner_max_output_tokens,
            temperature=0.05,
            settings=settings,
        )
        if planner_key == "tourapi_detail":
            fragment = normalize_tourapi_detail_planner_payload(
                gemini_result.data,
                capability_routing=capability_routing,
                gap_report=gap_report,
                settings=settings,
                max_call_budget=max_call_budget,
                existing_planned_count=lane_existing_planned_count,
            )
        else:
            fragment = normalize_family_planner_payload(
                gemini_result.data,
                planner_key=planner_key,
                capability_routing=capability_routing,
                gap_report=gap_report,
                settings=settings,
                max_call_budget=max_call_budget,
                existing_planned_count=lane_existing_planned_count,
            )
        meta = _gemini_generation_meta(definition["agent_name"], definition["purpose"], gemini_result)
        step.model = gemini_result.model
        next_fragments = [*existing_fragments, fragment]
        output = {"fragment": fragment, "generation": meta}
        if planner_key == "theme_data":
            fragment_planned_count = len(fragment.get("planned_calls") or [])
            output["merged_plan"] = merge_enrichment_plan_fragments(
                next_fragments,
                max_call_budget=max(max_call_budget, existing_planned_count + fragment_planned_count),
            )
        step.output = output
        result: GraphState = {
            "enrichment_plan_fragments": next_fragments,
            "agent_execution": _append_agent_execution(state, meta),
        }
        if planner_key == "theme_data":
            result["enrichment_plan"] = output["merged_plan"]
        return result


def data_enrichment_agent(db: Session, state: GraphState) -> GraphState:
    input_payload = {
        "gap_report": state.get("data_gap_report") or {"gaps": []},
        "plan": state.get("enrichment_plan")
        or merge_enrichment_plan_fragments(
            state.get("enrichment_plan_fragments") or [],
            max_call_budget=int(get_settings().enrichment_max_call_budget),
        ),
    }
    with step_log(db, state["run_id"], "EnrichmentExecutor", "data_enrichment", input_payload) as step:
        enrichment_run = create_enrichment_run(
            db=db,
            workflow_run_id=state["run_id"],
            gap_report=input_payload["gap_report"],
            plan=input_payload["plan"],
            trigger_type="workflow",
        )
        summary = execute_enrichment_plan(
            db=db,
            provider=get_tourism_provider(),
            enrichment_run=enrichment_run,
            source_items=state.get("source_items", []),
            run_id=state["run_id"],
            step_id=step.id,
        )
        output = {
            "enrichment_run_id": enrichment_run.id,
            "status": enrichment_run.status,
            "summary": summary,
        }
        step.output = output
        step.model = "tool-executor-v1"
        return {"enrichment_summary": output}


def evidence_fusion_agent(db: Session, state: GraphState) -> GraphState:
    input_payload = {
        "source_item_count": len(state.get("source_items", [])),
        "retrieved_document_count": len(state.get("retrieved_documents", [])),
        "enrichment_summary": state.get("enrichment_summary") or {},
    }
    with step_log(db, state["run_id"], "EvidenceFusionAgent", "evidence_fusion", input_payload) as step:
        settings = get_settings()
        refreshed_documents = _refreshed_documents_after_enrichment(db, state, step.id)
        documents = _merge_retrieved_documents(
            _source_item_documents(db, state.get("source_items", [])),
            state.get("retrieved_documents", []),
            refreshed_documents,
        )
        base_fusion = fuse_evidence(
            db=db,
            source_items=state.get("source_items", []),
            retrieved_documents=documents,
            gap_report=state.get("data_gap_report") or {"gaps": []},
            enrichment_summary=state.get("enrichment_summary") or {},
        )
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose="evidence_fusion",
            prompt=build_evidence_fusion_prompt(
                base_fusion=base_fusion,
                retrieved_documents=documents,
                gap_report=state.get("data_gap_report") or {"gaps": []},
                enrichment_summary=state.get("enrichment_summary") or {},
            ),
            response_schema=EVIDENCE_FUSION_RESPONSE_SCHEMA,
            max_output_tokens=16384,
            temperature=0.1,
            settings=settings,
        )
        fusion = normalize_evidence_fusion_payload(gemini_result.data, base_fusion=base_fusion)
        meta = _gemini_generation_meta("EvidenceFusionAgent", "evidence_fusion", gemini_result)
        step.model = gemini_result.model
        output = {
            **fusion,
            "retrieved_documents": documents,
            "generation": meta,
        }
        step.output = output
        return {
            "retrieved_documents": documents,
            "evidence_profile": fusion["evidence_profile"],
            "productization_advice": fusion["productization_advice"],
            "data_coverage": fusion["data_coverage"],
            "unresolved_gaps": fusion["unresolved_gaps"],
            "source_confidence": fusion["source_confidence"],
            "ui_highlights": fusion.get("ui_highlights", []),
            "agent_execution": _append_agent_execution(state, meta),
        }


def _refreshed_documents_after_enrichment(
    db: Session,
    state: GraphState,
    step_id: str | None,
) -> list[dict[str, Any]]:
    normalized = state.get("normalized_request") or {}
    geo_scope = state.get("geo_scope") or normalized.get("geo_scope") or {}
    query = _rag_query_for_request(normalized, geo_scope)
    filters = _vector_filters_for_geo_scope(
        geo_scope,
        source=[
            "tourapi",
            "kto_tourism_photo",
            "kto_photo_contest",
            "kto_durunubi",
            "kto_related_places",
            "kto_tourism_bigdata",
            "kto_crowding_forecast",
            "kto_regional_tourism_demand",
            "kto_wellness",
            "kto_pet",
            "kto_audio",
            "kto_medical",
        ],
        normalized=normalized,
    )
    result = log_tool_call(
        db=db,
        run_id=state["run_id"],
        step_id=step_id,
        tool_name="vector_search_post_enrichment",
        arguments={
            "query": query,
            "top_k": 10,
            "filters": filters,
            "search_context": _rag_search_context(normalized, geo_scope),
        },
        source="chroma",
        call=lambda: search_source_documents_with_diagnostics(
            query=query,
            top_k=10,
            filters=filters,
            search_context=_rag_search_context(normalized, geo_scope),
        ),
    )
    documents = result.get("results", []) if isinstance(result, dict) else []
    return _filter_retrieved_documents_by_geo_scope(
        documents,
        geo_scope=geo_scope,
        run_id=state["run_id"],
    )


def _source_item_documents(db: Session, source_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    document_ids = [
        f"doc:{item.get('id')}"
        for item in source_items
        if isinstance(item, dict) and item.get("id")
    ]
    if not document_ids:
        return []
    rows = db.query(models.SourceDocument).filter(models.SourceDocument.id.in_(document_ids)).all()
    row_by_id = {row.id: row for row in rows}
    documents: list[dict[str, Any]] = []
    for document_id in document_ids:
        row = row_by_id.get(document_id)
        if row:
            documents.append(_source_document_row_to_retrieved_document(row, retrieval_reason="source_item_shortlist"))
    return documents


def _source_document_row_to_retrieved_document(
    row: models.SourceDocument,
    *,
    retrieval_reason: str,
) -> dict[str, Any]:
    metadata = row.document_metadata if isinstance(row.document_metadata, dict) else {}
    return {
        "doc_id": row.id,
        "title": row.title,
        "content": row.content,
        "snippet": row.content[:260],
        "score": None,
        "relevance_score": None,
        "matching_signals": [{"type": retrieval_reason, "label": "이번 run의 후보 근거"}],
        "source_role": metadata.get("source_role"),
        "metadata": metadata,
    }


def _merge_retrieved_documents(*document_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in document_groups:
        for document in group or []:
            if not isinstance(document, dict):
                continue
            doc_id = str(document.get("doc_id") or "").strip()
            if not doc_id:
                continue
            existing = merged.get(doc_id)
            if not existing:
                merged[doc_id] = document
                continue
            if len(str(document.get("content") or "")) > len(str(existing.get("content") or "")):
                merged[doc_id] = {**existing, **document}
    return list(merged.values())


def _region_code_from_area_result(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None
    value = item.get("region_code") or item.get("code") or item.get("areaCode") or item.get("areacode")
    if value is None:
        return None
    region_code = str(value).strip()
    return region_code or None


LEGACY_AREA_TO_LDONG_REGN = {
    "1": "11",
    "2": "28",
    "3": "30",
    "4": "27",
    "5": "29",
    "6": "26",
    "7": "31",
    "8": "36",
    "31": "41",
    "32": "51",
    "33": "43",
    "34": "44",
    "35": "52",
    "36": "46",
    "37": "47",
    "38": "48",
    "39": "50",
}

PROVINCE_NAME_TERMS = {
    "서울특별시",
    "부산광역시",
    "대구광역시",
    "인천광역시",
    "광주광역시",
    "대전광역시",
    "울산광역시",
    "세종특별자치시",
    "경기도",
    "강원특별자치도",
    "충청북도",
    "충청남도",
    "전북특별자치도",
    "전라북도",
    "전라남도",
    "경상북도",
    "경상남도",
    "제주특별자치도",
}


def _locations_for_tourapi_search(geo_scope: dict[str, Any]) -> list[dict[str, Any]]:
    if geo_scope.get("allow_nationwide"):
        return [{}]
    locations = geo_scope.get("locations")
    return locations if isinstance(locations, list) else []


def _geo_scope_with_tourapi_child_locations(db: Session, geo_scope: dict[str, Any]) -> dict[str, Any]:
    if geo_scope.get("allow_nationwide"):
        return geo_scope
    locations = _locations_for_tourapi_search(geo_scope)
    expanded_locations = _expand_locations_to_tourapi_child_signgus(db, locations)
    if expanded_locations == locations:
        return geo_scope
    return {**geo_scope, "locations": expanded_locations}


def _expand_locations_to_tourapi_child_signgus(
    db: Session,
    locations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    changed = False
    for location in locations:
        child_locations = _tourapi_child_signgu_locations(db, location)
        if child_locations:
            expanded.extend(child_locations)
            changed = True
        else:
            expanded.append(location)
    return expanded if changed else locations


def _tourapi_child_signgu_locations(db: Session, location: dict[str, Any]) -> list[dict[str, Any]]:
    regn_cd = str(location.get("ldong_regn_cd") or "").strip()
    signgu_cd = str(location.get("ldong_signgu_cd") or "").strip()
    full_name = str(location.get("base_name") or location.get("name") or "").strip()
    if not regn_cd or not signgu_cd or not full_name:
        return []
    rows = (
        db.query(models.TourApiLdongCode)
        .filter(models.TourApiLdongCode.ldong_regn_cd == regn_cd)
        .filter(models.TourApiLdongCode.ldong_signgu_cd.isnot(None))
        .filter(models.TourApiLdongCode.ldong_signgu_cd != signgu_cd)
        .filter(models.TourApiLdongCode.full_name.like(f"{full_name} %"))
        .order_by(models.TourApiLdongCode.ldong_signgu_cd)
        .all()
    )
    return [
        {
            **location,
            "name": row.full_name,
            "ldong_signgu_cd": row.ldong_signgu_cd,
            "ldong_signgu_nm": row.ldong_signgu_nm,
            "expanded_from_name": location.get("name") or full_name,
            "expanded_from_ldong_signgu_cd": signgu_cd,
        }
        for row in rows
        if row.ldong_signgu_cd
    ]


def _tourapi_geo_kwargs(location: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "ldong_regn_cd",
        "ldong_signgu_cd",
        "lcls_systm_1",
        "lcls_systm_2",
        "lcls_systm_3",
    ]
    return {key: location.get(key) for key in keys if location.get(key)}


def _keyword_for_geo_scope(
    normalized: dict[str, Any],
    geo_scope: dict[str, Any],
    location: dict[str, Any] | None = None,
) -> str:
    location_name = (
        (location or {}).get("keyword")
        or (location or {}).get("name")
        or (location or {}).get("location_name")
    )
    if not location_name:
        locations = geo_scope.get("locations") if isinstance(geo_scope.get("locations"), list) else []
        location_name = " ".join(
            str(item.get("keyword") or item.get("name") or item.get("location_name") or "") for item in locations
        )
    keywords = geo_scope.get("keywords") if isinstance(geo_scope.get("keywords"), list) else []
    local_terms = (
        (location or {}).get("sub_area_terms")
        if isinstance((location or {}).get("sub_area_terms"), list)
        else []
    )
    themes = normalized.get("preferred_themes") if isinstance(normalized.get("preferred_themes"), list) else []
    parts = [
        str(location_name or ""),
        str(normalized.get("target_customer") or "외국인"),
        *[str(term) for term in local_terms[:3]],
        *[str(keyword) for keyword in keywords[:3]],
        *[str(theme) for theme in themes[:3]],
        "액티비티",
    ]
    return " ".join(part for part in parts if part).strip()


def _rag_query_for_request(normalized: dict[str, Any], geo_scope: dict[str, Any]) -> str:
    message = str(normalized.get("message") or normalized.get("question") or "").strip()
    intent = str(normalized.get("user_intent") or "").strip()
    base = _keyword_for_geo_scope(normalized, geo_scope)
    content_terms = _content_type_terms_for_request(normalized)
    parts = [
        base,
        intent,
        message,
        " ".join(content_terms),
    ]
    return " ".join(part for part in parts if part).strip()


def _rag_search_context(normalized: dict[str, Any], geo_scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_customer": normalized.get("target_customer"),
        "preferred_themes": _string_list(normalized.get("preferred_themes")),
        "narrow_keywords": _narrow_keywords_for_geo_scope(geo_scope),
        "content_types": _content_type_filters_for_request(normalized),
        "original_message": normalized.get("message") or normalized.get("question"),
    }


def _narrow_keywords_for_geo_scope(geo_scope: dict[str, Any]) -> list[str]:
    keywords = geo_scope.get("keywords") if isinstance(geo_scope.get("keywords"), list) else []
    terms = [str(keyword).strip() for keyword in keywords if str(keyword or "").strip()]
    retained_keywords = geo_scope.get("retained_keywords") if isinstance(geo_scope.get("retained_keywords"), list) else []
    terms.extend(str(keyword).strip() for keyword in retained_keywords if str(keyword or "").strip())
    locations = geo_scope.get("locations") if isinstance(geo_scope.get("locations"), list) else []
    for location in locations:
        if not isinstance(location, dict):
            continue
        terms.extend(_string_list(location.get("sub_area_terms")))
        for key in ["keyword", "matched_text", "name", "location_name"]:
            value = str(location.get(key) or "").strip()
            if value:
                terms.append(value)
    return _dedupe_texts([term for term in terms if term])[:12]


def _content_type_terms_for_request(normalized: dict[str, Any]) -> list[str]:
    labels = {
        "event": "행사",
        "accommodation": "숙박",
        "leisure": "레저",
        "attraction": "관광지",
    }
    return [labels.get(item, item) for item in _content_type_filters_for_request(normalized)]


def _content_type_filters_for_request(normalized: dict[str, Any]) -> list[str]:
    explicit = _string_list(normalized.get("content_types"))
    if explicit:
        return explicit
    text = " ".join(
        [
            str(normalized.get("message") or ""),
            str(normalized.get("question") or ""),
            str(normalized.get("user_intent") or ""),
            " ".join(_string_list(normalized.get("preferred_themes"))),
        ]
    )
    content_types: list[str] = []
    checks = [
        (("축제", "행사", "페스티벌"), "event"),
        (("숙박", "호텔", "스테이"), "accommodation"),
        (("레저",), "leisure"),
    ]
    for tokens, content_type in checks:
        if any(token in text for token in tokens):
            content_types.append(content_type)
    return _dedupe_texts(content_types)


def _tourapi_keyword_queries(
    normalized: dict[str, Any],
    geo_scope: dict[str, Any],
    location: dict[str, Any] | None = None,
) -> list[str]:
    location_terms = _tourapi_location_keyword_terms(geo_scope, location)
    themes = [
        _clean_keyword_term(term)
        for term in (normalized.get("preferred_themes") if isinstance(normalized.get("preferred_themes"), list) else [])
    ]
    themes = [term for term in themes if term]
    queries: list[str] = []
    primary_location = location_terms[0] if location_terms else ""
    if primary_location:
        queries.append(primary_location)
    queries.extend(themes[:4])
    if primary_location:
        queries.extend(f"{primary_location} {theme}" for theme in themes[:4])
    if not queries:
        fallback = _clean_keyword_term(_keyword_for_geo_scope(normalized, geo_scope, location))
        if fallback:
            queries.append(fallback)
    return _dedupe_texts(queries)[:8]


def _tourapi_location_keyword_terms(
    geo_scope: dict[str, Any],
    location: dict[str, Any] | None = None,
) -> list[str]:
    terms: list[str] = []
    candidate_locations = [location] if location else []
    if not candidate_locations:
        locations = geo_scope.get("locations") if isinstance(geo_scope.get("locations"), list) else []
        candidate_locations = locations
    for item in candidate_locations:
        if not isinstance(item, dict):
            continue
        terms.extend(
            [
                item.get("keyword"),
                item.get("matched_text"),
                item.get("expanded_from_name"),
                item.get("base_name"),
                item.get("name"),
            ]
        )
    cleaned: list[str] = []
    for term in terms:
        keyword = _clean_location_keyword_term(term)
        if keyword:
            cleaned.append(keyword)
    return _dedupe_texts(cleaned)


def _clean_location_keyword_term(value: Any) -> str:
    term = _clean_keyword_term(value)
    if not term:
        return ""
    parts = term.split()
    if len(parts) >= 2:
        compact_parts = [part for part in parts if part not in PROVINCE_NAME_TERMS]
        if compact_parts:
            term = " ".join(compact_parts)
    term = re.sub(r"(특별자치시|특별자치도|특별시|광역시|자치도)$", "", term).strip()
    return term


def _clean_keyword_term(value: Any) -> str:
    term = str(value or "").strip()
    term = re.sub(r"\s+", " ", term)
    term = re.sub(r"[^\w가-힣\s·.-]", "", term)
    return term.strip()


def _vector_filters_for_geo_scope(
    geo_scope: dict[str, Any],
    *,
    source: str | list[str],
    normalized: dict[str, Any] | None = None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {"source": source}
    source_families = _source_family_filters_for_source(source)
    if source_families:
        filters["source_family"] = source_families if len(source_families) > 1 else source_families[0]
    if geo_scope.get("allow_nationwide"):
        if _source_filter_is_core_tourapi(source):
            _add_request_filters(filters, normalized or {}, [])
        return filters
    locations = _locations_for_tourapi_search(geo_scope)
    regn_codes = sorted(
        {str(location.get("ldong_regn_cd")) for location in locations if location.get("ldong_regn_cd")}
    )
    signgu_codes = sorted(
        {str(location.get("ldong_signgu_cd")) for location in locations if location.get("ldong_signgu_cd")}
    )
    if regn_codes:
        filters["ldong_regn_cd"] = regn_codes if len(regn_codes) > 1 else regn_codes[0]
    if signgu_codes and len(signgu_codes) == len(locations):
        filters["ldong_signgu_cd"] = signgu_codes if len(signgu_codes) > 1 else signgu_codes[0]
    lcls_filters = _lcls_filters_for_locations(locations)
    filters.update(lcls_filters)
    if _source_filter_is_core_tourapi(source):
        _add_request_filters(filters, normalized or {}, locations)
    return filters


def _source_family_filters_for_source(source: str | list[str]) -> list[str]:
    values = source if isinstance(source, list) else [source]
    families: list[str] = []
    for value in values:
        source_name = str(value or "").strip()
        if not source_name:
            continue
        families.append("kto_tourapi_kor" if source_name == "tourapi" else source_name)
    return _dedupe_texts(families)


def _source_filter_is_core_tourapi(source: str | list[str]) -> bool:
    values = source if isinstance(source, list) else [source]
    return set(str(value or "").strip() for value in values) <= {"tourapi"}


def _lcls_filters_for_locations(locations: list[dict[str, Any]]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for key in ["lcls_systm_1", "lcls_systm_2", "lcls_systm_3"]:
        values = sorted({str(location.get(key)) for location in locations if location.get(key)})
        if values:
            filters[key] = values if len(values) > 1 else values[0]
    return filters


def _add_request_filters(
    filters: dict[str, Any],
    normalized: dict[str, Any],
    locations: list[dict[str, Any]],
) -> None:
    content_types = _content_type_filters_for_request(normalized)
    if content_types:
        filters["content_type"] = content_types if len(content_types) > 1 else content_types[0]


def _retrieved_document_reasons(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    for document in documents:
        reasons.append(
            {
                "doc_id": document.get("doc_id"),
                "title": document.get("title"),
                "score": document.get("score"),
                "relevance_score": document.get("relevance_score"),
                "source_role": document.get("source_role"),
                "matching_signals": document.get("matching_signals") or [],
            }
        )
    return reasons


def _filter_items_by_geo_scope(
    items: list[Any],
    *,
    geo_scope: dict[str, Any],
    run_id: str | None,
) -> list[Any]:
    if geo_scope.get("allow_nationwide"):
        return items
    locations = _locations_for_tourapi_search(geo_scope)
    if not locations:
        return []
    filtered = [item for item in items if _item_matches_geo_scope(item, locations)]
    dropped = len(items) - len(filtered)
    if dropped:
        logger.warning(
            "Dropped %s off-region TourAPI items for run_id=%s geo_scope=%s",
            dropped,
            run_id,
            geo_scope,
        )
    return filtered


def _item_matches_geo_scope(item: Any, locations: list[dict[str, Any]]) -> bool:
    item_regn = _item_ldong_regn_cd(item)
    item_signgu = _item_ldong_signgu_cd(item)
    for location in locations:
        expected_regn = str(location.get("ldong_regn_cd") or "")
        expected_signgu = str(location.get("ldong_signgu_cd") or "")
        if not expected_regn:
            continue
        if item_regn != expected_regn:
            continue
        if expected_signgu and item_signgu and item_signgu != expected_signgu:
            continue
        locality_terms = _locality_terms_for_location(location)
        if locality_terms:
            item_text = " ".join(
                str(value or "")
                for value in [
                    getattr(item, "title", None),
                    getattr(item, "address", None),
                    getattr(item, "overview", None),
                    getattr(item, "raw", None),
                ]
            )
            if not any(term in item_text for term in locality_terms):
                continue
        return True
    return False


def _filter_retrieved_documents_by_geo_scope(
    documents: list[dict[str, Any]],
    *,
    geo_scope: dict[str, Any],
    run_id: str | None,
) -> list[dict[str, Any]]:
    scoped_documents = [
        document
        for document in documents
        if _document_passes_run_retrieval_scope(document, run_id)
        and _document_passes_evidence_integrity(document)
    ]
    scoped_dropped = len(documents) - len(scoped_documents)
    if scoped_dropped:
        logger.warning(
            "Dropped %s weakly-linked or out-of-run enrichment documents for run_id=%s",
            scoped_dropped,
            run_id,
        )
    if geo_scope.get("allow_nationwide"):
        return scoped_documents
    locations = _locations_for_tourapi_search(geo_scope)
    if not locations:
        return []
    geo_filtered = [
        document
        for document in scoped_documents
        if _document_matches_geo_scope(document, locations)
    ]
    dropped = len(scoped_documents) - len(geo_filtered)
    if dropped:
        logger.warning(
            "Dropped %s off-region retrieved documents for run_id=%s geo_scope=%s",
            dropped,
            run_id,
            geo_scope,
        )
    return geo_filtered


def _document_passes_run_retrieval_scope(document: dict[str, Any], run_id: str | None) -> bool:
    metadata = document.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    source_family = str(metadata.get("source_family") or metadata.get("source") or "")
    enrichment_families = {*VISUAL_SOURCE_FAMILIES, *ROUTE_SIGNAL_SOURCE_FAMILIES, *THEME_SOURCE_FAMILIES}
    if source_family not in enrichment_families:
        return True
    if not run_id:
        return False
    return run_id in {
        str(metadata.get("first_seen_run_id") or ""),
        str(metadata.get("last_seen_run_id") or ""),
    }


def _document_passes_evidence_integrity(document: dict[str, Any]) -> bool:
    metadata = document.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    source_family = str(metadata.get("source_family") or metadata.get("source") or "")
    content_type = str(metadata.get("content_type") or "")
    if content_type != "theme" and source_family not in THEME_SOURCE_FAMILIES:
        return True
    return bool(_metadata_string_list(metadata.get("theme_match_signals")))


def _metadata_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item or "").strip()]
    return []


def _document_matches_geo_scope(document: dict[str, Any], locations: list[dict[str, Any]]) -> bool:
    metadata = document.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    if not _metadata_matches_geo_scope(metadata, locations):
        return False
    for location in locations:
        locality_terms = _locality_terms_for_location(location)
        if not locality_terms:
            return True
        document_text = " ".join(
            str(value or "")
            for value in [
                document.get("title"),
                document.get("snippet"),
                document.get("content"),
                *(metadata.values()),
            ]
        )
        if any(term in document_text for term in locality_terms):
            return True
    return False


def _metadata_matches_geo_scope(metadata: dict[str, Any], locations: list[dict[str, Any]]) -> bool:
    metadata_regn = _metadata_ldong_regn_cd(metadata)
    metadata_signgu = _string_or_empty(metadata.get("ldong_signgu_cd"))
    for location in locations:
        expected_regn = str(location.get("ldong_regn_cd") or "")
        expected_signgu = str(location.get("ldong_signgu_cd") or "")
        if not expected_regn:
            continue
        if metadata_regn != expected_regn:
            continue
        if expected_signgu and metadata_signgu and metadata_signgu != expected_signgu:
            continue
        return True
    return False


def _locality_terms_for_location(location: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    sub_area_terms = location.get("sub_area_terms")
    if isinstance(sub_area_terms, list):
        terms.extend(str(term).strip() for term in sub_area_terms if str(term or "").strip())
    keyword = str(location.get("keyword") or "").strip()
    if keyword:
        terms.append(keyword)
    return _dedupe_texts(terms)


def _item_ldong_regn_cd(item: Any) -> str:
    value = getattr(item, "ldong_regn_cd", None)
    if value:
        return str(value)
    legacy_area = getattr(item, "legacy_area_code", None) or getattr(item, "region_code", None)
    return LEGACY_AREA_TO_LDONG_REGN.get(str(legacy_area or ""), str(legacy_area or ""))


def _item_ldong_signgu_cd(item: Any) -> str:
    value = getattr(item, "ldong_signgu_cd", None)
    if value:
        return str(value)
    return str(getattr(item, "legacy_sigungu_code", None) or getattr(item, "sigungu_code", None) or "")


def _metadata_ldong_regn_cd(metadata: dict[str, Any]) -> str:
    value = metadata.get("ldong_regn_cd")
    if value:
        return str(value)
    legacy_area = metadata.get("legacy_area_code") or metadata.get("region_code")
    return LEGACY_AREA_TO_LDONG_REGN.get(str(legacy_area or ""), str(legacy_area or ""))


def _string_or_empty(value: Any) -> str:
    return str(value or "")


def research_agent(db: Session, state: GraphState) -> GraphState:
    input_payload = {
        "retrieved_document_count": len(state.get("retrieved_documents", [])),
        "candidate_card_count": len(_candidate_cards_from_context(_evidence_context_from_state(state))),
        "unresolved_gap_count": len(state.get("unresolved_gaps", [])),
        "source_confidence": state.get("source_confidence") or 0.0,
    }
    with step_log(db, state["run_id"], "ResearchSynthesisAgent", "research", input_payload) as step:
        docs = state.get("retrieved_documents", [])
        evidence_context = _evidence_context_from_state(state)
        settings = get_settings()
        prompt_kwargs = {
            "normalized": state.get("normalized_request", {}),
            "docs": docs,
            "evidence_context": evidence_context,
            "data_gap_report": state.get("data_gap_report") or {},
            "enrichment_summary": state.get("enrichment_summary") or {},
        }
        try:
            gemini_result = call_gemini_json(
                db=db,
                run_id=state["run_id"],
                step_id=step.id,
                purpose="research_synthesis",
                prompt=_research_synthesis_prompt(**prompt_kwargs),
                response_schema=RESEARCH_SYNTHESIS_RESPONSE_SCHEMA,
                max_output_tokens=8192,
                temperature=0.15,
                settings=settings,
            )
        except GeminiGatewayError as exc:
            if not _is_timeout_like_gemini_error(exc):
                raise
            logger.warning(
                "Retrying research synthesis with compact prompt after Gemini timeout. run_id=%s step_id=%s error=%s",
                state["run_id"],
                step.id,
                exc,
            )
            gemini_result = call_gemini_json(
                db=db,
                run_id=state["run_id"],
                step_id=step.id,
                purpose="research_synthesis_compact_retry",
                prompt=_research_synthesis_prompt(**prompt_kwargs, compact_retry_error=str(exc)),
                response_schema=RESEARCH_SYNTHESIS_RESPONSE_SCHEMA,
                max_output_tokens=4096,
                temperature=0.1,
                settings=settings,
            )
        summary = validate_research_synthesis(gemini_result.data, state)
        meta = _gemini_generation_meta("ResearchSynthesisAgent", "research_synthesis", gemini_result)
        step.model = gemini_result.model
        step.output = {"research_summary": summary, "generation": meta}
        return {
            "research_summary": summary,
            "agent_execution": _append_agent_execution(state, meta),
        }


def _region_label_from_normalized(normalized: dict[str, Any]) -> str:
    geo_scope = normalized.get("geo_scope") if isinstance(normalized.get("geo_scope"), dict) else {}
    locations = geo_scope.get("locations") if isinstance(geo_scope.get("locations"), list) else []
    names = [str(location.get("name")) for location in locations if location.get("name")]
    if names:
        return " - ".join(names)
    if geo_scope.get("allow_nationwide"):
        return "전국"
    return str(normalized.get("region_name") or "요청 지역")


def product_agent(db: Session, state: GraphState) -> GraphState:
    normalized = state["normalized_request"]
    with step_log(db, state["run_id"], "ProductAgent", "product_generation", state.get("research_summary")) as step:
        docs = state.get("retrieved_documents", [])
        evidence_context = _evidence_context_from_state(state)
        qa_settings = _qa_settings_from_state(state)
        settings = get_settings()
        product_prompt = _product_prompt(
            normalized,
            state.get("research_summary", {}),
            docs,
            evidence_context=evidence_context,
            source_items=state.get("source_items", []),
            qa_settings=qa_settings,
        )
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose="product_generation",
            prompt=product_prompt,
            response_schema=PRODUCT_RESPONSE_SCHEMA,
            max_output_tokens=16384,
            temperature=0.35,
            settings=settings,
        )
        try:
            products = validate_products(
                gemini_result.data,
                normalized,
                docs,
                evidence_context=evidence_context,
                qa_settings=qa_settings,
            )
        except ValueError as exc:
            repair_result = call_gemini_json(
                db=db,
                run_id=state["run_id"],
                step_id=step.id,
                purpose="product_generation_repair",
                prompt=_product_prompt(
                    normalized,
                    state.get("research_summary", {}),
                    docs,
                    evidence_context=evidence_context,
                    source_items=state.get("source_items", []),
                    qa_settings=qa_settings,
                    validation_error=str(exc),
                ),
                response_schema=PRODUCT_RESPONSE_SCHEMA,
                max_output_tokens=16384,
                temperature=0.2,
                settings=settings,
            )
            products = validate_products(
                repair_result.data,
                normalized,
                docs,
                evidence_context=evidence_context,
                qa_settings=qa_settings,
            )
            gemini_result = repair_result
        meta = _gemini_generation_meta("ProductAgent", "product_generation", gemini_result)
        step.model = gemini_result.model
        step.output = {"products": products, "generation": meta}
        return {
            "product_ideas": products,
            "agent_execution": _append_agent_execution(state, meta),
        }


def marketing_agent(db: Session, state: GraphState) -> GraphState:
    with step_log(db, state["run_id"], "MarketingAgent", "marketing_generation", state.get("product_ideas")) as step:
        settings = get_settings()
        products = state.get("product_ideas", [])
        evidence_context = _evidence_context_from_state(state)
        docs = state.get("retrieved_documents", [])
        revision_context = state.get("revision_context")
        qa_settings = _qa_settings_from_state(state)
        assets: list[dict[str, Any]] = []
        generation_results: list[GeminiJsonResult] = []
        for product_batch in _marketing_product_batches(products):
            _raise_if_cancelled(db, state["run_id"])
            batch_docs = _marketing_docs_for_products(product_batch, docs)
            gemini_result = call_gemini_json(
                db=db,
                run_id=state["run_id"],
                step_id=step.id,
                purpose="marketing_generation",
                prompt=_marketing_prompt(
                    product_batch,
                    batch_docs,
                    revision_context,
                    evidence_context,
                    qa_settings,
                ),
                response_schema=MARKETING_RESPONSE_SCHEMA,
                max_output_tokens=MARKETING_BATCH_MAX_OUTPUT_TOKENS,
                temperature=0.35,
                settings=settings,
            )
            try:
                batch_assets = validate_marketing_assets(
                    gemini_result.data,
                    product_batch,
                    evidence_context=evidence_context,
                )
            except ValueError as exc:
                if not _should_retry_marketing_validation(exc):
                    raise
                _raise_if_cancelled(db, state["run_id"])
                repair_result = call_gemini_json(
                    db=db,
                    run_id=state["run_id"],
                    step_id=step.id,
                    purpose="marketing_generation_repair",
                    prompt=_marketing_prompt(
                        product_batch,
                        batch_docs,
                        revision_context,
                        evidence_context,
                        qa_settings,
                        validation_error=str(exc),
                    ),
                    response_schema=MARKETING_RESPONSE_SCHEMA,
                    max_output_tokens=MARKETING_BATCH_MAX_OUTPUT_TOKENS,
                    temperature=0.2,
                    settings=settings,
                )
                batch_assets = validate_marketing_assets(
                    repair_result.data,
                    product_batch,
                    evidence_context=evidence_context,
                )
                gemini_result = repair_result
            assets.extend(batch_assets)
            generation_results.append(gemini_result)
        assets = validate_marketing_assets({"marketing_assets": assets}, products, evidence_context=evidence_context)
        meta = _combined_gemini_generation_meta("MarketingAgent", "marketing_generation", generation_results)
        step.model = meta["model"]
        step.output = {"marketing_assets": assets, "generation": meta}
        return {
            "marketing_assets": assets,
            "agent_execution": _append_agent_execution(state, meta),
        }


def qa_agent(db: Session, state: GraphState) -> GraphState:
    with step_log(db, state["run_id"], "QAComplianceAgent", "qa_review", state.get("marketing_assets")) as step:
        settings = get_settings()
        products = state.get("product_ideas", [])
        assets = state.get("marketing_assets", [])
        docs = state.get("retrieved_documents", [])
        evidence_context = _evidence_context_from_state(state)
        qa_settings = _qa_settings_from_state(state)
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose="qa_review",
            prompt=_qa_prompt(
                products,
                assets,
                docs,
                qa_settings,
                evidence_context,
            ),
            response_schema=QA_RESPONSE_SCHEMA,
            max_output_tokens=16384,
            temperature=0.1,
            settings=settings,
        )
        qa_report = validate_qa_report(
            gemini_result.data,
            products,
            docs=docs,
            evidence_context=evidence_context,
            marketing_assets=assets,
            qa_settings=qa_settings,
        )
        meta = _gemini_generation_meta("QAComplianceAgent", "qa_review", gemini_result)
        step.model = gemini_result.model
        step.output = {"qa_report": qa_report, "generation": meta}
        return {
            "qa_report": qa_report,
            "agent_execution": _append_agent_execution(state, meta),
        }


def revision_patch_agent(db: Session, state: GraphState) -> GraphState:
    with step_log(
        db,
        state["run_id"],
        "RevisionPatchAgent",
        "revision_patch",
        state.get("revision_context"),
    ) as step:
        source_output = state.get("revision_context", {}).get("source_final_output", {})
        products = json.loads(json.dumps(source_output.get("products") or [], ensure_ascii=False))
        marketing_assets = json.loads(json.dumps(source_output.get("marketing_assets") or [], ensure_ascii=False))
        if not products or not marketing_assets:
            raise ValueError("AI revision requires source products and marketing_assets")

        settings = get_settings()
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose="revision_patch",
            prompt=_revision_patch_prompt(
                products,
                marketing_assets,
                state.get("revision_context", {}),
            ),
            response_schema=REVISION_PATCH_RESPONSE_SCHEMA,
            max_output_tokens=16384,
            temperature=0.15,
            settings=settings,
        )
        patch_payload = gemini_result.data
        meta = _gemini_generation_meta("RevisionPatchAgent", "revision_patch", gemini_result)
        step.model = gemini_result.model

        patched_products, patched_assets = apply_revision_patch(
            patch_payload,
            products,
            marketing_assets,
            allowed_patch_scope=_revision_allowed_patch_scope(state.get("revision_context", {})),
        )
        output = {
            "patch": patch_payload,
            "products": patched_products,
            "marketing_assets": patched_assets,
            "generation": meta,
        }
        step.output = output
        return {
            "product_ideas": patched_products,
            "marketing_assets": patched_assets,
            "agent_execution": _append_agent_execution(state, meta),
        }


def targeted_revision_qa_agent(db: Session, state: GraphState) -> GraphState:
    with step_log(
        db,
        state["run_id"],
        "QAComplianceAgent",
        "qa_targeted_revision_review",
        state.get("revision_context"),
    ) as step:
        revision_context = state.get("revision_context", {})
        source_output = revision_context.get("source_final_output", {}) if isinstance(revision_context, dict) else {}
        selected_issues = revision_context.get("qa_issues", []) if isinstance(revision_context, dict) else []
        products = state.get("product_ideas", [])
        assets = state.get("marketing_assets", [])
        settings = get_settings()
        gemini_result = call_gemini_json(
            db=db,
            run_id=state["run_id"],
            step_id=step.id,
            purpose="qa_targeted_revision_review",
            prompt=_targeted_revision_qa_prompt(
                source_output.get("products") or [],
                source_output.get("marketing_assets") or [],
                products,
                assets,
                selected_issues,
                revision_context.get("qa_settings", {}) if isinstance(revision_context, dict) else {},
            ),
            response_schema=TARGETED_QA_RESPONSE_SCHEMA,
            max_output_tokens=4096,
            temperature=0.05,
            settings=settings,
        )
        qa_report = validate_targeted_revision_qa_report(
            gemini_result.data,
            selected_issues,
            products,
            marketing_assets=assets,
            source_output=source_output,
        )
        meta = _gemini_generation_meta("QAComplianceAgent", "qa_targeted_revision_review", gemini_result)
        step.model = gemini_result.model
        step.output = {"qa_report": qa_report, "generation": meta}
        return {
            "qa_report": qa_report,
            "agent_execution": _append_agent_execution(state, meta),
        }


def human_approval_node(db: Session, state: GraphState) -> GraphState:
    with step_log(db, state["run_id"], "HumanApprovalNode", "human_approval", state.get("qa_report")) as step:
        report = {
            "status": "awaiting_approval",
            "normalized_request": state.get("normalized_request"),
            "geo_scope": state.get("geo_scope") or (state.get("normalized_request") or {}).get("geo_scope"),
            "source_items": state.get("source_items", []),
            "candidate_pool_summary": state.get("candidate_pool_summary", {}),
            "retrieved_documents": state.get("retrieved_documents", []),
            "data_gap_report": state.get("data_gap_report", {}),
            "capability_routing": state.get("capability_routing", {}),
            "enrichment_plan_fragments": state.get("enrichment_plan_fragments", []),
            "enrichment_plan": state.get("enrichment_plan", {}),
            "enrichment_summary": state.get("enrichment_summary", {}),
            "evidence_profile": state.get("evidence_profile", {}),
            "productization_advice": state.get("productization_advice", {}),
            "data_coverage": state.get("data_coverage", {}),
            "unresolved_gaps": state.get("unresolved_gaps", []),
            "source_confidence": state.get("source_confidence", 0.0),
            "ui_highlights": state.get("ui_highlights", []),
            "research_summary": state.get("research_summary", {}),
            "products": state.get("product_ideas", []),
            "marketing_assets": state.get("marketing_assets", []),
            "qa_report": state.get("qa_report", {}),
            "agent_execution": state.get("agent_execution", []),
            "cost_summary": _cost_summary(db, state["run_id"]),
            "revision": _run_revision_metadata(db, state["run_id"], state),
            "approval": {
                "required": True,
                "status": "awaiting_approval",
                "message": "검토 승인 전 외부 저장/export는 실행되지 않습니다.",
            },
        }
        step.output = report
        return {"approval": report["approval"], "final_report": report}


GEO_RESOLUTION_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["locations", "excluded_locations", "allow_nationwide", "unsupported_locations"],
    "properties": {
        "locations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "role", "normalized_text", "is_foreign"],
            },
        },
        "resolved_locations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "text",
                    "role",
                    "name",
                    "ldong_regn_cd",
                    "ldong_signgu_cd",
                    "confidence",
                    "reason",
                ],
                "properties": {
                    "text": {"type": "string"},
                    "role": {"type": "string"},
                    "name": {"type": "string"},
                    "ldong_regn_cd": {"type": "string"},
                    "ldong_signgu_cd": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                    "sub_area_terms": {"type": "array"},
                    "keywords": {"type": "array"},
                },
            },
        },
        "clarification_candidates": {"type": "array", "items": {"type": "object"}},
        "excluded_locations": {"type": "array"},
        "allow_nationwide": {"type": "boolean"},
        "unsupported_locations": {"type": "array"},
        "notes": {"type": "array"},
    },
}


PLANNER_RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "user_intent",
        "product_count",
        "target_customer",
        "preferred_themes",
        "avoid",
        "period",
        "output_language",
        "request_type",
        "product_generation_constraints",
        "evidence_requirements",
    ],
    "properties": {
        "user_intent": {"type": "string"},
        "product_count": {"type": "integer"},
        "target_customer": {"type": "string"},
        "preferred_themes": {"type": "array", "items": {"type": "string"}},
        "avoid": {"type": "array", "items": {"type": "string"}},
        "period": {"type": "string"},
        "output_language": {"type": "string"},
        "request_type": {"type": "string"},
        "product_generation_constraints": {"type": "array", "items": {"type": "string"}},
        "evidence_requirements": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}


RESEARCH_SYNTHESIS_RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "research_brief",
        "candidate_card_guidance",
        "usable_claims",
        "restricted_claims",
        "operational_unknowns",
        "unresolved_gaps",
        "product_generation_guidance",
        "qa_risk_notes",
    ],
    "properties": {
        "research_brief": {"type": "string"},
        "candidate_card_guidance": {"type": "array", "items": {"type": "object"}},
        "candidate_evidence_cards": {"type": "array", "items": {"type": "object"}},
        "usable_claims": {"type": "array", "items": {"type": "string"}},
        "restricted_claims": {"type": "array", "items": {"type": "string"}},
        "operational_unknowns": {"type": "array", "items": {"type": "string"}},
        "unresolved_gaps": {"type": "array", "items": {"type": "object"}},
        "product_generation_guidance": {"type": "array", "items": {"type": "string"}},
        "qa_risk_notes": {"type": "array", "items": {"type": "string"}},
    },
}


PRODUCT_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["products"],
    "properties": {
        "products": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "title",
                    "one_liner",
                    "target_customer",
                    "core_value",
                    "itinerary",
                    "estimated_duration",
                    "operation_difficulty",
                    "source_ids",
                    "assumptions",
                    "not_to_claim",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "one_liner": {"type": "string"},
                    "target_customer": {"type": "string"},
                    "core_value": {"type": "array", "items": {"type": "string"}},
                    "itinerary": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["order", "name", "source_id"],
                            "properties": {
                                "order": {"type": "integer"},
                                "name": {"type": "string"},
                                "source_id": {"type": "string"},
                            },
                        },
                    },
                    "estimated_duration": {"type": "string"},
                    "operation_difficulty": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "assumptions": {"type": "array", "items": {"type": "string"}},
                    "not_to_claim": {"type": "array", "items": {"type": "string"}},
                    "evidence_summary": {"type": "string"},
                    "needs_review": {"type": "array", "items": {"type": "string"}},
                    "coverage_notes": {"type": "array", "items": {"type": "string"}},
                    "claim_limits": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}

MARKETING_PRODUCT_BATCH_SIZE = 3
MARKETING_BATCH_MAX_OUTPUT_TOKENS = 24576


MARKETING_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["marketing_assets"],
    "properties": {
        "marketing_assets": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["product_id", "sales_copy", "faq", "search_keywords"],
                "properties": {
                    "product_id": {"type": "string"},
                    "sales_copy": {"type": "object"},
                    "faq": {"type": "array", "items": {"type": "object"}},
                    "search_keywords": {"type": "array", "items": {"type": "string"}},
                    "evidence_disclaimer": {"type": "string"},
                    "claim_limits": {"type": "array", "items": {"type": "string"}},
                    "marketing_strategy": {"type": "object"},
                    "landing_page_outline": {"type": "object"},
                    "faq_strategy": {"type": "object"},
                    "sns_campaign": {"type": "object"},
                    "claim_strategy": {
                        "type": "object",
                        "properties": {
                            "usable_claims": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["claim", "evidence_basis"],
                                    "properties": {
                                        "claim": {"type": "string"},
                                        "evidence_basis": {"type": "string"},
                                    },
                                },
                            },
                            "caution_phrasing": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["phrase", "reason"],
                                    "properties": {
                                        "phrase": {"type": "string"},
                                        "reason": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
    },
}

REVISION_PATCH_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["product_patches", "marketing_patches"],
    "properties": {
        "product_patches": {"type": "array"},
        "marketing_patches": {"type": "array"},
        "marketing_field_patches": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["product_id", "field_path", "value"],
                "properties": {
                    "product_id": {"type": "string"},
                    "field_path": {"type": "string"},
                    "value": {},
                },
            },
        },
        "notes": {"type": "array"},
    },
}

TARGETED_QA_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["summary", "items"],
    "properties": {
        "summary": {"type": "string"},
        "items": {"type": "array"},
    },
}

QA_RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "overall_status",
        "summary",
        "issues",
        "pass_count",
        "needs_review_count",
        "fail_count",
    ],
}


def validate_geo_resolution_hints(payload: dict[str, Any]) -> dict[str, Any]:
    locations: list[dict[str, Any]] = []
    for item in payload.get("locations") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        normalized_text = str(item.get("normalized_text") or text).strip()
        if not text and not normalized_text:
            continue
        role = str(item.get("role") or "primary").strip()
        if role not in {"primary", "nearby_anchor", "comparison", "excluded"}:
            role = "primary"
        locations.append(
            {
                "text": text,
                "normalized_text": normalized_text,
                "role": role,
                "is_foreign": item.get("is_foreign") is True,
            }
        )
    resolved_locations: list[dict[str, Any]] = []
    for item in payload.get("resolved_locations") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("matched_text") or "").strip()
        role = str(item.get("role") or "primary").strip()
        if role not in {"primary", "nearby_anchor", "comparison", "excluded"}:
            role = "primary"
        regn_cd = str(item.get("ldong_regn_cd") or "").strip()
        signgu_cd = str(item.get("ldong_signgu_cd") or "").strip()
        if not regn_cd:
            continue
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        resolved_locations.append(
            {
                "text": text,
                "role": role,
                "name": str(item.get("name") or "").strip(),
                "ldong_regn_cd": regn_cd,
                "ldong_signgu_cd": signgu_cd,
                "confidence": max(0.0, min(1.0, confidence)),
                "reason": str(item.get("reason") or "").strip(),
                "sub_area_terms": _string_list(item.get("sub_area_terms"))[:8],
                "keywords": _string_list(item.get("keywords"))[:8],
            }
        )
    return {
        "locations": locations[:12],
        "resolved_locations": resolved_locations[:12],
        "clarification_candidates": payload.get("clarification_candidates") if isinstance(payload.get("clarification_candidates"), list) else [],
        "excluded_locations": _string_list(payload.get("excluded_locations"))[:12],
        "allow_nationwide": payload.get("allow_nationwide") is True,
        "unsupported_locations": _string_list(payload.get("unsupported_locations"))[:12],
        "notes": _string_list(payload.get("notes"))[:12],
    }


def validate_planner_output(payload: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    default = _default_normalized_request(request)
    preferred_themes = _safe_korean_string_list(payload.get("preferred_themes"), "planner.preferred_themes")
    preferred_themes = _merge_explicit_request_themes(
        preferred_themes=preferred_themes,
        request=request,
        planner_intent=payload.get("user_intent"),
        fallback=default["preferred_themes"],
    )
    avoid = _safe_korean_string_list(payload.get("avoid"), "planner.avoid")
    constraints = _safe_korean_string_list(
        payload.get("product_generation_constraints"),
        "planner.product_generation_constraints",
    )
    evidence_requirements = _safe_korean_string_list(
        payload.get("evidence_requirements"),
        "planner.evidence_requirements",
    )
    notes = _safe_korean_string_list(payload.get("notes"), "planner.notes")
    period = str(payload.get("period") or request.get("period") or default.get("period") or "").strip()
    output_language = str(payload.get("output_language") or request.get("output_language") or "ko").strip()
    if output_language not in {"ko", "en"}:
        output_language = "ko"

    normalized = {
        **default,
        "user_intent": _safe_korean_text(
            payload.get("user_intent"),
            "planner.user_intent",
            fallback=default["user_intent"],
        ),
        "request_type": str(payload.get("request_type") or default["request_type"]),
        "period": period or default.get("period"),
        "start_date": _period_start(period or request.get("period")),
        "end_date": _period_end(period or request.get("period")),
        "target_customer": _safe_korean_text(
            payload.get("target_customer"),
            "planner.target_customer",
            fallback=default["target_customer"],
        ),
        "product_count": _coerce_product_count(payload.get("product_count"), fallback=default["product_count"]),
        "preferred_themes": preferred_themes or default["preferred_themes"],
        "avoid": avoid or default["avoid"],
        "output_language": output_language,
        "product_generation_constraints": constraints or default["product_generation_constraints"],
        "evidence_requirements": evidence_requirements or default["evidence_requirements"],
        "planner_notes": notes,
        "message": request.get("message"),
    }
    # Planner must not resolve TourAPI/ldong codes. Region text stays as a user hint for GeoResolver.
    normalized["region_name"] = request.get("region")
    return normalized


def _merge_explicit_request_themes(
    *,
    preferred_themes: list[str],
    request: dict[str, Any],
    planner_intent: Any,
    fallback: list[str],
) -> list[str]:
    message = str(request.get("message") or "")
    intent_text = str(planner_intent or "")
    explicit_themes = _explicit_theme_terms_from_text(f"{message}\n{intent_text}")
    if not explicit_themes:
        return preferred_themes or fallback

    request_preferences = _string_list(request.get("preferences"))
    default_ui_preferences = {"야간 관광", "축제"}
    merged: list[str] = []
    for theme in [*explicit_themes, *preferred_themes, *request_preferences]:
        if not theme:
            continue
        if theme in default_ui_preferences and theme not in explicit_themes and not _theme_mentioned_in_text(theme, message):
            continue
        if theme not in merged:
            merged.append(theme)
    return merged or explicit_themes or preferred_themes or fallback


def _theme_mentioned_in_text(theme: str, text: str) -> bool:
    if theme in text:
        return True
    if theme == "야간 관광":
        return "야간" in text or "밤" in text
    if theme == "축제":
        return "축제" in text or "페스티벌" in text
    return False


def _explicit_theme_terms_from_text(text: str) -> list[str]:
    checks = [
        (("웰니스", "힐링"), "웰니스"),
        (("반려동물", "반려", "펫", "강아지"), "반려동물"),
        (("오디오", "해설"), "오디오 해설"),
        (("의료", "메디컬"), "의료관광"),
    ]
    themes: list[str] = []
    for tokens, label in checks:
        if any(token in text for token in tokens) and label not in themes:
            themes.append(label)
    return themes


def validate_products(
    payload: dict[str, Any],
    normalized: dict[str, Any],
    docs: list[dict[str, Any]],
    *,
    evidence_context: dict[str, Any] | None = None,
    qa_settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    products = payload.get("products")
    requested_count = _desired_product_count(normalized, fallback=1)
    effective_count = _effective_product_count(normalized, docs)
    if not isinstance(products, list) or not products:
        raise ValueError("Gemini product response has invalid products")
    if len(products) < effective_count:
        raise ValueError(
            f"Gemini product response returned {len(products)} products but {effective_count} products are required"
        )
    product_count = effective_count
    available_source_ids = [str(doc["doc_id"]) for doc in docs if doc.get("doc_id")]
    allowed_source_ids = set(available_source_ids)
    if not allowed_source_ids:
        raise ValueError("TourAPI source documents are required for product validation")
    evidence_context = evidence_context or {}
    qa_settings = qa_settings or {}
    context_review = _needs_review_from_context(evidence_context)
    context_claim_limits = _claim_limits_from_context(evidence_context)
    context_coverage_notes = _coverage_notes_from_context(evidence_context)
    avoid_limits = [f"요청 avoid 기준: {item}" for item in _string_list(qa_settings.get("avoid"))]
    validated = []
    source_aliases = _source_id_alias_map(docs)
    shortage_note = _product_count_shortage_note(requested_count, product_count, len(available_source_ids))
    for index, product in enumerate(products[:product_count]):
        if not isinstance(product, dict):
            raise ValueError("Product item must be an object")
        raw_source_ids = _string_list(product.get("source_ids"))
        source_ids: list[str] = []
        unresolved_invalid_source_ids: list[str] = []
        source_id_diagnostics: list[dict[str, Any]] = []
        repaired_source_id = False
        for raw_source_id in raw_source_ids:
            if raw_source_id in allowed_source_ids:
                source_ids.append(raw_source_id)
                source_id_diagnostics.append(
                    _source_id_guardrail_diagnostic(
                        product_id=str(product.get("id") or f"product_{index + 1}"),
                        raw_source_id=raw_source_id,
                        action="accepted",
                        reason="provided_source_id_allowed",
                        normalized_to=raw_source_id,
                    )
                )
                continue
            canonical_source_id = source_aliases.get(_normalize_source_alias(raw_source_id))
            if canonical_source_id and canonical_source_id in allowed_source_ids:
                source_ids.append(canonical_source_id)
                repaired_source_id = True
                source_id_diagnostics.append(
                    _source_id_guardrail_diagnostic(
                        product_id=str(product.get("id") or f"product_{index + 1}"),
                        raw_source_id=raw_source_id,
                        action="normalized",
                        reason="source_id_alias_resolved_to_single_allowed_document",
                        normalized_to=canonical_source_id,
                    )
                )
                continue
            unresolved_invalid_source_ids.append(raw_source_id)
            source_id_diagnostics.append(
                _source_id_guardrail_diagnostic(
                    product_id=str(product.get("id") or f"product_{index + 1}"),
                    raw_source_id=raw_source_id,
                    action="excluded",
                    reason="source_id_not_in_allowed_documents",
                )
            )
        source_ids = _dedupe_texts(source_ids)
        inferred_source_ids: list[str] = []
        if not source_ids:
            inferred_source_ids = _infer_source_ids_from_product_text(product, docs)
            if inferred_source_ids:
                source_ids = inferred_source_ids
                for inferred_source_id in inferred_source_ids:
                    source_id_diagnostics.append(
                        _source_id_guardrail_diagnostic(
                            product_id=str(product.get("id") or f"product_{index + 1}"),
                            raw_source_id="",
                            action="normalized",
                            reason="source_id_inferred_from_exact_evidence_title_match",
                            normalized_to=inferred_source_id,
                        )
                    )
        source_ids = _expand_product_source_ids_with_linked_evidence(source_ids, docs, max_ids=5)
        review_notes = _safe_korean_string_list(product.get("needs_review"), "products[].needs_review")
        if not source_ids:
            review_notes.append("상품에 연결된 근거 문서가 없어 게시 전 근거 연결이 필요합니다.")
        if shortage_note:
            review_notes.append(shortage_note)
        assumptions = (
            _safe_korean_string_list(product.get("assumptions"), "products[].assumptions")
            or ["세부 가격과 예약 가능 여부는 운영자가 확정해야 합니다."]
        )
        not_to_claim = (
            _safe_korean_string_list(product.get("not_to_claim"), "products[].not_to_claim")
            or ["가격 확정", "항상 운영", "예약 즉시 확정"]
        )
        claim_limits = _dedupe_texts(
            [
                *_safe_korean_string_list(product.get("claim_limits"), "products[].claim_limits"),
                *not_to_claim,
                *context_claim_limits,
                *avoid_limits,
            ]
        )[:10]
        needs_review = _dedupe_texts([*review_notes, *context_review])[:10]
        coverage_notes = _dedupe_texts(
            [
                *_safe_korean_string_list(product.get("coverage_notes"), "products[].coverage_notes"),
                *([shortage_note] if shortage_note else []),
                *context_coverage_notes,
            ]
        )[:8]
        product_id = str(product.get("id") or f"product_{index + 1}")
        validated_product = {
            "id": product_id,
            "title": _required_string(product, "title"),
            "one_liner": _required_string(product, "one_liner"),
            "target_customer": str(product.get("target_customer") or normalized.get("target_customer") or "외국인"),
            "core_value": _korean_string_list(product.get("core_value"), "products[].core_value")[:5] or ["지역 경험"],
            "itinerary": _validate_itinerary(product.get("itinerary"), source_ids),
            "estimated_duration": _korean_text(
                str(product.get("estimated_duration") or "3~4시간"),
                "products[].estimated_duration",
            ),
            "operation_difficulty": _korean_text(
                _normalize_difficulty(product.get("operation_difficulty")),
                "products[].operation_difficulty",
            ),
            "source_ids": source_ids[:5],
            "assumptions": assumptions[:8],
            "not_to_claim": not_to_claim[:8],
            "evidence_summary": _normalize_evidence_summary(
                product.get("evidence_summary"),
                source_ids,
                docs,
            ),
            "needs_review": needs_review,
            "coverage_notes": coverage_notes,
            "claim_limits": claim_limits,
            "review_notes": _product_display_notes(
                needs_review=needs_review,
                coverage_notes=coverage_notes,
                claim_limits=claim_limits,
            ),
        }
        product_source_id_diagnostics = [
            {**diagnostic, "product_id": product_id}
            for diagnostic in source_id_diagnostics
            if diagnostic.get("action") != "accepted"
        ]
        if product_source_id_diagnostics:
            validated_product["internal_diagnostics"] = product_source_id_diagnostics
        validated.append(validated_product)
    return validated


def _source_id_guardrail_diagnostic(
    *,
    product_id: str,
    raw_source_id: str,
    action: str,
    reason: str,
    normalized_to: str | None = None,
) -> dict[str, Any]:
    diagnostic = {
        "category": "source_id_guardrail",
        "product_id": product_id,
        "invalid_source_id": raw_source_id,
        "reason": reason,
        "action": action,
    }
    if normalized_to:
        diagnostic["normalized_to"] = normalized_to
    return diagnostic


def validate_marketing_assets(
    payload: dict[str, Any],
    products: list[dict[str, Any]],
    *,
    evidence_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    assets = payload.get("marketing_assets")
    if not isinstance(assets, list):
        raise ValueError("Gemini marketing response has invalid marketing_assets")
    product_ids = {product["id"] for product in products}
    by_product_id = {asset.get("product_id"): asset for asset in assets if isinstance(asset, dict)}
    validated = []
    for product in products:
        asset = by_product_id.get(product["id"])
        if not isinstance(asset, dict):
            raise ValueError(f"Missing marketing asset for {product['id']}")
        sales_copy = _normalize_sales_copy(asset.get("sales_copy"), product)
        faq = _validate_faq(asset.get("faq"), require_korean=True)
        if not faq:
            raise ValueError(f"marketing_assets[{product['id']}].faq must not be empty")
        if not _faq_includes_buyer_value(faq):
            raise ValueError(
                f"marketing_assets[{product['id']}].faq must include at least one buyer-facing value question"
            )
        search_keywords = _normalize_search_keywords(asset.get("search_keywords"), product)[:12]
        if not search_keywords:
            raise ValueError(f"marketing_assets[{product['id']}].search_keywords must not be empty")
        evidence_disclaimer = _safe_korean_text(
            asset.get("evidence_disclaimer"),
            "marketing_assets[].evidence_disclaimer",
            fallback=_marketing_evidence_disclaimer(product, evidence_context or {}),
        )
        _assert_marketing_user_text(evidence_disclaimer, "marketing_assets[].evidence_disclaimer")
        validated_asset = {
            "product_id": product["id"] if asset.get("product_id") in product_ids else product["id"],
            "sales_copy": sales_copy,
            "faq": faq,
            "search_keywords": search_keywords,
            "evidence_disclaimer": evidence_disclaimer,
            "claim_limits": _dedupe_texts(
                [
                    *_safe_korean_string_list(asset.get("claim_limits"), "marketing_assets[].claim_limits"),
                    *_string_list(product.get("claim_limits")),
                    *_string_list(product.get("not_to_claim")),
                ]
            )[:10],
        }
        for field_name, normalizer in [
            ("marketing_strategy", _normalize_marketing_strategy),
            ("landing_page_outline", _normalize_landing_page_outline),
            ("faq_strategy", _normalize_faq_strategy),
            ("sns_campaign", _normalize_sns_campaign),
            ("claim_strategy", _normalize_claim_strategy),
        ]:
            if field_name in asset and asset.get(field_name) not in (None, ""):
                validated_asset[field_name] = normalizer(asset.get(field_name), product["id"])
        if "sns_campaign" not in validated_asset:
            raise ValueError(f"marketing_assets[{product['id']}].sns_campaign must be present")
        validated.append(validated_asset)
    return validated


def _faq_includes_buyer_value(faq: list[dict[str, str]]) -> bool:
    """Return whether FAQ contains at least one purchase-decision question.

    This intentionally checks broad semantic signals instead of product-specific
    examples. Operational-only FAQ still belongs in the output, but it must not
    be the entire FAQ set.
    """
    buyer_value_terms = [
        "누구",
        "추천",
        "어떤 경험",
        "기대",
        "좋은",
        "어울",
        "외국인",
        "관광객",
        "처음",
        "가족",
        "친구",
        "커플",
        "혼자",
        "아이",
        "포인트",
        "매력",
        "즐길",
        "느낄",
        "배울",
    ]
    operational_only_terms = [
        "가격",
        "요금",
        "무료",
        "예약",
        "운영시간",
        "휴무",
        "휴관",
        "집결",
        "우천",
        "취소",
        "변경",
        "확정",
        "문의",
        "확인",
    ]
    for item in faq:
        text = f"{item.get('question', '')} {item.get('answer', '')}"
        if any(term in text for term in buyer_value_terms):
            return True
    return not faq or not all(
        any(term in f"{item.get('question', '')} {item.get('answer', '')}" for term in operational_only_terms)
        for item in faq
    )


def _assert_marketing_user_text(text: str, field_path: str) -> None:
    raw = str(text or "")
    lowered = raw.lower()
    blocked_raw_terms = [
        "not_to_claim",
        "claim_limits",
        "source_id",
        "source_ids",
        "doc_id",
        "field_path",
        "missing_pet_policy",
        "needs_review",
        "data_coverage",
        "unresolved_gaps",
    ]
    blocked_korean_terms = [
        "금지 claim",
        "금지 클레임",
        "내부 필드",
        "필드 경로",
        "소스 아이디",
    ]
    if any(term in lowered for term in blocked_raw_terms) or any(term in raw for term in blocked_korean_terms):
        raise ValueError(f"{field_path} contains internal diagnostic terminology")


def _required_marketing_text(payload: dict[str, Any], key: str, field_path: str) -> str:
    value = _korean_text(str(payload.get(key) or ""), f"{field_path}.{key}")
    _assert_marketing_user_text(value, f"{field_path}.{key}")
    return value


def _optional_marketing_text(payload: dict[str, Any], key: str, field_path: str) -> str:
    value = payload.get(key)
    if value in (None, ""):
        return ""
    text = _korean_text(str(value), f"{field_path}.{key}")
    _assert_marketing_user_text(text, f"{field_path}.{key}")
    return text


def _marketing_text_list(value: Any, field_path: str, *, limit: int = 8) -> list[str]:
    items = [_korean_text(item, field_path) for item in _string_list(value)[:limit]]
    for item in items:
        _assert_marketing_user_text(item, field_path)
    return items


def _marketing_record_list(value: Any, field_path: str, *, limit: int = 8) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_path} must be an array")
    records: list[dict[str, Any]] = []
    for item in value[:limit]:
        if not isinstance(item, dict):
            raise ValueError(f"{field_path} items must be objects")
        records.append(item)
    return records


def _normalize_marketing_strategy(value: Any, product_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"marketing_assets[{product_id}].marketing_strategy must be an object")
    field_path = f"marketing_assets[{product_id}].marketing_strategy"
    target = value.get("target_segment") if isinstance(value.get("target_segment"), dict) else {}
    positioning = value.get("product_positioning") if isinstance(value.get("product_positioning"), dict) else {}
    key_selling_points: list[dict[str, str]] = []
    for item in _marketing_record_list(value.get("key_selling_points"), f"{field_path}.key_selling_points", limit=6):
        point = _required_marketing_text(item, "point", f"{field_path}.key_selling_points[]")
        evidence_basis = _required_marketing_text(item, "evidence_basis", f"{field_path}.key_selling_points[]")
        key_selling_points.append(
            {
                "point": point,
                "evidence_basis": evidence_basis,
                "usage_note": _optional_marketing_text(item, "usage_note", f"{field_path}.key_selling_points[]"),
            }
        )
    if not key_selling_points:
        raise ValueError(f"{field_path}.key_selling_points must include evidence-backed Selling Points")

    customer_objections: list[dict[str, Any]] = []
    for item in _marketing_record_list(value.get("customer_objections"), f"{field_path}.customer_objections", limit=6):
        customer_objections.append(
            {
                "objection": _required_marketing_text(item, "objection", f"{field_path}.customer_objections[]"),
                "response": _required_marketing_text(item, "response", f"{field_path}.customer_objections[]"),
                "requires_confirmation": item.get("requires_confirmation") is True,
            }
        )

    operation_checklist: list[dict[str, str]] = []
    for item in _marketing_record_list(value.get("operation_checklist"), f"{field_path}.operation_checklist", limit=8):
        operation_checklist.append(
            {
                "item": _required_marketing_text(item, "item", f"{field_path}.operation_checklist[]"),
                "reason": _required_marketing_text(item, "reason", f"{field_path}.operation_checklist[]"),
            }
        )

    return {
        "target_segment": {
            "primary": _required_marketing_text(target, "primary", f"{field_path}.target_segment"),
            "secondary": _marketing_text_list(target.get("secondary"), f"{field_path}.target_segment.secondary", limit=5),
            "foreigner_context": _optional_marketing_text(target, "foreigner_context", f"{field_path}.target_segment"),
        },
        "product_positioning": {
            "summary": _required_marketing_text(positioning, "summary", f"{field_path}.product_positioning"),
            "differentiation": _required_marketing_text(positioning, "differentiation", f"{field_path}.product_positioning"),
        },
        "key_selling_points": key_selling_points,
        "customer_objections": customer_objections,
        "operation_checklist": operation_checklist,
    }


def _normalize_landing_page_outline(value: Any, product_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"marketing_assets[{product_id}].landing_page_outline must be an object")
    field_path = f"marketing_assets[{product_id}].landing_page_outline"
    hero = value.get("hero") if isinstance(value.get("hero"), dict) else {}
    evidence_points: list[dict[str, str]] = []
    for item in _marketing_record_list(value.get("evidence_backed_points"), f"{field_path}.evidence_backed_points", limit=6):
        evidence_points.append(
            {
                "point": _required_marketing_text(item, "point", f"{field_path}.evidence_backed_points[]"),
                "evidence_basis": _required_marketing_text(item, "evidence_basis", f"{field_path}.evidence_backed_points[]"),
            }
        )
    return {
        "hero": {
            "headline": _required_marketing_text(hero, "headline", f"{field_path}.hero"),
            "subheadline": _required_marketing_text(hero, "subheadline", f"{field_path}.hero"),
            "hook": _required_marketing_text(hero, "hook", f"{field_path}.hero"),
        },
        "why_this_product": _marketing_text_list(value.get("why_this_product"), f"{field_path}.why_this_product", limit=6),
        "evidence_backed_points": evidence_points,
        "practical_info": _marketing_text_list(value.get("practical_info"), f"{field_path}.practical_info", limit=8),
    }


def _normalize_faq_strategy(value: Any, product_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"marketing_assets[{product_id}].faq_strategy must be an object")
    buyer_faq = _validate_faq(value.get("buyer_faq"), require_korean=True)[:6]
    operation_faq = _validate_faq(value.get("operation_faq"), require_korean=True)[:6]
    if not buyer_faq and not operation_faq:
        raise ValueError(f"marketing_assets[{product_id}].faq_strategy must include buyer_faq or operation_faq")
    for item in [*buyer_faq, *operation_faq]:
        _assert_marketing_user_text(item.get("question", ""), f"marketing_assets[{product_id}].faq_strategy.question")
        _assert_marketing_user_text(item.get("answer", ""), f"marketing_assets[{product_id}].faq_strategy.answer")
    return {"buyer_faq": buyer_faq, "operation_faq": operation_faq}


def _normalize_sns_campaign(value: Any, product_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"marketing_assets[{product_id}].sns_campaign must be an object")
    field_path = f"marketing_assets[{product_id}].sns_campaign"
    campaign_angles: list[dict[str, str]] = []
    for item in _marketing_record_list(value.get("campaign_angles"), f"{field_path}.campaign_angles", limit=5):
        campaign_angles.append(
            {
                "angle": _required_marketing_text(item, "angle", f"{field_path}.campaign_angles[]"),
                "rationale": _required_marketing_text(item, "rationale", f"{field_path}.campaign_angles[]"),
            }
        )
    posts: list[dict[str, Any]] = []
    for item in _marketing_record_list(value.get("posts"), f"{field_path}.posts", limit=6):
        post_format = str(item.get("format") or "feed").strip().lower()
        if post_format not in {"feed", "reels", "story"}:
            raise ValueError(f"{field_path}.posts[].format must be feed, reels, or story")
        posts.append(
            {
                "format": post_format,
                "hook": _required_marketing_text(item, "hook", f"{field_path}.posts[]"),
                "body": _required_marketing_text(item, "body", f"{field_path}.posts[]"),
                "hashtags": _marketing_text_list(item.get("hashtags"), f"{field_path}.posts[].hashtags", limit=8),
            }
        )
    return {
        "campaign_angles": campaign_angles,
        "posts": posts,
        "visual_direction": _marketing_text_list(value.get("visual_direction"), f"{field_path}.visual_direction", limit=8),
    }


def _normalize_claim_strategy(value: Any, product_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"marketing_assets[{product_id}].claim_strategy must be an object")
    field_path = f"marketing_assets[{product_id}].claim_strategy"
    usable_claims: list[dict[str, str]] = []
    raw_usable_claims = value.get("usable_claims")
    if raw_usable_claims in (None, ""):
        raw_usable_claims = []
    if not isinstance(raw_usable_claims, list):
        raise ValueError(f"{field_path}.usable_claims must be an array")
    for item in raw_usable_claims[:6]:
        if isinstance(item, str):
            claim = _korean_text(item, f"{field_path}.usable_claims[]")
            _assert_marketing_user_text(claim, f"{field_path}.usable_claims[]")
            evidence_basis = claim
        elif isinstance(item, dict):
            claim = _required_marketing_text(item, "claim", f"{field_path}.usable_claims[]")
            evidence_basis = _required_marketing_text(item, "evidence_basis", f"{field_path}.usable_claims[]")
        else:
            raise ValueError(f"{field_path}.usable_claims items must be objects or Korean strings")
        if _is_unsupported_operational_claim(claim):
            raise ValueError(f"{field_path}.usable_claims contains unsupported operational claim")
        usable_claims.append({"claim": claim, "evidence_basis": evidence_basis})
    if not usable_claims:
        raise ValueError(f"{field_path}.usable_claims must include evidence-backed usable claims")
    caution_phrasing: list[dict[str, str]] = []
    for item in _marketing_record_list(value.get("caution_phrasing"), f"{field_path}.caution_phrasing", limit=12):
        phrase = _optional_marketing_text(item, "phrase", f"{field_path}.caution_phrasing[]") or _optional_marketing_text(item, "claim", f"{field_path}.caution_phrasing[]")
        reason = _required_marketing_text(item, "reason", f"{field_path}.caution_phrasing[]")
        if phrase:
            caution_phrasing.append({"phrase": phrase, "reason": reason})
    # Backward-compatible input normalization: old strategy packs may still contain
    # separate confirmation/avoid fields, but normalized new output exposes only
    # one user-facing caution_phrasing collection.
    for item in _marketing_record_list(value.get("needs_confirmation"), f"{field_path}.needs_confirmation", limit=8):
        caution_phrasing.append(
            {
                "phrase": _required_marketing_text(item, "claim", f"{field_path}.needs_confirmation[]"),
                "reason": _required_marketing_text(item, "reason", f"{field_path}.needs_confirmation[]"),
            }
        )
    for item in _marketing_record_list(value.get("avoid_phrasing"), f"{field_path}.avoid_phrasing", limit=8):
        caution_phrasing.append(
            {
                "phrase": _required_marketing_text(item, "phrase", f"{field_path}.avoid_phrasing[]"),
                "reason": _required_marketing_text(item, "reason", f"{field_path}.avoid_phrasing[]"),
            }
        )
    return {
        "usable_claims": usable_claims,
        "caution_phrasing": caution_phrasing,
    }


def _is_unsupported_operational_claim(text: str) -> bool:
    terms = [
        "무료",
        "가격",
        "요금",
        "할인",
        "운영시간",
        "예약",
        "상시",
        "즉시 확정",
        "안전",
        "무사고",
        "치료",
        "의료",
        "효능",
        "건강 개선",
        "외국어 지원",
        "영어 지원",
        "중국어 지원",
        "일본어 지원",
    ]
    return any(term in text for term in terms)


def _desired_product_count(normalized: dict[str, Any], fallback: int) -> int:
    try:
        count = int(normalized.get("product_count") or fallback)
    except (TypeError, ValueError):
        count = fallback
    return max(1, min(MAX_PRODUCT_COUNT, count))


def _effective_product_count(normalized: dict[str, Any], docs: list[dict[str, Any]], fallback: int = 1) -> int:
    return _desired_product_count(normalized, fallback=fallback)


def _product_count_shortage_note(requested_count: int, generated_count: int, evidence_count: int) -> str:
    return ""


def _safe_korean_text(value: Any, field_path: str, *, fallback: str) -> str:
    text = str(value or "").strip()
    if text and _has_korean(text):
        return text
    return _korean_text(fallback, field_path)


def _safe_korean_string_list(value: Any, field_path: str) -> list[str]:
    values: list[str] = []
    for item in _string_list(value):
        if _has_korean(item):
            values.append(item)
        else:
            values.append(f"{_field_path_label(field_path)} 확인 필요: {item}")
    return values


def _should_retry_marketing_validation(exc: ValueError) -> bool:
    message = str(exc)
    if message.startswith("Missing marketing asset for "):
        return True
    if "marketing_assets" not in message and not any(
        field in message
        for field in [
            "sales_copy",
            "faq",
                    "search_keywords",
            "marketing_strategy",
            "landing_page_outline",
            "faq_strategy",
            "sns_campaign",
            "claim_strategy",
        ]
    ):
        return False
    return (
        "must be written in Korean" in message
        or "must not be empty" in message
        or "internal diagnostic terminology" in message
        or "unsupported operational claim" in message
        or "must include" in message
        or "must be an object" in message
    )


def _dedupe_texts(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def _source_id_alias_map(docs: list[dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()
    primary_by_key: dict[str, str] = {}
    for doc in docs:
        doc_id = str(doc.get("doc_id") or "").strip()
        if not doc_id:
            continue
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        source_family = str(metadata.get("source_family") or metadata.get("source") or "").lower()
        keys = {
            doc_id,
            str(doc.get("source_item_id") or "").strip(),
            str(metadata.get("source_item_id") or "").strip(),
            str(doc.get("content_id") or "").strip(),
            str(metadata.get("content_id") or "").strip(),
        }
        content_id = str(metadata.get("content_id") or doc.get("content_id") or "").strip()
        if content_id:
            keys.add(f"tourapi:content:{content_id}")
            keys.add(f"doc:tourapi:content:{content_id}")
        for key in keys:
            normalized_key = _normalize_source_alias(key)
            if not normalized_key:
                continue
            if _is_primary_tourapi_document(doc_id, source_family):
                primary_by_key[normalized_key] = doc_id
            if normalized_key in aliases and aliases[normalized_key] != doc_id:
                ambiguous.add(normalized_key)
                continue
            aliases[normalized_key] = doc_id
    for key in ambiguous:
        if key in primary_by_key:
            aliases[key] = primary_by_key[key]
        else:
            aliases.pop(key, None)
    return aliases


def _normalize_source_alias(value: Any) -> str:
    return str(value or "").strip()


def _is_primary_tourapi_document(doc_id: str, source_family: str) -> bool:
    return doc_id.startswith("doc:tourapi:content:") or source_family in {"kto_tourapi_kor", "tourapi"}


def _infer_source_ids_from_product_text(product: dict[str, Any], docs: list[dict[str, Any]]) -> list[str]:
    product_text = _normalized_evidence_link_text(
        " ".join(
            [
                str(product.get("title") or ""),
                str(product.get("one_liner") or ""),
                " ".join(_string_list(product.get("core_value"))),
                _itinerary_text(product.get("itinerary")),
                str(product.get("evidence_summary") or ""),
            ]
        )
    )
    if not product_text:
        return []
    scored: list[tuple[int, int, str]] = []
    for index, doc in enumerate(docs):
        doc_id = str(doc.get("doc_id") or "").strip()
        title = str(doc.get("title") or "").strip()
        if not doc_id or not title:
            continue
        score = _evidence_title_match_score(title, product_text)
        if score >= 100:
            scored.append((score, index, doc_id))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return _dedupe_texts([doc_id for _, _, doc_id in scored[:3]])


def _expand_product_source_ids_with_linked_evidence(
    source_ids: list[str],
    docs: list[dict[str, Any]],
    *,
    max_ids: int,
) -> list[str]:
    if not source_ids:
        return []
    doc_by_id = {str(doc.get("doc_id") or ""): doc for doc in docs if doc.get("doc_id")}
    selected_docs = [doc_by_id[source_id] for source_id in source_ids if source_id in doc_by_id]
    if not selected_docs:
        return source_ids[:max_ids]
    linked_keys = {
        key
        for doc in selected_docs
        for key in _source_link_keys(doc)
    }
    if not linked_keys:
        return source_ids[:max_ids]
    expanded = list(source_ids)
    for doc in docs:
        doc_id = str(doc.get("doc_id") or "").strip()
        if not doc_id or doc_id in expanded:
            continue
        if not linked_keys.intersection(_source_link_keys(doc)):
            continue
        if not _is_directly_linked_supporting_document(doc, selected_docs):
            continue
        expanded.append(doc_id)
        if len(expanded) >= max_ids:
            break
    return _dedupe_texts(expanded)[:max_ids]


def _source_link_keys(doc: dict[str, Any]) -> set[str]:
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    keys: set[str] = set()
    for value in [
        doc.get("source_item_id"),
        metadata.get("source_item_id"),
        doc.get("content_id"),
        metadata.get("content_id"),
    ]:
        text = str(value or "").strip()
        if text:
            keys.add(text)
    content_id = str(metadata.get("content_id") or doc.get("content_id") or "").strip()
    if content_id:
        keys.add(f"tourapi:content:{content_id}")
    return keys


def _is_directly_linked_supporting_document(doc: dict[str, Any], selected_docs: list[dict[str, Any]]) -> bool:
    doc_id = str(doc.get("doc_id") or "")
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    source_family = str(metadata.get("source_family") or metadata.get("source") or "").lower()
    if _is_primary_tourapi_document(doc_id, source_family):
        return False
    doc_keys = _source_link_keys(doc)
    if not doc_keys:
        return False
    return any(doc_keys.intersection(_source_link_keys(selected_doc)) for selected_doc in selected_docs)


def _itinerary_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        parts.extend(
            [
                str(item.get("name") or ""),
                str(item.get("description") or ""),
                str(item.get("activity") or ""),
            ]
        )
    return " ".join(parts)


def _evidence_title_match_score(title: str, product_text: str) -> int:
    variants = _evidence_title_variants(title)
    for variant in variants:
        if len(variant) >= 4 and variant in product_text:
            return 100 + len(variant)
    return 0


_SOURCE_TITLE_PREFIXES = {
    "서울",
    "서울특별시",
    "부산",
    "부산광역시",
    "대구",
    "대구광역시",
    "인천",
    "인천광역시",
    "광주",
    "광주광역시",
    "대전",
    "대전광역시",
    "울산",
    "울산광역시",
    "세종",
    "세종특별자치시",
    "경기",
    "경기도",
    "강원",
    "강원특별자치도",
    "충북",
    "충청북도",
    "충남",
    "충청남도",
    "전북",
    "전라북도",
    "전남",
    "전라남도",
    "경북",
    "경상북도",
    "경남",
    "경상남도",
    "제주",
    "제주특별자치도",
}


def _evidence_title_variants(title: str) -> list[str]:
    normalized = _normalized_evidence_link_text(title)
    variants = [normalized] if normalized else []
    for prefix in _SOURCE_TITLE_PREFIXES:
        normalized_prefix = _normalized_evidence_link_text(prefix)
        if normalized_prefix and normalized.startswith(normalized_prefix):
            stripped = normalized[len(normalized_prefix) :]
            if stripped:
                variants.append(stripped)
    return _dedupe_texts(variants)


def _normalized_evidence_link_text(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum() or "\uac00" <= ch <= "\ud7a3")


def _candidate_cards_from_context(evidence_context: dict[str, Any]) -> list[dict[str, Any]]:
    advice = evidence_context.get("productization_advice")
    if not isinstance(advice, dict):
        return []
    cards = advice.get("candidate_evidence_cards")
    if not isinstance(cards, list):
        return []
    return [card for card in cards if isinstance(card, dict)]


def _human_gap_type(gap_type: Any) -> str:
    mapping = {
        "missing_detail_info": "상세 설명",
        "missing_image_asset": "이미지 후보",
        "missing_operating_hours": "운영시간",
        "missing_price_or_fee": "요금/가격",
        "missing_booking_info": "예약 가능 여부",
        "missing_related_places": "주변 연계 장소",
        "missing_route_context": "동선 정보",
        "missing_theme_specific_data": "테마별 조건",
    }
    return mapping.get(str(gap_type or ""), str(gap_type or "근거 정보"))


def _needs_review_from_context(evidence_context: dict[str, Any]) -> list[str]:
    gaps = evidence_context.get("unresolved_gaps") if isinstance(evidence_context.get("unresolved_gaps"), list) else []
    notes: list[str] = []
    for gap in gaps[:8]:
        if not isinstance(gap, dict):
            continue
        reason = str(gap.get("productization_impact") or gap.get("reason") or "").strip()
        if reason and _has_korean(reason):
            notes.append(reason[:180])
        else:
            notes.append(f"{_human_gap_type(gap.get('gap_type'))} 근거가 부족해 운영자 확인이 필요합니다.")
    return _dedupe_texts(notes)


def _claim_limits_from_context(evidence_context: dict[str, Any]) -> list[str]:
    gaps = evidence_context.get("unresolved_gaps") if isinstance(evidence_context.get("unresolved_gaps"), list) else []
    gap_types = {str(gap.get("gap_type")) for gap in gaps if isinstance(gap, dict)}
    limits: list[str] = []
    if "missing_operating_hours" in gap_types:
        limits.append("운영시간 확정")
    if "missing_price_or_fee" in gap_types:
        limits.append("가격, 무료 여부, 할인율 단정")
    if "missing_booking_info" in gap_types:
        limits.append("예약 즉시 확정 또는 상시 예약 가능")
    if "missing_route_context" in gap_types:
        limits.append("정확한 이동 시간과 동선 확정")
    if "missing_theme_specific_data" in gap_types:
        limits.append("반려동물, 웰니스, 의료 효능 등 테마 조건 단정")
    try:
        source_confidence = float(evidence_context.get("source_confidence") or 0.0)
    except (TypeError, ValueError):
        source_confidence = 0.0
    if source_confidence and source_confidence < 0.6:
        limits.append("근거 신뢰도가 낮은 후보를 대표 상품처럼 단정")
    return _dedupe_texts(limits)


def _coverage_notes_from_context(evidence_context: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    gaps = evidence_context.get("unresolved_gaps") if isinstance(evidence_context.get("unresolved_gaps"), list) else []
    if gaps:
        gap_labels = sorted({_human_gap_type(gap.get("gap_type")) for gap in gaps if isinstance(gap, dict)})
        if gap_labels:
            notes.append(f"게시 전 확인이 필요한 정보: {', '.join(gap_labels[:6])}")
    return _dedupe_texts(notes)


def _product_display_notes(
    *,
    needs_review: list[str],
    coverage_notes: list[str],
    claim_limits: list[str],
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for message in needs_review:
        notes.append(
            {
                "audience": "user",
                "category": "publish_check",
                "message": message,
                "source": "needs_review",
            }
        )
    for message in coverage_notes:
        notes.append(
            {
                "audience": "user",
                "category": "evidence_scope",
                "message": message,
                "source": "coverage_notes",
            }
        )
    for message in claim_limits:
        notes.append(
            {
                "audience": "user",
                "category": "copy_caution",
                "message": message,
                "source": "claim_limits",
            }
        )
    return notes


def _normalize_evidence_summary(value: Any, source_ids: list[str], docs: list[dict[str, Any]]) -> str:
    if not source_ids:
        return _evidence_summary_for_product(source_ids, docs)
    if isinstance(value, str) and value.strip() and _has_korean(value):
        return _append_linked_evidence_note(value.strip(), source_ids, docs)
    list_value = _safe_korean_string_list(value, "products[].evidence_summary")
    if list_value:
        return _append_linked_evidence_note(" ".join(list_value[:3]), source_ids, docs)
    return _evidence_summary_for_product(source_ids, docs)


def _evidence_summary_for_product(source_ids: list[str], docs: list[dict[str, Any]]) -> str:
    titles_by_id = {str(doc.get("doc_id")): str(doc.get("title") or "근거 문서") for doc in docs if doc.get("doc_id")}
    titles = [titles_by_id.get(source_id, source_id) for source_id in source_ids]
    if not titles:
        return "연결된 근거가 부족해 운영자 확인이 필요합니다."
    return f"{len(source_ids)}개 근거를 사용했습니다: {', '.join(titles[:3])}"


def _append_linked_evidence_note(summary: str, source_ids: list[str], docs: list[dict[str, Any]]) -> str:
    supporting_titles = _linked_supporting_evidence_titles(source_ids, docs)
    if not supporting_titles:
        return summary
    note = f" 보강 근거로 {', '.join(supporting_titles[:2])}도 함께 확인했습니다."
    if all(title in summary for title in supporting_titles[:2]):
        return summary
    return f"{summary}{note}"


def _linked_supporting_evidence_titles(source_ids: list[str], docs: list[dict[str, Any]]) -> list[str]:
    doc_by_id = {str(doc.get("doc_id") or ""): doc for doc in docs if doc.get("doc_id")}
    titles: list[str] = []
    for source_id in source_ids:
        doc = doc_by_id.get(source_id)
        if not doc:
            continue
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        source_family = str(metadata.get("source_family") or metadata.get("source") or "").lower()
        if _is_primary_tourapi_document(source_id, source_family):
            continue
        title = str(doc.get("title") or "").strip()
        if title:
            titles.append(title)
    return _dedupe_texts(titles)


def _marketing_evidence_disclaimer(
    product: dict[str, Any],
    evidence_context: dict[str, Any] | None = None,
) -> str:
    review_items = _string_list(product.get("needs_review")) or _needs_review_from_context(evidence_context or {})
    if review_items:
        return f"근거가 부족한 항목은 운영자 확인 후 게시하세요: {', '.join(review_items[:3])}"
    return "상품 문구는 연결된 근거를 기준으로 작성했으며, 가격/일정/예약 조건은 게시 전 최종 확인해야 합니다."


def _dedupe_qa_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for issue in issues:
        key = (
            str(issue.get("product_id") or ""),
            str(issue.get("type") or ""),
            str(issue.get("message") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


QA_USER_ISSUE_TYPES = {
    "avoid_rule",
    "unsupported_claim",
    "source_missing",
    "operational_uncertainty",
    "content_format",
    "price_claim",
    "booking_claim",
    "operating_hours_claim",
    "theme_claim",
    "safety_claim",
}


def _evidence_based_qa_issues(
    products: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    evidence_context: dict[str, Any],
    qa_settings: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    allowed_source_ids = {str(doc.get("doc_id")) for doc in docs if doc.get("doc_id")}
    gaps = evidence_context.get("unresolved_gaps") if isinstance(evidence_context.get("unresolved_gaps"), list) else []
    unresolved_types = {str(gap.get("gap_type")) for gap in gaps if isinstance(gap, dict)}
    assets_by_product_id = {str(asset.get("product_id")): asset for asset in assets if isinstance(asset, dict)}
    avoid_rules = _string_list(qa_settings.get("avoid"))

    for product in products:
        product_id = str(product.get("id") or "")
        source_ids = _string_list(product.get("source_ids"))
        if allowed_source_ids:
            invalid_source_ids = [source_id for source_id in source_ids if source_id not in allowed_source_ids]
            if not source_ids:
                issues.append(
                    _qa_issue(
                        product_id,
                        "high",
                        "source_missing",
                        "상품에 연결된 근거가 없습니다.",
                        "상품마다 실제 근거 문서 1개 이상을 연결하세요.",
                    )
                )
            elif invalid_source_ids:
                issues.append(
                    _qa_issue(
                        product_id,
                        "info",
                        "internal_diagnostic",
                        "상품의 근거 연결에서 내부 문서 보정이 필요합니다.",
                        "Developer 영역에서 근거 연결 로그를 확인하세요.",
                        user_visible=False,
                        details={"invalid_source_ids": invalid_source_ids},
                    )
                )

        public_text = _public_product_text(product)
        asset = assets_by_product_id.get(product_id)
        if asset:
            public_text = f"{public_text}\n{_public_marketing_text(asset)}"
        issues.extend(
            _unsupported_claim_issues(
                product_id,
                public_text,
                unresolved_types,
                segments=_public_text_segments(product, asset),
            )
        )
        for avoid in avoid_rules:
            if avoid and avoid in public_text:
                avoid_match = _first_public_text_match([re.escape(avoid)], public_text, _public_text_segments(product, asset))
                quote = avoid_match["quote"] if avoid_match else avoid
                label = avoid_match["label"] if avoid_match else "고객 노출 문구"
                issues.append(
                    _qa_issue(
                        product_id,
                        "medium",
                        "avoid_rule",
                        f"{label}에 요청한 회피 조건과 충돌하는 문제 문구 '{quote}'가 있습니다.",
                        "해당 표현을 제거하거나 운영자 확인 필요 문구로 바꾸세요.",
                        field_path=avoid_match["field_path"] if avoid_match else "",
                        issue_category="avoid_rule",
                    )
                )
    return _dedupe_qa_issues(issues)


def _qa_issue(
    product_id: str | None,
    severity: str,
    issue_type: str,
    message: str,
    suggested_fix: str,
    field_path: str = "",
    *,
    issue_category: str | None = None,
    user_visible: bool = True,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issue = {
        "product_id": product_id,
        "severity": severity,
        "type": issue_type,
        "issue_category": issue_category or _qa_issue_category(issue_type, message),
        "user_visible": user_visible,
        "message": message,
        "field_path": field_path,
        "suggested_fix": suggested_fix,
    }
    if details:
        issue["details"] = details
    return issue


def _qa_issue_category(issue_type: str, message: str = "") -> str:
    issue_type = str(issue_type or "").lower()
    text = f"{issue_type} {message}"
    if issue_type == "internal_diagnostic":
        return "internal_diagnostic"
    if issue_type == "avoid_rule" or "avoid" in issue_type or "prohibited" in issue_type:
        return "avoid_rule"
    if issue_type == "source_missing" or "출처" in text or "근거 누락" in text:
        return "source_missing"
    if any(term in text for term in ["operating_hours", "booking", "reservation", "availability", "운영시간", "예약"]):
        return "operational_uncertainty"
    if any(term in text for term in ["price", "safety", "language", "theme", "claim", "가격", "안전", "외국어", "효능", "반려동물"]):
        return "unsupported_claim"
    if "format" in issue_type or "제목" in text:
        return "content_format"
    return "unsupported_claim"


def _normalize_user_qa_issue_type(issue_type: str, message: str, suggested_fix: str) -> str:
    raw = str(issue_type or "").strip().lower()
    text = f"{raw} {message} {suggested_fix}"
    if raw in QA_USER_ISSUE_TYPES:
        return raw
    if "prohibited" in raw or "avoid" in raw or "금지" in text or "회피" in text:
        return "avoid_rule"
    if "source" in raw or "evidence" in raw or "citation" in raw or "근거" in text or "출처" in text:
        return "source_missing"
    if any(term in text for term in ["운영시간", "예약", "예약 가능", "상시 운영", "운영 조건"]):
        return "operational_uncertainty"
    if any(term in text for term in ["가격", "무료", "최저가", "안전", "외국어", "웰니스", "의료", "반려동물"]):
        return "unsupported_claim"
    if "제목" in text or "불필요한 문자" in text:
        return "content_format"
    return "unsupported_claim"


def _normalize_qa_severity(severity: str, issue_type: str, message: str) -> str:
    normalized = str(severity or "").lower()
    if normalized not in {"critical", "high", "medium", "low", "info"}:
        normalized = "medium"
    if issue_type == "internal_diagnostic":
        return "info"
    if any(term in message for term in ["100%", "완전 안전", "최저가 보장", "치료", "완치"]):
        return "high"
    return normalized


def _public_product_text(product: dict[str, Any]) -> str:
    itinerary_names = []
    itinerary = product.get("itinerary") if isinstance(product.get("itinerary"), list) else []
    for item in itinerary:
        if isinstance(item, dict):
            itinerary_names.append(str(item.get("name") or ""))
    public_values = [
        product.get("title"),
        product.get("one_liner"),
        " ".join(_string_list(product.get("core_value"))),
        " ".join(itinerary_names),
        product.get("estimated_duration"),
        product.get("operation_difficulty"),
    ]
    return "\n".join(str(value or "") for value in public_values)


def _public_marketing_text(asset: dict[str, Any]) -> str:
    return "\n".join(segment["text"] for segment in _public_marketing_segments(asset))


def _public_text_segments(product: dict[str, Any], asset: dict[str, Any] | None) -> list[dict[str, str]]:
    segments: list[dict[str, str]] = []

    def add(label: str, field_path: str, value: Any) -> None:
        text = str(value or "").strip()
        if text:
            segments.append({"label": label, "field_path": field_path, "text": text})

    add("상품 제목", "title", product.get("title"))
    add("한 줄 설명", "one_liner", product.get("one_liner"))
    for index, value in enumerate(_string_list(product.get("core_value"))):
        add("핵심 가치", f"core_value[{index}]", value)
    itinerary = product.get("itinerary") if isinstance(product.get("itinerary"), list) else []
    for index, item in enumerate(itinerary):
        if isinstance(item, dict):
            add("일정 항목", f"itinerary[{index}].name", item.get("name"))
            add("일정 설명", f"itinerary[{index}].description", item.get("description"))
    add("예상 소요 시간", "estimated_duration", product.get("estimated_duration"))
    add("운영 난이도", "operation_difficulty", product.get("operation_difficulty"))

    if not isinstance(asset, dict):
        return segments
    segments.extend(_public_marketing_segments(asset))
    return segments


def _public_marketing_segments(asset: dict[str, Any]) -> list[dict[str, str]]:
    segments: list[dict[str, str]] = []

    def add(label: str, field_path: str, value: Any) -> None:
        text = str(value or "").strip()
        if text:
            segments.append({"label": label, "field_path": field_path, "text": text})

    sales_copy = asset.get("sales_copy") if isinstance(asset.get("sales_copy"), dict) else {}
    add("홍보 제목", "sales_copy.headline", sales_copy.get("headline"))
    add("홍보 부제목", "sales_copy.subheadline", sales_copy.get("subheadline"))
    sections = sales_copy.get("sections") if isinstance(sales_copy.get("sections"), list) else []
    for index, section in enumerate(sections):
        if isinstance(section, dict):
            add("상세 설명 제목", f"sales_copy.sections[{index}].title", section.get("title"))
            add("상세 설명", f"sales_copy.sections[{index}].body", section.get("body"))
    faq = asset.get("faq") if isinstance(asset.get("faq"), list) else []
    for index, item in enumerate(faq):
        if isinstance(item, dict):
            add("FAQ 질문", f"faq[{index}].question", item.get("question"))
            add("FAQ 답변", f"faq[{index}].answer", item.get("answer"))
    strategy = asset.get("marketing_strategy") if isinstance(asset.get("marketing_strategy"), dict) else {}
    target = strategy.get("target_segment") if isinstance(strategy.get("target_segment"), dict) else {}
    positioning = strategy.get("product_positioning") if isinstance(strategy.get("product_positioning"), dict) else {}
    add("판매 대상", "marketing_strategy.target_segment.primary", target.get("primary"))
    add("외국인 관광객 맥락", "marketing_strategy.target_segment.foreigner_context", target.get("foreigner_context"))
    add("상품 포지셔닝", "marketing_strategy.product_positioning.summary", positioning.get("summary"))
    add("상품 차별점", "marketing_strategy.product_positioning.differentiation", positioning.get("differentiation"))
    for index, item in enumerate(strategy.get("key_selling_points") if isinstance(strategy.get("key_selling_points"), list) else []):
        if isinstance(item, dict):
            add("핵심 Selling Point", f"marketing_strategy.key_selling_points[{index}].point", item.get("point"))
            add("핵심 Selling Point 근거", f"marketing_strategy.key_selling_points[{index}].evidence_basis", item.get("evidence_basis"))
            add("핵심 Selling Point 활용", f"marketing_strategy.key_selling_points[{index}].usage_note", item.get("usage_note"))

    outline = asset.get("landing_page_outline") if isinstance(asset.get("landing_page_outline"), dict) else {}
    hero = outline.get("hero") if isinstance(outline.get("hero"), dict) else {}
    add("상세페이지 첫 화면 제목", "landing_page_outline.hero.headline", hero.get("headline"))
    add("상세페이지 첫 화면 보조 문구", "landing_page_outline.hero.subheadline", hero.get("subheadline"))
    add("상세페이지 첫 문장", "landing_page_outline.hero.hook", hero.get("hook"))
    for index, value in enumerate(_string_list(outline.get("why_this_product"))):
        add("상세페이지 선택 이유", f"landing_page_outline.why_this_product[{index}]", value)
    for index, item in enumerate(outline.get("evidence_backed_points") if isinstance(outline.get("evidence_backed_points"), list) else []):
        if isinstance(item, dict):
            add("근거 기반 상세페이지 포인트", f"landing_page_outline.evidence_backed_points[{index}].point", item.get("point"))
            add("상세페이지 포인트 근거", f"landing_page_outline.evidence_backed_points[{index}].evidence_basis", item.get("evidence_basis"))
    for index, value in enumerate(_string_list(outline.get("practical_info"))):
        add("상세페이지 확인 정보", f"landing_page_outline.practical_info[{index}]", value)

    faq_strategy = asset.get("faq_strategy") if isinstance(asset.get("faq_strategy"), dict) else {}
    for group_key, group_label in [("buyer_faq", "구매 전환 FAQ"), ("operation_faq", "운영 확인 FAQ")]:
        for index, item in enumerate(faq_strategy.get(group_key) if isinstance(faq_strategy.get(group_key), list) else []):
            if isinstance(item, dict):
                add(f"{group_label} 질문", f"faq_strategy.{group_key}[{index}].question", item.get("question"))
                add(f"{group_label} 답변", f"faq_strategy.{group_key}[{index}].answer", item.get("answer"))

    campaign = asset.get("sns_campaign") if isinstance(asset.get("sns_campaign"), dict) else {}
    for index, item in enumerate(campaign.get("campaign_angles") if isinstance(campaign.get("campaign_angles"), list) else []):
        if isinstance(item, dict):
            add("SNS 각도", f"sns_campaign.campaign_angles[{index}].angle", item.get("angle"))
            add("SNS 각도 근거", f"sns_campaign.campaign_angles[{index}].rationale", item.get("rationale"))
    for index, item in enumerate(campaign.get("posts") if isinstance(campaign.get("posts"), list) else []):
        if isinstance(item, dict):
            add("SNS Hook", f"sns_campaign.posts[{index}].hook", item.get("hook"))
            add("SNS 본문", f"sns_campaign.posts[{index}].body", item.get("body"))
            for tag_index, value in enumerate(_string_list(item.get("hashtags"))):
                add("SNS 해시태그", f"sns_campaign.posts[{index}].hashtags[{tag_index}]", value)

    claim_strategy = asset.get("claim_strategy") if isinstance(asset.get("claim_strategy"), dict) else {}
    for index, item in enumerate(claim_strategy.get("usable_claims") if isinstance(claim_strategy.get("usable_claims"), list) else []):
        if isinstance(item, dict):
            add("활용 가능한 주장", f"claim_strategy.usable_claims[{index}].claim", item.get("claim"))
            add("활용 가능한 주장 근거", f"claim_strategy.usable_claims[{index}].evidence_basis", item.get("evidence_basis"))
    return segments


def _unsupported_claim_issues(
    product_id: str,
    public_text: str,
    unresolved_types: set[str],
    *,
    segments: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    checks = [
        (
            "missing_price_or_fee",
            "price_claim",
            [r"\d[\d,]*\s*원(?:입니다|으로|에|부터|까지)?", r"최저가(?:를)? 보장"],
            "가격이나 요금 정보를 단정하고 있습니다.",
            "가격/요금은 운영자 확인 필요 문구로 바꾸세요.",
        ),
        (
            "missing_booking_info",
            "booking_claim",
            [r"예약 즉시 확정", r"예약이 확정", r"바로 확정", r"상시 예약 가능"],
            "예약 가능 여부를 단정하고 있습니다.",
            "예약 가능 여부는 확인 필요 문구로 바꾸세요.",
        ),
        (
            "missing_operating_hours",
            "operating_hours_claim",
            [r"항상 운영", r"상시 운영", r"매일 운영합니다", r"운영시간은\s*\d"],
            "운영시간이나 상시 운영 여부를 단정하고 있습니다.",
            "운영시간은 공식 확인 후 게시한다고 안내하세요.",
        ),
        (
            "missing_theme_specific_data",
            "theme_claim",
            [r"반려동물 동반 가능", r"영어 가이드 제공", r"외국어 안내 제공", r"웰니스 효능", r"치료", r"완치"],
            "테마 조건이나 효능을 근거 없이 단정하고 있습니다.",
            "테마 조건과 효능 표현은 운영자 확인 필요 항목으로 분리하세요.",
        ),
    ]
    for gap_type, issue_type, patterns, message, suggested_fix in checks:
        if gap_type not in unresolved_types:
            continue
        match = _first_public_text_match(patterns, public_text, segments or [])
        if match:
            issues.append(
                _qa_issue(
                    product_id,
                    "high",
                    issue_type,
                    f"{match['label']}에 문제 문구 '{match['quote']}'가 있습니다. {message}",
                    suggested_fix,
                    field_path=match["field_path"],
                )
            )

    absolute_safety_patterns = [r"100%\s*안전", r"완전 안전", r"안전(?:을)? 보장"]
    safety_match = _first_public_text_match(absolute_safety_patterns, public_text, segments or [])
    if safety_match:
        issues.append(
            _qa_issue(
                product_id,
                "high",
                "safety_claim",
                f"{safety_match['label']}에 문제 문구 '{safety_match['quote']}'가 있습니다. 절대적 안전 보장처럼 보이는 표현이 포함되어 있습니다.",
                "안전 관련 표현은 현장 조건과 운영자 확인 기준으로 완화하세요.",
                field_path=safety_match["field_path"],
            )
        )
    return issues


def _first_public_text_match(
    patterns: list[str],
    public_text: str,
    segments: list[dict[str, str]],
) -> dict[str, str] | None:
    for segment in segments:
        text = segment.get("text") or ""
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return {
                    "label": segment.get("label") or "고객 노출 문구",
                    "field_path": segment.get("field_path") or "",
                    "quote": _qa_problem_quote(text, match),
                }
    for pattern in patterns:
        match = re.search(pattern, public_text)
        if match:
            return {
                "label": "고객 노출 문구",
                "field_path": "",
                "quote": _qa_problem_quote(public_text, match),
            }
    return None


def _qa_problem_quote(text: str, match: re.Match[str]) -> str:
    matched = match.group(0).strip()
    if matched:
        return matched[:80]
    start = max(0, match.start() - 24)
    end = min(len(text), match.end() + 24)
    return text[start:end].strip()[:80]


def _revision_allowed_patch_scope(revision_context: dict[str, Any]) -> dict[str, set[str]] | None:
    if not isinstance(revision_context, dict):
        return None
    issues = revision_context.get("qa_issues")
    if not isinstance(issues, list) or not issues:
        return None
    scope: dict[str, set[str]] = {}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        product_id = str(issue.get("product_id") or "").strip()
        if not product_id:
            continue
        field_path = str(issue.get("field_path") or "").strip()
        paths = _revision_patch_paths_from_issue(field_path, str(issue.get("message") or ""))
        scope.setdefault(product_id, set()).update(paths)
    return scope or None


def _revision_patch_paths_from_issue(field_path: str, message: str) -> set[str]:
    normalized = field_path.strip()
    if normalized:
        return {normalized}
    text = message or ""
    if "FAQ" in text or "faq" in text.lower():
        return {"faq"}
    if "SNS" in text or "sns" in text.lower():
        return {"sns_campaign.posts"}
    if "제목" in text or "headline" in text.lower():
        return {"title", "sales_copy.headline"}
    if "상세 설명" in text or "sales copy" in text.lower() or "판매 문구" in text:
        return {"sales_copy.sections"}
    return {"one_liner", "sales_copy.headline", "sales_copy.subheadline", "sales_copy.sections", "faq", "sns_campaign.posts"}


def _revision_patch_path_allowed(
    allowed_patch_scope: dict[str, set[str]] | None,
    product_id: str,
    candidate_path: str,
) -> bool:
    if allowed_patch_scope is None:
        return True
    allowed_paths = allowed_patch_scope.get(product_id)
    if not allowed_paths:
        return False
    for allowed_path in allowed_paths:
        if candidate_path == allowed_path:
            return True
        if allowed_path in {"faq", "search_keywords"} and candidate_path.startswith(allowed_path):
            return True
        if allowed_path == "sales_copy.sections" and candidate_path.startswith("sales_copy.sections"):
            return True
        if allowed_path in MARKETING_FIELD_PARENT_PATCHES and candidate_path.startswith(f"{allowed_path}."):
            return True
        if allowed_path in MARKETING_FIELD_PARENT_PATCHES and candidate_path.startswith(f"{allowed_path}["):
            return True
    return False


def apply_revision_patch(
    payload: dict[str, Any],
    products: list[dict[str, Any]],
    marketing_assets: list[dict[str, Any]],
    *,
    allowed_patch_scope: dict[str, set[str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    patched_products = json.loads(json.dumps(products, ensure_ascii=False))
    patched_assets = json.loads(json.dumps(marketing_assets, ensure_ascii=False))
    product_by_id = {product.get("id"): product for product in patched_products}
    asset_by_id = {asset.get("product_id"): asset for asset in patched_assets}

    product_patches = payload.get("product_patches") or []
    if not isinstance(product_patches, list):
        raise ValueError("revision_patch.product_patches must be an array")
    for patch in product_patches:
        if not isinstance(patch, dict):
            continue
        product = product_by_id.get(patch.get("product_id"))
        fields = patch.get("fields")
        if not product or not isinstance(fields, dict):
            continue
        for key in ["title", "one_liner", "estimated_duration", "operation_difficulty"]:
            if key in fields and _revision_patch_path_allowed(allowed_patch_scope, str(product.get("id") or ""), key):
                product[key] = _korean_text(str(fields[key]), f"products[].{key}")
        for key in ["core_value", "assumptions", "not_to_claim"]:
            if key in fields and _revision_patch_path_allowed(allowed_patch_scope, str(product.get("id") or ""), key):
                product[key] = _korean_string_list(fields[key], f"products[].{key}") or product.get(key, [])

    marketing_patches = payload.get("marketing_patches") or []
    if not isinstance(marketing_patches, list):
        raise ValueError("revision_patch.marketing_patches must be an array")
    for patch in marketing_patches:
        if not isinstance(patch, dict):
            continue
        asset = asset_by_id.get(patch.get("product_id"))
        if not asset:
            continue
        sales_copy_patch = patch.get("sales_copy")
        if isinstance(sales_copy_patch, dict):
            sales_copy = asset.setdefault("sales_copy", {})
            for key in ["headline", "subheadline", "disclaimer"]:
                path = f"sales_copy.{key}"
                if key in sales_copy_patch and _revision_patch_path_allowed(allowed_patch_scope, str(asset.get("product_id") or ""), path):
                    sales_copy[key] = _korean_text(str(sales_copy_patch[key]), f"sales_copy.{key}")
            _apply_section_patches(
                sales_copy,
                sales_copy_patch.get("sections"),
                allowed_patch_scope=allowed_patch_scope,
                product_id=str(asset.get("product_id") or ""),
            )

        _apply_faq_patches(
            asset,
            patch.get("faq"),
            allowed_patch_scope=allowed_patch_scope,
            product_id=str(asset.get("product_id") or ""),
        )
        if "search_keywords" in patch and _revision_patch_path_allowed(allowed_patch_scope, str(asset.get("product_id") or ""), "search_keywords"):
            product = product_by_id.get(asset.get("product_id")) or {}
            keywords = _normalize_search_keywords(patch.get("search_keywords"), product)
            if keywords:
                asset["search_keywords"] = keywords[:12]

    marketing_field_patches = payload.get("marketing_field_patches") or []
    if not isinstance(marketing_field_patches, list):
        raise ValueError("revision_patch.marketing_field_patches must be an array")
    for patch in marketing_field_patches:
        if not isinstance(patch, dict):
            continue
        product_id = str(patch.get("product_id") or "")
        asset = asset_by_id.get(product_id)
        field_path = str(patch.get("field_path") or "").strip()
        if not asset or not field_path:
            continue
        if not _marketing_field_patch_path_allowed(field_path):
            continue
        if not _revision_patch_path_allowed(allowed_patch_scope, product_id, field_path):
            continue
        value = patch.get("value")
        _assert_marketing_patch_value(value, f"marketing_assets[].{field_path}")
        _set_nested_value(asset, field_path, value)

    return patched_products, patched_assets


def _marketing_field_patch_path_allowed(path: str) -> bool:
    tokens = _path_tokens(path)
    if not tokens:
        return False
    if any(str(token) in REMOVED_MARKETING_STRATEGY_FIELDS for token in tokens if isinstance(token, str)):
        return False
    if any(str(token) in {"source_ids", "source_id", "evidence", "retrieved_documents"} for token in tokens if isinstance(token, str)):
        return False
    root = str(tokens[0])
    if root in {"sales_copy", "faq", "search_keywords"}:
        return True
    if root not in {
        "marketing_strategy",
        "landing_page_outline",
        "faq_strategy",
        "sns_campaign",
        "claim_strategy",
    }:
        return False
    return True


def _assert_marketing_patch_value(value: Any, field_path: str) -> None:
    if isinstance(value, str):
        _assert_marketing_user_text(value, field_path)
        if _is_unsupported_operational_claim(value) and "claim_strategy.usable_claims" in field_path:
            raise ValueError(f"{field_path} contains unsupported operational claim")
        return
    if isinstance(value, list):
        for item in value:
            _assert_marketing_patch_value(item, field_path)
        return
    if isinstance(value, dict):
        if any(key in REMOVED_MARKETING_STRATEGY_FIELDS for key in value):
            raise ValueError(f"{field_path} contains removed marketing strategy field")
        for key, item in value.items():
            _assert_marketing_patch_value(item, f"{field_path}.{key}")
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise ValueError(f"{field_path} has unsupported patch value type")


def _apply_section_patches(
    sales_copy: dict[str, Any],
    patches: Any,
    *,
    allowed_patch_scope: dict[str, set[str]] | None = None,
    product_id: str = "",
) -> None:
    if not isinstance(patches, list):
        return
    sections = sales_copy.get("sections")
    if not isinstance(sections, list):
        return
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        index = patch.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(sections):
            continue
        section = sections[index]
        if not isinstance(section, dict):
            continue
        if "title" in patch and _revision_patch_path_allowed(allowed_patch_scope, product_id, f"sales_copy.sections[{index}].title"):
            section["title"] = _korean_text(str(patch["title"]), "sales_copy.sections[].title")
        if "body" in patch and _revision_patch_path_allowed(allowed_patch_scope, product_id, f"sales_copy.sections[{index}].body"):
            section["body"] = _korean_text(str(patch["body"]), "sales_copy.sections[].body")


def _apply_faq_patches(
    asset: dict[str, Any],
    patches: Any,
    *,
    allowed_patch_scope: dict[str, set[str]] | None = None,
    product_id: str = "",
) -> None:
    if not isinstance(patches, list):
        return
    faq = asset.get("faq")
    if not isinstance(faq, list):
        return
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        index = patch.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(faq):
            continue
        item = faq[index]
        if not isinstance(item, dict):
            continue
        if "question" in patch and _revision_patch_path_allowed(allowed_patch_scope, product_id, f"faq[{index}].question"):
            item["question"] = _korean_text(str(patch["question"]), "faq[].question")
        if "answer" in patch and _revision_patch_path_allowed(allowed_patch_scope, product_id, f"faq[{index}].answer"):
            item["answer"] = _korean_text(str(patch["answer"]), "faq[].answer")


def _normalize_sales_copy(
    sales_copy: Any,
    product: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(sales_copy, dict):
        raise ValueError("sales_copy must be an object")
    sections = sales_copy.get("sections")
    if not isinstance(sections, list):
        raise ValueError("sales_copy.sections must be an array")
    normalized_sections = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = _korean_text(str(section.get("title") or "섹션"), "sales_copy.sections[].title")
        body = _korean_text(str(section.get("body") or ""), "sales_copy.sections[].body")
        _assert_marketing_user_text(title, "sales_copy.sections[].title")
        _assert_marketing_user_text(body, "sales_copy.sections[].body")
        normalized_sections.append({"title": title, "body": body})
        if len(normalized_sections) >= 4:
            break
    if not normalized_sections:
        raise ValueError("sales_copy.sections must contain at least one valid section")
    headline = _korean_text(str(sales_copy.get("headline") or product["title"]), "sales_copy.headline")
    subheadline = _korean_text(str(sales_copy.get("subheadline") or product["one_liner"]), "sales_copy.subheadline")
    disclaimer = _korean_text(
        str(
            sales_copy.get("disclaimer")
            or "세부 일정, 가격, 포함사항은 운영자가 최종 확정해야 합니다."
        ),
        "sales_copy.disclaimer",
    )
    for field_path, value in [
        ("sales_copy.headline", headline),
        ("sales_copy.subheadline", subheadline),
        ("sales_copy.disclaimer", disclaimer),
    ]:
        _assert_marketing_user_text(value, field_path)
    return {
        "headline": headline,
        "subheadline": subheadline,
        "sections": normalized_sections,
        "disclaimer": disclaimer,
    }


def validate_qa_report(
    payload: dict[str, Any],
    products: list[dict[str, Any]],
    *,
    docs: list[dict[str, Any]] | None = None,
    evidence_context: dict[str, Any] | None = None,
    marketing_assets: list[dict[str, Any]] | None = None,
    qa_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues = payload.get("issues")
    if not isinstance(issues, list):
        raise ValueError("QA issues must be an array")
    product_ids = {product["id"] for product in products}
    validated_issues: list[dict[str, Any]] = []
    internal_diagnostics: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        message = _normalize_qa_issue_message(issue)
        suggested_fix = _normalize_qa_suggested_fix(issue)
        raw_type = str(issue.get("type") or "general")
        if _is_non_actionable_source_metadata_issue(message, suggested_fix):
            continue
        if _is_internal_diagnostic_issue(raw_type, message, suggested_fix):
            internal_diagnostics.append(
                _qa_internal_diagnostic(
                    issue,
                    message,
                    suggested_fix,
                    product_ids,
                    products,
                    reason="internal_field_or_source_metadata",
                )
            )
            continue
        if _is_safe_uncertainty_phrase_issue(message, suggested_fix):
            continue
        if _is_marketing_tone_only_issue(message, suggested_fix):
            continue
        if _is_copy_quality_only_issue(message, suggested_fix):
            continue
        if not _qa_issue_has_problem_quote(message) and not _is_allowed_unquoted_qa_issue(raw_type, message):
            internal_diagnostics.append(
                _qa_internal_diagnostic(
                    issue,
                    message,
                    suggested_fix,
                    product_ids,
                    products,
                    reason="missing_problem_quote",
                )
            )
            continue
        product_id = issue.get("product_id")
        inferred_product_id = _infer_issue_product_id(message, products)
        resolved_product_id = product_id if product_id in product_ids else inferred_product_id
        issue_type = _normalize_user_qa_issue_type(raw_type, message, suggested_fix)
        validated_issues.append(
            {
                "product_id": resolved_product_id,
                "severity": _normalize_qa_severity(str(issue.get("severity") or "medium"), issue_type, message),
                "type": issue_type,
                "issue_category": _qa_issue_category(issue_type, message),
                "user_visible": True,
                "message": message,
                "field_path": str(issue.get("field_path") or ""),
                "suggested_fix": _enrich_qa_suggested_fix(message, suggested_fix, products),
            }
        )
    deterministic_issues = _evidence_based_qa_issues(
        products,
        marketing_assets or [],
        docs or [],
        evidence_context or {},
        qa_settings or {},
    )
    for issue in deterministic_issues:
        if issue.get("type") == "internal_diagnostic" or issue.get("user_visible") is False:
            internal_diagnostics.append(issue)
        else:
            validated_issues.append(issue)
    validated_issues = _dedupe_qa_issues(validated_issues)
    internal_diagnostics = _dedupe_qa_issues(internal_diagnostics)
    overall_status = str(payload.get("overall_status") or ("needs_review" if validated_issues else "pass"))
    if validated_issues and overall_status == "pass":
        overall_status = "needs_review"
    if not validated_issues:
        report = {
            "overall_status": "pass",
            "summary": _normalize_qa_summary(None, []),
            "issues": [],
            "pass_count": len(products),
            "needs_review_count": 0,
            "fail_count": 0,
        }
        if internal_diagnostics:
            report["internal_diagnostics"] = internal_diagnostics
        return report
    report = {
        "overall_status": overall_status,
        "summary": _normalize_qa_summary(
            _qa_summary_value_for_issues(payload.get("summary"), validated_issues),
            validated_issues,
        ),
        "issues": validated_issues,
        "pass_count": int(payload.get("pass_count") or (len(products) if not validated_issues else 0)),
        "needs_review_count": int(payload.get("needs_review_count") or (len(products) if validated_issues else 0)),
        "fail_count": int(payload.get("fail_count") or 0),
    }
    if internal_diagnostics:
        report["internal_diagnostics"] = internal_diagnostics
    return report


def validate_targeted_revision_qa_report(
    payload: dict[str, Any],
    selected_issues: list[Any],
    products: list[dict[str, Any]],
    *,
    marketing_assets: list[dict[str, Any]] | None = None,
    source_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    issue_results: list[dict[str, Any]] = []
    product_ids = {str(product.get("id")) for product in products if isinstance(product, dict)}
    current_product_by_id = {str(product.get("id")): product for product in products if isinstance(product, dict)}
    current_asset_by_id = {
        str(asset.get("product_id")): asset
        for asset in (marketing_assets or [])
        if isinstance(asset, dict)
    }
    visible_issues: list[dict[str, Any]] = _revision_unselected_qa_issues(
        source_output or {},
        selected_issues,
        current_product_by_id=current_product_by_id,
        current_asset_by_id=current_asset_by_id,
    )
    for index, selected_issue in enumerate(selected_issues):
        if not isinstance(selected_issue, dict):
            continue
        item = items[index] if index < len(items) and isinstance(items[index], dict) else {}
        status = str(item.get("status") or "").strip().lower()
        server_resolved_reason = _targeted_issue_resolved_by_current_text(
            selected_issue,
            current_product_by_id,
            current_asset_by_id,
        )
        is_resolved = status == "resolved" or server_resolved_reason is not None
        result_message = _strip_internal_field_paths(str(item.get("message") or selected_issue.get("message") or "").strip())
        result_fix = _strip_internal_field_paths(str(item.get("suggested_fix") or selected_issue.get("suggested_fix") or "").strip())
        if not is_resolved and not _qa_issue_has_problem_quote(result_message):
            quote = _targeted_issue_quote_for_current_text(
                selected_issue,
                current_product_by_id,
                current_asset_by_id,
            )
            if quote:
                result_message = _targeted_still_open_message(selected_issue, quote)
            else:
                result_message = _normalize_qa_issue_message(selected_issue)
        issue_results.append(
            {
                "original_issue_index": index,
                "product_id": selected_issue.get("product_id"),
                "status": "resolved" if is_resolved else "still_open",
                "message": result_message,
                "suggested_fix": result_fix,
                "server_resolved_reason": server_resolved_reason,
            }
        )
        if is_resolved:
            continue
        product_id = selected_issue.get("product_id")
        raw_type = str(selected_issue.get("type") or "unsupported_claim")
        issue_type = _normalize_user_qa_issue_type(raw_type, result_message, result_fix)
        visible_issues.append(
            {
                "product_id": product_id if product_id in product_ids else None,
                "severity": _normalize_qa_severity(str(selected_issue.get("severity") or "medium"), issue_type, result_message),
                "type": issue_type,
                "issue_category": _qa_issue_category(issue_type, result_message),
                "user_visible": True,
                "message": result_message or _normalize_qa_issue_message(selected_issue),
                "field_path": str(selected_issue.get("field_path") or ""),
                "suggested_fix": result_fix or _normalize_qa_suggested_fix(selected_issue),
            }
        )
    visible_issues = _dedupe_qa_issues(visible_issues)
    summary = str(payload.get("summary") or "").strip()
    return {
        "overall_status": "needs_review" if visible_issues else "pass",
        "summary": summary if summary and _has_korean(summary) else _normalize_qa_summary(None, visible_issues),
        "issues": visible_issues,
        "pass_count": len(products) if not visible_issues else 0,
        "needs_review_count": len({issue.get("product_id") for issue in visible_issues if issue.get("product_id")}),
        "fail_count": 0,
        "targeted_recheck": True,
        "rechecked_issue_count": len(issue_results),
        "revision_issue_results": issue_results,
    }


def _revision_unselected_qa_issues(
    source_output: dict[str, Any],
    selected_issues: list[Any],
    *,
    current_product_by_id: dict[str, dict[str, Any]] | None = None,
    current_asset_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    original_report = source_output.get("qa_report") if isinstance(source_output.get("qa_report"), dict) else {}
    original_issues = original_report.get("issues") if isinstance(original_report.get("issues"), list) else []
    selected_keys = {
        _qa_issue_identity(issue)
        for issue in selected_issues
        if isinstance(issue, dict)
    }
    carryover: list[dict[str, Any]] = []
    for issue in original_issues:
        if not isinstance(issue, dict):
            continue
        if _qa_issue_identity(issue) in selected_keys:
            continue
        copied = json.loads(json.dumps(issue, ensure_ascii=False))
        copied["revision_carryover"] = True
        copied["user_visible"] = copied.get("user_visible", True)
        if not _qa_issue_has_problem_quote(str(copied.get("message") or "")):
            quote = _targeted_issue_quote_for_current_text(
                copied,
                current_product_by_id or {},
                current_asset_by_id or {},
            )
            if quote:
                copied["message"] = _targeted_still_open_message(copied, quote)
        carryover.append(copied)
    return carryover


def _qa_issue_identity(issue: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(issue.get("product_id") or ""),
        str(issue.get("type") or ""),
        str(issue.get("field_path") or ""),
        re.sub(r"\s+", " ", str(issue.get("message") or "")).strip(),
    )


def _targeted_issue_resolved_by_current_text(
    selected_issue: dict[str, Any],
    current_product_by_id: dict[str, dict[str, Any]],
    current_asset_by_id: dict[str, dict[str, Any]],
) -> str | None:
    quote = _extract_qa_problem_quote(str(selected_issue.get("message") or ""))
    if not quote:
        return None
    product_id = str(selected_issue.get("product_id") or "")
    field_path = str(selected_issue.get("field_path") or "")
    product = current_product_by_id.get(product_id) or {}
    asset = current_asset_by_id.get(product_id) or {}
    current_value = _revision_current_value_for_field(product, asset, field_path)
    current_text = str(current_value or "").strip()
    if current_text and quote not in current_text:
        return "problem_quote_removed_from_target_field"
    return None


def _targeted_issue_quote_for_current_text(
    selected_issue: dict[str, Any],
    current_product_by_id: dict[str, dict[str, Any]],
    current_asset_by_id: dict[str, dict[str, Any]],
) -> str | None:
    product_id = str(selected_issue.get("product_id") or "")
    field_path = str(selected_issue.get("field_path") or "")
    product = current_product_by_id.get(product_id) or {}
    asset = current_asset_by_id.get(product_id) or {}
    current_value = _revision_current_value_for_field(product, asset, field_path)
    current_text = str(current_value or "").strip()
    if not current_text:
        return None
    original_quote = _extract_qa_problem_quote(str(selected_issue.get("message") or ""))
    if original_quote and original_quote in current_text:
        return original_quote
    return current_text[:120]


def _targeted_still_open_message(selected_issue: dict[str, Any], quote: str) -> str:
    issue_type = _qa_issue_category(str(selected_issue.get("type") or ""), str(selected_issue.get("message") or ""))
    location_label = _field_path_label(str(selected_issue.get("field_path") or ""))
    if issue_type == "source_missing":
        return f"{location_label}에 '{quote}'라고 명시되어 있으나, 이는 근거 문서에 명확히 확인되지 않는 주장입니다."
    if issue_type == "operational_uncertainty":
        return f"{location_label}에 '{quote}'라고 명시되어 있으나, 운영자가 확인해야 할 정보를 단정하고 있습니다."
    if issue_type == "unsupported_claim":
        return f"{location_label}에 '{quote}'라고 명시되어 있으나, 근거 없이 단정적인 주장으로 보입니다."
    if issue_type == "avoid_rule":
        return f"{location_label}에 '{quote}'라는 문구가 남아 있어 선택한 회피 조건과 충돌합니다."
    return f"{location_label}에 '{quote}'라는 문제 문구가 아직 남아 있습니다."


def _extract_qa_problem_quote(message: str) -> str | None:
    patterns = [
        r"문제 문구\s*['\"“”‘’]([^'\"“”‘’]+)['\"“”‘’]",
        r"['\"“”‘’]([^'\"“”‘’]{3,})['\"“”‘’]",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            quote = match.group(1).strip()
            if quote:
                return quote
    return None


def validate_research_synthesis(payload: dict[str, Any], state: GraphState) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Research synthesis response must be an object")
    return _complete_research_synthesis(payload, state)


def _is_timeout_like_gemini_error(exc: GeminiGatewayError) -> bool:
    message = str(exc).lower()
    return (
        "timeout" in message
        or "timed out" in message
        or "maxoutputtokens" in message
        or "max_tokens" in message
        or "truncated" in message
    )


def _complete_research_synthesis(payload: dict[str, Any], state: GraphState) -> dict[str, Any]:
    evidence_context = _evidence_context_from_state(state)
    advice = (
        evidence_context.get("productization_advice")
        if isinstance(evidence_context.get("productization_advice"), dict)
        else {}
    )
    base_cards = _product_evidence_context_for_prompt(evidence_context)["candidate_evidence_cards"]
    payload_cards = (
        payload.get("candidate_card_guidance")
        if isinstance(payload.get("candidate_card_guidance"), list)
        else payload.get("candidate_evidence_cards")
        if isinstance(payload.get("candidate_evidence_cards"), list)
        else []
    )
    cards = _merge_research_candidate_cards(base_cards, payload_cards)
    unresolved = _merge_research_unresolved_gaps(
        _compact_unresolved_gaps_for_product(evidence_context.get("unresolved_gaps")),
        payload.get("unresolved_gaps"),
    )
    usable_claims = _dedupe_texts(
        [
            *_safe_korean_string_list(payload.get("usable_claims"), "research.usable_claims"),
            *_string_list(advice.get("usable_claims")),
        ]
    )[:12]
    restricted_claims = _dedupe_texts(
        [
            *_safe_korean_string_list(payload.get("restricted_claims"), "research.restricted_claims"),
            *_claim_limits_from_context(evidence_context),
            *[claim for card in cards for claim in _string_list(card.get("restricted_claims"))],
        ]
    )[:16]
    operational_unknowns = _dedupe_texts(
        [
            *_safe_korean_string_list(payload.get("operational_unknowns"), "research.operational_unknowns"),
            *_needs_review_from_context(evidence_context),
            *[unknown for card in cards for unknown in _string_list(card.get("operational_unknowns"))],
        ]
    )[:16]
    guidance = _safe_korean_string_list(
        payload.get("product_generation_guidance"),
        "research.product_generation_guidance",
    ) or [
        "candidate evidence card의 usable facts를 상품 본문에 우선 반영하세요.",
        "운영 조건이 불확실한 내용은 needs_review와 claim_limits로 분리하세요.",
    ]
    qa_risk_notes = _safe_korean_string_list(payload.get("qa_risk_notes"), "research.qa_risk_notes") or [
        "근거 없는 가격, 예약, 운영시간, 안전, 외국어 지원, 의료/웰니스 효능 claim을 만들지 마세요."
    ]
    summary = {
        "research_brief": _safe_korean_text(
            payload.get("research_brief"),
            "research.research_brief",
            fallback="EvidenceFusion 결과를 상품 생성에 사용할 수 있도록 후보별 근거와 제한 claim을 정리했습니다.",
        ),
        "candidate_evidence_cards": cards,
        "usable_claims": usable_claims,
        "restricted_claims": restricted_claims,
        "operational_unknowns": operational_unknowns,
        "unresolved_gaps": unresolved,
        "product_generation_guidance": guidance[:10],
        "qa_risk_notes": qa_risk_notes[:10],
        "retrieved_documents": _summarize_evidence(state.get("retrieved_documents", []), limit=10),
        "evidence_profile": evidence_context.get("evidence_profile") or {},
        "productization_advice": {
            **advice,
            "candidate_evidence_cards": cards,
        },
        "data_coverage": evidence_context.get("data_coverage") or {},
        "source_confidence": evidence_context.get("source_confidence") or 0.0,
        "ui_highlights": evidence_context.get("ui_highlights") or [],
    }
    return summary


def _merge_research_candidate_cards(
    base_cards: list[dict[str, Any]],
    payload_cards: list[Any],
) -> list[dict[str, Any]]:
    payload_by_key: dict[str, dict[str, Any]] = {}
    for raw_card in payload_cards:
        if not isinstance(raw_card, dict):
            continue
        key = _research_card_key(raw_card)
        if key:
            payload_by_key[key] = raw_card

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for base in base_cards:
        key = _research_card_key(base)
        raw = payload_by_key.get(key, {})
        card = {**base, **raw}
        for field in ["usable_facts", "operational_unknowns", "restricted_claims", "evidence_document_ids"]:
            if not card.get(field):
                card[field] = base.get(field) or []
        for field in ["experience_hooks", "recommended_product_angles"]:
            card[field] = _dedupe_texts(_string_list(card.get(field)) or _string_list(base.get(field)))[:4]
        merged.append(card)
        if key:
            seen.add(key)

    for raw_card in payload_cards:
        if not isinstance(raw_card, dict):
            continue
        key = _research_card_key(raw_card)
        if key and key in seen:
            continue
        compact = _compact_candidate_card_for_product(raw_card)
        if compact.get("usable_facts") or compact.get("evidence_document_ids"):
            merged.append(compact)
    return merged[:MAX_PRODUCT_COUNT]


def _research_card_key(card: dict[str, Any]) -> str:
    for key in ["content_id", "source_item_id", "title"]:
        value = str(card.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    return ""


def _merge_research_unresolved_gaps(base_gaps: list[dict[str, Any]], payload_gaps: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_gap in [*base_gaps, *(payload_gaps if isinstance(payload_gaps, list) else [])]:
        if not isinstance(raw_gap, dict):
            continue
        gap = {
            "gap_type": raw_gap.get("gap_type"),
            "label": raw_gap.get("label") or _human_gap_type(raw_gap.get("gap_type")),
            "severity": raw_gap.get("severity"),
            "reason": str(raw_gap.get("reason") or "")[:180],
            "target_content_id": raw_gap.get("target_content_id"),
            "target_item_id": raw_gap.get("target_item_id"),
            "source_item_title": raw_gap.get("source_item_title"),
        }
        key = (str(gap["gap_type"] or ""), str(gap["target_content_id"] or ""), str(gap["target_item_id"] or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(gap)
    return merged[:16]


def _planner_prompt(request: dict[str, Any]) -> str:
    context = {
        "역할": "PlannerAgent",
        "목표": "사용자 요청을 관광 상품 생성 workflow가 사용할 실행 의도와 제약으로 정규화합니다.",
        "요청": {
            "message": request.get("message"),
            "region_hint": request.get("region"),
            "period": request.get("period"),
            "target_customer": request.get("target_customer"),
            "product_count": request.get("product_count"),
            "preferences": request.get("preferences"),
            "avoid": request.get("avoid"),
            "output_language": request.get("output_language"),
        },
        "역할_경계": [
            "지역명, 지역 코드, lDongRegnCd/lDongSignguCd는 절대 확정하지 마세요. 지역 확정은 GeoResolverAgent가 합니다.",
            "해외/지원 범위 밖 판단은 preflight와 GeoResolver 정책을 따릅니다. Planner는 region code를 만들지 않습니다.",
            "Baseline TourAPI 검색 전략은 현재 deterministic 수집 코드가 담당합니다. Planner는 API query plan을 만들지 않습니다.",
        ],
        "출력_규칙": [
            f"product_count는 1~{MAX_PRODUCT_COUNT} 사이 정수로 반환하세요. 사용자가 {MAX_PRODUCT_COUNT}개 이상을 말하면 {MAX_PRODUCT_COUNT}로 제한하세요.",
            "preferred_themes와 avoid는 사용자가 준 값과 자연어 요청에서 명확한 값만 포함하세요.",
            "자연어 요청에 웰니스, 반려동물, 오디오 해설, 의료 같은 테마가 명시되면 preferences 값과 달라도 preferred_themes에 반드시 포함하세요.",
            "product_generation_constraints에는 상품 생성 단계가 지켜야 할 제약을 한국어 문장으로 넣으세요.",
            "evidence_requirements에는 근거 연결, 단정 금지, 운영자 확인 항목 분리 기준을 한국어 문장으로 넣으세요.",
            "TourAPI code, areaCode, ldong code, sigungu code, geo_scope 필드는 출력하지 마세요.",
            "사용자에게 보이는 모든 텍스트는 한국어로 작성하세요.",
        ],
        "출력_예시": {
            "user_intent": "대전에서 외국인 대상 야간 관광 상품을 기획합니다.",
            "product_count": 3,
            "target_customer": "외국인",
            "preferred_themes": ["야간 관광"],
            "avoid": ["가격 단정 표현"],
            "period": "2026-05",
            "output_language": "ko",
            "request_type": "tourism_product_generation",
            "product_generation_constraints": [f"상품 개수는 최대 {MAX_PRODUCT_COUNT}개입니다."],
            "evidence_requirements": ["각 상품은 실제 근거 문서와 연결되어야 합니다."],
        },
    }
    return json.dumps(context, ensure_ascii=False)


def _research_synthesis_prompt(
    *,
    normalized: dict[str, Any],
    docs: list[dict[str, Any]],
    evidence_context: dict[str, Any],
    data_gap_report: dict[str, Any],
    enrichment_summary: dict[str, Any],
    compact_retry_error: str | None = None,
) -> str:
    compact_retry = bool(compact_retry_error)
    research_evidence_context = _research_evidence_context_for_prompt(evidence_context, compact=compact_retry)
    context = {
        "역할": "ResearchSynthesisAgent",
        "목표": (
            "EvidenceFusion이 이미 보존한 근거 card 위에 ProductAgent가 참고할 상품화 해석과 risk guidance만 추가합니다. "
            "원본 TourAPI/RAG/API facts를 대체하거나 재출력하지 않습니다."
        ),
        "요청": {
            "normalized_request": normalized,
            "geo_scope": normalized.get("geo_scope"),
            "target_customer": normalized.get("target_customer"),
            "preferred_themes": normalized.get("preferred_themes"),
            "avoid": normalized.get("avoid"),
        },
        "재시도_사유": compact_retry_error,
        "retrieved_document_summary": _summarize_evidence(docs, limit=3 if compact_retry else 6),
        "evidence_context": research_evidence_context,
        "data_gap_summary": {
            "gap_count": len(data_gap_report.get("gaps") or []) if isinstance(data_gap_report.get("gaps"), list) else 0,
            "coverage": data_gap_report.get("coverage") if isinstance(data_gap_report, dict) else {},
        },
        "enrichment_summary": _compact_enrichment_summary_for_research(enrichment_summary),
        "보존해야_하는_정보": [
            "서버가 보존하는 candidate_evidence_cards[].usable_facts",
            "서버가 보존하는 candidate_evidence_cards[].operational_unknowns",
            "서버가 보존하는 candidate_evidence_cards[].restricted_claims",
            "서버가 보존하는 candidate_evidence_cards[].evidence_document_ids",
            "unresolved_gaps",
            "data_coverage와 source_confidence의 의미",
        ],
        "출력_규칙": [
            "candidate_evidence_cards 필드를 출력하지 마세요.",
            "usable_facts, detail_facts, evidence_document_ids, 주소, 개요 원문을 반복 출력하지 마세요.",
            "후보별 보강 판단은 candidate_card_guidance에 content_id/source_item_id/title과 짧은 guidance만 넣으세요.",
            "candidate_card_guidance는 최대 8개만 작성하세요. 추가 guidance가 없는 후보는 생략하세요.",
            "각 candidate_card_guidance 항목에는 product_angle, experience_hooks, recommended_product_angles, operational_unknowns, restricted_claims만 필요한 만큼 짧게 넣으세요.",
            "서버가 candidate_card_guidance를 기존 candidate_evidence_cards와 병합하므로 원본 근거는 유지됩니다.",
            "근거가 없는 운영시간, 요금, 예약 가능 여부, 외국어 지원, 안전성, 의료/웰니스 효능은 restricted_claims 또는 operational_unknowns로 분리하세요.",
            "새 evidence_document_id를 만들지 마세요.",
            "각 배열은 꼭 필요한 항목만 남기되 너무 과하게 줄이지 마세요. usable_claims, restricted_claims, operational_unknowns, product_generation_guidance, qa_risk_notes는 각각 최대 8개로 제한하세요.",
            "사용자에게 보이는 모든 텍스트는 한국어로 작성하세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def _geo_catalog_options_for_prompt(catalog: list[Any]) -> list[dict[str, str | None]]:
    options: list[dict[str, str | None]] = []
    for candidate in catalog:
        options.append(
            {
                "name": candidate.full_name,
                "ldong_regn_cd": candidate.ldong_regn_cd,
                "ldong_regn_nm": candidate.ldong_regn_nm,
                "ldong_signgu_cd": candidate.ldong_signgu_cd or "",
                "ldong_signgu_nm": candidate.ldong_signgu_nm or "",
            }
        )
    return options


def _geo_resolution_prompt(
    resolver_input: dict[str, Any],
    *,
    catalog_options: list[dict[str, str | None]] | None = None,
) -> str:
    context = {
        "요청": resolver_input,
        "역할": (
            "사용자 자연어에서 지역 의도를 추출하고, 아래 TourAPI 법정동 후보 목록 중 "
            "실제로 검색에 넣을 수 있는 시도/시군구 코드를 선택합니다."
        ),
        "TourAPI_법정동_후보": catalog_options or [],
        "출력_규칙": [
            "locations에는 요청 문장에 실제로 등장한 국내/해외 장소 표현만 넣으세요.",
            "text는 원문에 등장한 장소 span 그대로 쓰세요. 오타가 있으면 text에는 오타 원문을, normalized_text에는 교정 후보를 쓰세요.",
            "role은 primary, nearby_anchor, comparison, excluded 중 하나만 쓰세요.",
            "두 곳 이상 지역이나 이동 코스 표현이 있어도 역할을 나누지 말고, 등장한 지역을 각각 primary로 남기세요.",
            "resolved_locations에는 반드시 TourAPI_법정동_후보에 있는 코드만 넣으세요. 후보에 없는 코드는 절대 만들지 마세요.",
            "섬, 관광지명, 생활권명, 동네명이 후보 목록에 직접 없으면, 일반 지식으로 어느 시군구에 속하는지 판단한 뒤 해당 시군구 후보를 고르세요.",
            "후보 목록에 없는 세부 지명, 섬, 관광지, 생활권, 동네명은 resolved_locations[].sub_area_terms와 keywords에 원문 표현 그대로 넣으세요. 예: 해운대 반여동 -> 부산광역시 해운대구 + sub_area_terms ['반여동'].",
            "반려동물, 야간, 혼잡, 수요, 사진, 외국인, 웰니스, 축제 같은 상품 테마/조건/고객 표현은 절대 장소나 sub_area_terms/keywords로 넣지 마세요.",
            "확신이 낮거나 같은 이름 후보가 여러 개면 resolved_locations를 비우고 clarification_candidates에 후보만 넣으세요.",
            "confidence는 0.0~1.0 숫자로 쓰고, 실제 검색에 써도 될 정도로 확실할 때만 0.72 이상으로 쓰세요.",
            "resolved_locations.reason에는 왜 그 코드가 맞는지 짧게 쓰세요.",
            "전국, 국내 전체처럼 사용자가 명시한 경우에만 allow_nationwide=true로 쓰세요.",
            "도쿄, 오사카, 파리처럼 해외 목적지를 요청하면 unsupported_locations에 넣고 해당 location의 is_foreign=true로 표시하세요.",
            "해외 목적지는 원문에 등장한 장소 span 기준으로만 판단하세요. 서로 다른 단어가 붙어서 생긴 부분 문자열은 장소로 보지 마세요.",
            "외국인, 해외 관광객, 인바운드처럼 고객 대상을 뜻하는 표현은 해외 목적지로 취급하지 마세요.",
            "장소가 애매해도 억지로 특정 행정구역을 선택하지 마세요.",
        ],
        "예시": [
            {
                "input": "부산에서 반려동물 동반 외국인 대상 관광 상품 3개 기획해줘",
                "locations": [
                    {"text": "부산", "normalized_text": "부산광역시", "role": "primary", "is_foreign": False},
                ],
                "resolved_locations": [
                    {
                        "text": "부산",
                        "role": "primary",
                        "name": "부산광역시",
                        "ldong_regn_cd": "26",
                        "ldong_signgu_cd": "",
                        "confidence": 0.95,
                        "reason": "부산은 TourAPI 후보의 부산광역시에 해당합니다.",
                        "sub_area_terms": [],
                        "keywords": [],
                    }
                ],
            },
            {
                "input": "부산 해운대 반여동에서 외국인 대상 관광 상품 3개 기획해줘",
                "locations": [
                    {"text": "부산 해운대 반여동", "normalized_text": "부산광역시 해운대구 반여동", "role": "primary", "is_foreign": False},
                ],
                "resolved_locations": [
                    {
                        "text": "부산 해운대 반여동",
                        "role": "primary",
                        "name": "부산광역시 해운대구",
                        "ldong_regn_cd": "26",
                        "ldong_signgu_cd": "350",
                        "confidence": 0.9,
                        "reason": "반여동은 부산광역시 해운대구 관할로 판단됩니다.",
                        "sub_area_terms": ["반여동"],
                        "keywords": ["반여동"],
                    }
                ],
            },
            {
                "input": "도쿄에서 외국인 대상 액티비티 상품",
                "locations": [
                    {"text": "도쿄", "normalized_text": "도쿄", "role": "primary", "is_foreign": True},
                ],
                "unsupported_locations": ["도쿄"],
            },
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def _product_prompt(
    normalized: dict[str, Any],
    research_summary: dict[str, Any],
    docs: list[dict[str, Any]],
    *,
    evidence_context: dict[str, Any] | None = None,
    source_items: list[dict[str, Any]] | None = None,
    qa_settings: dict[str, Any] | None = None,
    validation_error: str | None = None,
) -> str:
    evidence_context = evidence_context or {}
    qa_settings = qa_settings or {}
    requested_product_count = _desired_product_count(normalized, fallback=3)
    effective_product_count = _effective_product_count(normalized, docs, fallback=3)
    evidence_count = len({str(doc.get("doc_id")) for doc in docs if doc.get("doc_id")})
    priority_doc_ids = _priority_evidence_document_ids(evidence_context)
    evidence_prompt_limit = min(MAX_PRODUCT_COUNT, max(12, effective_product_count * 4, len(priority_doc_ids)))
    context = {
        "요청": {
            "normalized_request": normalized,
            "geo_scope": normalized.get("geo_scope"),
            "requested_product_count": requested_product_count,
            "product_count": effective_product_count,
            "available_evidence_count": evidence_count,
            "product_count_note": "요청한 상품 수는 근거 문서 수로 줄이지 않습니다. 직접 연결할 근거가 부족한 상품은 source_ids를 빈 배열로 두고 coverage_notes에 근거 부족을 남기세요.",
            "target_customer": normalized.get("target_customer"),
            "preferred_themes": normalized.get("preferred_themes"),
            "avoid": _string_list(normalized.get("avoid")),
        },
        "리서치_요약": research_summary,
        "source_items_shortlist": _summarize_source_items_for_prompt(source_items or [], limit=evidence_prompt_limit),
        "retrieved_documents": _summarize_evidence(
            docs,
            limit=evidence_prompt_limit,
            priority_doc_ids=priority_doc_ids,
        ),
        "evidence_based_generation_context": _product_evidence_context_for_prompt(evidence_context),
        "QA_avoid_rules": _string_list(qa_settings.get("avoid")),
        "수정_요청": _prompt_revision_context(normalized.get("revision_context")),
        "재작성_요청": (
            {
                "reason": validation_error,
                "instruction": "아래 규칙을 지켜 전체 products 배열을 다시 작성하세요. 특히 요청.product_count와 정확히 같은 개수의 상품을 반환해야 합니다.",
            }
            if validation_error
            else None
        ),
        "출력_필드_추가_의미": {
            "evidence_summary": "상품이 어떤 근거를 썼는지 한 문장으로 요약",
            "needs_review": "상품 본문에 단정하지 말고 운영자가 확인해야 할 항목",
            "coverage_notes": "이 상품의 근거 커버리지와 남은 공백",
            "claim_limits": "본문/마케팅에서 단정하면 안 되는 claim 제한",
        },
        "상품성_기준": {
            "title": "장소/테마/경험이 드러나는 실제 여행 상품명이어야 합니다. '근거 기반 상품', '관광 상품 1'처럼 형식적인 이름은 피하세요.",
            "one_liner": "고객이 이 상품을 선택할 이유를 한 문장으로 설명해야 합니다. 장소명만 나열하거나 '구성합니다'로 끝나는 내부 설명은 피하세요.",
            "core_value": "운영 정보가 아니라 고객이 얻는 경험 가치, 감정, 대상 고객 맥락을 2~4개로 분리하세요.",
            "differentiation": "같은 run 안의 상품은 서로 다른 angle을 가져야 하며 제목/one_liner/core_value가 복사한 듯 반복되면 안 됩니다.",
        },
        "규칙": [
            f"요청.product_count 값과 정확히 같은 개수의 상품을 생성하세요. 최대 {MAX_PRODUCT_COUNT}개를 절대 넘지 마세요.",
            "근거 문서 수가 요청 상품 수보다 적어도 상품 개수를 줄이지 마세요.",
            "source_ids는 반드시 retrieved_documents 안에 있는 doc_id만 사용하세요. content_id나 임의 id를 쓰지 마세요.",
            "source_ids에 확실하지 않은 값을 넣지 마세요. 허용된 doc_id가 없으면 source_ids는 빈 배열이어야 합니다.",
            "다른 source_id 형식, content_id, 관광지 id, API item id를 추측해서 만들지 마세요.",
            "각 product의 source_ids에는 상품과 직접 관련된 근거만 넣으세요. 직접 관련 근거가 없으면 빈 배열을 반환하고 needs_review/coverage_notes에 근거 부족을 남기세요.",
            "candidate_evidence_cards의 usable_facts, experience_hooks, recommended_product_angles를 우선 활용하세요.",
            "상품명, one_liner, core_value는 마케팅 단계의 기반이므로 구체적인 장소/경험/대상 고객 맥락을 담으세요.",
            "여러 상품을 만들 때 같은 제목 패턴, 같은 one_liner 구조, 같은 core_value 표현을 반복하지 마세요.",
            "unresolved_gaps에 남은 정보는 상품 본문에 단정하지 말고 needs_review, assumptions, not_to_claim, claim_limits로 분리하세요.",
            "운영시간, 요금, 예약 가능 여부, 외국어 지원, 안전성, 의료/웰니스 효능은 근거가 없으면 절대 단정하지 마세요.",
            "지역 mismatch가 있거나 source_confidence가 낮은 근거는 핵심 claim에 쓰지 말고 coverage_notes에 확인 필요로 남기세요.",
            "요청의 avoid에 포함된 제한은 claim_limits와 not_to_claim에 반영하세요.",
            "사용자에게 보이는 모든 텍스트 필드는 반드시 한국어로 작성하세요. 영어 문장을 쓰지 마세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def _marketing_prompt(
    products: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    revision_context: dict[str, Any] | None = None,
    evidence_context: dict[str, Any] | None = None,
    qa_settings: dict[str, Any] | None = None,
    validation_error: str | None = None,
) -> str:
    context = {
        "상품_목록": products,
        "근거_문서": _summarize_evidence(docs),
        "근거_프로필": _product_evidence_context_for_prompt(evidence_context or {}),
        "QA_avoid_rules": _string_list((qa_settings or {}).get("avoid")),
        "수정_요청": _prompt_revision_context(revision_context),
        "마케팅_출력_품질_기준": {
            "product_title": "실제 여행 상품처럼 장소/테마/경험이 드러나는 구체적인 이름을 유지하고, 너무 행정적인 제목으로 약화하지 않습니다.",
            "one_liner": "고객이 왜 이 상품을 선택해야 하는지 한 문장으로 말합니다. 단순 '근거 기반 상품' 같은 설명은 피합니다.",
            "core_value": "상품의 선택 이유를 경험, 감정, 대상 고객 맥락으로 분리합니다.",
            "marketing_strategy": "상품별로 누구에게, 왜, 어떤 포인트로 팔 수 있는지 관광상품 판매 기획서 수준의 전략을 작성합니다.",
            "landing_page_outline": "상세페이지 첫 화면, 선택 이유, 근거 기반 포인트, 확인 정보를 구조화합니다.",
            "sales_copy": "headline → subheadline → sections가 관심 유도, 경험 상상, 예약 전 확인 순서로 이어지는 설득 흐름을 가집니다.",
            "faq_strategy": "구매 전환 FAQ와 운영 확인 FAQ를 분리해 고객 설득과 게시 전 확인을 모두 지원합니다.",
            "sns_campaign": "SNS 문구는 이 필드 하나에 캠페인 각도, 포맷별 hook/body/해시태그, 시각 방향으로 작성합니다.",
            "claim_strategy": "활용 가능한 주장과 주의 표현을 구분합니다.",
            "faq": "기존 호환용 FAQ에도 구매 전 궁금증과 게시 전 확인 정보를 함께 담습니다. 운영 확인 안내만 반복하지 않습니다.",
            "claims": "근거로 활용 가능한 Selling Point와 게시 전 확인이 필요한 정보를 구분하고, 근거 없는 사실은 단정하지 않습니다.",
        },
        "Marketing_Strategy_Pack_출력_형식": {
            "marketing_strategy": {
                "target_segment": {"primary": "핵심 구매자", "secondary": ["부가 타깃"], "foreigner_context": "외국인 대상 맥락"},
                "product_positioning": {"summary": "한 줄 포지셔닝", "differentiation": "차별화 지점"},
                "key_selling_points": [{"point": "근거 기반 판매 포인트", "evidence_basis": "근거에서 확인되는 사실", "usage_note": "활용 위치"}],
                "customer_objections": [{"objection": "망설임", "response": "설명 방향", "requires_confirmation": True}],
                "operation_checklist": [{"item": "게시/판매 전 확인 항목", "reason": "확인 이유"}],
            },
            "landing_page_outline": {
                "hero": {"headline": "상세페이지 제목", "subheadline": "보조 문구", "hook": "첫 문장"},
                "why_this_product": ["선택 이유"],
                "evidence_backed_points": [{"point": "근거 기반 포인트", "evidence_basis": "근거 내용"}],
                "practical_info": ["게시 전 확인 필요한 운영 정보"],
            },
            "faq_strategy": {
                "buyer_faq": [{"question": "구매자가 궁금해할 질문", "answer": "구매 전환에 도움 되는 답변"}],
                "operation_faq": [{"question": "운영/게시 전 확인 질문", "answer": "확인 필요 정보를 자연스럽게 안내"}],
            },
            "sns_campaign": {
                "campaign_angles": [{"angle": "캠페인 각도", "rationale": "좋은 이유"}],
                "posts": [{"format": "feed | reels | story", "hook": "첫 문장", "body": "본문", "hashtags": ["한국어 해시태그"]}],
                "visual_direction": ["사진/장면 방향"],
            },
            "claim_strategy": {
                "usable_claims": [{"claim": "근거 기반으로 바로 쓸 수 있는 주장", "evidence_basis": "근거에서 확인되는 사실"}],
                "caution_phrasing": [{"phrase": "주의 표현 또는 게시 전 확인이 필요한 주장", "reason": "주의/확인이 필요한 이유"}],
            },
        },
        "상품별_차별화_지시": [
            "같은 run 안의 상품들이 같은 문장 구조와 같은 표현으로 시작하지 않게 하세요.",
            "각 상품마다 서로 다른 angle을 정하세요. 예: 역사 스토리, 로컬 미식, 가족 체험, 야간 산책, 자연 관찰, 포토 스팟 등.",
            "상품명, headline, SNS 첫 문장이 서로 복사한 듯 반복되면 실패입니다.",
            "근거가 같은 지역에 있더라도 각 상품의 장소/행사/체험 단서를 다르게 살리세요.",
        ],
        "근거_안전_마케팅_정책": {
            "활용_가능": "근거 문서에서 확인되는 장소명, 행사 성격, 전시/체험 요소, 지역 맥락, 스토리 소재는 Selling Point로 전환할 수 있습니다.",
            "게시_전_확인": "요금/무료 여부, 운영시간, 예약 가능 여부, 외국어 지원, 안전 조건, 사용권은 근거가 명확하지 않으면 확인 필요로 표현합니다.",
            "표현_주의": "근거 없는 가격, 운영시간, 예약 확정, 안전 보장, 의료/웰니스 효능, 외국어 지원은 단정하지 않습니다.",
            "톤": "주의사항을 쓰더라도 상품 매력을 죽이는 법무 문구처럼 쓰지 말고, 운영자가 게시 전 확인할 정보로 자연스럽게 분리합니다.",
        },
        "출력_언어": {
            "language": "ko",
            "rule": "외국인 대상 상품이어도 출력 문구는 전부 한국어로 작성합니다.",
            "forbidden": [
                "중국어 문장",
                "일본어 문장",
                "영어만 있는 문장",
                "영어/중국어/일본어 해시태그만 있는 SNS 문구",
                "다국어 번역 홍보문",
            ],
            "allowed": [
                "공식 고유명사나 브랜드명은 필요할 때만 원문을 유지할 수 있습니다.",
                "외국인 고객에게 필요한 내용도 한국어 운영자 검토 문장으로 작성합니다.",
            ],
        },
        "규칙": [
            "각 product_id마다 marketing_asset을 정확히 1개씩 생성하세요. product_id 값은 상품_목록의 id를 그대로 사용하세요.",
            "각 marketing_asset에는 marketing_strategy, landing_page_outline, faq_strategy, sns_campaign, claim_strategy를 모두 포함하세요.",
            "marketing_strategy.key_selling_points와 claim_strategy.usable_claims는 근거 문서나 상품의 evidence_summary에서 확인되는 내용만 사용하세요.",
            "근거가 부족한 가격/운영시간/예약/안전/의료/웰니스 효능/외국어 지원은 Selling Point나 usable_claims가 아니라 operation_checklist, customer_objections, faq_strategy.operation_faq, claim_strategy.caution_phrasing으로 분리하세요.",
            "landing_page_outline을 먼저 설계한 뒤, 기존 sales_copy는 그 outline의 hero/why/practical_info를 압축한 홍보 문구처럼 작성하세요.",
            "faq_strategy.buyer_faq는 구매 전환에 도움 되는 질문으로, operation_faq는 가격/운영시간/예약/언어 지원 등 운영 정보 질문으로 구분하세요.",
            "FAQ 답변은 너무 보수적으로 회피하지 마세요. 축제 기간, 행사 장소, 운영시간, 요금, 프로그램처럼 근거 문서나 상품 입력에 명확히 있는 사실은 답변에 구체적으로 활용하세요.",
            "근거에 있는 날짜/운영정보를 사용할 때는 '근거 기준으로는 ...입니다'처럼 말하고, 변경 가능성이 있는 행사/운영 정보는 마지막에 '게시 전 최신 공지 확인' 정도로만 보완하세요. 근거가 있는데도 '공식 홈페이지에서 확인하세요'만 반복하면 실패입니다.",
            "SNS 문구는 sns_campaign.posts에만 작성하세요. 각 post는 첫 문장에 hook이 있어야 합니다.",
            "claim_strategy에는 usable_claims와 caution_phrasing만 작성하세요. needs_confirmation, avoid_phrasing, safe_alternatives는 생성하지 마세요.",
            "marketing_strategy에는 reasons_to_believe와 recommended_sales_angle을 생성하지 마세요.",
            "landing_page_outline에는 experience_story와 conversion_cta를 생성하지 마세요.",
            "sales_copy는 문자열이 아니라 JSON 객체여야 합니다.",
            "sales_copy.headline은 상품명 반복이 아니라 고객이 클릭하고 싶어지는 홍보 제목이어야 합니다.",
            "sales_copy.subheadline은 이 상품만의 선택 이유를 구체적으로 말해야 합니다.",
            "sales_copy.sections는 title과 body를 가진 객체 배열이며 상품당 2~4개 작성하세요. 각 section은 경험 상상, 핵심 매력, 이용 전 확인 중 하나의 역할을 가져야 합니다.",
            "FAQ에는 구매 전 궁금증(누구에게 좋은지, 어떤 경험인지, 외국인에게 어떤 점이 편한지)과 운영 확인 질문(요금/예약/운영시간/언어 지원)을 균형 있게 포함하되 상품당 최대 5개만 작성하세요.",
            "외국인 대상이라는 이유로 SNS 문구를 중국어, 일본어, 영어 등으로 번역하지 마세요. output_language가 ko이므로 한국어 운영 문구만 작성하세요.",
            "search_keywords는 상품당 최대 10개만 작성하고, 각 항목은 한국어 문자열이어야 합니다.",
            "search_keywords에는 Busan, yacht, food tour 같은 영어만 있는 값을 쓰지 말고 부산, 요트, 푸드투어처럼 한국어로 작성하세요.",
            "상품_목록의 needs_review, assumptions, not_to_claim, claim_limits는 hard constraint입니다.",
            "근거 문서에 없는 운영 정보를 사실처럼 새로 만들지 마세요.",
            "가격, 예약, 운영시간, 외국어 지원, 안전 보장, 의료/웰니스 효능은 근거가 없으면 FAQ와 유의 문구에서 확인 필요로만 표현하세요.",
            "evidence_disclaimer에는 data_coverage와 unresolved_gaps를 반영하되, 상품 매력을 죽이는 경고문이 아니라 게시 전 확인 안내로 작성하세요.",
            "claim_limits에는 상품 설명에 활용하면 안 되는 내부 용어가 아니라, 표현 시 주의할 정보를 운영자가 이해할 수 있는 한국어 문장으로 요약하세요.",
            "FAQ와 disclaimer에서 '운영자 확인 필요'만 반복하지 말고, 고객이 기대할 수 있는 경험과 확인해야 할 조건을 함께 말하세요.",
            "요청의 avoid에 포함된 금지 기준을 우선 적용하세요.",
            "운영자가 바로 검토할 수 있게 자연스럽고 실무적인 문장으로 작성하되, 지나치게 짧고 형식적인 문구는 피하세요.",
            "not_to_claim, claim_limits, source_id, field_path, missing_pet_policy 같은 내부 용어를 고객 노출 문구에 쓰지 마세요.",
            "사용자에게 보이는 모든 텍스트 필드는 반드시 한국어로 작성하세요. 영어 문장을 쓰지 마세요.",
        ],
    }
    if validation_error:
        context["검증_실패_수정"] = {
            "error": validation_error,
            "instruction": "이전 응답이 서버 검증을 통과하지 못했습니다. 전체 marketing_assets를 다시 작성하되, 상품_목록의 모든 product_id에 대해 marketing_asset을 정확히 1개씩 포함하세요. claim_strategy.usable_claims는 문자열 배열이 아니라 반드시 {claim, evidence_basis} 객체 배열이어야 하고, caution_phrasing도 {phrase, reason} 객체 배열이어야 합니다. 모든 FAQ/SNS 문구/키워드가 한국어 문자열인지 자체 점검한 뒤 출력하세요.",
        }
    return json.dumps(context, ensure_ascii=False)


def _marketing_product_batches(products: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batch_size = max(1, MARKETING_PRODUCT_BATCH_SIZE)
    return [products[index : index + batch_size] for index in range(0, len(products), batch_size)]


def _marketing_docs_for_products(products: list[dict[str, Any]], docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_ids: set[str] = set()
    for product in products:
        source_ids.update(_string_list(product.get("source_ids")))
        for itinerary_item in product.get("itinerary") or []:
            if isinstance(itinerary_item, dict):
                source_id = str(itinerary_item.get("source_id") or "").strip()
                if source_id:
                    source_ids.add(source_id)
    if not source_ids:
        return []
    matched = [doc for doc in docs if str(doc.get("doc_id") or "").strip() in source_ids]
    return matched


def _qa_prompt(
    products: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    qa_settings: dict[str, Any],
    evidence_context: dict[str, Any] | None = None,
) -> str:
    avoid = _string_list(qa_settings.get("avoid"))
    extra_checks = avoid if avoid else ["가격 단정 표현", "과장 표현", "출처 없는 주장"]
    allowed_doc_ids = [str(doc.get("doc_id")) for doc in docs if doc.get("doc_id")]
    context = {
        "상품_목록": products,
        "마케팅_자산": assets,
        "근거_문서": _summarize_evidence(docs),
        "허용된_source_ids": allowed_doc_ids,
        "근거_프로필": _product_evidence_context_for_prompt(evidence_context or {}),
        "검수_설정": qa_settings,
        "검수_항목": [
            "금지 표현 포함 여부",
            "출처 근거 누락 여부",
            "unresolved gap을 고객 노출 문구에서 단정 claim으로 바꾼 경우",
            "근거 없는 운영시간/요금/예약/안전/외국어/의료/웰니스 claim",
            *extra_checks,
        ],
        "규칙": [
            "사용자에게 보이는 모든 텍스트 필드는 반드시 한국어로 작성하세요. 영어 문장을 쓰지 마세요.",
            "QA 요약, 이슈 메시지, 수정 제안은 반드시 한국어로 작성하세요.",
            "QA의 중심은 사용자가 지정한 avoid와 명백한 evidence risk입니다.",
            "사용자가 지정한 avoid는 단순 금지어 목록이 아니라 evidence risk 기준입니다. 고객 노출 문구가 연결 근거로 직접 뒷받침되면 issue로 만들지 마세요.",
            "특정 단어가 보인다는 이유만으로 issue를 만들지 말고, 해당 문장이 연결 근거 없이 단정한 claim인지 판단하세요.",
            "가격, 요금, 예약, 운영시간 같은 구체 claim은 연결 근거 없이 단정한 경우에만 issue로 만드세요.",
            "검수_항목에 있는 근거 기반 제한은 실제 운영/법무/신뢰 리스크가 있는 고객 노출 문구에만 적용하세요.",
            "검수 대상은 상품_목록과 마케팅_자산의 고객 노출 문구입니다. 근거_문서 자체의 메타데이터 품질 문제를 이슈로 만들지 마세요.",
            "상품_목록의 not_to_claim, assumptions, needs_review는 내부 운영 참고 항목입니다. 이 항목 자체를 고객 노출 문구 위반으로 지적하지 마세요.",
            "source_id, field_path, needs_review, missing_pet_policy 같은 내부 필드명이나 gap type은 message/suggested_fix에 쓰지 마세요.",
            "sales_copy.disclaimer의 '운영자가 최종 확정해야 합니다', '확인 필요', '변동될 수 있습니다' 같은 문구는 단정 표현이 아니라 안전한 완화 문구입니다.",
            "FAQ에서 '~수 있습니다', '확인 필요', '문의 필요', '현장 상황에 따라', '사전에 확인'은 단정 표현이 아니라 불확실성/확인 필요 표현입니다. 이 표현만으로 이슈를 만들지 마세요.",
            "우천, 기상, 현장 상황에 따라 취소/변경/중단될 수 있다는 문구는 정상적인 리스크 안내입니다. 이 표현만으로 이슈를 만들지 마세요.",
            "'환상적인', '아름다운', '특별한', '여유로운', '만끽하세요', '감상하세요', '즐겨보세요', '기대할 수 있습니다' 같은 일반 홍보 표현은 금지 표현이 아닙니다.",
            "금지 표현은 실제 운영 리스크가 분명하고 근거가 부족한 표현만 의미합니다. 근거가 있는 운영 정보와 근거 없는 단정 claim을 구분하세요.",
            "출처 근거 누락은 구체적 사실 주장에만 적용하세요. 분위기, 감상, 추천형 홍보 문구만으로 출처 누락 이슈를 만들지 마세요.",
            "문구가 짧다, 매력이 부족하다, 상세 설명이 약하다는 copy 품질 평가는 QA issue로 만들지 마세요. 이 평가는 별도 Marketing hardening 범위입니다.",
            "명확한 법무/운영 리스크가 없거나 단순 문체 선호에 가까우면 issue를 만들지 마세요.",
            "근거_문서의 event_start_date, event_end_date가 비어 있다는 이유만으로 이슈를 만들지 마세요.",
            "source document나 근거 문서를 업데이트하라는 수정 제안은 하지 마세요. 필요한 경우 상품 문구에 '운영자 확인 필요'를 추가하라고 제안하세요.",
            "각 issue.product_id는 문제가 있는 상품_목록의 id를 그대로 넣으세요. 전체 공통 문제가 아니면 null로 두지 마세요.",
            "issue.field_path는 문제가 있는 고객 노출 필드를 간단히 넣으세요. 예: title, sales_copy.sections[0].body, faq[2].answer",
            "issue.message와 issue.suggested_fix에는 disclaimer, not_to_claim, sales_copy 같은 내부 필드명을 직접 쓰지 마세요. '유의 문구', '운영 주의사항', '상세 설명', 'FAQ 답변'처럼 사람이 이해하는 이름을 쓰세요.",
            "issue.message에는 반드시 문제가 되는 고객 노출 문구를 짧게 직접 인용하세요. 예: 상세 설명에 문제 문구 '상시 운영'이 있습니다. 운영시간이나 상시 운영 여부를 단정하고 있습니다.",
            "문제가 되는 정확한 문구를 인용할 수 없으면 issue를 만들지 마세요.",
            "issues 배열의 모든 issue는 message를 빈 문자열로 두지 말고 구체적인 한국어 문장으로 작성하세요.",
            "issue.message에는 문제 위치와 문제 원인만 작성하세요. 수정 권장 문장이나 대체 문구는 쓰지 마세요.",
            "issue.suggested_fix에는 수정 제안만 작성하세요. message와 같은 내용을 반복하지 마세요.",
            "검수 이슈가 없으면 issues는 빈 배열로 반환하세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def _revision_patch_prompt(
    products: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    revision_context: dict[str, Any],
) -> str:
    targets = _revision_patch_targets_for_prompt(products, assets, revision_context)
    context = {
        "현재_상품_요약": _revision_product_summaries(products),
        "수정_대상": targets,
        "선택된_QA_이슈": revision_context.get("qa_issues", []),
        "검토_코멘트": revision_context.get("comment"),
        "QA_설정": revision_context.get("qa_settings", {}),
        "출력_형식": {
            "product_patches": [
                {
                    "product_id": "수정할 상품 id",
                    "fields": {
                        "title": "필요할 때만",
                        "one_liner": "필요할 때만",
                        "assumptions": ["필요할 때만"],
                        "not_to_claim": ["필요할 때만"],
                    },
                }
            ],
            "marketing_patches": [
                {
                    "product_id": "수정할 상품 id",
                    "sales_copy": {
                        "headline": "필요할 때만",
                        "subheadline": "필요할 때만",
                        "sections": [
                            {"index": 0, "title": "필요할 때만", "body": "필요할 때만"}
                        ],
                        "disclaimer": "필요할 때만",
                    },
                    "faq": [
                        {"index": 0, "question": "필요할 때만", "answer": "필요할 때만"}
                    ],
                    "search_keywords": ["전체 교체가 필요할 때만"],
                }
            ],
            "marketing_field_patches": [
                {
                    "product_id": "수정할 상품 id",
                    "field_path": "faq_strategy.operation_faq[0].answer",
                    "value": "새 Marketing Strategy Pack 필드 수정값",
                }
            ],
            "notes": ["수정 이유"],
        },
        "규칙": [
            "전체 상품이나 전체 마케팅 자산을 다시 생성하지 마세요.",
            "수정_대상에 있는 product_id와 field_path만 수정하세요.",
            "선택된_QA_이슈를 해결하는 데 필요한 최소 문구만 patch에 포함하세요.",
            "수정이 필요 없는 product_id는 product_patches와 marketing_patches에 포함하지 마세요.",
            "수정하지 않는 기존 값은 출력하지 마세요. 기존 값은 서버가 그대로 유지합니다.",
            "source_ids, evidence, claim_limits, needs_review, retrieved_documents는 수정하지 마세요.",
            "새 Marketing Strategy Pack 필드(marketing_strategy, landing_page_outline, faq_strategy, sns_campaign, claim_strategy)는 marketing_field_patches에 field_path/value로만 수정하세요.",
            "marketing_field_patches.field_path는 수정_대상의 field_path와 정확히 일치하거나 그 하위 경로여야 합니다.",
            "reasons_to_believe, recommended_sales_angle, experience_story, conversion_cta, needs_confirmation, avoid_phrasing, safe_alternatives는 생성하지 마세요.",
            "field_path가 sales_copy.sections[n].body이면 해당 index의 body만 출력하세요. 다른 섹션이나 FAQ, SNS는 출력하지 마세요.",
            "field_path가 faq[n].answer이면 해당 index의 answer만 출력하세요. 다른 FAQ나 sales copy는 출력하지 마세요.",
            "index는 현재_마케팅_자산 배열 내부 faq/sections의 0부터 시작하는 위치입니다.",
            "사용자에게 보이는 모든 텍스트는 한국어로 작성하세요.",
            "가격, 운영 시간, 예약 가능 여부, 외국어 지원을 단정하지 마세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def _targeted_revision_qa_prompt(
    original_products: list[dict[str, Any]],
    original_assets: list[dict[str, Any]],
    current_products: list[dict[str, Any]],
    current_assets: list[dict[str, Any]],
    selected_issues: list[Any],
    qa_settings: dict[str, Any],
) -> str:
    context = {
        "역할": "AI 수정 후 선택된 QA 이슈만 다시 확인합니다.",
        "QA_설정": qa_settings,
        "재검수_대상": _targeted_qa_items_for_prompt(
            original_products,
            original_assets,
            current_products,
            current_assets,
            selected_issues,
        ),
        "출력_형식": {
            "summary": "선택된 QA 이슈 재검수 요약",
            "items": [
                {
                    "original_issue_index": 0,
                    "status": "resolved 또는 still_open",
                    "message": "still_open일 때만 현재 남은 문제 설명",
                    "suggested_fix": "still_open일 때만 추가 수정 방향",
                }
            ],
        },
        "규칙": [
            "재검수_대상에 들어온 원래 QA 이슈만 판단하세요.",
            "새로운 QA 이슈를 찾거나 만들지 마세요.",
            "다른 필드, 다른 상품, 다른 근거 공백은 평가하지 마세요.",
            "original_value와 current_value를 비교해서 원래 지적된 문제가 사라졌는지만 판단하세요.",
            "원래 문제 문구가 current_value에 없고 같은 위험이 남아 있지 않으면 status=resolved로 쓰세요.",
            "같은 위험이 current_value에 남아 있으면 status=still_open으로 쓰고, 현재 문제 문구를 짧게 인용하세요.",
            "message와 suggested_fix에는 source_id, field_path, needs_review 같은 내부 용어를 쓰지 마세요.",
            "모든 출력 텍스트는 한국어로 작성하세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def _targeted_qa_items_for_prompt(
    original_products: list[dict[str, Any]],
    original_assets: list[dict[str, Any]],
    current_products: list[dict[str, Any]],
    current_assets: list[dict[str, Any]],
    selected_issues: list[Any],
) -> list[dict[str, Any]]:
    original_product_by_id = {str(product.get("id")): product for product in original_products if isinstance(product, dict)}
    original_asset_by_id = {str(asset.get("product_id")): asset for asset in original_assets if isinstance(asset, dict)}
    current_product_by_id = {str(product.get("id")): product for product in current_products if isinstance(product, dict)}
    current_asset_by_id = {str(asset.get("product_id")): asset for asset in current_assets if isinstance(asset, dict)}
    items: list[dict[str, Any]] = []
    for index, issue in enumerate(selected_issues):
        if not isinstance(issue, dict):
            continue
        product_id = str(issue.get("product_id") or "").strip()
        field_path = str(issue.get("field_path") or "").strip()
        items.append(
            {
                "original_issue_index": index,
                "product_id": product_id,
                "product_title": (current_product_by_id.get(product_id) or original_product_by_id.get(product_id) or {}).get("title"),
                "field_path": field_path,
                "original_issue": {
                    "type": issue.get("type"),
                    "severity": issue.get("severity"),
                    "message": issue.get("message"),
                    "suggested_fix": issue.get("suggested_fix"),
                },
                "original_value": _revision_current_value_for_field(
                    original_product_by_id.get(product_id) or {},
                    original_asset_by_id.get(product_id) or {},
                    field_path,
                ),
                "current_value": _revision_current_value_for_field(
                    current_product_by_id.get(product_id) or {},
                    current_asset_by_id.get(product_id) or {},
                    field_path,
                ),
            }
        )
    return items


def _revision_product_summaries(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        summaries.append(
            {
                "id": product.get("id"),
                "title": product.get("title"),
                "one_liner": product.get("one_liner"),
                "not_to_claim": product.get("not_to_claim", []),
            }
        )
    return summaries


def _revision_patch_targets_for_prompt(
    products: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    revision_context: dict[str, Any],
) -> list[dict[str, Any]]:
    issues = revision_context.get("qa_issues") if isinstance(revision_context, dict) else []
    if not isinstance(issues, list):
        return []
    product_by_id = {str(product.get("id")): product for product in products if isinstance(product, dict)}
    asset_by_id = {str(asset.get("product_id")): asset for asset in assets if isinstance(asset, dict)}
    targets: list[dict[str, Any]] = []
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            continue
        product_id = str(issue.get("product_id") or "").strip()
        if not product_id:
            continue
        field_path = str(issue.get("field_path") or "").strip()
        current_value = _revision_current_value_for_field(
            product_by_id.get(product_id) or {},
            asset_by_id.get(product_id) or {},
            field_path,
        )
        targets.append(
            {
                "issue_index": index,
                "product_id": product_id,
                "product_title": (product_by_id.get(product_id) or {}).get("title"),
                "field_path": field_path,
                "current_value": current_value,
                "issue_message": issue.get("message"),
                "suggested_fix": issue.get("suggested_fix"),
            }
        )
    return targets


def _revision_current_value_for_field(product: dict[str, Any], asset: dict[str, Any], field_path: str) -> Any:
    if not field_path:
        return None
    if field_path in product:
        return product.get(field_path)
    sales_copy = asset.get("sales_copy") if isinstance(asset.get("sales_copy"), dict) else {}
    if field_path.startswith("sales_copy."):
        remainder = field_path.removeprefix("sales_copy.")
        section_match = re.match(r"sections\[(\d+)\]\.(title|body)$", remainder)
        if section_match:
            sections = sales_copy.get("sections") if isinstance(sales_copy.get("sections"), list) else []
            index = int(section_match.group(1))
            key = section_match.group(2)
            if 0 <= index < len(sections) and isinstance(sections[index], dict):
                return sections[index].get(key)
        return sales_copy.get(remainder)
    faq_match = re.match(r"faq\[(\d+)\]\.(question|answer)$", field_path)
    if faq_match:
        faq = asset.get("faq") if isinstance(asset.get("faq"), list) else []
        index = int(faq_match.group(1))
        key = faq_match.group(2)
        if 0 <= index < len(faq) and isinstance(faq[index], dict):
            return faq[index].get(key)
    generic_value = _get_nested_value(asset, field_path)
    if generic_value is not None:
        return generic_value
    return None


def _prompt_revision_context(revision_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(revision_context, dict):
        return {}
    return {
        "source_run_id": revision_context.get("source_run_id"),
        "revision_mode": revision_context.get("revision_mode"),
        "requested_changes": revision_context.get("requested_changes", []),
        "qa_settings": revision_context.get("qa_settings", {}),
        "review_comment": revision_context.get("comment"),
    }


def _evidence_context_from_state(state: GraphState) -> dict[str, Any]:
    return {
        "evidence_profile": state.get("evidence_profile") or {},
        "productization_advice": state.get("productization_advice") or {},
        "data_coverage": state.get("data_coverage") or {},
        "unresolved_gaps": state.get("unresolved_gaps") or [],
        "source_confidence": state.get("source_confidence") or 0.0,
        "ui_highlights": state.get("ui_highlights") or [],
    }


def _qa_settings_from_state(state: GraphState) -> dict[str, Any]:
    normalized = state.get("normalized_request") or {}
    revision_context = state.get("revision_context") or {}
    override = revision_context.get("qa_settings") if isinstance(revision_context, dict) else {}
    override = override if isinstance(override, dict) else {}
    return {
        "region": override.get("region") or normalized.get("region_name"),
        "period": override.get("period")
        or _period_from_range(normalized.get("start_date"), normalized.get("end_date")),
        "target_customer": override.get("target_customer") or normalized.get("target_customer"),
        "product_count": override.get("product_count") or normalized.get("product_count"),
        "preferences": _string_list(override.get("preferences")) or _string_list(normalized.get("preferred_themes")),
        "avoid": _string_list(override.get("avoid")) or _string_list(normalized.get("avoid")),
        "output_language": override.get("output_language") or normalized.get("output_language") or "ko",
    }


def _period_from_range(start_date: Any, _end_date: Any) -> str | None:
    if not isinstance(start_date, str) or len(start_date) < 7:
        return None
    return start_date[:7]


def _summarize_evidence(
    docs: list[dict[str, Any]],
    limit: int = 6,
    *,
    priority_doc_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    summarized = []
    ordered_docs = _prioritize_documents_for_summary(docs, priority_doc_ids or [])
    for doc in ordered_docs[:limit]:
        metadata = doc.get("metadata") or {}
        summarized.append(
            {
                "doc_id": doc.get("doc_id"),
                "title": doc.get("title"),
                "source_item_id": metadata.get("source_item_id"),
                "content_id": metadata.get("content_id"),
                "content_type": metadata.get("content_type"),
                "region_code": metadata.get("region_code"),
                "event_start_date": metadata.get("event_start_date"),
                "event_end_date": metadata.get("event_end_date"),
                "snippet": str(doc.get("snippet") or doc.get("content") or "")[:240],
                "score": doc.get("score"),
            }
        )
    return summarized


def _prioritize_documents_for_summary(
    docs: list[dict[str, Any]],
    priority_doc_ids: list[str],
) -> list[dict[str, Any]]:
    if not priority_doc_ids:
        return docs
    priority = {doc_id: index for index, doc_id in enumerate(priority_doc_ids)}
    indexed_docs = list(enumerate(docs))
    indexed_docs.sort(
        key=lambda item: (
            priority.get(str(item[1].get("doc_id") or ""), len(priority)),
            item[0],
        )
    )
    return [doc for _, doc in indexed_docs]


def _priority_evidence_document_ids(evidence_context: dict[str, Any]) -> list[str]:
    doc_ids: list[str] = []
    for card in _candidate_cards_from_context(evidence_context):
        doc_ids.extend(_string_list(card.get("evidence_document_ids")))
    return _dedupe_texts(doc_ids)


def _summarize_source_items_for_prompt(source_items: list[dict[str, Any]], limit: int = MAX_PRODUCT_COUNT) -> list[dict[str, Any]]:
    summarized: list[dict[str, Any]] = []
    for item in source_items[:limit]:
        if not isinstance(item, dict):
            continue
        summarized.append(
            {
                "id": item.get("id"),
                "content_id": item.get("content_id"),
                "title": item.get("title"),
                "content_type": item.get("content_type"),
                "address": item.get("address"),
                "overview": str(item.get("overview") or "")[:300],
                "event_start_date": item.get("event_start_date"),
                "event_end_date": item.get("event_end_date"),
            }
        )
    return summarized


def _product_evidence_context_for_prompt(evidence_context: dict[str, Any]) -> dict[str, Any]:
    cards = _candidate_cards_from_context(evidence_context)
    advice = evidence_context.get("productization_advice")
    advice = advice if isinstance(advice, dict) else {}
    recommendations = advice.get("candidate_recommendations")
    recommendations = recommendations if isinstance(recommendations, list) else []
    return {
        "source_confidence": evidence_context.get("source_confidence"),
        "data_coverage": evidence_context.get("data_coverage") or {},
        "ui_highlights": _compact_ui_highlights(evidence_context.get("ui_highlights")),
        "usable_claims": _string_list(advice.get("usable_claims"))[:8],
        "candidate_recommendations": [
            item for item in recommendations[:8] if isinstance(item, dict)
        ],
        "candidate_evidence_cards": [_compact_candidate_card_for_product(card) for card in cards[:MAX_PRODUCT_COUNT]],
        "unresolved_gaps": _compact_unresolved_gaps_for_product(evidence_context.get("unresolved_gaps")),
        "claim_limits": _claim_limits_from_context(evidence_context),
        "needs_review": _needs_review_from_context(evidence_context),
    }


def _research_evidence_context_for_prompt(evidence_context: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
    product_context = _product_evidence_context_for_prompt(evidence_context)
    card_refs: list[dict[str, Any]] = []
    card_limit = 8 if compact else MAX_PRODUCT_COUNT
    fact_sample_limit = 1 if compact else 2
    for card in (product_context.get("candidate_evidence_cards") or [])[:card_limit]:
        if not isinstance(card, dict):
            continue
        usable_facts = card.get("usable_facts") if isinstance(card.get("usable_facts"), list) else []
        fact_samples: list[dict[str, Any]] = []
        for fact in usable_facts[:fact_sample_limit]:
            if not isinstance(fact, dict):
                continue
            fact_samples.append(
                {
                    "field": fact.get("field"),
                    "value": str(fact.get("value") or "")[:80],
                }
            )
        card_refs.append(
            {
                "content_id": card.get("content_id"),
                "source_item_id": card.get("source_item_id"),
                "title": card.get("title"),
                "evidence_strength": card.get("evidence_strength"),
                "source_confidence": card.get("source_confidence"),
                "usable_fact_count": len(usable_facts),
                "usable_fact_samples": fact_samples,
                "experience_hook_count": len(_string_list(card.get("experience_hooks"))),
                "recommended_angle_count": len(_string_list(card.get("recommended_product_angles"))),
                "operational_unknowns": _string_list(card.get("operational_unknowns"))[:4],
                "restricted_claims": _string_list(card.get("restricted_claims"))[:4],
                "evidence_document_count": len(_string_list(card.get("evidence_document_ids"))),
            }
        )
    return {
        "source_confidence": product_context.get("source_confidence"),
        "data_coverage": product_context.get("data_coverage"),
        "ui_highlights": product_context.get("ui_highlights"),
        "usable_claims": product_context.get("usable_claims"),
        "candidate_recommendations": product_context.get("candidate_recommendations"),
        "candidate_card_refs": card_refs,
        "candidate_card_count": len(product_context.get("candidate_evidence_cards") or []),
        "unresolved_gaps": (product_context.get("unresolved_gaps") or [])[:8 if compact else 12],
        "claim_limits": (product_context.get("claim_limits") or [])[:6 if compact else 12],
        "needs_review": (product_context.get("needs_review") or [])[:6 if compact else 12],
        "merge_contract": "응답에는 candidate_card_guidance만 작성하세요. 서버가 이 guidance를 원래 candidate_evidence_cards와 병합합니다.",
    }


def _compact_enrichment_summary_for_research(enrichment_summary: dict[str, Any]) -> dict[str, Any]:
    summary = enrichment_summary.get("summary") if isinstance(enrichment_summary.get("summary"), dict) else enrichment_summary
    summary = summary if isinstance(summary, dict) else {}
    executed = summary.get("executed") if isinstance(summary.get("executed"), list) else []
    failed = summary.get("failed") if isinstance(summary.get("failed"), list) else []
    skipped = summary.get("skipped") if isinstance(summary.get("skipped"), list) else []
    return {
        "executed_calls": summary.get("executed_calls", 0),
        "skipped_calls": summary.get("skipped_calls", 0),
        "failed_calls": summary.get("failed_calls", 0),
        "indexed_documents": summary.get("indexed_documents", 0),
        "visual_assets": summary.get("visual_assets", 0),
        "route_assets": summary.get("route_assets", 0),
        "signal_records": summary.get("signal_records", 0),
        "theme_candidates": summary.get("theme_candidates", 0),
        "executed_families": _count_source_families(executed),
        "failed_families": _count_source_families(failed),
        "skipped_families": _count_source_families(skipped),
    }


def _count_source_families(items: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        family = str(item.get("source_family") or "unknown")
        counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _compact_candidate_card_for_product(card: dict[str, Any]) -> dict[str, Any]:
    usable_facts = card.get("usable_facts") if isinstance(card.get("usable_facts"), list) else []
    return {
        "content_id": card.get("content_id"),
        "source_item_id": card.get("source_item_id"),
        "title": card.get("title"),
        "address": card.get("address"),
        "evidence_strength": card.get("evidence_strength"),
        "source_confidence": card.get("source_confidence"),
        "usable_facts": [fact for fact in usable_facts[:8] if isinstance(fact, dict)],
        "experience_hooks": _string_list(card.get("experience_hooks"))[:3],
        "recommended_product_angles": _string_list(card.get("recommended_product_angles"))[:3],
        "operational_unknowns": _string_list(card.get("operational_unknowns"))[:6],
        "restricted_claims": _string_list(card.get("restricted_claims"))[:6],
        "evidence_document_ids": _string_list(card.get("evidence_document_ids"))[:6],
    }


def _compact_unresolved_gaps_for_product(value: Any, limit: int = 12) -> list[dict[str, Any]]:
    gaps = value if isinstance(value, list) else []
    compact: list[dict[str, Any]] = []
    for gap in gaps[:limit]:
        if not isinstance(gap, dict):
            continue
        compact.append(
            {
                "gap_type": gap.get("gap_type"),
                "label": _human_gap_type(gap.get("gap_type")),
                "severity": gap.get("severity"),
                "reason": str(gap.get("productization_impact") or gap.get("reason") or "")[:180],
                "target_content_id": gap.get("target_content_id"),
                "target_item_id": gap.get("target_item_id"),
                "source_item_title": gap.get("source_item_title"),
            }
        )
    return compact


def _compact_ui_highlights(value: Any, limit: int = 5) -> list[dict[str, Any]]:
    highlights = value if isinstance(value, list) else []
    compact: list[dict[str, Any]] = []
    for highlight in highlights[:limit]:
        if not isinstance(highlight, dict):
            continue
        compact.append(
            {
                "title": highlight.get("title"),
                "body": highlight.get("body"),
                "severity": highlight.get("severity"),
            }
        )
    return compact


def _gemini_generation_meta(agent_name: str, purpose: str, result: GeminiJsonResult) -> dict[str, Any]:
    return {
        "agent": agent_name,
        "purpose": purpose,
        "provider": "gemini",
        "model": result.model,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "cost_usd": round(result.cost_usd, 8),
        "paid_tier_equivalent_cost_usd": round(result.paid_tier_equivalent_cost_usd, 8),
        "latency_ms": result.latency_ms,
    }


def _combined_gemini_generation_meta(
    agent_name: str,
    purpose: str,
    results: list[GeminiJsonResult],
) -> dict[str, Any]:
    if not results:
        return {
            "agent": agent_name,
            "purpose": purpose,
            "provider": "gemini",
            "model": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "paid_tier_equivalent_cost_usd": 0.0,
            "latency_ms": 0,
            "call_count": 0,
        }
    models = _dedupe_texts([result.model for result in results])
    return {
        "agent": agent_name,
        "purpose": purpose,
        "provider": "gemini",
        "model": ", ".join(models),
        "prompt_tokens": sum(result.prompt_tokens for result in results),
        "completion_tokens": sum(result.completion_tokens for result in results),
        "total_tokens": sum(result.total_tokens for result in results),
        "cost_usd": round(sum(result.cost_usd for result in results), 8),
        "paid_tier_equivalent_cost_usd": round(
            sum(result.paid_tier_equivalent_cost_usd for result in results),
            8,
        ),
        "latency_ms": sum(result.latency_ms for result in results),
        "call_count": len(results),
    }


def _append_agent_execution(state: GraphState, meta: dict[str, Any]) -> list[dict[str, Any]]:
    return [*state.get("agent_execution", []), meta]


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return _korean_text(value.strip(), key)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    values = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("content") or item.get("text") or item.get("message") or item.get("title") or ""
        text = str(item).strip()
        if text:
            values.append(text)
    return values


def _korean_string_list(value: Any, field_path: str) -> list[str]:
    values = _string_list(value)
    for item in values:
        _korean_text(item, field_path)
    return values


def _normalize_search_keywords(value: Any, product: dict[str, Any]) -> list[str]:
    aliases = {
        "busan": "부산",
        "yacht": "요트",
        "night": "야간 관광",
        "night tour": "야간 관광",
        "food": "푸드투어",
        "food tour": "푸드투어",
        "market": "전통시장",
        "traditional market": "전통시장",
        "festival": "축제",
        "beach": "해변",
        "photo": "사진",
        "photo tour": "사진 투어",
        "foreigner": "외국인",
        "foreigners": "외국인",
        "activity": "액티비티",
        "activities": "액티비티",
        "tour": "투어",
    }
    values: list[str] = []
    for item in _string_list(value):
        normalized = aliases.get(item.strip().lower(), item.strip())
        if _has_korean(normalized):
            values.append(normalized)

    if not values:
        values.extend(_string_list(product.get("core_value")))
        values.append(str(product.get("title") or ""))

    deduped: list[str] = []
    for item in values:
        text = item.strip()
        if text and _has_korean(text) and text not in deduped:
            deduped.append(text)
    return deduped


def _normalize_qa_issue_message(issue: dict[str, Any]) -> str:
    raw_message = str(issue.get("message") or "").strip()
    if raw_message and _has_korean(raw_message):
        return _strip_qa_fix_sentence(_strip_internal_field_paths(raw_message))

    issue_type = str(issue.get("type") or "").strip().lower()
    field_path = str(issue.get("field_path") or "").strip()
    base_message = _qa_issue_default_message(issue_type)
    if field_path:
        return f"{base_message} 확인 위치: {_field_path_label(field_path)}"
    return base_message


def _normalize_qa_suggested_fix(issue: dict[str, Any]) -> str:
    raw_fix = str(issue.get("suggested_fix") or "").strip()
    if not raw_fix:
        return _extract_suggested_fix_from_message(str(issue.get("message") or ""))
    if _has_korean(raw_fix):
        return _strip_internal_field_paths(raw_fix)
    return "운영자가 확인 가능한 표현으로 바꾸고 출처 근거를 함께 표시하세요."


def _is_internal_diagnostic_issue(issue_type: str, message: str, suggested_fix: str) -> bool:
    text = f"{issue_type} {message} {suggested_fix}".lower()
    raw_terms = [
        "source_id",
        "source id",
        "doc_id",
        "field_path",
        "needs_review",
        "missing_pet_policy",
        "fallback",
        "correction",
        "server correction",
    ]
    korean_terms = [
        "서버가 사용 가능한 근거를 보정",
        "실제 근거 목록에 없는",
        "근거 id",
        "근거 문서 id",
        "내부 문서",
        "서버 보정",
    ]
    return any(term in text for term in raw_terms) or any(term in message or term in suggested_fix for term in korean_terms)


def _qa_internal_diagnostic(
    issue: dict[str, Any],
    message: str,
    suggested_fix: str,
    product_ids: set[str],
    products: list[dict[str, Any]],
    *,
    reason: str,
) -> dict[str, Any]:
    product_id = issue.get("product_id")
    inferred_product_id = _infer_issue_product_id(message, products)
    return _qa_issue(
        product_id if product_id in product_ids else inferred_product_id,
        "info",
        "internal_diagnostic",
        message,
        suggested_fix,
        field_path=str(issue.get("field_path") or ""),
        user_visible=False,
        details={"reason": reason, "original_type": issue.get("type")},
    )


def _is_non_actionable_source_metadata_issue(message: str, suggested_fix: str) -> bool:
    text = f"{message} {suggested_fix}"
    if "근거 문서" not in text and "source document" not in text.lower():
        return False
    metadata_terms = ["이벤트 기간 정보가 누락", "event_start_date", "event_end_date", "메타데이터"]
    update_terms = ["근거 문서를 업데이트", "source document", "업데이트해"]
    return any(term in text for term in metadata_terms) or any(term in text for term in update_terms)


def _is_safe_uncertainty_phrase_issue(message: str, suggested_fix: str) -> bool:
    text = f"{message} {suggested_fix}"
    safe_terms = [
        "확인해야 합니다",
        "확인 필요",
        "사전에 확인",
        "문의",
        "변동될 수 있습니다",
        "달라질 수 있습니다",
        "결정될 수 있습니다",
        "중단될 수 있습니다",
        "취소될 수 있습니다",
        "변경될 수 있습니다",
        "어려울 수 있습니다",
        "발생할 수 있습니다",
        "제한이 있을 수 있습니다",
        "최종 확정해야 합니다",
        "현장 상황에 따라",
        "기상 악화",
        "날씨",
    ]
    prohibited_terms = [
        "항상 운영",
        "예약 즉시 확정",
        "반드시 이용 가능",
        "100%",
        "최저가 보장",
        "완전 안전",
        "무조건",
        "확정됩니다",
        "보장합니다",
    ]
    return any(term in text for term in safe_terms) and not any(term in text for term in prohibited_terms)


def _is_marketing_tone_only_issue(message: str, suggested_fix: str) -> bool:
    text = f"{message} {suggested_fix}"
    tone_terms = [
        "환상적인",
        "아름다운",
        "특별한",
        "여유로운",
        "평화로운",
        "편안하게",
        "만끽",
        "감상",
        "즐겨",
        "기대할 수",
        "선사합니다",
        "경험하세요",
        "경험해",
    ]
    if not any(term in text for term in tone_terms):
        return False
    actionable_terms = [
        "출처",
        "근거",
        "가격은",
        "원입니다",
        "최저가",
        "항상",
        "반드시",
        "무조건",
        "100%",
        "예약 즉시 확정",
        "보장합니다",
        "완전 안전",
    ]
    return not any(term in text for term in actionable_terms)


def _is_copy_quality_only_issue(message: str, suggested_fix: str) -> bool:
    text = f"{message} {suggested_fix}"
    copy_quality_terms = [
        "매력이 부족",
        "상품의 매력",
        "상세히 설명",
        "상세 설명이 부족",
        "고객의 이해",
        "특징과 장점",
        "문구가 짧",
        "구체성이 부족",
        "홍보 효과",
        "전환",
    ]
    if not any(term in text for term in copy_quality_terms):
        return False
    risk_terms = [
        "가격",
        "운영시간",
        "상시 운영",
        "예약",
        "안전",
        "외국어",
        "의료",
        "웰니스",
        "효능",
        "반려동물",
        "100%",
        "최저가",
        "보장",
    ]
    return not any(term in text for term in risk_terms)


def _qa_issue_has_problem_quote(message: str) -> bool:
    return bool(re.search(r"['\"“”‘’][^'\"“”‘’]{2,}['\"“”‘’]", message))


def _is_allowed_unquoted_qa_issue(issue_type: str, message: str) -> bool:
    normalized_type = str(issue_type or "").lower()
    if normalized_type in {"source_missing", "content_format"}:
        return True
    if "제목" in message and "불필요한 문자" in message:
        return True
    return False


def _infer_issue_product_id(message: str, products: list[dict[str, Any]]) -> str | None:
    for product in products:
        title = str(product.get("title") or "").strip()
        if title and title in message:
            return str(product.get("id"))
    return None


def _enrich_qa_suggested_fix(
    message: str,
    suggested_fix: str,
    products: list[dict[str, Any]],
) -> str:
    if "불필요한 문자" in message and "제목" in message:
        for product in products:
            title = str(product.get("title") or "").strip()
            cleaned_title = re.sub(r"[\s\d]{3,}$", "", title).strip()
            if title and cleaned_title and title != cleaned_title and title in message:
                return f"상품 제목을 '{cleaned_title}'로 수정하세요."
    return suggested_fix


def _normalize_qa_summary(value: Any, issues: list[dict[str, Any]]) -> str:
    raw_summary = str(value or "").strip()
    if raw_summary and _has_korean(raw_summary):
        return raw_summary
    if issues:
        return f"QA 검수에서 추가 확인이 필요한 이슈 {len(issues)}건이 발견되었습니다."
    return "QA 검수 완료. 차단 수준의 이슈가 없습니다."


def _qa_summary_value_for_issues(value: Any, issues: list[dict[str, Any]]) -> Any:
    if not issues:
        return value
    raw_summary = str(value or "").strip()
    pass_like_terms = ["검수 완료", "이슈가 없습니다", "문제가 없습니다", "pass"]
    if any(term in raw_summary for term in pass_like_terms):
        return None
    return value


def _qa_issue_default_message(issue_type: str) -> str:
    if "prohibited" in issue_type or "forbidden" in issue_type:
        return "금지 표현 포함 여부를 추가 확인해야 합니다."
    if "source" in issue_type or "evidence" in issue_type or "citation" in issue_type:
        return "출처 근거가 충분히 연결되었는지 확인해야 합니다."
    if "price" in issue_type or "cost" in issue_type:
        return "가격 단정 표현 여부를 확인해야 합니다."
    if "date" in issue_type or "schedule" in issue_type or "time" in issue_type:
        return "일정 또는 운영 시간 단정 표현 여부를 확인해야 합니다."
    if "reservation" in issue_type or "availability" in issue_type or "booking" in issue_type:
        return "예약 가능 여부 단정 표현을 확인해야 합니다."
    if "safe" in issue_type or "safety" in issue_type:
        return "절대적 안전 보장 표현 여부를 확인해야 합니다."
    if "language" in issue_type or "foreign" in issue_type:
        return "외국어 지원 표현이 과장되지 않았는지 확인해야 합니다."
    return "QA 검수에서 추가 확인이 필요한 이슈가 있습니다."


def _strip_internal_field_paths(text: str) -> str:
    text = re.sub(
        r"['\"]?([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\]|\.[A-Za-z_][A-Za-z0-9_]*)+)['\"]?",
        lambda match: _field_path_label(match.group(1)),
        text,
    )
    labels = {
        "disclaimer": "유의 문구",
        "not_to_claim": "운영 주의사항",
        "assumptions": "운영 가정",
        "sales_copy": "판매 문구",
        "marketing_assets": "마케팅 문구",
        "source_id": "근거 문서",
        "source_ids": "근거 문서",
        "doc_id": "근거 문서",
        "field_path": "문제 위치",
        "needs_review": "운영자 확인 항목",
        "missing_pet_policy": "반려동물 동반 조건 확인",
    }
    for field_name, label in labels.items():
        text = re.sub(rf"\b{re.escape(field_name)}\b", label, text)
    text = re.sub(r"\bsource id\b", "근거 문서", text, flags=re.IGNORECASE)
    return text


def _field_path_label(path: str) -> str:
    normalized = path.lower()
    if normalized == "disclaimer":
        return "유의 문구"
    if normalized == "not_to_claim":
        return "운영 주의사항"
    if normalized == "assumptions":
        return "운영 가정"
    if "sales_copy.headline" in normalized:
        return "헤드라인"
    if "sales_copy.subheadline" in normalized:
        return "보조 문구"
    if "sales_copy.disclaimer" in normalized:
        return "유의 문구"
    if "sales_copy.sections" in normalized:
        return "상세 설명"
    if normalized.startswith("faq") and ".question" in normalized:
        return "FAQ 질문"
    if normalized.startswith("faq") and ".answer" in normalized:
        return "FAQ 답변"
    if normalized.startswith("search_keywords"):
        return "검색 키워드"
    strategy_label = _marketing_strategy_field_label(path)
    if strategy_label:
        return strategy_label
    if normalized.startswith("marketing_assets"):
        return "마케팅 자산"
    if normalized.startswith("products"):
        return "상품 정보"
    return "해당 항목"


def _extract_suggested_fix_from_message(message: str) -> str:
    sanitized_message = _strip_internal_field_paths(message)
    patterns = [
        r"'([^']+)'(?:와|과) 같이 수정하는 것을 권장합니다",
        r'"([^"]+)"(?:와|과) 같이 수정하는 것을 권장합니다',
        r"'([^']+)'(?:로|으로) 수정",
        r'"([^"]+)"(?:로|으로) 수정',
    ]
    for pattern in patterns:
        match = re.search(pattern, sanitized_message)
        if match:
            return f"'{match.group(1)}'처럼 완화된 표현으로 수정하세요."
    return "표현을 완화하고, 운영자가 확인 가능한 조건형 문장으로 수정하세요."


def _strip_qa_fix_sentence(text: str) -> str:
    patterns = [
        r"\s*['\"][^'\"]+['\"](?:와|과) 같이 수정하는 것을 권장합니다\.?",
        r"\s*['\"][^'\"]+['\"](?:로|으로) 수정하는 것을 권장합니다\.?",
        r"\s*['\"][^'\"]+['\"](?:처럼) 완화된 표현으로 수정하세요\.?",
    ]
    result = text
    for pattern in patterns:
        result = re.sub(pattern, "", result)
    return result.strip()


def _validate_itinerary(value: Any, source_ids: list[str]) -> list[dict[str, Any]]:
    fallback_source_id = source_ids[0] if source_ids else ""
    if not isinstance(value, list):
        return [{"order": 1, "name": "운영 단계 확인", "source_id": fallback_source_id}]
    itinerary = []
    for index, item in enumerate(value[:5]):
        if not isinstance(item, dict):
            continue
        item_source_id = item.get("source_id")
        itinerary.append(
            {
                "order": int(item.get("order") or index + 1),
                "name": _korean_text(str(item.get("name") or "운영 단계 확인"), "itinerary[].name"),
                "source_id": item_source_id if item_source_id in source_ids else fallback_source_id,
            }
        )
    return itinerary or [{"order": 1, "name": "운영 단계 확인", "source_id": fallback_source_id}]


def _validate_faq(value: Any, require_korean: bool = False) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    faq = []
    for item in value[:8]:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if question and answer:
            if require_korean:
                question = _korean_text(question, "faq[].question")
                answer = _korean_text(answer, "faq[].answer")
            _assert_marketing_user_text(question, "faq[].question")
            _assert_marketing_user_text(answer, "faq[].answer")
            faq.append({"question": question, "answer": answer})
    return faq


def _normalize_difficulty(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    mapping = {
        "low": "낮음",
        "easy": "낮음",
        "medium": "보통",
        "moderate": "보통",
        "high": "높음",
        "hard": "높음",
    }
    return mapping.get(normalized, str(value or "보통"))


def _optional_korean_text(value: str, field_path: str) -> str:
    if not value.strip():
        return ""
    return _korean_text(value, field_path)


def _korean_text(value: str, field_path: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_path} must not be empty")
    if not _has_korean(text):
        raise ValueError(f"{field_path} must be written in Korean")
    return text


def _has_korean(text: str) -> bool:
    return any("\uac00" <= char <= "\ud7a3" for char in text)


@contextmanager
def step_log(db: Session, run_id: str, agent_name: str, step_type: str, input_payload: Any):
    started = time.perf_counter()
    step = models.AgentStep(
        run_id=run_id,
        agent_name=agent_name,
        step_type=step_type,
        status="running",
        input=_jsonable(input_payload),
        started_at=models.utcnow(),
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    try:
        yield step
        step.status = "succeeded"
    except Exception as exc:
        step.status = "failed"
        step.error = {"type": exc.__class__.__name__, "message": str(exc)}
        raise
    finally:
        step.latency_ms = int((time.perf_counter() - started) * 1000)
        step.finished_at = models.utcnow()
        db.commit()


def _cost_summary(db: Session, run_id: str) -> dict[str, Any]:
    calls = db.query(models.LLMCall).filter(models.LLMCall.run_id == run_id).all()
    providers = sorted({call.provider for call in calls})
    gemini_calls = sum(1 for call in calls if call.provider == "gemini")
    return {
        "estimated_cost_usd": float(sum(call.cost_usd or 0 for call in calls)),
        "llm_calls": len(calls),
        "gemini_calls": gemini_calls,
        "providers": providers,
        "mode": "gemini",
    }


def _period_start(period: str | None) -> str:
    if period and len(period) >= 7:
        return f"{period[:7]}-01"
    return "2026-05-01"


def _period_end(period: str | None) -> str:
    if period and len(period) >= 7:
        return f"{period[:7]}-31" if period[:7].endswith(("01", "03", "05", "07", "08", "10", "12")) else f"{period[:7]}-30"
    return "2026-05-31"


def _dedupe_items(items):
    seen = set()
    deduped = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        deduped.append(item)
    return deduped


def _tourism_item_to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "to_dict"):
        return item.to_dict()
    return {
        "id": item.id,
        "source": item.source,
        "content_id": item.content_id,
        "content_type": item.content_type,
        "title": item.title,
        "region_code": item.region_code,
        "sigungu_code": item.sigungu_code,
        "legacy_area_code": item.legacy_area_code,
        "legacy_sigungu_code": item.legacy_sigungu_code,
        "ldong_regn_cd": item.ldong_regn_cd,
        "ldong_signgu_cd": item.ldong_signgu_cd,
        "lcls_systm_1": item.lcls_systm_1,
        "lcls_systm_2": item.lcls_systm_2,
        "lcls_systm_3": item.lcls_systm_3,
        "address": item.address,
        "map_x": float(item.map_x) if item.map_x is not None else None,
        "map_y": float(item.map_y) if item.map_y is not None else None,
        "tel": item.tel,
        "homepage": item.homepage,
        "overview": item.overview,
        "image_url": item.image_url,
        "license_type": item.license_type,
        "event_start_date": item.event_start_date,
        "event_end_date": item.event_end_date,
        "raw": item.raw,
    }


def _estimate_tokens(payload: Any) -> int:
    return max(1, len(str(payload)) // 4)


def _jsonable(payload: Any) -> Any:
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    if isinstance(payload, list):
        return [_jsonable(item) for item in payload]
    if isinstance(payload, dict):
        return {str(key): _jsonable(value) for key, value in payload.items()}
    return str(payload)
