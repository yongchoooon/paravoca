from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models


Metric = dict[str, Any]
EvaluationContext = dict[str, Any]

SUCCESS_STATUSES = {"awaiting_approval", "approved", "changes_requested"}
NON_BLOCKING_ENRICHMENT_STATUSES = {"succeeded", "no_candidates", "skipped", "disabled"}

METRIC_DEFINITIONS: dict[str, dict[str, str]] = {
    "workflow_success": {
        "evaluator_type": "code",
        "principle": "워크플로우가 검토 가능한 결과로 끝났는지, 또는 지원 불가/지역 확인/데이터 부족처럼 의도된 종료 형태로 끝났는지 코드로 확인합니다.",
        "expected": "정상 요청은 검토 가능한 상태로 끝나야 하고, 지원 불가나 지역 확인 필요 케이스는 내부 오류가 아니라 통제된 안내로 끝나야 합니다.",
        "next_check": "실패했다면 Workflow Run error, 마지막 agent step, LLM/tool call 실패 원인을 먼저 확인하세요.",
    },
    "geo_resolution_accuracy": {
        "evaluator_type": "code",
        "principle": "GeoResolver 결과의 지역 모드와 TourAPI ldong 시도/시군구 코드가 데이터셋 기대값과 일치하는지 코드로 비교합니다.",
        "expected": "데이터셋에 지정한 지역 코드, 모드, 세부 keyword가 실제 geo_scope에 반영되어야 합니다.",
        "next_check": "감점되면 geo_resolution step의 입력 문장, 후보 catalog, resolved geo_scope를 확인하세요.",
    },
    "unsupported_or_clarification_accuracy": {
        "evaluator_type": "code",
        "principle": "지원 불가 또는 지역 확인 필요 요청이 억지로 검색/상품 생성으로 넘어가지 않았는지 코드로 확인합니다.",
        "expected": "해외 목적지는 지원 불가로, 애매한 지역은 후보 제시/확인 필요로 종료되어야 합니다.",
        "next_check": "감점되면 preflight/GeoResolver의 unsupported_locations와 clarification_candidates를 확인하세요.",
    },
    "retrieval_result_count": {
        "evaluator_type": "code",
        "principle": "상품 생성에 사용할 retrieved document가 운영 기준 이상 확보됐는지 workflow output의 retrieval diagnostics로 확인합니다.",
        "expected": "정상 상품 생성 케이스는 사용 가능한 근거 문서가 최소 기준 이상 있어야 합니다. 조기 종료 케이스는 평가 대상이 아닙니다.",
        "next_check": "감점되면 TourAPI raw count, Chroma where filter, post geo filter count, retrieved_documents를 확인하세요.",
    },
    "source_document_indexed_count": {
        "evaluator_type": "code",
        "principle": "수집된 관광 후보가 source document로 저장/색인되어 RAG와 ProductAgent가 사용할 수 있는지 진단합니다.",
        "expected": "정상 상품 생성 케이스는 source document가 최소 기준 이상 업서트 또는 색인되어야 합니다. 조기 종료 케이스는 평가 대상이 아닙니다.",
        "next_check": "감점되면 source_document_upsert_count, indexed_document_count, embedding_status, Chroma upsert 로그를 확인하세요.",
    },
    "expected_source_family_coverage": {
        "evaluator_type": "code",
        "principle": "데이터셋이 기대한 KTO source family가 source document metadata 또는 enrichment tool call 결과에 나타났는지 확인합니다.",
        "expected": "요청 의도에 필요한 source family는 covered, no_candidates, skipped, disabled 중 진단 가능한 상태로 남아야 합니다.",
        "next_check": "missing이면 router/planner lane이 열렸는지, feature flag와 enrichment_tool_calls의 source_family를 확인하세요.",
    },
    "enrichment_call_success_rate": {
        "evaluator_type": "code",
        "principle": "실제로 실행된 enrichment tool call이 workflow를 막지 않고 succeeded/no_candidates/skipped/disabled 상태로 정리됐는지 확인합니다.",
        "expected": "활성화된 보강 호출은 실패해도 원인이 기록되어야 하며, 비차단 API 실패가 전체 workflow를 불필요하게 깨뜨리면 안 됩니다.",
        "next_check": "failed가 있으면 enrichment_tool_calls의 operation, arguments, error, latency를 확인하세요.",
    },
    "evidence_document_validity": {
        "evaluator_type": "code",
        "principle": "ProductAgent가 참조할 수 있도록 retrieved document마다 안정적인 doc_id가 있는지 확인합니다.",
        "expected": "모든 retrieved document에는 doc_id 또는 id가 있어야 합니다.",
        "next_check": "invalid_count가 있으면 source_documents 저장과 RAG search response 변환을 확인하세요.",
    },
    "product_count_satisfaction": {
        "evaluator_type": "code",
        "principle": "요청 상품 수, 최대 20개 제한, 근거 부족 시 가능한 개수 생성 정책을 기준으로 상품 개수를 확인합니다.",
        "expected": "상품 수는 요청 수와 시스템 상한을 넘지 않아야 하며, 최소 기대 개수보다 적으면 데이터 부족 사유가 명시되어야 합니다.",
        "next_check": "감점되면 ProductAgent output, evidence shortage 진단, requested product_count를 확인하세요.",
    },
    "product_source_id_validity": {
        "evaluator_type": "code",
        "principle": "각 상품의 source_ids가 실제 retrieved_documents의 doc_id를 가리키는지 코드로 검증합니다.",
        "expected": "모든 상품은 최소 1개 이상의 실제 근거 문서에 연결되어야 하고, 존재하지 않는 source_id를 쓰면 안 됩니다.",
        "next_check": "실패하면 ProductAgent prompt의 allowed source_ids와 final output의 source_ids를 비교하세요.",
    },
    "claim_limit_compliance": {
        "evaluator_type": "code",
        "principle": "요청/데이터셋의 claim 제한이 상품, 마케팅, QA, unresolved gap의 제한/확인 필요 필드에 반영됐는지 코드로 검사합니다.",
        "expected": "요청한 claim 제한이 결과물의 제한/확인 필요 항목에 명시되어야 합니다.",
        "next_check": "미반영 claim이 상품, 마케팅, QA 중 어디에서 빠졌는지 확인하세요.",
    },
    "qa_issue_detection": {
        "evaluator_type": "code",
        "principle": "QA 결과 또는 최종 출력 텍스트가 데이터셋이 기대한 claim risk를 실제로 드러냈는지 코드로 확인합니다.",
        "expected": "예상 claim risk가 QA issue 또는 결과의 제한/확인 필요 문구에 나타나야 합니다.",
        "next_check": "QA issue와 상품/마케팅의 claim 제한 항목을 비교하세요.",
    },
    "latency_ms": {
        "evaluator_type": "code",
        "principle": "Workflow 실행 시간을 운영 관찰값으로 기록합니다.",
        "expected": "아직 pass/fail 기준은 두지 않고 추세와 이상치를 봅니다.",
        "next_check": "시간이 급증하면 LLM retry, KTO timeout, embedding/indexing 시간을 확인하세요.",
    },
    "llm_cost_usd": {
        "evaluator_type": "code",
        "principle": "실제 기록된 LLM 비용을 USD 기준 운영 관찰값으로 표시합니다.",
        "expected": "아직 pass/fail 기준은 두지 않고 case별 비용 추세를 봅니다.",
        "next_check": "비용이 급증하면 prompt size, output token, retry count를 확인하세요.",
    },
    "llm_cost_krw": {
        "evaluator_type": "code",
        "principle": "설정된 환율을 적용해 LLM 비용을 원화 기준 운영 관찰값으로 표시합니다.",
        "expected": "아직 pass/fail 기준은 두지 않고 case별 비용 추세를 봅니다.",
        "next_check": "비용이 급증하면 prompt size, output token, retry count를 확인하세요.",
    },
}


