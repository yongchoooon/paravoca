from __future__ import annotations

import json
import logging
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
    DATA_GAP_PROFILE_RESPONSE_SCHEMA,
    EVIDENCE_FUSION_RESPONSE_SCHEMA,
    API_FAMILY_PLANNER_RESPONSE_SCHEMA,
    TOURAPI_DETAIL_PLANNER_RESPONSE_SCHEMA,
    build_api_capability_router_prompt,
    build_api_family_planner_prompt,
    build_data_gap_profile_prompt,
    build_evidence_fusion_prompt,
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
    plan_family_deterministic,
    profile_data_gaps,
    select_enrichment_candidate_items,
    summarize_candidate_pool,
    PLANNER_DEFINITIONS,
)
from app.core.config import get_settings
from app.db import models
from app.llm.gemini_gateway import GeminiGatewayError, GeminiJsonResult, call_gemini_json
from app.llm.usage_log import safe_write_llm_usage_log
from app.rag.chroma_store import index_source_documents, search_source_documents
from app.rag.source_documents import upsert_source_documents_from_items
from app.tools.tourism import get_tourism_provider, log_tool_call, upsert_tourism_items


logger = logging.getLogger("uvicorn.error")

MAX_PRODUCT_COUNT = 20


def run_product_planning_workflow(db: Session, run_id: str) -> dict[str, Any]:
    run = _get_workflow_run(db, run_id)
    started = _start_run(db, run)
    graph = _build_graph(db)
    state = _initial_workflow_state(run)
    try:
        final_state = graph.invoke(state)
    except Exception as exc:
        _fail_run(db, run, started, exc)
        raise
    return _complete_run(db, run, started, final_state)


def run_revision_workflow(db: Session, run_id: str) -> dict[str, Any]:
    run = _get_workflow_run(db, run_id)
    context = _revision_context_from_run(run)
    mode = context["revision_mode"]
    started = _start_run(db, run)

    try:
        if mode == "manual_save":
            final_state = _run_manual_save_revision(db, run, context)
        elif mode in {"manual_edit", "qa_only"}:
            final_state = _run_qa_only_revision(db, run, context)
        elif mode == "llm_partial_rewrite":
            final_state = _run_llm_partial_revision(db, run, context)
        else:
            raise ValueError(f"Unsupported revision_mode: {mode}")
    except Exception as exc:
        _fail_run(db, run, started, exc)
        raise
    return _complete_run(db, run, started, final_state)


def _get_workflow_run(db: Session, run_id: str) -> models.WorkflowRun:
    run = db.get(models.WorkflowRun, run_id)
    if not run:
        raise ValueError(f"Workflow run not found: {run_id}")
    return run


def _start_run(db: Session, run: models.WorkflowRun) -> float:
    started = time.perf_counter()
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
        "cost_summary": {"estimated_cost_usd": 0.0, "mode": "rule_based"},
    }


def _fail_run(
    db: Session,
    run: models.WorkflowRun,
    started: float,
    exc: Exception,
) -> None:
    run.status = "failed"
    run.error = {"type": exc.__class__.__name__, "message": str(exc)}
    _finish_run(db, run, started)


def _complete_run(
    db: Session,
    run: models.WorkflowRun,
    started: float,
    final_state: GraphState,
) -> dict[str, Any]:
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
    state.update(
        {
            "product_ideas": products,
            "marketing_assets": marketing_assets,
        }
    )
    _revision_context_step(db, state, context)
    state.update(qa_agent(db, state))
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
    state.update(
        {
            "product_ideas": products,
            "marketing_assets": marketing_assets,
            "qa_report": source_output.get("qa_report") or {},
        }
    )
    _revision_context_step(db, state, context)
    state.update(human_approval_node(db, state))
    return state


def _run_llm_partial_revision(
    db: Session,
    run: models.WorkflowRun,
    context: dict[str, Any],
) -> GraphState:
    state = _base_revision_state(run, context)
    _revision_context_step(db, state, context)
    state.update(revision_patch_agent(db, state))
    state.update(qa_agent(db, state))
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
        "cost_summary": {"estimated_cost_usd": 0.0, "mode": "rule_based"},
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
    return {
        "root_run_id": context.get("root_run_id") if isinstance(context, dict) else run.parent_run_id,
        "parent_run_id": run.parent_run_id,
        "revision_number": run.revision_number,
        "revision_mode": run.revision_mode,
        "source_run_id": context.get("source_run_id") if isinstance(context, dict) else run.parent_run_id,
        "requested_changes": context.get("requested_changes", []) if isinstance(context, dict) else [],
        "qa_settings": context.get("qa_settings", {}) if isinstance(context, dict) else {},
        "comment": context.get("comment") if isinstance(context, dict) else None,
        "approval_history": context.get("approval_history", []) if isinstance(context, dict) else [],
    }


