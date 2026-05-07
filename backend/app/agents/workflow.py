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

from app.agents.geo_resolver import resolve_geo_scope, save_geo_resolution
from app.agents.state import GraphState
from app.core.config import get_settings
from app.db import models
from app.llm.gemini_gateway import GeminiJsonResult, call_gemini_json
from app.llm.usage_log import safe_write_llm_usage_log
from app.rag.chroma_store import index_source_documents, search_source_documents
from app.rag.source_documents import upsert_source_documents_from_items
from app.tools.tourism import get_tourism_provider, log_tool_call, upsert_tourism_items
from app.tools.tourism_enrichment import enrich_items_with_tourapi_details


logger = logging.getLogger("uvicorn.error")


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
        "retrieved_documents": source_output.get("retrieved_documents", []),
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
    graph.add_node("data", lambda state: data_agent(db, state))
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
            "data": "data",
        },
    )
    graph.add_edge("geo_exit", END)
    graph.add_edge("data", "research")
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


def planner_agent(db: Session, state: GraphState) -> GraphState:
    with step_log(db, state["run_id"], "PlannerAgent", "planner", state.get("user_request")) as step:
        request = state["user_request"]
        region = request.get("region")
        normalized = {
            "region_name": region,
            "start_date": _period_start(request.get("period")),
            "end_date": _period_end(request.get("period")),
            "target_customer": request.get("target_customer") or "외국인",
            "product_count": min(int(request.get("product_count") or 3), 10),
            "preferred_themes": request.get("preferences") or ["야간 관광", "축제"],
            "avoid": request.get("avoid") or [],
            "output_language": request.get("output_language") or "ko",
        }
        plan = [
            {"id": "resolve_geo_scope", "agent": "GeoResolverAgent"},
            {"id": "search_attractions", "tool": "tourapi_search_keyword"},
            {"id": "search_events", "tool": "tourapi_search_festival"},
            {"id": "search_stays", "tool": "tourapi_search_stay"},
            {"id": "rag_search", "tool": "vector_search"},
            {"id": "generate_products", "agent": "ProductAgent"},
            {"id": "generate_marketing", "agent": "MarketingAgent"},
            {"id": "qa_review", "agent": "QAComplianceAgent"},
            {"id": "human_approval", "node": "HumanApprovalNode"},
        ]
        output = {"normalized_request": normalized, "plan": plan}
        step.output = output
        record_rule_based_llm_call(db, state["run_id"], step.id, "planner", request, output)
        return {"normalized_request": normalized, "plan": plan}


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
            gemini_result = call_gemini_json(
                db=db,
                run_id=state["run_id"],
                step_id=step.id,
                purpose="geo_resolution",
                prompt=_geo_resolution_prompt(resolver_input),
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


def data_agent(db: Session, state: GraphState) -> GraphState:
    normalized = state["normalized_request"]
    with step_log(db, state["run_id"], "DataAgent", "data_collection", normalized) as step:
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

        items = _dedupe_items(all_items)
        items = _filter_items_by_geo_scope(items, geo_scope=geo_scope, run_id=run_id)
        if not items:
            raise RuntimeError(
                f"TourAPI returned no tourism items for resolved geo_scope={geo_scope!r}"
            )
        upsert_tourism_items(db, items)
        settings = get_settings()
        detail_limit = min(settings.tourapi_detail_enrichment_limit, len(items))
        detail_enrichment = enrich_items_with_tourapi_details(
            db=db,
            provider=provider,
            items=items,
            run_id=run_id,
            step_id=step.id,
            limit=detail_limit,
        )
        if detail_enrichment["items"]:
            enriched_by_id = {item.id: item for item in detail_enrichment["items"]}
            items = [enriched_by_id.get(item.id, item) for item in items]
        source_documents = upsert_source_documents_from_items(db, items)
        indexed_count = index_source_documents(db, source_documents)
        vector_filters = _vector_filters_for_geo_scope(geo_scope, source=provider_source)
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
        retrieved = _filter_retrieved_documents_by_geo_scope(
            retrieved,
            geo_scope=geo_scope,
            run_id=run_id,
        )
        if not retrieved:
            raise RuntimeError(
                f"No TourAPI source documents were retrieved from vector search for geo_scope={geo_scope!r}"
            )
        output = {
            "geo_scope": geo_scope,
            "source_items": [_tourism_item_to_dict(item) for item in items],
            "retrieved_documents": retrieved,
            "indexed_documents": indexed_count,
            "detail_enrichment": detail_enrichment["summary"],
        }
        step.output = output
        record_rule_based_llm_call(db, run_id, step.id, "data_summary", normalized, output)
        return {
            "geo_scope": geo_scope,
            "source_items": output["source_items"],
            "retrieved_documents": retrieved,
        }


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


def _vector_filters_for_geo_scope(geo_scope: dict[str, Any], *, source: str) -> dict[str, Any]:
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
        if _metadata_matches_geo_scope(document.get("metadata") or {}, locations)
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
        sub_area_terms = location.get("sub_area_terms")
        if isinstance(sub_area_terms, list) and sub_area_terms:
            item_text = " ".join(
                str(value or "")
                for value in [
                    getattr(item, "title", None),
                    getattr(item, "address", None),
                    getattr(item, "overview", None),
                    getattr(item, "raw", None),
                ]
            )
            if not any(str(term) in item_text for term in sub_area_terms):
                continue
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
        sub_area_terms = location.get("sub_area_terms")
        if isinstance(sub_area_terms, list) and sub_area_terms:
            metadata_text = " ".join(str(value or "") for value in metadata.values())
            if not any(str(term) in metadata_text for term in sub_area_terms):
                continue
        return True
    return False


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
    with step_log(db, state["run_id"], "ResearchAgent", "research", state.get("retrieved_documents")) as step:
        docs = state.get("retrieved_documents", [])
        source_ids = [doc["doc_id"] for doc in docs[:5]]
        region_label = _region_label_from_normalized(state.get("normalized_request", {}))
        summary = {
            "region_insights": [
                {
                    "claim": f"{region_label}은 수집된 TourAPI 근거를 기준으로 액티비티 동선을 검토할 수 있습니다.",
                    "evidence_source_ids": source_ids,
                    "confidence": 0.78,
                }
            ],
            "recommended_themes": [
                {"theme": "local_activity_route", "reason": "지역 기반 후보지가 검색 근거에 포함되어 있습니다."},
                {"theme": "seasonal_event_plus_place", "reason": "요청 기간 내 행사와 주변 관광지를 함께 검토할 수 있습니다."},
                {"theme": "foreigner_friendly_short_course", "reason": "외국인 대상 짧은 이동 동선으로 재구성할 수 있습니다."},
            ],
            "constraints": [
                "가격, 예약 가능 여부, 운영 시간은 운영자가 최종 확인해야 합니다.",
                "이미지 사용 전 공공데이터 이용 조건을 확인해야 합니다.",
            ],
        }
        step.output = summary
        record_rule_based_llm_call(db, state["run_id"], step.id, "research", docs, summary)
        return {"research_summary": summary}


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
        settings = get_settings()
        if not settings.llm_enabled:
            products = build_rule_based_products(normalized, docs)
            meta = _rule_based_generation_meta("ProductAgent", "product_generation")
            step.model = "rule-based-v1"
            record_rule_based_llm_call(db, state["run_id"], step.id, "product_generation", normalized, products)
        else:
            gemini_result = call_gemini_json(
                db=db,
                run_id=state["run_id"],
                step_id=step.id,
                purpose="product_generation",
                prompt=_product_prompt(normalized, state.get("research_summary", {}), docs),
                response_schema=PRODUCT_RESPONSE_SCHEMA,
                max_output_tokens=4096,
                temperature=0.35,
                settings=settings,
            )
            products = validate_products(gemini_result.data, normalized, docs)
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
                    state.get("retrieved_documents", []),
                    state.get("revision_context"),
                ),
                response_schema=MARKETING_RESPONSE_SCHEMA,
                max_output_tokens=8192,
                temperature=0.35,
                settings=settings,
            )
            assets = validate_marketing_assets(gemini_result.data, products)
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
        if not settings.llm_enabled:
            qa_report = build_rule_based_qa(products, assets)
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
                    state.get("retrieved_documents", []),
                    _qa_settings_from_state(state),
                ),
                response_schema=QA_RESPONSE_SCHEMA,
                max_output_tokens=4096,
                temperature=0.1,
                settings=settings,
            )
            qa_report = validate_qa_report(gemini_result.data, products)
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
                max_output_tokens=4096,
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
            "retrieved_documents": state.get("retrieved_documents", []),
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
        "excluded_locations": {"type": "array"},
        "allow_nationwide": {"type": "boolean"},
        "unsupported_locations": {"type": "array"},
        "notes": {"type": "array"},
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