@dataclass
class EvalOptions:
    usd_krw_rate: float


def collect_run_evaluation_context(db: Session, run: models.WorkflowRun) -> EvaluationContext:
    enrichment_runs = (
        db.query(models.EnrichmentRun)
        .filter(models.EnrichmentRun.workflow_run_id == run.id)
        .order_by(models.EnrichmentRun.created_at.asc())
        .all()
    )
    enrichment_tool_calls = [
        {
            "id": call.id,
            "tool_name": call.tool_name,
            "source_family": call.source_family,
            "status": call.status,
            "arguments": call.arguments,
            "response_summary": call.response_summary,
            "error": call.error,
            "latency_ms": call.latency_ms,
        }
        for enrichment_run in enrichment_runs
        for call in enrichment_run.tool_calls
    ]
    tool_calls = [
        {
            "id": call.id,
            "tool_name": call.tool_name,
            "source": call.source,
            "status": call.status,
            "arguments": call.arguments,
            "response_summary": call.response_summary,
            "error": call.error,
            "latency_ms": call.latency_ms,
        }
        for call in run.tool_calls
    ]
    llm_calls = [
        {
            "id": call.id,
            "provider": call.provider,
            "model": call.model,
            "purpose": call.purpose,
            "total_tokens": call.total_tokens,
            "cost_usd": float(call.cost_usd or 0),
            "latency_ms": call.latency_ms,
        }
        for call in run.llm_calls
    ]
    return {
        "run_id": run.id,
        "status": run.status,
        "input": run.input,
        "normalized_input": run.normalized_input or {},
        "final_output": run.final_output or {},
        "error": run.error or {},
        "latency_ms": run.latency_ms,
        "cost_total_usd": float(run.cost_total_usd or 0),
        "tool_calls": tool_calls,
        "enrichment_tool_calls": enrichment_tool_calls,
        "llm_calls": llm_calls,
    }