def _build_graph(db: Session):
    graph = StateGraph(GraphState)
    graph.add_node("planner", lambda state: planner_agent(db, state))
    graph.add_node("geo_resolver", lambda state: geo_resolver_agent(db, state))
    graph.add_node("geo_exit", lambda state: geo_exit_node(db, state))
    graph.add_node("baseline_data", lambda state: baseline_data_agent(db, state))
    graph.add_node("data_gap_profiler", lambda state: data_gap_profiler_agent(db, state))
    graph.add_node("api_capability_router", lambda state: api_capability_router_agent(db, state))
    graph.add_node("tourapi_detail_planner", lambda state: tourapi_detail_planner_agent(db, state))
    graph.add_node("visual_data_planner", lambda state: visual_data_planner_agent(db, state))
    graph.add_node("route_signal_planner", lambda state: route_signal_planner_agent(db, state))
    graph.add_node("theme_data_planner", lambda state: theme_data_planner_agent(db, state))
    graph.add_node("data_enrichment", lambda state: data_enrichment_agent(db, state))
    graph.add_node("evidence_fusion", lambda state: evidence_fusion_agent(db, state))
    graph.add_node("research", lambda state: research_agent(db, state))
    graph.add_node("product", lambda state: product_agent(db, state))
    graph.add_node("marketing", lambda state: marketing_agent(db, state))
    graph.add_node("qa", lambda state: qa_agent(db, state))
    graph.add_node("human_approval", lambda state: human_approval_node(db, state))

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
        if settings.llm_enabled:
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
        else:
            normalized = _default_normalized_request(request)
            meta = _rule_based_generation_meta("PlannerAgent", "planner")
            step.model = "rule-based-v1"
            record_rule_based_llm_call(db, state["run_id"], step.id, "planner", request, normalized)
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
        if settings.llm_enabled:
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
        else:
            meta = _rule_based_generation_meta("GeoResolverAgent", "geo_resolution")
            step.model = "rule-based-v1"
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
        if not settings.llm_enabled:
            record_rule_based_llm_call(db, state["run_id"], step.id, "geo_resolution", resolver_input, step.output)
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
        record_rule_based_llm_call(db, state["run_id"], step.id, "geo_scope_exit", geo_scope, report)
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

        locations = _locations_for_tourapi_search(geo_scope)
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
        }
        primary_keyword = _keyword_for_geo_scope(normalized, geo_scope)
        for location in locations:
            geo_kwargs = _tourapi_geo_kwargs(location)
            keyword = _keyword_for_geo_scope(normalized, geo_scope, location)
            arguments_base = {
                **geo_kwargs,
                "geo_role": location.get("role") if location else None,
                "location_name": location.get("name") if location else "nationwide",
            }
            attractions = log_tool_call(
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
        items = _filter_items_by_geo_scope(items, geo_scope=geo_scope, run_id=run_id)
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
        source_documents = upsert_source_documents_from_items(db, items)
        diagnostics["source_document_upsert_count"] = len(source_documents)
        indexed_count = index_source_documents(db, source_documents)
        diagnostics["indexed_document_count"] = indexed_count
        vector_filters = _vector_filters_for_geo_scope(geo_scope, source=provider_source)
        diagnostics["vector_search_filter"] = vector_filters
        retrieved = log_tool_call(
            db=db,
            run_id=run_id,
            step_id=step.id,
            tool_name="vector_search",
            arguments={
                "query": primary_keyword,
                "top_k": 10,
                "filters": vector_filters,
            },
            source="chroma",
            call=lambda: search_source_documents(
                query=primary_keyword,
                top_k=10,
                filters=vector_filters,
            ),
        )
        diagnostics["vector_search_result_count"] = len(retrieved)
        retrieved = _filter_retrieved_documents_by_geo_scope(
            retrieved,
            geo_scope=geo_scope,
            run_id=run_id,
        )
        diagnostics["post_geo_filter_result_count"] = len(retrieved)
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
    input_payload = {
        "source_item_count": len(state.get("source_items", [])),
        "retrieved_document_count": len(state.get("retrieved_documents", [])),
        "normalized_request": state.get("normalized_request", {}),
        "candidate_pool_summary": state.get("candidate_pool_summary", {}),
    }
    with step_log(db, state["run_id"], "DataGapProfilerAgent", "data_gap_profile", input_payload) as step:
        if settings.llm_enabled:
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
                ),
                response_schema=DATA_GAP_PROFILE_RESPONSE_SCHEMA,
                max_output_tokens=16384,
                temperature=0.1,
                settings=settings,
            )
            gap_report = normalize_gap_profile_payload(
                gemini_result.data,
                source_items=state.get("source_items", []),
                retrieved_documents=state.get("retrieved_documents", []),
                normalized_request=state.get("normalized_request", {}),
            )
            meta = _gemini_generation_meta("DataGapProfilerAgent", "data_gap_profile", gemini_result)
            step.model = gemini_result.model
        else:
            gap_report = profile_data_gaps(
                source_items=state.get("source_items", []),
                retrieved_documents=state.get("retrieved_documents", []),
                normalized_request=state.get("normalized_request", {}),
            )
            gap_report = {
                **gap_report,
                "reasoning_summary": gap_report.get("reasoning_summary")
                or "LLM_ENABLED=false라 Gemini gap 판단을 실행하지 않고 로컬 테스트 호환 경로로 계산했습니다.",
                "needs_review": gap_report.get("needs_review") or [],
            }
            meta = _offline_generation_meta("DataGapProfilerAgent", "data_gap_profile")
            step.model = meta["model"]
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
        if settings.llm_enabled:
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
        else:
            capability_routing = normalize_family_routing_payload(
                {"family_routes": [], "routing_reasoning": "LLM_ENABLED=false라 로컬 호환 경로로 family lane을 분배했습니다."},
                gap_report=gap_report,
                settings=settings,
            )
            meta = _offline_generation_meta("ApiCapabilityRouterAgent", "api_capability_routing")
            step.model = meta["model"]
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
        if settings.llm_enabled:
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
        else:
            fragment = plan_family_deterministic(
                planner_key=planner_key,
                capability_routing=capability_routing,
                gap_report=gap_report,
                settings=settings,
                max_call_budget=max_call_budget,
                existing_planned_count=lane_existing_planned_count,
            )
            meta = _offline_generation_meta(definition["agent_name"], definition["purpose"])
            step.model = meta["model"]
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
        documents = refreshed_documents or state.get("retrieved_documents", [])
        base_fusion = fuse_evidence(
            db=db,
            source_items=state.get("source_items", []),
            retrieved_documents=documents,
            gap_report=state.get("data_gap_report") or {"gaps": []},
            enrichment_summary=state.get("enrichment_summary") or {},
        )
        if settings.llm_enabled:
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
        else:
            fusion = {
                **base_fusion,
                "ui_highlights": _offline_fusion_highlights(base_fusion, state.get("enrichment_summary") or {}),
            }
            meta = _offline_generation_meta("EvidenceFusionAgent", "evidence_fusion")
            step.model = meta["model"]
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
    query = _keyword_for_geo_scope(normalized, geo_scope)
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
            "kto_eco",
            "kto_medical",
        ],
    )
    documents = log_tool_call(
        db=db,
        run_id=state["run_id"],
        step_id=step_id,
        tool_name="vector_search_post_enrichment",
        arguments={"query": query, "top_k": 10, "filters": filters},
        source="chroma",
        call=lambda: search_source_documents(query=query, top_k=10, filters=filters),
    )
    return _filter_retrieved_documents_by_geo_scope(
        documents,
        geo_scope=geo_scope,
        run_id=state["run_id"],
    )


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


def _locations_for_tourapi_search(geo_scope: dict[str, Any]) -> list[dict[str, Any]]:
    if geo_scope.get("allow_nationwide"):
        return [{}]
    locations = geo_scope.get("locations")
    return locations if isinstance(locations, list) else []


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
    location_name = (location or {}).get("keyword") or (location or {}).get("name")
    if not location_name:
        locations = geo_scope.get("locations") if isinstance(geo_scope.get("locations"), list) else []
        location_name = " ".join(str(item.get("keyword") or item.get("name") or "") for item in locations)
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