def build_rule_based_products(normalized: dict[str, Any], docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    count = normalized.get("product_count", 3)
    region_label = _region_label_from_normalized(normalized)
    templates = [
        (f"{region_label} 야간 로컬 미식 투어", ["야경", "로컬 음식", "짧은 동선"]),
        (f"{region_label} 대표 액티비티 사진 코스", ["액티비티", "사진", "야간 관광"]),
        (f"{region_label} 시즌 행사 연계 패키지", ["축제", "관광지", "시즌성"]),
        (f"{region_label} 로컬 산책 + 카페 투어", ["로컬 산책", "카페", "가벼운 도보"]),
        (f"{region_label} 문화 체험 입문 클래스", ["문화 체험", "푸드투어", "현장 확인"]),
    ]
    source_ids = [doc["doc_id"] for doc in docs[:5]]
    if not source_ids:
        raise ValueError("TourAPI source documents are required for product generation")
    products = []
    for index in range(count):
        title, core = templates[index % len(templates)]
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
                "source_ids": source_ids[: min(3, len(source_ids))],
                "assumptions": ["세부 가격과 예약 가능 여부는 운영자가 확정해야 합니다."],
                "not_to_claim": ["가격 확정", "항상 운영", "예약 즉시 확정"],
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
            }
        )
    return assets