def evaluate_case(case: dict[str, Any], context: EvaluationContext, options: EvalOptions | None = None) -> dict[str, Any]:
    options = options or EvalOptions(usd_krw_rate=get_settings().usd_krw_rate)
    final_output = _dict(context.get("final_output"))
    metrics = [
        _workflow_success_metric(case, context),
        _geo_metric(case, context),
        _unsupported_or_clarification_metric(case, context),
        _retrieval_count_metric(case, final_output),
        _indexed_count_metric(case, final_output),
        _source_family_metric(case, context),
        _enrichment_success_metric(context),
        _evidence_document_validity_metric(final_output),
        _product_count_metric(case, final_output),
        _product_source_id_metric(final_output),
        _value_metric("latency_ms", context.get("latency_ms"), "Workflow latency in milliseconds."),
        _value_metric("llm_cost_usd", round(float(context.get("cost_total_usd") or 0), 6), "Recorded LLM cost in USD."),
        _value_metric(
            "llm_cost_krw",
            round(float(context.get("cost_total_usd") or 0) * options.usd_krw_rate, 2),
            f"Recorded LLM cost converted with {options.usd_krw_rate} KRW/USD.",
        ),
    ]
    blocking = [metric for metric in metrics if metric.get("blocking") and not metric.get("passed")]
    score_metrics = [metric for metric in metrics if metric.get("score") is not None]
    average_score = (
        sum(float(metric.get("score") or 0) for metric in score_metrics) / len(score_metrics)
        if score_metrics
        else 0.0
    )
    return {
        "case_id": case.get("case_id"),
        "name": case.get("name"),
        "status": "failed" if blocking else "passed",
        "score": round(average_score, 4),
        "workflow_run_id": context.get("run_id"),
        "input": case.get("input"),
        "tags": case.get("tags") or [],
        "metrics": metrics,
        "failures": [
            {
                "metric": metric["name"],
                "reason": metric.get("reason") or "metric failed",
                "value": metric.get("value"),
            }
            for metric in blocking
        ],
        "source_family_coverage": _source_family_coverage(case, context),
        "latency_ms": context.get("latency_ms"),
        "llm_cost_usd": round(float(context.get("cost_total_usd") or 0), 6),
        "llm_cost_krw": round(float(context.get("cost_total_usd") or 0) * options.usd_krw_rate, 2),
    }


def skipped_case_result(case: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "name": case.get("name"),
        "status": "skipped",
        "score": None,
        "workflow_run_id": None,
        "input": case.get("input"),
        "tags": case.get("tags") or [],
        "metrics": [
            _metric(
                "workflow_success",
                True,
                1.0,
                "skipped",
                reason,
                blocking=False,
            )
        ],
        "failures": [],
        "source_family_coverage": [],
        "latency_ms": None,
        "llm_cost_usd": 0,
        "llm_cost_krw": 0,
        "skip_reason": reason,
    }


def summarize_evaluation(cases: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for case in cases if case.get("status") == "passed")
    failed = sum(1 for case in cases if case.get("status") == "failed")
    skipped = sum(1 for case in cases if case.get("status") == "skipped")
    scored = [float(case["score"]) for case in cases if isinstance(case.get("score"), (int, float))]
    return {
        "case_count": len(cases),
        "passed_count": passed,
        "failed_count": failed,
        "skipped_count": skipped,
        "average_score": round(sum(scored) / len(scored), 4) if scored else None,
        "llm_cost_usd": round(sum(float(case.get("llm_cost_usd") or 0) for case in cases), 6),
        "llm_cost_krw": round(sum(float(case.get("llm_cost_krw") or 0) for case in cases), 2),
        "latency_ms": sum(int(case.get("latency_ms") or 0) for case in cases),
    }


