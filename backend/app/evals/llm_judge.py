from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.evals.metrics import EvaluationContext, Metric
from app.llm.gemini_gateway import GeminiGatewayError, call_gemini_json


@dataclass(frozen=True)
class JudgeDefinition:
    name: str
    purpose: str
    title: str
    principle: str
    expected: str
    prompt_instruction: str


JUDGE_DEFINITIONS = [
    JudgeDefinition(
        name="product_quality_judge",
        purpose="eval_product_quality_judge",
        title="상품 품질 LLM 평가",
        principle="상품 결과가 사용자 요청에 맞고, 외국인 대상 상품으로 자연스럽고, 서로 구분되는지 LLM judge가 보조 평가합니다.",
        expected="상품이 요청 조건을 충족하고, 구체적이며, 운영자 확인 필요 항목을 단정 claim으로 섞지 않아야 합니다.",
        prompt_instruction=(
            "상품 품질을 평가하세요. 사용자 요청과의 적합성, 외국인 대상 자연스러움, 상품 간 차별성, "
            "itinerary/one_liner/core_value의 구체성, 확인 필요 항목의 단정 claim 혼입 여부를 보세요."
        ),
    ),
    JudgeDefinition(
        name="evidence_usefulness_judge",
        purpose="eval_evidence_usefulness_judge",
        title="근거 활용 LLM 평가",
        principle="근거가 단순 연결을 넘어 상품화 포인트로 잘 전환됐는지 LLM judge가 보조 평가합니다.",
        expected="상품 설명은 evidence/source_ids와 자연스럽게 연결되어야 하고, 약한 근거는 needs_review나 claim_limits로 분리되어야 합니다.",
        prompt_instruction=(
            "근거 활용 품질을 평가하세요. source_id 존재 여부 자체는 코드 metric이 이미 검사합니다. "
            "여기서는 근거가 상품화 포인트로 잘 전환됐는지, 약한 정보가 제한/확인 필요로 빠졌는지 판단하세요."
        ),
    ),
    JudgeDefinition(
        name="marketing_quality_judge",
        purpose="eval_marketing_quality_judge",
        title="마케팅 품질 LLM 평가",
        principle="마케팅 문구, FAQ, SNS, 검색 키워드가 상품과 일관되고 과장되지 않았는지 LLM judge가 보조 평가합니다.",
        expected="마케팅 결과는 상품과 일관되어야 하고, 외국인 대상 커뮤니케이션으로 자연스러우며, claim 제한을 반영해야 합니다.",
        prompt_instruction=(
            "마케팅 품질을 평가하세요. copy/FAQ/SNS/search keyword의 상품 일관성, 과장 표현, "
            "외국인 대상 자연스러움, claim_limits/evidence_disclaimer 반영 여부를 보세요."
        ),
    ),
    JudgeDefinition(
        name="claim_risk_llm_judge",
        purpose="eval_claim_risk_judge",
        title="복합 Claim 위험 LLM 평가",
        principle="코드 검사로 잡기 어려운 암시적 단정 표현과 자연어 뉘앙스의 claim 위험을 LLM judge가 보조 평가합니다.",
        expected="웰니스 효능, 혼잡 회피, 반려동물 동반 가능, 이미지 사용권 같은 항목을 근거 없이 확정처럼 말하면 안 됩니다.",
        prompt_instruction=(
            "복합 claim 위험과 claim 제한 반영 여부를 평가하세요. 단어 포함 여부만 보지 말고 문장의 의미와 맥락을 보세요. "
            "expected_claim_limits가 상품/마케팅/QA의 제한, 확인 필요, disclaimer에 실제로 반영됐는지 확인하고, "
            "효능/안전/혼잡/반려동물/이미지 사용권을 근거 없이 사실상 보장하는 표현이 있는지 판단하세요."
        ),
    ),
]