def build_rule_based_qa(products: list[dict[str, Any]], assets: list[dict[str, Any]]) -> dict[str, Any]:
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
        if role not in {"primary", "origin", "destination", "stopover", "nearby_anchor", "comparison", "excluded"}:
            role = "primary"
        locations.append(
            {
                "text": text,
                "normalized_text": normalized_text,
                "role": role,
                "is_foreign": item.get("is_foreign") is True,
            }
        )
    return {
        "locations": locations[:12],
        "excluded_locations": _string_list(payload.get("excluded_locations"))[:12],
        "allow_nationwide": payload.get("allow_nationwide") is True,
        "unsupported_locations": _string_list(payload.get("unsupported_locations"))[:12],
        "notes": _string_list(payload.get("notes"))[:12],
    }


def validate_products(
    payload: dict[str, Any],
    normalized: dict[str, Any],
    docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    products = payload.get("products")
    if not isinstance(products, list) or len(products) < int(normalized.get("product_count", 1)):
        raise ValueError("Gemini product response has invalid products")
    allowed_source_ids = {doc["doc_id"] for doc in docs}
    if not allowed_source_ids:
        raise ValueError("TourAPI source documents are required for product validation")
    available_source_ids = list(allowed_source_ids)
    validated = []
    for index, product in enumerate(products[: int(normalized.get("product_count", len(products)))]):
        if not isinstance(product, dict):
            raise ValueError("Product item must be an object")
        source_ids = _string_list(product.get("source_ids")) or available_source_ids[:3]
        source_ids = [source_id for source_id in source_ids if source_id in allowed_source_ids] or available_source_ids[:3]
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
                "assumptions": _korean_string_list(product.get("assumptions"), "products[].assumptions")
                or ["세부 가격과 예약 가능 여부는 운영자가 확정해야 합니다."],
                "not_to_claim": _korean_string_list(product.get("not_to_claim"), "products[].not_to_claim")
                or ["가격 확정", "항상 운영", "예약 즉시 확정"],
            }
        )
    return validated


def validate_marketing_assets(payload: dict[str, Any], products: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
            }
        )
    return validated


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


def validate_qa_report(payload: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
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
    overall_status = str(payload.get("overall_status") or ("needs_review" if validated_issues else "pass"))
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
        "summary": _normalize_qa_summary(payload.get("summary"), validated_issues),
        "issues": validated_issues,
        "pass_count": int(payload.get("pass_count") or (len(products) if not validated_issues else 0)),
        "needs_review_count": int(payload.get("needs_review_count") or (len(products) if validated_issues else 0)),
        "fail_count": int(payload.get("fail_count") or 0),
    }