def _workflow_success_metric(case: dict[str, Any], context: EvaluationContext) -> Metric:
    expected_status = _dict(case.get("expected_geo")).get("status")
    status = str(context.get("status") or "")
    final_output = _dict(context.get("final_output"))
    reason = final_output.get("reason") or _dict(context.get("error")).get("message")
    expected_exit = expected_status in {"needs_clarification", "unsupported"}
    if expected_exit:
        passed = status == "failed" or str(final_output.get("status") or "").startswith("unsupported")
        return _metric(
            "workflow_success",
            passed,
            1.0 if passed else 0.0,
            status,
            "Expected diagnostic exit." if passed else f"Expected controlled exit but got {status}: {reason}",
            actual=(
                f"실제 run status는 {status}이고, 기대한 조기 종료 상태는 {expected_status}입니다."
                if passed
                else f"실제 run status는 {status}입니다. 기대한 조기 종료가 감지되지 않았습니다. 원인: {reason}"
            ),
            penalty_reason=None if passed else f"{expected_status}로 안내 종료되어야 했지만 실제 상태가 {status}였습니다.",
        )
    passed = status in SUCCESS_STATUSES
    if not passed and final_output.get("reason") == "insufficient_source_data":
        return _metric(
            "workflow_success",
            True,
            0.6,
            status,
            "Workflow ended with insufficient_source_data diagnostic, not an internal crash.",
            blocking=False,
            actual="Workflow가 내부 오류 대신 insufficient_source_data 안내로 종료됐습니다.",
            penalty_reason="검토 가능한 상품 결과까지 도달하지는 못했기 때문에 부분 점수입니다.",
            next_check="retrieval_diagnostics에서 TourAPI raw count, 색인 수, vector search 결과 수를 확인하세요.",
        )
    return _metric(
        "workflow_success",
        passed,
        1.0 if passed else 0.0,
        status,
        "Workflow reached reviewable output." if passed else f"Workflow did not complete: {reason}",
        actual=(
            f"실제 run status는 {status}이며 검토 가능한 결과 상태입니다."
            if passed
            else f"실제 run status는 {status}입니다. workflow가 검토 가능한 결과까지 도달하지 못했습니다. 원인: {reason}"
        ),
        penalty_reason=None if passed else f"Workflow가 검토 가능한 상태로 끝나야 했지만 {status}로 끝났습니다.",
    )


def _geo_metric(case: dict[str, Any], context: EvaluationContext) -> Metric:
    expected = _dict(case.get("expected_geo"))
    if not expected:
        return _metric(
            "geo_resolution_accuracy",
            True,
            None,
            "not_applicable",
            "이 case에는 기대 지역 조건이 없어 지역 해석을 점수화하지 않습니다.",
            blocking=False,
        )
    if expected.get("status") in {"needs_clarification", "unsupported"}:
        return _metric(
            "geo_resolution_accuracy",
            True,
            None,
            "handled_by_exit_metric",
            "지원 불가/확인 필요 케이스는 지역 코드 확정이 아니라 조기 종료 metric에서 평가합니다.",
            blocking=False,
        )
    actual = _geo_scope(context)
    failures: list[str] = []
    for key in ("mode", "ldong_regn_cd", "ldong_signgu_cd"):
        if expected.get(key) and expected.get(key) != _actual_geo_value(actual, key):
            failures.append(f"{key}: expected {expected.get(key)}, got {_actual_geo_value(actual, key)}")
    expected_keywords = _expected_geo_keywords(expected)
    actual_keywords = _geo_keyword_tokens(actual)
    missing_keywords = [keyword for keyword in expected_keywords if _keyword_token(keyword) not in actual_keywords]
    if missing_keywords:
        failures.append(f"keyword(s) {', '.join(missing_keywords)} not found")
    passed = not failures
    return _metric(
        "geo_resolution_accuracy",
        passed,
        1.0 if passed else 0.0,
        _compact_geo(actual),
        "Geo scope matches expected codes." if passed else "; ".join(failures),
        actual=(
            "실제 geo_scope가 기대 지역 코드와 일치합니다."
            if passed
            else "실제 geo_scope가 기대값과 다릅니다: " + "; ".join(failures)
        ),
        penalty_reason=None if passed else "자연어 지역 해석 결과가 데이터셋 기대 지역과 일치하지 않습니다.",
    )