JUDGE_RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "score",
        "passed",
        "actual",
        "penalty_reason",
        "judge_reasoning_summary",
        "evidence_quotes_or_refs",
    ],
    "properties": {
        "score": {"type": "number"},
        "passed": {"type": "boolean"},
        "actual": {"type": "string"},
        "penalty_reason": {"type": "string"},
        "judge_reasoning_summary": {"type": "string"},
        "evidence_quotes_or_refs": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


def run_llm_judges(
    *,
    db: Session,
    case: dict[str, Any],
    context: EvaluationContext,
    settings: Settings | None = None,
) -> list[Metric]:
    settings = settings or get_settings()
    if not settings.llm_enabled or not settings.gemini_api_key:
        return [_skipped_metric(definition, "LLM judge requires LLM_ENABLED=true and GEMINI_API_KEY.") for definition in JUDGE_DEFINITIONS]

    final_output = _dict(context.get("final_output"))
    if not _list(final_output.get("products")):
        return [_skipped_metric(definition, "상품 결과가 없어 LLM judge 평가 대상이 아닙니다.") for definition in JUDGE_DEFINITIONS]

    metrics: list[Metric] = []
    for definition in JUDGE_DEFINITIONS:
        metrics.append(_run_single_judge(db=db, case=case, context=context, definition=definition, settings=settings))
    return metrics


def _run_single_judge(
    *,
    db: Session,
    case: dict[str, Any],
    context: EvaluationContext,
    definition: JudgeDefinition,
    settings: Settings,
) -> Metric:
    prompt = _build_judge_prompt(case=case, context=context, definition=definition)
    try:
        result = call_gemini_json(
            db=db,
            run_id=str(context.get("run_id") or ""),
            step_id=None,  # evaluation judge call, not a workflow agent step
            purpose=definition.purpose,
            prompt=prompt,
            response_schema=JUDGE_RESPONSE_SCHEMA,
            max_output_tokens=2048,
            temperature=0.1,
            settings=settings,
        )
    except GeminiGatewayError as exc:
        return _errored_metric(definition, str(exc))

    payload = result.data
    score = _clamp_score(payload.get("score"))
    passed = bool(payload.get("passed")) and score >= 0.8
    penalty_reason = str(payload.get("penalty_reason") or "").strip()
    if passed and not penalty_reason:
        penalty_reason = ""
    metric = _judge_metric(
        definition,
        passed=passed,
        score=score,
        value={
            "status": "judged",
            "model": result.model,
            "judge_cost_usd": round(result.cost_usd, 6),
            "latency_ms": result.latency_ms,
        },
        actual=str(payload.get("actual") or "").strip() or "LLM judge가 평가 결과를 반환했습니다.",
        penalty_reason=penalty_reason if not passed else None,
        judge_reasoning_summary=str(payload.get("judge_reasoning_summary") or "").strip(),
        evidence_quotes_or_refs=[str(item) for item in _list(payload.get("evidence_quotes_or_refs"))[:5]],
    )
    return metric


def _build_judge_prompt(*, case: dict[str, Any], context: EvaluationContext, definition: JudgeDefinition) -> str:
    final_output = _dict(context.get("final_output"))
    payload = {
        "judge_task": {
            "metric_name": definition.name,
            "instruction": definition.prompt_instruction,
            "scoring": {
                "1.0": "바로 검토 가능한 수준입니다.",
                "0.5": "방향은 맞지만 일부 결과가 약하거나 일반적입니다.",
                "0.0": "요청과 크게 어긋나거나 평가 기준을 충족하지 못합니다.",
            },
            "important_rules": [
                "긴 사고 과정을 쓰지 말고 짧은 판단 요약만 작성하세요.",
                "제공된 결과와 근거 안에서만 평가하세요.",
                "코드 검사 metric과 중복해 source_id 존재 여부만 다시 평가하지 마세요.",
                "score는 0과 1 사이 숫자여야 합니다.",
            ],
        },
        "case": {
            "case_id": case.get("case_id"),
            "name": case.get("name"),
            "input": case.get("input"),
            "expected_claim_limits": case.get("expected_claim_limits"),
            "expected_evidence_requirements": case.get("expected_evidence_requirements"),
            "expected_quality": case.get("expected_quality"),
            "judge_rubric": case.get("judge_rubric"),
            "tags": case.get("tags"),
        },
        "workflow_result": _compact_final_output(final_output),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _compact_final_output(final_output: dict[str, Any]) -> dict[str, Any]:
    return {
        "reason": final_output.get("reason"),
        "geo_scope": _compact_geo(_dict(final_output.get("geo_scope"))),
        "products": [_compact_product(item) for item in _list(final_output.get("products"))[:20]],
        "marketing_assets": [_compact_marketing(item) for item in _list(final_output.get("marketing_assets"))[:20]],
        "qa_report": _dict(final_output.get("qa_report")),
        "data_coverage": final_output.get("data_coverage"),
        "unresolved_gaps": _list(final_output.get("unresolved_gaps"))[:20],
        "retrieved_documents": [_compact_doc(item) for item in _list(final_output.get("retrieved_documents"))[:20]],
        "candidate_evidence_cards": _list(final_output.get("candidate_evidence_cards"))[:12],
    }


def _compact_geo(geo_scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": geo_scope.get("status"),
        "mode": geo_scope.get("mode"),
        "locations": [
            {
                "name": _dict(location).get("name"),
                "ldong_regn_cd": _dict(location).get("ldong_regn_cd"),
                "ldong_signgu_cd": _dict(location).get("ldong_signgu_cd"),
                "keyword": _dict(location).get("keyword"),
                "sub_area_terms": _dict(location).get("sub_area_terms"),
            }
            for location in _list(geo_scope.get("locations"))[:3]
        ],
    }


def _compact_product(product: Any) -> dict[str, Any]:
    data = _dict(product)
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "one_liner": data.get("one_liner"),
        "core_value": data.get("core_value"),
        "itinerary": data.get("itinerary"),
        "source_ids": data.get("source_ids"),
        "evidence_summary": data.get("evidence_summary"),
        "needs_review": data.get("needs_review"),
        "coverage_notes": data.get("coverage_notes"),
        "claim_limits": data.get("claim_limits"),
        "not_to_claim": data.get("not_to_claim"),
    }


def _compact_marketing(asset: Any) -> dict[str, Any]:
    data = _dict(asset)
    return {
        "product_id": data.get("product_id"),
        "headline": data.get("headline"),
        "copy": data.get("copy"),
        "faq": data.get("faq"),
        "sns_posts": data.get("sns_posts"),
        "search_keywords": data.get("search_keywords"),
        "evidence_disclaimer": data.get("evidence_disclaimer"),
        "claim_limits": data.get("claim_limits"),
    }


def _compact_doc(doc: Any) -> dict[str, Any]:
    data = _dict(doc)
    metadata = _dict(data.get("metadata")) or _dict(data.get("document_metadata"))
    return {
        "doc_id": data.get("doc_id") or data.get("id"),
        "title": data.get("title"),
        "content_type": data.get("content_type") or metadata.get("content_type"),
        "source_family": metadata.get("source_family"),
        "summary": str(data.get("summary") or data.get("content") or "")[:500],
    }


def _judge_metric(
    definition: JudgeDefinition,
    *,
    passed: bool,
    score: float | None,
    value: Any,
    actual: str,
    penalty_reason: str | None,
    judge_reasoning_summary: str,
    evidence_quotes_or_refs: list[str],
) -> Metric:
    return {
        "name": definition.name,
        "passed": passed,
        "score": None if score is None else round(score, 4),
        "value": value,
        "reason": judge_reasoning_summary or actual,
        "blocking": False,
        "evaluator_type": "llm",
        "principle": definition.principle,
        "expected": definition.expected,
        "actual": actual,
        "penalty_reason": penalty_reason,
        "next_check": "Judge 요약과 Developer JSON의 상품/마케팅/QA 결과를 함께 확인하세요.",
        "not_applicable_reason": None,
        "judge_reasoning_summary": judge_reasoning_summary,
        "evidence_quotes_or_refs": evidence_quotes_or_refs,
    }


def _skipped_metric(definition: JudgeDefinition, reason: str) -> Metric:
    return _judge_metric(
        definition,
        passed=True,
        score=None,
        value={"status": "skipped", "reason": reason},
        actual=reason,
        penalty_reason=None,
        judge_reasoning_summary="LLM judge를 실행하지 않았습니다.",
        evidence_quotes_or_refs=[],
    ) | {"not_applicable_reason": reason}


def _errored_metric(definition: JudgeDefinition, error: str) -> Metric:
    return _judge_metric(
        definition,
        passed=False,
        score=0.0,
        value={"status": "errored", "error": error},
        actual=f"LLM judge 호출이 실패했습니다: {error}",
        penalty_reason="Judge 자체가 실패했으므로 이 평가 항목은 신뢰할 수 없습니다.",
        judge_reasoning_summary="LLM judge 호출 실패",
        evidence_quotes_or_refs=[],
    )


def _clamp_score(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