def _geo_resolution_prompt(resolver_input: dict[str, Any]) -> str:
    context = {
        "요청": resolver_input,
        "역할": "사용자 자연어에서 지역 의도만 추출합니다. TourAPI 코드 확정은 별도 catalog resolver가 수행합니다.",
        "출력_규칙": [
            "locations에는 요청 문장에 실제로 등장한 국내/해외 장소 표현만 넣으세요.",
            "text는 원문에 등장한 장소 span 그대로 쓰세요. 오타가 있으면 text에는 오타 원문을, normalized_text에는 교정 후보를 쓰세요.",
            "role은 primary, origin, destination, stopover, nearby_anchor, comparison, excluded 중 하나만 쓰세요.",
            "부산에서 시작해서 양산에서 끝나는 요청은 부산 origin, 양산 destination으로 분리하세요.",
            "전국, 국내 전체처럼 사용자가 명시한 경우에만 allow_nationwide=true로 쓰세요.",
            "도쿄, 오사카, 파리처럼 해외 목적지를 요청하면 unsupported_locations에 넣고 해당 location의 is_foreign=true로 표시하세요.",
            "외국인, 해외 관광객, 인바운드처럼 고객 대상을 뜻하는 표현은 해외 목적지로 취급하지 마세요.",
            "TourAPI 코드, 법정동 코드, confidence, 후보 목록은 만들지 마세요.",
            "장소가 애매해도 억지로 특정 행정구역을 선택하지 말고 원문 span만 추출하세요.",
        ],
        "예시": [
            {
                "input": "부산에서 시작해서 양산에서 끝나는 상품",
                "locations": [
                    {"text": "부산", "normalized_text": "부산광역시", "role": "origin", "is_foreign": False},
                    {"text": "양산", "normalized_text": "양산시", "role": "destination", "is_foreign": False},
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
) -> str:
    context = {
        "요청": normalized,
        "리서치_요약": research_summary,
        "근거_문서": _summarize_evidence(docs),
        "수정_요청": _prompt_revision_context(normalized.get("revision_context")),
        "규칙": [
            "request.product_count 값과 정확히 같은 개수의 상품을 생성하세요.",
            "source_ids는 반드시 근거_문서 안에 있는 doc_id만 사용하세요.",
            "근거 문서에 없는 운영 정보를 사실처럼 새로 만들지 마세요.",
            "요청의 avoid에 포함되지 않은 제한을 새 금지 기준으로 만들지 마세요.",
            "사용자에게 보이는 모든 텍스트 필드는 반드시 한국어로 작성하세요. 영어 문장을 쓰지 마세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def _marketing_prompt(
    products: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    revision_context: dict[str, Any] | None = None,
) -> str:
    context = {
        "상품_목록": products,
        "근거_문서": _summarize_evidence(docs),
        "수정_요청": _prompt_revision_context(revision_context),
        "규칙": [
            "각 product_id마다 marketing_asset을 정확히 1개씩 생성하세요. product_id 값은 상품_목록의 id를 그대로 사용하세요.",
            "sales_copy는 문자열이 아니라 JSON 객체여야 합니다.",
            "sales_copy.sections는 title과 body를 가진 객체 배열이며 상품당 최대 3개만 작성하세요.",
            "FAQ에는 우천, 가격 확정 여부, 외국어 안내, 집결지, 일정 변경 관련 질문을 포함하되 상품당 최대 5개만 작성하세요.",
            "sns_posts는 상품당 최대 3개만 작성하고, 각 항목은 platform/content 객체가 아니라 한국어 문자열이어야 합니다.",
            "search_keywords는 상품당 최대 10개만 작성하고, 각 항목은 한국어 문자열이어야 합니다.",
            "search_keywords에는 Busan, yacht, food tour 같은 영어만 있는 값을 쓰지 말고 부산, 요트, 푸드투어처럼 한국어로 작성하세요.",
            "근거 문서에 없는 운영 정보를 사실처럼 새로 만들지 마세요.",
            "요청의 avoid에 포함된 금지 기준을 우선 적용하세요.",
            "운영자가 바로 검토할 수 있게 간결하고 실무적인 문장으로 작성하세요.",
            "사용자에게 보이는 모든 텍스트 필드는 반드시 한국어로 작성하세요. 영어 문장을 쓰지 마세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def _qa_prompt(
    products: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    docs: list[dict[str, Any]],
    qa_settings: dict[str, Any],
) -> str:
    avoid = _string_list(qa_settings.get("avoid"))
    extra_checks = avoid if avoid else ["가격 단정 표현", "과장 표현", "출처 없는 주장"]
    context = {
        "상품_목록": products,
        "마케팅_자산": assets,
        "근거_문서": _summarize_evidence(docs),
        "검수_설정": qa_settings,
        "검수_항목": [
            "금지 표현 포함 여부",
            "출처 근거 누락 여부",
            *extra_checks,
        ],
        "규칙": [
            "사용자에게 보이는 모든 텍스트 필드는 반드시 한국어로 작성하세요. 영어 문장을 쓰지 마세요.",
            "QA 요약, 이슈 메시지, 수정 제안은 반드시 한국어로 작성하세요.",
            "검수_항목에 없는 제한을 새로 만들지 마세요. 예를 들어 검수_항목에 '가격 단정 표현'만 있으면 일정, 예약 가능 여부, 안전 보장은 별도 이슈로 만들지 마세요.",
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


def _rule_based_generation_meta(agent_name: str, purpose: str) -> dict[str, Any]:
    return {
        "agent": agent_name,
        "purpose": purpose,
        "provider": "rule_based",
        "model": "rule-based-v1",
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