def _unsupported_or_clarification_metric(case: dict[str, Any], context: EvaluationContext) -> Metric:
    expected_status = _dict(case.get("expected_geo")).get("status")
    if expected_status not in {"needs_clarification", "unsupported"}:
        return _metric(
            "unsupported_or_clarification_accuracy",
            True,
            None,
            "not_applicable",
            "이 case는 지원 불가/지역 확인 필요 조기 종료를 기대하지 않으므로 이 항목은 평가하지 않습니다.",
            blocking=False,
        )
    geo = _geo_scope(context)
    final_output = _dict(context.get("final_output"))
    final_status = str(final_output.get("status") or "")
    final_reason = str(final_output.get("reason") or "")
    if expected_status == "needs_clarification":
        passed = (
            geo.get("status") == "needs_clarification"
            or bool(geo.get("needs_clarification"))
            or final_status == "needs_clarification"
            or final_reason in {"needs_clarification", "ambiguous_location", "unsupported_multi_region"}
        )
    else:
        passed = (
            geo.get("status") == "unsupported"
            or final_status.startswith("unsupported")
            or final_reason in {"unsupported", "unsupported_destination", "foreign_destination_detected"}
        )
    return _metric(
        "unsupported_or_clarification_accuracy",
        passed,
        1.0 if passed else 0.0,
        _compact_geo(geo),
        "Expected exit behavior was detected." if passed else "Expected exit behavior was not detected.",
        actual=(
            f"실제 결과에서 {expected_status} 조기 종료가 감지됐습니다."
            if passed
            else f"실제 결과에서 기대한 {expected_status} 조기 종료가 감지되지 않았습니다."
        ),
        penalty_reason=None if passed else "지원 불가 또는 지역 확인 필요 요청이 명확한 안내 종료로 처리되지 않았습니다.",
    )


def _expects_controlled_exit(case: dict[str, Any]) -> bool:
    return _dict(case.get("expected_geo")).get("status") in {"needs_clarification", "unsupported"}


def _retrieval_count_metric(case: dict[str, Any], final_output: dict[str, Any]) -> Metric:
    if _expects_controlled_exit(case):
        return _metric(
            "retrieval_result_count",
            True,
            None,
            "not_applicable",
            "지원 불가 또는 지역 확인 필요로 조기 종료되는 케이스라 검색 결과 수를 평가하지 않습니다.",
            blocking=False,
        )
    docs = _list(final_output.get("retrieved_documents"))
    diagnostics = _dict(final_output.get("retrieval_diagnostics"))
    expected_min_count = 3
    value = {
        "retrieved_documents": len(docs),
        "expected_min_count_for_full_score": expected_min_count,
        "vector_search_result_count": diagnostics.get("vector_search_result_count"),
        "post_geo_filter_result_count": diagnostics.get("post_geo_filter_result_count"),
    }
    return _metric(
        "retrieval_result_count",
        True,
        min(1.0, len(docs) / expected_min_count) if docs else 0.0,
        value,
        (
            f"검색에 사용 가능한 retrieved document가 {len(docs)}개입니다. "
            f"운영 진단 기준은 {expected_min_count}개 이상이면 1점입니다."
        ),
        blocking=False,
        expected=f"정상 상품 생성 케이스에서는 사용 가능한 근거 문서가 {expected_min_count}개 이상이면 1점입니다.",
        actual=(
            f"사용 가능한 retrieved document가 {len(docs)}개입니다. "
            f"Vector 검색 결과는 {_count_label(diagnostics.get('vector_search_result_count'))}, "
            f"지역 필터 후 결과는 {_count_label(diagnostics.get('post_geo_filter_result_count'))}입니다."
        ),
        penalty_reason=(
            None
            if len(docs) >= expected_min_count
            else f"근거 문서가 {expected_min_count}개 미만이라 상품 생성에 사용할 근거 풀이 약합니다."
        ),
    )