def _vector_filters_for_geo_scope(geo_scope: dict[str, Any], *, source: str | list[str]) -> dict[str, Any]:
    filters: dict[str, Any] = {"source": source}
    if geo_scope.get("allow_nationwide"):
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
    return filters


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
    if geo_scope.get("allow_nationwide"):
        return documents
    locations = _locations_for_tourapi_search(geo_scope)
    if not locations:
        return []
    filtered = [
        document
        for document in documents
        if _document_matches_geo_scope(document, locations)
    ]
    dropped = len(documents) - len(filtered)
    if dropped:
        logger.warning(
            "Dropped %s off-region retrieved documents for run_id=%s geo_scope=%s",
            dropped,
            run_id,
            geo_scope,
        )
    return filtered


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
        if settings.llm_enabled:
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
        else:
            summary = build_offline_research_synthesis(state)
            meta = _rule_based_generation_meta("ResearchSynthesisAgent", "research")
            step.model = "rule-based-v1"
            record_rule_based_llm_call(db, state["run_id"], step.id, "research", docs, summary)
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
        if not settings.llm_enabled:
            products = build_rule_based_products(normalized, docs, evidence_context=evidence_context)
            meta = _rule_based_generation_meta("ProductAgent", "product_generation")
            step.model = "rule-based-v1"
            record_rule_based_llm_call(db, state["run_id"], step.id, "product_generation", normalized, products)
        else:
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
        if not settings.llm_enabled:
            assets = build_rule_based_marketing(products)
            meta = _rule_based_generation_meta("MarketingAgent", "marketing_generation")
            step.model = "rule-based-v1"
            record_rule_based_llm_call(db, state["run_id"], step.id, "marketing_generation", products, assets)
        else:
            gemini_result = call_gemini_json(
                db=db,
                run_id=state["run_id"],
                step_id=step.id,
                purpose="marketing_generation",
                prompt=_marketing_prompt(
                    products,
                    docs,
                    revision_context,
                    evidence_context,
                    qa_settings,
                ),
                response_schema=MARKETING_RESPONSE_SCHEMA,
                max_output_tokens=16384,
                temperature=0.35,
                settings=settings,
            )
            try:
                assets = validate_marketing_assets(gemini_result.data, products, evidence_context=evidence_context)
            except ValueError as exc:
                if not _should_retry_marketing_validation(exc):
                    raise
                repair_result = call_gemini_json(
                    db=db,
                    run_id=state["run_id"],
                    step_id=step.id,
                    purpose="marketing_generation_repair",
                    prompt=_marketing_prompt(
                        products,
                        docs,
                        revision_context,
                        evidence_context,
                        qa_settings,
                        validation_error=str(exc),
                    ),
                    response_schema=MARKETING_RESPONSE_SCHEMA,
                    max_output_tokens=16384,
                    temperature=0.2,
                    settings=settings,
                )
                assets = validate_marketing_assets(repair_result.data, products, evidence_context=evidence_context)
                gemini_result = repair_result
            meta = _gemini_generation_meta("MarketingAgent", "marketing_generation", gemini_result)
            step.model = gemini_result.model
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
        if not settings.llm_enabled:
            qa_report = build_rule_based_qa(
                products,
                assets,
                docs=docs,
                evidence_context=evidence_context,
                qa_settings=qa_settings,
            )
            meta = _rule_based_generation_meta("QAComplianceAgent", "qa_review")
            step.model = "rule-based-v1"
            record_rule_based_llm_call(db, state["run_id"], step.id, "qa_review", assets, qa_report)
        else:
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
        if not settings.llm_enabled:
            patch_payload = build_rule_based_revision_patch(
                products,
                marketing_assets,
                state.get("revision_context", {}),
            )
            meta = _rule_based_generation_meta("RevisionPatchAgent", "revision_patch")
            step.model = "rule-based-v1"
            record_rule_based_llm_call(
                db,
                state["run_id"],
                step.id,
                "revision_patch",
                state.get("revision_context", {}),
                patch_payload,
            )
        else:
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
        "candidate_evidence_cards",
        "usable_claims",
        "restricted_claims",
        "operational_unknowns",
        "unresolved_gaps",
        "product_generation_guidance",
        "qa_risk_notes",
    ],
    "properties": {
        "research_brief": {"type": "string"},
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
                    "itinerary": {"type": "array", "items": {"type": "object"}},
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

MARKETING_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["marketing_assets"],
    "properties": {
        "marketing_assets": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["product_id", "sales_copy", "faq", "sns_posts", "search_keywords"],
                "properties": {
                    "product_id": {"type": "string"},
                    "sales_copy": {"type": "object"},
                    "faq": {"type": "array", "items": {"type": "object"}},
                    "sns_posts": {"type": "array", "items": {"type": "string"}},
                    "search_keywords": {"type": "array", "items": {"type": "string"}},
                    "evidence_disclaimer": {"type": "string"},
                    "claim_limits": {"type": "array", "items": {"type": "string"}},
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
        "notes": {"type": "array"},
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


def build_rule_based_products(
    normalized: dict[str, Any],
    docs: list[dict[str, Any]],
    *,
    evidence_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    requested_count = _desired_product_count(normalized, fallback=3)
    count = _effective_product_count(normalized, docs, fallback=3)
    region_label = _region_label_from_normalized(normalized)
    templates = [
        (f"{region_label} 야간 로컬 미식 투어", ["야경", "로컬 음식", "짧은 동선"]),
        (f"{region_label} 대표 액티비티 사진 코스", ["액티비티", "사진", "야간 관광"]),
        (f"{region_label} 시즌 행사 연계 패키지", ["축제", "관광지", "시즌성"]),
        (f"{region_label} 로컬 산책 + 카페 투어", ["로컬 산책", "카페", "가벼운 도보"]),
        (f"{region_label} 문화 체험 입문 클래스", ["문화 체험", "푸드투어", "현장 확인"]),
    ]
    source_ids = [str(doc["doc_id"]) for doc in docs if doc.get("doc_id")]
    if not source_ids:
        raise ValueError("TourAPI source documents are required for product generation")
    coverage_notes = _coverage_notes_from_context(evidence_context or {})
    shortage_note = _product_count_shortage_note(requested_count, count, len(source_ids))
    if shortage_note:
        coverage_notes = _dedupe_texts([shortage_note, *coverage_notes])
    context_claim_limits = _claim_limits_from_context(evidence_context or {})
    products = []
    for index in range(count):
        title, core = templates[index % len(templates)]
        product_source_ids = source_ids[: min(3, len(source_ids))]
        not_to_claim = _dedupe_texts(["가격 확정", "항상 운영", "예약 즉시 확정", *context_claim_limits])[:8]
        products.append(
            {
                "id": f"product_{index + 1}",
                "title": title,
                "one_liner": f"{region_label}에서 {normalized['target_customer']} 대상 운영자가 검토할 수 있는 액티비티 초안입니다.",
                "target_customer": normalized["target_customer"],
                "core_value": core,
                "itinerary": [
                    {"order": 1, "name": "source 기반 후보지 방문", "source_id": source_ids[index % len(source_ids)]},
                    {"order": 2, "name": "현장 운영 조건 확인", "source_id": source_ids[(index + 1) % len(source_ids)]},
                ],
                "estimated_duration": "3~4시간",
                "operation_difficulty": "보통",
                "source_ids": product_source_ids,
                "assumptions": ["세부 가격과 예약 가능 여부는 운영자가 확정해야 합니다."],
                "not_to_claim": not_to_claim,
                "evidence_summary": _evidence_summary_for_product(product_source_ids, docs),
                "needs_review": _needs_review_from_context(evidence_context or {})[:6],
                "coverage_notes": coverage_notes[:6],
                "claim_limits": not_to_claim,
            }
        )
    return products


def build_rule_based_marketing(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assets = []
    for product in products:
        assets.append(
            {
                "product_id": product["id"],
                "sales_copy": {
                    "headline": product["title"],
                    "subheadline": product["one_liner"],
                    "sections": [
                        {"title": "추천 포인트", "body": ", ".join(product["core_value"])},
                        {"title": "운영 메모", "body": "일정, 가격, 포함사항은 최종 확인 후 게시하세요."},
                        {"title": "출처 기반 구성", "body": "연결된 관광 데이터 source를 기준으로 구성한 초안입니다."},
                    ],
                    "disclaimer": "세부 일정, 가격, 포함사항은 운영자가 최종 확정해야 합니다.",
                },
                "faq": [
                    {"question": "우천 시에도 진행하나요?", "answer": "현장 안전 기준에 따라 변경될 수 있어 운영자 확인이 필요합니다."},
                    {"question": "가격이 확정되어 있나요?", "answer": "가격은 공급사 조건 확인 후 확정해야 합니다."},
                    {"question": "외국어 안내가 포함되나요?", "answer": "가이드 포함 여부는 운영자가 최종 설정해야 합니다."},
                    {"question": "집결지는 어디인가요?", "answer": "상품 등록 전 정확한 집결지를 확정해야 합니다."},
                    {"question": "행사 일정이 바뀌면 어떻게 되나요?", "answer": "공식 일정 변경 시 상품 일정도 함께 업데이트해야 합니다."},
                ],
                "sns_posts": [
                    f"{product['title']} 초안",
                    "요청 지역의 로컬 경험을 묶은 액티비티 후보",
                    "운영 확정 전 일정과 포함사항을 확인하세요",
                ],
                "search_keywords": [product["title"], "외국인", "액티비티", "야경", "푸드투어", "축제", "로컬", "전통시장"],
                "evidence_disclaimer": _marketing_evidence_disclaimer(product),
                "claim_limits": _dedupe_texts(
                    _string_list(product.get("claim_limits")) + _string_list(product.get("not_to_claim"))
                )[:8],
            }
        )
    return assets


def build_rule_based_qa(
    products: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    *,
    docs: list[dict[str, Any]] | None = None,
    evidence_context: dict[str, Any] | None = None,
    qa_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues = []
    prohibited = ["100% 만족", "무조건", "항상 운영", "최저가 보장", "완전 안전", "예약 즉시 확정"]
    for asset in assets:
        text = str(asset)
        for phrase in prohibited:
            if phrase in text:
                issues.append(
                    {
                        "product_id": asset["product_id"],
                        "severity": "high",
                        "type": "prohibited_phrase",
                        "message": f"금지 표현 포함: {phrase}",
                        "field_path": "marketing_assets",
                        "suggested_fix": "과장 또는 단정 표현을 운영자 확인 필요 문구로 바꾸세요.",
                    }
                )
    issues = _dedupe_qa_issues(
        [
            *issues,
            *_evidence_based_qa_issues(
                products,
                assets,
                docs or [],
                evidence_context or {},
                qa_settings or {},
            ),
        ]
    )
    return {
        "overall_status": "needs_review" if issues else "pass",
        "summary": "자동 검수 완료. 가격/일정/포함사항은 사람 승인 전 확인 필요.",
        "issues": issues,
        "pass_count": len(products) if not issues else 0,
        "needs_review_count": len(products) if issues else 0,
        "fail_count": 0,
    }


def build_rule_based_revision_patch(
    products: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    revision_context: dict[str, Any],
) -> dict[str, Any]:
    product_patches = []
    for product in products:
        title = str(product.get("title") or "")
        cleaned_title = re.sub(r"[\s\d]{3,}$", "", title).strip()
        if cleaned_title and cleaned_title != title:
            product_patches.append(
                {
                    "product_id": product.get("id"),
                    "fields": {"title": cleaned_title},
                }
            )
    return {
        "product_patches": product_patches,
        "marketing_patches": [],
        "notes": ["규칙 기반 revision patch는 명확한 제목 정리만 처리합니다."],
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
        (("생태", "친환경"), "생태"),
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
    shortage_note = _product_count_shortage_note(requested_count, product_count, len(available_source_ids))
    for index, product in enumerate(products[:product_count]):
        if not isinstance(product, dict):
            raise ValueError("Product item must be an object")
        raw_source_ids = _string_list(product.get("source_ids"))
        invalid_source_ids = [source_id for source_id in raw_source_ids if source_id not in allowed_source_ids]
        source_ids = [source_id for source_id in raw_source_ids if source_id in allowed_source_ids]
        review_notes = _safe_korean_string_list(product.get("needs_review"), "products[].needs_review")
        if invalid_source_ids:
            review_notes.append("모델이 실제 근거 목록에 없는 source id를 반환해 서버에서 제외했습니다.")
        if not source_ids:
            source_ids = available_source_ids[: min(3, len(available_source_ids))]
            review_notes.append("상품에 연결할 근거 id가 부족해 서버가 사용 가능한 근거를 보정했습니다.")
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
        validated.append(
            {
                "id": str(product.get("id") or f"product_{index + 1}"),
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
                "source_ids": source_ids[:3],
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
            }
        )
    return validated


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
        sns_posts = _korean_string_list(asset.get("sns_posts"), "marketing_assets[].sns_posts")[:5]
        if not sns_posts:
            raise ValueError(f"marketing_assets[{product['id']}].sns_posts must not be empty")
        search_keywords = _normalize_search_keywords(asset.get("search_keywords"), product)[:12]
        if not search_keywords:
            raise ValueError(f"marketing_assets[{product['id']}].search_keywords must not be empty")
        validated.append(
            {
                "product_id": product["id"] if asset.get("product_id") in product_ids else product["id"],
                "sales_copy": sales_copy,
                "faq": faq,
                "sns_posts": sns_posts,
                "search_keywords": search_keywords,
                "evidence_disclaimer": _safe_korean_text(
                    asset.get("evidence_disclaimer"),
                    "marketing_assets[].evidence_disclaimer",
                    fallback=_marketing_evidence_disclaimer(product, evidence_context or {}),
                ),
                "claim_limits": _dedupe_texts(
                    [
                        *_safe_korean_string_list(asset.get("claim_limits"), "marketing_assets[].claim_limits"),
                        *_string_list(product.get("claim_limits")),
                        *_string_list(product.get("not_to_claim")),
                    ]
                )[:10],
            }
        )
    return validated


def _desired_product_count(normalized: dict[str, Any], fallback: int) -> int:
    try:
        count = int(normalized.get("product_count") or fallback)
    except (TypeError, ValueError):
        count = fallback
    return max(1, min(MAX_PRODUCT_COUNT, count))


def _effective_product_count(normalized: dict[str, Any], docs: list[dict[str, Any]], fallback: int = 1) -> int:
    requested = _desired_product_count(normalized, fallback=fallback)
    evidence_count = len({str(doc.get("doc_id")) for doc in docs if doc.get("doc_id")})
    if evidence_count <= 0:
        return requested
    return max(1, min(requested, evidence_count))


def _product_count_shortage_note(requested_count: int, generated_count: int, evidence_count: int) -> str:
    if requested_count <= generated_count:
        return ""
    return (
        f"요청한 상품은 {requested_count}개지만 사용 가능한 근거 데이터가 {evidence_count}개라 "
        f"{generated_count}개까지만 생성했습니다."
    )


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
    return (
        "must be written in Korean" in message
        and (
            "marketing_assets" in message
            or "sales_copy" in message
            or "faq" in message
            or "sns_posts" in message
            or "search_keywords" in message
        )
    )


def _dedupe_texts(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


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
    source_confidence = evidence_context.get("source_confidence")
    if isinstance(source_confidence, (int, float)):
        notes.append(f"전체 근거 신뢰도는 약 {round(float(source_confidence) * 100)}% 수준입니다.")
    gaps = evidence_context.get("unresolved_gaps") if isinstance(evidence_context.get("unresolved_gaps"), list) else []
    if gaps:
        gap_labels = sorted({_human_gap_type(gap.get("gap_type")) for gap in gaps if isinstance(gap, dict)})
        notes.append(f"확인이 필요한 정보: {', '.join(gap_labels[:6])}")
    coverage = evidence_context.get("data_coverage")
    if isinstance(coverage, dict) and coverage:
        notes.append("상세, 이미지, 운영 조건 커버리지는 Data Coverage에서 함께 확인해야 합니다.")
    return _dedupe_texts(notes)


def _normalize_evidence_summary(value: Any, source_ids: list[str], docs: list[dict[str, Any]]) -> str:
    if isinstance(value, str) and value.strip() and _has_korean(value):
        return value.strip()
    list_value = _safe_korean_string_list(value, "products[].evidence_summary")
    if list_value:
        return " ".join(list_value[:3])
    return _evidence_summary_for_product(source_ids, docs)


def _evidence_summary_for_product(source_ids: list[str], docs: list[dict[str, Any]]) -> str:
    titles_by_id = {str(doc.get("doc_id")): str(doc.get("title") or "근거 문서") for doc in docs if doc.get("doc_id")}
    titles = [titles_by_id.get(source_id, source_id) for source_id in source_ids]
    if not titles:
        return "연결된 근거가 부족해 운영자 확인이 필요합니다."
    return f"{len(source_ids)}개 근거를 사용했습니다: {', '.join(titles[:3])}"


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
                        "high",
                        "source_missing",
                        "상품이 실제 근거 목록에 없는 문서를 참조하고 있습니다.",
                        "실제 근거 문서에 있는 source id만 연결하세요.",
                    )
                )

        public_text = _public_product_text(product)
        asset = assets_by_product_id.get(product_id)
        if asset:
            public_text = f"{public_text}\n{_public_marketing_text(asset)}"
        issues.extend(_unsupported_claim_issues(product_id, public_text, unresolved_types))
        for avoid in avoid_rules:
            if avoid and avoid in public_text:
                issues.append(
                    _qa_issue(
                        product_id,
                        "medium",
                        "avoid_rule",
                        f"요청한 회피 조건과 충돌하는 표현이 포함되어 있습니다: {avoid}",
                        "해당 표현을 제거하거나 운영자 확인 필요 문구로 바꾸세요.",
                    )
                )
    return _dedupe_qa_issues(issues)


def _qa_issue(
    product_id: str | None,
    severity: str,
    issue_type: str,
    message: str,
    suggested_fix: str,
) -> dict[str, Any]:
    return {
        "product_id": product_id,
        "severity": severity,
        "type": issue_type,
        "message": message,
        "field_path": "",
        "suggested_fix": suggested_fix,
    }


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
    sales_copy = asset.get("sales_copy") if isinstance(asset.get("sales_copy"), dict) else {}
    sections = sales_copy.get("sections") if isinstance(sales_copy.get("sections"), list) else []
    faq = asset.get("faq") if isinstance(asset.get("faq"), list) else []
    values: list[str] = [
        str(sales_copy.get("headline") or ""),
        str(sales_copy.get("subheadline") or ""),
    ]
    for section in sections:
        if isinstance(section, dict):
            values.extend([str(section.get("title") or ""), str(section.get("body") or "")])
    for item in faq:
        if isinstance(item, dict):
            values.extend([str(item.get("question") or ""), str(item.get("answer") or "")])
    values.extend(_string_list(asset.get("sns_posts")))
    return "\n".join(values)


def _unsupported_claim_issues(product_id: str, public_text: str, unresolved_types: set[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    checks = [
        (
            "missing_price_or_fee",
            "price_claim",
            [r"\d[\d,]*\s*원(?:입니다|으로|에|부터|까지)?", r"무료입니다", r"최저가(?:를)? 보장"],
            "가격이나 무료 여부를 단정하고 있습니다.",
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
        if any(re.search(pattern, public_text) for pattern in patterns):
            issues.append(_qa_issue(product_id, "high", issue_type, message, suggested_fix))

    absolute_safety_patterns = [r"100%\s*안전", r"완전 안전", r"안전(?:을)? 보장"]
    if any(re.search(pattern, public_text) for pattern in absolute_safety_patterns):
        issues.append(
            _qa_issue(
                product_id,
                "high",
                "safety_claim",
                "절대적 안전 보장처럼 보이는 표현이 포함되어 있습니다.",
                "안전 관련 표현은 현장 조건과 운영자 확인 기준으로 완화하세요.",
            )
        )
    return issues


def apply_revision_patch(
    payload: dict[str, Any],
    products: list[dict[str, Any]],
    marketing_assets: list[dict[str, Any]],
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
            if key in fields:
                product[key] = _korean_text(str(fields[key]), f"products[].{key}")
        for key in ["core_value", "assumptions", "not_to_claim"]:
            if key in fields:
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
                if key in sales_copy_patch:
                    sales_copy[key] = _korean_text(str(sales_copy_patch[key]), f"sales_copy.{key}")
            _apply_section_patches(sales_copy, sales_copy_patch.get("sections"))

        _apply_faq_patches(asset, patch.get("faq"))
        if "sns_posts" in patch:
            sns_posts = _korean_string_list(patch.get("sns_posts"), "marketing_assets[].sns_posts")
            if sns_posts:
                asset["sns_posts"] = sns_posts[:5]
        if "search_keywords" in patch:
            product = product_by_id.get(asset.get("product_id")) or {}
            keywords = _normalize_search_keywords(patch.get("search_keywords"), product)
            if keywords:
                asset["search_keywords"] = keywords[:12]

    return patched_products, patched_assets


def _apply_section_patches(sales_copy: dict[str, Any], patches: Any) -> None:
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
        if "title" in patch:
            section["title"] = _korean_text(str(patch["title"]), "sales_copy.sections[].title")
        if "body" in patch:
            section["body"] = _korean_text(str(patch["body"]), "sales_copy.sections[].body")


def _apply_faq_patches(asset: dict[str, Any], patches: Any) -> None:
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
        if "question" in patch:
            item["question"] = _korean_text(str(patch["question"]), "faq[].question")
        if "answer" in patch:
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
    normalized_sections = [
        {
            "title": _korean_text(str(section.get("title") or "섹션"), "sales_copy.sections[].title"),
            "body": _korean_text(str(section.get("body") or ""), "sales_copy.sections[].body"),
        }
        for section in sections
        if isinstance(section, dict)
    ][:4]
    if not normalized_sections:
        raise ValueError("sales_copy.sections must contain at least one valid section")
    return {
        "headline": _korean_text(str(sales_copy.get("headline") or product["title"]), "sales_copy.headline"),
        "subheadline": _korean_text(str(sales_copy.get("subheadline") or product["one_liner"]), "sales_copy.subheadline"),
        "sections": normalized_sections,
        "disclaimer": _korean_text(str(
            sales_copy.get("disclaimer")
            or "세부 일정, 가격, 포함사항은 운영자가 최종 확정해야 합니다."
        ), "sales_copy.disclaimer"),
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
    validated_issues = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        message = _normalize_qa_issue_message(issue)
        suggested_fix = _normalize_qa_suggested_fix(issue)
        if _is_non_actionable_source_metadata_issue(message, suggested_fix):
            continue
        if _is_safe_uncertainty_phrase_issue(message, suggested_fix):
            continue
        if _is_marketing_tone_only_issue(message, suggested_fix):
            continue
        product_id = issue.get("product_id")
        inferred_product_id = _infer_issue_product_id(message, products)
        validated_issues.append(
            {
                "product_id": product_id if product_id in product_ids else inferred_product_id,
                "severity": str(issue.get("severity") or "medium"),
                "type": str(issue.get("type") or "general"),
                "message": message,
                "field_path": str(issue.get("field_path") or ""),
                "suggested_fix": _enrich_qa_suggested_fix(message, suggested_fix, products),
            }
        )
    validated_issues = _dedupe_qa_issues(
        [
            *validated_issues,
            *_evidence_based_qa_issues(
                products,
                marketing_assets or [],
                docs or [],
                evidence_context or {},
                qa_settings or {},
            ),
        ]
    )
    overall_status = str(payload.get("overall_status") or ("needs_review" if validated_issues else "pass"))
    if validated_issues and overall_status == "pass":
        overall_status = "needs_review"
    if not validated_issues:
        return {
            "overall_status": "pass",
            "summary": _normalize_qa_summary(None, []),
            "issues": [],
            "pass_count": len(products),
            "needs_review_count": 0,
            "fail_count": 0,
        }
    return {
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


def build_offline_research_synthesis(state: GraphState) -> dict[str, Any]:
    docs = state.get("retrieved_documents", [])
    evidence_context = _evidence_context_from_state(state)
    source_ids = [str(doc.get("doc_id")) for doc in docs[:5] if doc.get("doc_id")]
    region_label = _region_label_from_normalized(state.get("normalized_request", {}))
    payload = {
        "research_brief": (
            f"{region_label}은 수집된 TourAPI/RAG 근거를 기준으로 상품화 후보를 검토할 수 있습니다. "
            "세부 운영 조건은 EvidenceFusion의 후보별 card와 unresolved gap을 따라야 합니다."
        ),
        "candidate_evidence_cards": _product_evidence_context_for_prompt(evidence_context)["candidate_evidence_cards"],
        "usable_claims": _string_list(
            (evidence_context.get("productization_advice") or {}).get("usable_claims")
            if isinstance(evidence_context.get("productization_advice"), dict)
            else []
        ) or ["TourAPI에 있는 장소명, 주소, 개요는 근거와 함께 사용할 수 있습니다."],
        "restricted_claims": _claim_limits_from_context(evidence_context)
        or ["가격, 예약 가능 여부, 운영 시간은 운영자가 최종 확인해야 합니다."],
        "operational_unknowns": _needs_review_from_context(evidence_context),
        "unresolved_gaps": _compact_unresolved_gaps_for_product(evidence_context.get("unresolved_gaps")),
        "product_generation_guidance": [
            "각 상품은 실제 evidence_document_ids와 연결된 candidate evidence card를 사용하세요.",
            "운영 조건이 부족한 항목은 상품 본문이 아니라 확인 필요 항목으로 분리하세요.",
        ],
        "qa_risk_notes": [
            "근거 없는 가격, 예약, 운영시간, 안전, 외국어 지원, 의료/웰니스 효능 claim을 만들지 마세요."
        ],
        "region_insights": [
            {
                "claim": f"{region_label}의 수집 근거를 기준으로 후보 동선을 검토합니다.",
                "evidence_source_ids": source_ids,
                "confidence": evidence_context.get("source_confidence") or 0.0,
            }
        ],
    }
    return _complete_research_synthesis(payload, state)


def validate_research_synthesis(payload: dict[str, Any], state: GraphState) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Research synthesis response must be an object")
    return _complete_research_synthesis(payload, state)


def _is_timeout_like_gemini_error(exc: GeminiGatewayError) -> bool:
    message = str(exc).lower()
    return "timeout" in message or "timed out" in message


def _complete_research_synthesis(payload: dict[str, Any], state: GraphState) -> dict[str, Any]:
    evidence_context = _evidence_context_from_state(state)
    advice = (
        evidence_context.get("productization_advice")
        if isinstance(evidence_context.get("productization_advice"), dict)
        else {}
    )
    base_cards = _product_evidence_context_for_prompt(evidence_context)["candidate_evidence_cards"]
    payload_cards = payload.get("candidate_evidence_cards") if isinstance(payload.get("candidate_evidence_cards"), list) else []
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
            "자연어 요청에 웰니스, 반려동물, 오디오 해설, 생태, 의료 같은 테마가 명시되면 preferences 값과 달라도 preferred_themes에 반드시 포함하세요.",
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
    product_evidence_context = _product_evidence_context_for_prompt(evidence_context)
    context = {
        "역할": "ResearchSynthesisAgent",
        "목표": (
            "EvidenceFusion 결과를 ProductAgent가 바로 사용할 수 있는 근거 브리프로 재구성합니다. "
            "요약해서 정보를 줄이는 단계가 아니라, 상품 생성에 필요한 후보별 사실과 제한 claim을 보존하는 단계입니다."
        ),
        "요청": {
            "normalized_request": normalized,
            "geo_scope": normalized.get("geo_scope"),
            "target_customer": normalized.get("target_customer"),
            "preferred_themes": normalized.get("preferred_themes"),
            "avoid": normalized.get("avoid"),
        },
        "재시도_사유": compact_retry_error,
        "retrieved_documents": _summarize_evidence(docs, limit=10),
        "evidence_context": product_evidence_context,
        "data_gap_summary": {
            "gap_count": len(data_gap_report.get("gaps") or []) if isinstance(data_gap_report.get("gaps"), list) else 0,
            "coverage": data_gap_report.get("coverage") if isinstance(data_gap_report, dict) else {},
        },
        "enrichment_summary": enrichment_summary,
        "보존해야_하는_정보": [
            "candidate_evidence_cards[].usable_facts",
            "candidate_evidence_cards[].operational_unknowns",
            "candidate_evidence_cards[].restricted_claims",
            "candidate_evidence_cards[].evidence_document_ids",
            "unresolved_gaps",
            "data_coverage와 source_confidence의 의미",
        ],
        "출력_규칙": [
            "raw TourAPI/RAG 전체를 그대로 복사하지 마세요.",
            "하지만 candidate_evidence_cards의 상품화에 필요한 세부 facts는 삭제하지 마세요.",
            "candidate_evidence_cards 원본은 서버가 이미 보존합니다. 응답에서는 원본 card 전체를 다시 쓰지 말고, 후보별 상품화 판단, 스토리 각도, 리스크 보강이 필요한 항목을 content_id/title 중심으로 반환하세요.",
            "추가 guidance가 없는 후보는 생략해도 됩니다. 서버가 기존 card를 병합하므로 원본 근거는 유지됩니다.",
            "usable_facts와 evidence_document_ids를 원문 그대로 반복하지 마세요. 서버가 기존 값을 보존합니다.",
            "근거가 없는 운영시간, 요금, 예약 가능 여부, 외국어 지원, 안전성, 의료/웰니스 효능은 restricted_claims 또는 operational_unknowns로 분리하세요.",
            "candidate_evidence_cards는 evidence_context.candidate_evidence_cards의 후보를 유지하고, 필요한 guidance만 보강하세요.",
            "evidence_document_ids는 실제 doc_id만 유지하세요. 임의 id를 만들지 마세요.",
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
    evidence_prompt_limit = min(MAX_PRODUCT_COUNT, max(10, effective_product_count))
    context = {
        "요청": {
            "normalized_request": normalized,
            "geo_scope": normalized.get("geo_scope"),
            "requested_product_count": requested_product_count,
            "product_count": effective_product_count,
            "available_evidence_count": evidence_count,
            "product_count_note": (
                _product_count_shortage_note(requested_product_count, effective_product_count, evidence_count)
                or "요청한 상품 수만큼 생성할 근거가 있습니다."
            ),
            "target_customer": normalized.get("target_customer"),
            "preferred_themes": normalized.get("preferred_themes"),
            "avoid": _string_list(normalized.get("avoid")),
        },
        "리서치_요약": research_summary,
        "source_items_shortlist": _summarize_source_items_for_prompt(source_items or [], limit=evidence_prompt_limit),
        "retrieved_documents": _summarize_evidence(docs, limit=evidence_prompt_limit),
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
        "규칙": [
            f"요청.product_count 값과 정확히 같은 개수의 상품을 생성하세요. 최대 {MAX_PRODUCT_COUNT}개를 절대 넘지 마세요.",
            "요청.requested_product_count가 요청.product_count보다 크면, 근거 데이터가 부족해서 생성 개수를 줄인 것입니다. 이 사실을 각 상품의 needs_review 또는 coverage_notes에 반영하세요.",
            "각 product는 최소 1개 이상의 source_id를 가져야 합니다.",
            "source_ids는 반드시 retrieved_documents 안에 있는 doc_id만 사용하세요. content_id나 임의 id를 쓰지 마세요.",
            "candidate_evidence_cards의 usable_facts, experience_hooks, recommended_product_angles를 우선 활용하세요.",
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
            "sales_copy는 문자열이 아니라 JSON 객체여야 합니다.",
            "sales_copy.sections는 title과 body를 가진 객체 배열이며 상품당 최대 3개만 작성하세요.",
            "FAQ에는 우천, 가격 확정 여부, 외국어 안내, 집결지, 일정 변경 관련 질문을 포함하되 상품당 최대 5개만 작성하세요.",
            "sns_posts는 상품당 최대 3개만 작성하고, 각 항목은 platform/content 객체가 아니라 한국어 문자열이어야 합니다.",
            "sns_posts는 반드시 한글 문장을 포함해야 합니다. 중국어/일본어/영어로 작성하지 마세요.",
            "외국인 대상이라는 이유로 SNS 문구를 중국어, 일본어, 영어 등으로 번역하지 마세요. output_language가 ko이므로 한국어 운영 문구만 작성하세요.",
            "search_keywords는 상품당 최대 10개만 작성하고, 각 항목은 한국어 문자열이어야 합니다.",
            "search_keywords에는 Busan, yacht, food tour 같은 영어만 있는 값을 쓰지 말고 부산, 요트, 푸드투어처럼 한국어로 작성하세요.",
            "상품_목록의 needs_review, assumptions, not_to_claim, claim_limits는 hard constraint입니다.",
            "근거 문서에 없는 운영 정보를 사실처럼 새로 만들지 마세요.",
            "가격, 예약, 운영시간, 외국어 지원, 안전 보장, 의료/웰니스 효능은 근거가 없으면 FAQ와 유의 문구에서 확인 필요로만 표현하세요.",
            "evidence_disclaimer에는 data_coverage와 unresolved_gaps를 반영한 검토 필요 문장을 쓰세요.",
            "claim_limits에는 상품별 not_to_claim과 unresolved gap 기반 금지 claim을 요약하세요.",
            "요청의 avoid에 포함된 금지 기준을 우선 적용하세요.",
            "운영자가 바로 검토할 수 있게 간결하고 실무적인 문장으로 작성하세요.",
            "사용자에게 보이는 모든 텍스트 필드는 반드시 한국어로 작성하세요. 영어 문장을 쓰지 마세요.",
        ],
    }
    if validation_error:
        context["검증_실패_수정"] = {
            "error": validation_error,
            "instruction": "이전 응답이 서버 검증을 통과하지 못했습니다. 전체 marketing_assets를 다시 작성하되, 모든 sns_posts/FAQ/문구/키워드가 한국어 문자열인지 자체 점검한 뒤 출력하세요.",
        }
    return json.dumps(context, ensure_ascii=False)


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
            "존재하지 않는 source_id 참조 여부",
            "unresolved gap을 고객 노출 문구에서 단정 claim으로 바꾼 경우",
            "근거 없는 운영시간/요금/예약/안전/외국어/의료/웰니스 claim",
            *extra_checks,
        ],
        "규칙": [
            "사용자에게 보이는 모든 텍스트 필드는 반드시 한국어로 작성하세요. 영어 문장을 쓰지 마세요.",
            "QA 요약, 이슈 메시지, 수정 제안은 반드시 한국어로 작성하세요.",
            "검수_항목에 있는 근거 기반 제한은 요청 avoid에 없더라도 반드시 검수하세요.",
            "검수 대상은 상품_목록과 마케팅_자산의 고객 노출 문구입니다. 근거_문서 자체의 메타데이터 품질 문제를 이슈로 만들지 마세요.",
            "상품_목록의 not_to_claim과 assumptions는 내부 운영 참고 항목입니다. 이 항목 자체를 고객 노출 문구 위반으로 지적하지 마세요.",
            "sales_copy.disclaimer의 '운영자가 최종 확정해야 합니다', '확인 필요', '변동될 수 있습니다' 같은 문구는 단정 표현이 아니라 안전한 완화 문구입니다.",
            "FAQ에서 '~수 있습니다', '확인 필요', '문의 필요', '현장 상황에 따라', '사전에 확인'은 단정 표현이 아니라 불확실성/확인 필요 표현입니다. 이 표현만으로 이슈를 만들지 마세요.",
            "우천, 기상, 현장 상황에 따라 취소/변경/중단될 수 있다는 문구는 정상적인 리스크 안내입니다. 이 표현만으로 이슈를 만들지 마세요.",
            "'환상적인', '아름다운', '특별한', '여유로운', '만끽하세요', '감상하세요', '즐겨보세요', '기대할 수 있습니다' 같은 일반 홍보 표현은 금지 표현이 아닙니다.",
            "금지 표현은 실제 운영 리스크가 분명한 표현만 의미합니다. 예: '항상 운영', '예약 즉시 확정', '반드시 이용 가능', '가격은 N원입니다', '무료입니다', '100% 안전', '최저가 보장', '무조건 만족'.",
            "출처 근거 누락은 구체적 사실 주장에만 적용하세요. 분위기, 감상, 추천형 홍보 문구만으로 출처 누락 이슈를 만들지 마세요.",
            "명확한 법무/운영 리스크가 없거나 단순 문체 선호에 가까우면 issue를 만들지 마세요.",
            "근거_문서의 event_start_date, event_end_date가 비어 있다는 이유만으로 이슈를 만들지 마세요.",
            "source document나 근거 문서를 업데이트하라는 수정 제안은 하지 마세요. 필요한 경우 상품 문구에 '운영자 확인 필요'를 추가하라고 제안하세요.",
            "각 issue.product_id는 문제가 있는 상품_목록의 id를 그대로 넣으세요. 전체 공통 문제가 아니면 null로 두지 마세요.",
            "issue.field_path는 문제가 있는 고객 노출 필드를 간단히 넣으세요. 예: title, sales_copy.sections[0].body, faq[2].answer",
            "issue.message와 issue.suggested_fix에는 disclaimer, not_to_claim, sales_copy 같은 내부 필드명을 직접 쓰지 마세요. '유의 문구', '운영 주의사항', '상세 설명', 'FAQ 답변'처럼 사람이 이해하는 이름을 쓰세요.",
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
    context = {
        "현재_상품": products,
        "현재_마케팅_자산": assets,
        "선택된_QA_이슈": revision_context.get("qa_issues", []),
        "수정_요청": revision_context.get("requested_changes", []),
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
                    "sns_posts": ["전체 교체가 필요할 때만"],
                    "search_keywords": ["전체 교체가 필요할 때만"],
                }
            ],
            "notes": ["수정 이유"],
        },
        "규칙": [
            "전체 상품이나 전체 마케팅 자산을 다시 생성하지 마세요.",
            "선택된_QA_이슈와 수정_요청을 해결하는 데 필요한 최소 필드만 patch에 포함하세요.",
            "수정이 필요 없는 product_id는 product_patches와 marketing_patches에 포함하지 마세요.",
            "수정하지 않는 기존 값은 출력하지 마세요. 기존 값은 서버가 그대로 유지합니다.",
            "index는 현재_마케팅_자산 배열 내부 faq/sections의 0부터 시작하는 위치입니다.",
            "사용자에게 보이는 모든 텍스트는 한국어로 작성하세요.",
            "가격, 운영 시간, 예약 가능 여부, 외국어 지원을 단정하지 마세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


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


def _summarize_evidence(docs: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    summarized = []
    for doc in docs[:limit]:
        metadata = doc.get("metadata") or {}
        summarized.append(
            {
                "doc_id": doc.get("doc_id"),
                "title": doc.get("title"),
                "content_type": metadata.get("content_type"),
                "region_code": metadata.get("region_code"),
                "event_start_date": metadata.get("event_start_date"),
                "event_end_date": metadata.get("event_end_date"),
                "snippet": str(doc.get("snippet") or doc.get("content") or "")[:240],
                "score": doc.get("score"),
            }
        )
    return summarized


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


def _rule_based_generation_meta(agent_name: str, purpose: str) -> dict[str, Any]:
    return {
        "agent": agent_name,
        "purpose": purpose,
        "provider": "rule_based",
        "model": "rule-based-v1",
        "cost_usd": 0.0,
        "paid_tier_equivalent_cost_usd": 0.0,
    }


def _offline_generation_meta(agent_name: str, purpose: str) -> dict[str, Any]:
    return {
        "agent": agent_name,
        "purpose": purpose,
        "provider": "offline_compat",
        "model": "gemini-required-offline-compat-v1",
        "cost_usd": 0.0,
        "paid_tier_equivalent_cost_usd": 0.0,
    }


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


def _append_agent_execution(state: GraphState, meta: dict[str, Any]) -> list[dict[str, Any]]:
    return [*state.get("agent_execution", []), meta]


def _offline_fusion_highlights(
    base_fusion: dict[str, Any],
    enrichment_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    coverage = base_fusion.get("data_coverage") if isinstance(base_fusion.get("data_coverage"), dict) else {}
    unresolved = base_fusion.get("unresolved_gaps") if isinstance(base_fusion.get("unresolved_gaps"), list) else []
    summary = enrichment_summary.get("summary") if isinstance(enrichment_summary.get("summary"), dict) else {}
    executed_calls = int(summary.get("executed_calls") or 0)
    failed_calls = int(summary.get("failed_calls") or 0)
    highlights: list[dict[str, Any]] = [
        {
            "title": "근거 공백 요약",
            "body": f"현재 상품화 전에 확인해야 할 공백이 {len(unresolved)}개 남아 있습니다.",
            "severity": "warning" if unresolved else "success",
            "related_gap_types": sorted({str(gap.get("gap_type")) for gap in unresolved if isinstance(gap, dict)}),
        },
        {
            "title": "선택 보강 실행",
            "body": f"실행된 보강 호출 {executed_calls}개, 실패한 호출 {failed_calls}개입니다.",
            "severity": "warning" if failed_calls else "info",
            "related_gap_types": [],
        },
    ]
    if coverage:
        image_coverage = round(float(coverage.get("image_coverage") or 0.0) * 100)
        highlights.append(
            {
                "title": "이미지 근거",
                "body": f"이미지 근거 커버리지는 약 {image_coverage}%입니다. 게시 전 출처와 사용 조건 확인이 필요합니다.",
                "severity": "info",
                "related_gap_types": ["missing_image_asset"],
            }
        )
    return highlights


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
        "무료입니다",
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
    }
    for field_name, label in labels.items():
        text = re.sub(rf"\b{re.escape(field_name)}\b", label, text)
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
    if normalized.startswith("sns_posts"):
        return "SNS 문구"
    if normalized.startswith("search_keywords"):
        return "검색 키워드"
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
    if not isinstance(value, list):
        return [{"order": 1, "name": "source 기반 후보지 방문", "source_id": source_ids[0]}]
    itinerary = []
    for index, item in enumerate(value[:5]):
        if not isinstance(item, dict):
            continue
        itinerary.append(
            {
                "order": int(item.get("order") or index + 1),
                "name": _korean_text(str(item.get("name") or "운영 단계 확인"), "itinerary[].name"),
                "source_id": item.get("source_id") if item.get("source_id") in source_ids else source_ids[0],
            }
        )
    return itinerary or [{"order": 1, "name": "source 기반 후보지 방문", "source_id": source_ids[0]}]


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


def record_rule_based_llm_call(db: Session, run_id: str, step_id: str, purpose: str, input_payload: Any, output_payload: Any) -> None:
    input_tokens = _estimate_tokens(input_payload)
    output_tokens = _estimate_tokens(output_payload)
    call = models.LLMCall(
        run_id=run_id,
        step_id=step_id,
        provider="rule_based",
        model="rule-based-v1",
        purpose=purpose,
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_usd=0,
        latency_ms=0,
        cache_hit=False,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    safe_write_llm_usage_log(
        run_id=run_id,
        step_id=step_id,
        call_id=call.id,
        provider="rule_based",
        model="rule-based-v1",
        purpose=purpose,
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_usd=0,
        paid_tier_equivalent_cost_usd=0,
        latency_ms=0,
        request_hash=None,
    )


def _cost_summary(db: Session, run_id: str) -> dict[str, Any]:
    calls = db.query(models.LLMCall).filter(models.LLMCall.run_id == run_id).all()
    providers = sorted({call.provider for call in calls})
    gemini_calls = sum(1 for call in calls if call.provider == "gemini")
    rule_based_calls = sum(1 for call in calls if call.provider == "rule_based")
    return {
        "estimated_cost_usd": float(sum(call.cost_usd or 0 for call in calls)),
        "llm_calls": len(calls),
        "gemini_calls": gemini_calls,
        "rule_based_calls": rule_based_calls,
        "providers": providers,
        "mode": "gemini" if gemini_calls else "rule_based",
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
