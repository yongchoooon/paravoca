from app.agents.workflow import (
    PLANNER_RESPONSE_SCHEMA,
    RESEARCH_SYNTHESIS_RESPONSE_SCHEMA,
    planner_agent,
    research_agent,
    validate_planner_output,
)
from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal, init_db
from app.llm.gemini_gateway import GeminiGatewayError, GeminiJsonResult


def setup_module():
    init_db()


def _fake_result(data: dict) -> GeminiJsonResult:
    return GeminiJsonResult(
        data=data,
        model="gemini-test",
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        cost_usd=0.0,
        paid_tier_equivalent_cost_usd=0.0,
        latency_ms=1,
        raw_text="{}",
    )


def _create_run(db, input_payload: dict) -> models.WorkflowRun:
    run = models.WorkflowRun(
        template_id="default_product_planning",
        input=input_payload,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_planner_agent_uses_gemini_schema_caps_count_and_does_not_resolve_region(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    def fake_call_gemini_json(**kwargs):
        assert kwargs["purpose"] == "planner"
        assert kwargs["response_schema"] == PLANNER_RESPONSE_SCHEMA
        assert "지역 확정은 GeoResolverAgent" in kwargs["prompt"]
        return _fake_result(
            {
                "user_intent": "부산에서 외국인 대상 카페 투어 상품을 기획합니다.",
                "product_count": 25,
                "target_customer": "외국인",
                "preferred_themes": ["카페 투어", "로컬 산책"],
                "avoid": ["가격 단정 표현"],
                "period": "2026-05",
                "output_language": "ko",
                "request_type": "tourism_product_generation",
                "product_generation_constraints": ["상품 개수는 최대 20개입니다."],
                "evidence_requirements": ["각 상품은 실제 근거 문서와 연결되어야 합니다."],
                "ldong_regn_cd": "26",
            }
        )

    monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_call_gemini_json)

    with SessionLocal() as db:
        run = _create_run(
            db,
            {
                "message": "부산 부산진구 전포동 카페 투어 상품 25개",
                "region": "부산",
                "period": "2026-05",
                "target_customer": "외국인",
                "product_count": 25,
                "preferences": ["카페 투어"],
                "avoid": ["가격 단정 표현"],
            },
        )
        result = planner_agent(db, {"run_id": run.id, "user_request": run.input, "agent_execution": []})

    get_settings.cache_clear()

    normalized = result["normalized_request"]
    assert normalized["product_count"] == 20
    assert normalized["region_name"] == "부산"
    assert "ldong_regn_cd" not in normalized
    assert "geo_scope" not in normalized
    assert result["agent_execution"][0]["provider"] == "gemini"


def test_planner_validation_preserves_explicit_wellness_theme_over_default_preferences():
    normalized = validate_planner_output(
        {
            "user_intent": "부산에서 외국인 대상 웰니스 관광 상품을 기획합니다.",
            "product_count": 3,
            "target_customer": "외국인",
            "preferred_themes": ["야간 관광", "축제"],
            "avoid": ["건강 효능 단정 표현"],
            "period": "2026-05",
            "output_language": "ko",
            "request_type": "tourism_product_generation",
            "product_generation_constraints": [],
            "evidence_requirements": [],
        },
        {
            "message": "부산에서 외국인 대상 웰니스 관광 상품 3개 기획해줘. 건강 효능은 단정하지 말고 근거 기반으로 써줘.",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 3,
            "preferences": ["야간 관광", "축제"],
            "avoid": ["가격 단정 표현"],
        },
    )

    assert normalized["preferred_themes"][0] == "웰니스"
    assert "야간 관광" not in normalized["preferred_themes"]
    assert "축제" not in normalized["preferred_themes"]
    assert "웰니스" in normalized["message"]


def test_research_synthesis_preserves_candidate_card_detail(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    def fake_call_gemini_json(**kwargs):
        assert kwargs["purpose"] == "research_synthesis"
        assert kwargs["response_schema"] == RESEARCH_SYNTHESIS_RESPONSE_SCHEMA
        assert "상품 생성에 필요한 후보별 사실과 제한 claim을 보존" in kwargs["prompt"]
        return _fake_result(
            {
                "research_brief": "대전 수변 산책 후보는 근거 card를 기준으로 상품화할 수 있습니다.",
                "candidate_evidence_cards": [
                    {
                        "content_id": "100",
                        "title": "갑천 야간 산책",
                        "experience_hooks": ["수변 야간 산책"],
                    }
                ],
                "usable_claims": ["장소명과 개요는 사용할 수 있습니다."],
                "restricted_claims": ["가격 확정"],
                "operational_unknowns": ["요금 정보"],
                "unresolved_gaps": [
                    {
                        "gap_type": "missing_price_or_fee",
                        "reason": "요금 정보 확인 필요",
                        "target_content_id": "100",
                    }
                ],
                "product_generation_guidance": ["근거 card의 usable facts를 상품 본문에 반영하세요."],
                "qa_risk_notes": ["가격을 단정하지 마세요."],
            }
        )

    monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_call_gemini_json)

    with SessionLocal() as db:
        run = _create_run(db, {"message": "대전 야간 산책 상품"})
        state = {
            "run_id": run.id,
            "normalized_request": {"product_count": 2, "target_customer": "외국인"},
            "retrieved_documents": [
                {
                    "doc_id": "doc_1",
                    "title": "갑천 야간 산책",
                    "snippet": "갑천 수변 산책 근거",
                    "metadata": {},
                }
            ],
            "evidence_profile": {},
            "productization_advice": {
                "usable_claims": ["TourAPI 장소명과 주소는 사용할 수 있습니다."],
                "candidate_evidence_cards": [
                    {
                        "content_id": "100",
                        "source_item_id": "item_1",
                        "title": "갑천 야간 산책",
                        "usable_facts": [{"field": "개요", "value": "갑천 수변 산책 근거", "source": "TourAPI"}],
                        "operational_unknowns": ["missing_price_or_fee"],
                        "restricted_claims": ["가격 확정"],
                        "evidence_document_ids": ["doc_1"],
                    }
                ],
            },
            "data_coverage": {"detail_coverage": 0.5},
            "unresolved_gaps": [
                {
                    "gap_type": "missing_price_or_fee",
                    "reason": "요금 정보 근거가 부족합니다.",
                    "target_content_id": "100",
                }
            ],
            "source_confidence": 0.74,
            "ui_highlights": [],
            "enrichment_summary": {},
            "data_gap_report": {},
            "agent_execution": [],
        }
        result = research_agent(db, state)

    get_settings.cache_clear()

    summary = result["research_summary"]
    card = summary["candidate_evidence_cards"][0]
    assert card["usable_facts"][0]["value"] == "갑천 수변 산책 근거"
    assert card["evidence_document_ids"] == ["doc_1"]
    assert "가격 확정" in card["restricted_claims"]
    assert summary["unresolved_gaps"][0]["gap_type"] == "missing_price_or_fee"
    assert result["agent_execution"][0]["provider"] == "gemini"


def test_research_synthesis_retries_with_compact_prompt_after_timeout(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    calls: list[dict] = []

    def fake_call_gemini_json(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise GeminiGatewayError("The read operation timed out")
        assert kwargs["purpose"] == "research_synthesis_compact_retry"
        assert "재시도_사유" in kwargs["prompt"]
        assert kwargs["max_output_tokens"] == 4096
        return _fake_result(
            {
                "research_brief": "시간 초과 후 compact 재시도로 근거 브리프를 생성했습니다.",
                "candidate_evidence_cards": [],
                "usable_claims": ["장소명과 개요는 사용할 수 있습니다."],
                "restricted_claims": ["가격 확정"],
                "operational_unknowns": ["요금 정보"],
                "unresolved_gaps": [],
                "product_generation_guidance": ["기존 evidence card를 기준으로 상품을 생성하세요."],
                "qa_risk_notes": ["가격을 단정하지 마세요."],
            }
        )

    monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_call_gemini_json)

    with SessionLocal() as db:
        run = _create_run(db, {"message": "부산 역사 문화 상품"})
        state = {
            "run_id": run.id,
            "normalized_request": {"product_count": 2, "target_customer": "외국인"},
            "retrieved_documents": [
                {"doc_id": "doc_1", "title": "부산 역사", "snippet": "역사 문화 근거", "metadata": {}}
            ],
            "productization_advice": {
                "candidate_evidence_cards": [
                    {
                        "content_id": "100",
                        "title": "부산 역사",
                        "usable_facts": [{"field": "개요", "value": "역사 문화 근거", "source": "TourAPI"}],
                        "evidence_document_ids": ["doc_1"],
                    }
                ]
            },
            "agent_execution": [],
        }
        result = research_agent(db, state)

    get_settings.cache_clear()

    assert [call["purpose"] for call in calls] == [
        "research_synthesis",
        "research_synthesis_compact_retry",
    ]
    assert result["research_summary"]["candidate_evidence_cards"][0]["evidence_document_ids"] == ["doc_1"]