def _indexed_count_metric(case: dict[str, Any], final_output: dict[str, Any]) -> Metric:
    if _expects_controlled_exit(case):
        return _metric(
            "source_document_indexed_count",
            True,
            None,
            "not_applicable",
            "지원 불가 또는 지역 확인 필요로 조기 종료되는 케이스라 색인 문서 수를 평가하지 않습니다.",
            blocking=False,
        )
    diagnostics = _dict(final_output.get("retrieval_diagnostics"))
    indexed = diagnostics.get("indexed_document_count")
    upserted = diagnostics.get("source_document_upsert_count")
    count = indexed if isinstance(indexed, int) else upserted if isinstance(upserted, int) else None
    expected_min_count = 3
    return _metric(
        "source_document_indexed_count",
        True,
        None if count is None else min(1.0, count / expected_min_count),
        {
            "indexed_or_upserted_documents": count,
            "expected_min_count_for_full_score": expected_min_count,
            "indexed_document_count": indexed,
            "source_document_upsert_count": upserted,
        },
        (
            "색인/업서트된 source document count를 확인할 수 없습니다."
            if count is None
            else f"색인/업서트된 source document가 {count}개입니다. 운영 진단 기준은 {expected_min_count}개 이상이면 1점입니다."
        ),
        blocking=False,
        expected=f"정상 상품 생성 케이스에서는 source document가 {expected_min_count}개 이상 저장 또는 색인되면 1점입니다.",
        actual=(
            "색인/업서트된 source document count를 확인할 수 없습니다."
            if count is None
            else f"확인된 source document count는 {count}개입니다. 색인 {_count_label(indexed)}, 저장 {_count_label(upserted)}입니다."
        ),
        penalty_reason=(
            None
            if count is None or count >= expected_min_count
            else f"저장/색인된 근거 문서가 {expected_min_count}개 미만이라 RAG와 상품 생성 입력이 약해질 수 있습니다."
        ),
    )


def _count_label(value: Any) -> str:
    return f"{value}개" if isinstance(value, int | float) else "0개"


def _source_family_metric(case: dict[str, Any], context: EvaluationContext) -> Metric:
    coverage = _source_family_coverage(case, context)
    expected = coverage
    if not expected:
        return _metric(
            "expected_source_family_coverage",
            True,
            None,
            [],
            "이 case에는 기대 source family가 없어 데이터 소스 커버리지를 점수화하지 않습니다.",
            blocking=False,
        )
    passed_count = sum(1 for item in coverage if item["status"] in {"covered", "no_candidates"})
    score = passed_count / len(coverage)
    passed = all(item["status"] in {"covered", "no_candidates", "disabled", "skipped"} for item in coverage)
    return _metric(
        "expected_source_family_coverage",
        passed,
        score,
        coverage,
        "Expected source families were observed or diagnostically skipped."
        if passed
        else "One or more expected source families were not observed.",
        expected="데이터셋이 지정한 source family가 covered, no_candidates, skipped, disabled 중 진단 가능한 상태로 남아야 합니다.",
        actual="; ".join(f"{item['source_family']}={item['status']}" for item in coverage),
        penalty_reason=None if passed else "기대 source family 중 일부가 source document나 enrichment call에서 관측되지 않았습니다.",
    )


def _enrichment_success_metric(context: EvaluationContext) -> Metric:
    calls = _list(context.get("enrichment_tool_calls"))
    active = [call for call in calls if call.get("status") not in {"skipped", "disabled"}]
    if not active:
        return _metric(
            "enrichment_call_success_rate",
            True,
            None,
            {"call_count": len(calls), "active_call_count": 0},
            "활성화된 enrichment call이 없어 보강 호출 성공률을 점수화하지 않습니다.",
            blocking=False,
            actual=f"전체 enrichment call은 {len(calls)}개이고, 실제 실행 대상 call은 0개입니다.",
        )
    ok_count = sum(1 for call in active if call.get("status") in NON_BLOCKING_ENRICHMENT_STATUSES)
    failed = [call for call in active if call.get("status") == "failed"]
    return _metric(
        "enrichment_call_success_rate",
        not failed,
        ok_count / len(active),
        {"active_call_count": len(active), "failed_call_count": len(failed)},
        "All active enrichment calls were non-blocking." if not failed else "Some enrichment calls failed.",
        blocking=False,
        actual=f"활성 enrichment call {len(active)}개 중 failed는 {len(failed)}개입니다.",
        penalty_reason=None if not failed else "일부 enrichment API 호출이 실패 상태로 기록됐습니다.",
    )


def _evidence_document_validity_metric(final_output: dict[str, Any]) -> Metric:
    docs = _list(final_output.get("retrieved_documents"))
    invalid = [doc for doc in docs if not _document_id(doc)]
    return _metric(
        "evidence_document_validity",
        not invalid,
        1.0 if docs and not invalid else 0.0 if invalid else None,
        {"document_count": len(docs), "invalid_count": len(invalid)},
        "All evidence documents have ids." if not invalid else "Some evidence documents do not have ids.",
        actual=f"retrieved document {len(docs)}개 중 doc_id가 없는 문서는 {len(invalid)}개입니다.",
        penalty_reason=None if not invalid else "근거 문서 ID가 없으면 ProductAgent의 source_ids 검증과 근거 추적이 깨질 수 있습니다.",
    )


def _product_count_metric(case: dict[str, Any], final_output: dict[str, Any]) -> Metric:
    if _expects_controlled_exit(case):
        return _metric(
            "product_count_satisfaction",
            True,
            None,
            "not_applicable",
            "지원 불가 또는 지역 확인 필요로 조기 종료되는 케이스라 상품 개수를 평가하지 않습니다.",
            blocking=False,
        )
    products = _list(final_output.get("products"))
    expected_min = int(case.get("expected_min_products") or 0)
    requested = int(_dict(case.get("input")).get("product_count") or 0)
    max_allowed = min(20, requested) if requested else 20
    count = len(products)
    insufficient = final_output.get("reason") == "insufficient_source_data"
    passed = count <= max_allowed and (count >= expected_min or insufficient or expected_min == 0)
    reason = "Product count satisfies configured expectation."
    if not passed:
        reason = f"Expected at least {expected_min} and at most {max_allowed}, got {count}."
    elif insufficient and count < expected_min:
        reason = "Evidence shortage was diagnosed; lower product count is acceptable."
    return _metric(
        "product_count_satisfaction",
        passed,
        1.0 if passed else 0.0,
        {"actual": count, "expected_min": expected_min, "max_allowed": max_allowed},
        reason,
        actual=f"생성된 상품은 {count}개이고, 기대 최소 {expected_min}개, 허용 최대 {max_allowed}개입니다.",
        penalty_reason=None if passed else f"상품 개수가 기대 범위({expected_min}~{max_allowed}개)를 벗어났습니다.",
    )


def _product_source_id_metric(final_output: dict[str, Any]) -> Metric:
    docs = _list(final_output.get("retrieved_documents"))
    doc_ids = {_document_id(doc) for doc in docs if _document_id(doc)}
    products = _list(final_output.get("products"))
    invalid: list[dict[str, Any]] = []
    for product in products:
        source_ids = [str(item) for item in _list(product.get("source_ids")) if item]
        if not source_ids:
            invalid.append({"product_id": product.get("id"), "reason": "source_ids empty"})
            continue
        missing = [source_id for source_id in source_ids if source_id not in doc_ids]
        if missing:
            invalid.append({"product_id": product.get("id"), "missing_source_ids": missing})
    return _metric(
        "product_source_id_validity",
        not invalid,
        1.0 if products and not invalid else 0.0 if invalid else None,
        {"invalid": invalid, "document_count": len(doc_ids), "product_count": len(products)},
        "All product source_ids point to retrieved documents." if not invalid else "Invalid product source_ids detected.",
        actual=f"상품 {len(products)}개와 근거 문서 {len(doc_ids)}개를 비교했고, 잘못된 source_id 연결은 {len(invalid)}개입니다.",
        penalty_reason=None if not invalid else "상품이 실제 retrieved document에 없는 source_id를 참조했습니다.",
    )


def _source_family_coverage(case: dict[str, Any], context: EvaluationContext) -> list[dict[str, Any]]:
    expected = [str(item) for item in _list(case.get("expected_source_families")) if item]
    if not expected:
        return []
    final_output = _dict(context.get("final_output"))
    docs = _list(final_output.get("retrieved_documents"))
    doc_families = {
        str(_dict(doc.get("metadata")).get("source_family") or _dict(doc.get("document_metadata")).get("source_family"))
        for doc in docs
    }
    enrichment_calls = _list(context.get("enrichment_tool_calls"))
    result: list[dict[str, Any]] = []
    for family in expected:
        calls = [call for call in enrichment_calls if call.get("source_family") == family]
        statuses = [str(call.get("status") or "") for call in calls]
        if family in doc_families:
            status = "covered"
            reason = "source document metadata contains the family"
        elif any(status in {"succeeded", "completed"} for status in statuses):
            status = "covered"
            reason = "enrichment call succeeded"
        elif any(status == "no_candidates" for status in statuses):
            status = "no_candidates"
            reason = "API was called but returned no candidates"
        elif any(status in {"disabled", "skipped"} for status in statuses):
            status = statuses[0]
            reason = "feature flag or router skipped this family"
        elif family == "kto_tourapi_kor" and docs:
            status = "covered"
            reason = "baseline TourAPI evidence documents exist"
        else:
            status = "missing"
            reason = "family was expected but no call or source document was found"
        result.append({"source_family": family, "status": status, "reason": reason, "call_statuses": statuses})
    return result


def _value_metric(name: str, value: Any, reason: str) -> Metric:
    return _metric(
        name,
        True,
        None,
        value,
        reason,
        blocking=False,
        actual=f"기록된 값은 {value if value is not None else '없음'}입니다.",
    )


def _metric(
    name: str,
    passed: bool,
    score: float | None,
    value: Any,
    reason: str,
    *,
    blocking: bool = True,
    evaluator_type: str | None = None,
    principle: str | None = None,
    expected: str | None = None,
    actual: str | None = None,
    penalty_reason: str | None = None,
    next_check: str | None = None,
    not_applicable_reason: str | None = None,
) -> Metric:
    definition = METRIC_DEFINITIONS.get(name, {})
    rounded_score = None if score is None else round(float(score), 4)
    is_not_applicable = _is_not_applicable_metric(value, reason, rounded_score)
    if is_not_applicable:
        not_applicable_reason = not_applicable_reason or reason
        penalty_reason = None
    elif penalty_reason is None and (not passed or (rounded_score is not None and rounded_score < 1)):
        penalty_reason = reason
    return {
        "name": name,
        "passed": passed,
        "score": rounded_score,
        "value": value,
        "reason": reason,
        "blocking": blocking,
        "evaluator_type": evaluator_type or definition.get("evaluator_type") or "code",
        "principle": principle or definition.get("principle") or "workflow 결과 JSON과 실행 로그를 기준으로 운영 진단 조건을 검사합니다.",
        "expected": expected or definition.get("expected") or "이 metric의 기대 조건이 충족되어야 합니다.",
        "actual": actual or _default_actual(value, reason, is_not_applicable=is_not_applicable),
        "penalty_reason": penalty_reason,
        "next_check": next_check or definition.get("next_check") or "Developer JSON과 연결된 workflow run detail을 확인하세요.",
        "not_applicable_reason": not_applicable_reason,
    }


def _is_not_applicable_metric(value: Any, reason: str, score: float | None) -> bool:
    if score is not None:
        return False
    if isinstance(value, str) and value in {"not_applicable", "handled_by_exit_metric"}:
        return True
    lowered = reason.lower()
    return "not applicable" in lowered or "평가하지 않습니다" in reason or "평가 대상" in reason


def _default_actual(value: Any, reason: str, *, is_not_applicable: bool) -> str:
    if is_not_applicable:
        return "이 케이스에서는 해당 단계가 실행되거나 점수화되는 것이 기대되지 않습니다."
    if isinstance(value, (str, int, float, bool)) or value is None:
        return f"실제 값은 {value if value is not None else '없음'}입니다."
    return reason


def _geo_scope(context: EvaluationContext) -> dict[str, Any]:
    final_output = _dict(context.get("final_output"))
    normalized = _dict(context.get("normalized_input"))
    return _dict(final_output.get("geo_scope")) or _dict(normalized.get("geo_scope"))


def _actual_geo_value(actual: dict[str, Any], key: str) -> Any:
    if actual.get(key):
        return actual.get(key)
    locations = _list(actual.get("locations"))
    if not locations:
        return None
    return _dict(locations[0]).get(key)


def _expected_geo_keywords(expected: dict[str, Any]) -> list[str]:
    value = expected.get("keyword_contains")
    if isinstance(value, list):
        return [str(item) for item in value if _keyword_token(item)]
    if _keyword_token(value):
        return [str(value)]
    return []


def _geo_keyword_tokens(actual: dict[str, Any]) -> set[str]:
    locations = _list(actual.get("locations"))
    values = _list(actual.get("keywords"))
    for location in locations:
        values.append(_dict(location).get("keyword"))
        values.extend(_list(_dict(location).get("sub_area_terms")))
    return {_keyword_token(value) for value in values if _keyword_token(value)}


def _keyword_token(value: Any) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").lower())


def _compact_geo(actual: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": actual.get("status"),
        "mode": actual.get("mode"),
        "needs_clarification": actual.get("needs_clarification"),
        "allow_nationwide": actual.get("allow_nationwide"),
        "locations": [
            {
                "name": _dict(location).get("name"),
                "ldong_regn_cd": _dict(location).get("ldong_regn_cd"),
                "ldong_signgu_cd": _dict(location).get("ldong_signgu_cd"),
                "keyword": _dict(location).get("keyword"),
            }
            for location in _list(actual.get("locations"))[:3]
        ],
    }


def _document_id(doc: Any) -> str | None:
    data = _dict(doc)
    value = data.get("doc_id") or data.get("id")
    return str(value) if value else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []

