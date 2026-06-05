import json

from fastapi.testclient import TestClient
import pytest
import httpx
from sqlalchemy import inspect

from app.agents.workflow import (
    _build_ai_revision_change_review,
    _build_targeted_revision_qa_diff_summary,
    _preserve_revision_source_state,
    apply_revision_patch,
    _filter_items_by_geo_scope,
    _filter_retrieved_documents_by_geo_scope,
    _geo_scope_with_tourapi_child_locations,
    _tourapi_keyword_queries,
    validate_qa_report,
    validate_targeted_revision_qa_report,
)
from app.core.config import Settings, get_settings
from app.db import models
from app.db.session import SessionLocal, engine, init_db
from app.llm.gemini_gateway import (
    GeminiGatewayError,
    GeminiJsonResult,
    call_gemini_json,
    _is_retryable_response,
    _parse_json,
    _retry_delay_seconds,
    _validate_json_schema,
)
from app.main import app
from app.rag.source_documents import build_source_document
from app.tests.geo_catalog_helpers import seed_test_ldong_catalog
from app.tools.tourism import TourismItem, _get_with_retries


def unwrap(response):
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    return body["data"]


def require_tourapi_key():
    if not get_settings().tourapi_service_key:
        pytest.skip("TOURAPI_SERVICE_KEY is required for workflow tests")


def fake_gemini_result(data: dict) -> GeminiJsonResult:
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


def fake_workflow_gemini_result(**kwargs) -> GeminiJsonResult:
    purpose = kwargs["purpose"]
    if purpose == "planner":
        return fake_gemini_result(
            {
                "message": "이번 달 부산에서 외국인 대상 액티비티 상품을 기획해줘",
                "region_name": "부산",
                "period": "2026-05",
                "target_customer": "외국인",
                "product_count": 3,
                "preferred_themes": ["야간 관광", "축제"],
                "avoid": ["가격 단정 표현"],
                "output_language": "ko",
                "user_intent": "외국인 대상 관광 상품 기획",
                "evidence_requirements": ["TourAPI 근거", "운영 조건 확인"],
            }
        )
    if purpose == "geo_resolution":
        prompt = kwargs.get("prompt") or ""
        if "없는지역" in prompt:
            resolved = []
        elif "부산에서 시작해서" in prompt and "양산" in prompt:
            return fake_gemini_result(
                {
                    "locations": [
                        {"text": "부산", "role": "primary", "normalized_text": "부산광역시", "is_foreign": False},
                        {"text": "양산", "role": "primary", "normalized_text": "경상남도 양산시", "is_foreign": False},
                    ],
                    "resolved_locations": [],
                    "excluded_locations": [],
                    "allow_nationwide": False,
                    "unsupported_locations": [],
                    "notes": ["복수 지역 요청"],
                }
            )
        elif "중구 야간 관광" in prompt:
            resolved = []
        elif "대전" in prompt:
            resolved = [{"text": "대전", "role": "primary", "name": "대전광역시", "ldong_regn_cd": "30", "ldong_signgu_cd": None, "confidence": 0.95, "reason": "요청에 대전이 명시됨"}]
        elif "부산진구" in prompt:
            resolved = [{"text": "부산 부산진구", "role": "primary", "name": "부산광역시 부산진구", "ldong_regn_cd": "26", "ldong_signgu_cd": "230", "confidence": 0.95, "reason": "요청에 부산진구가 명시됨"}]
        else:
            resolved = [{"text": "부산", "role": "primary", "name": "부산광역시", "ldong_regn_cd": "26", "ldong_signgu_cd": None, "confidence": 0.95, "reason": "요청에 부산이 명시됨"}]
        return fake_gemini_result(
            {
                "locations": [
                    {
                        "text": resolved[0]["text"] if resolved else "중구",
                        "role": "primary",
                        "normalized_text": resolved[0]["name"] if resolved else "중구",
                        "is_foreign": False,
                    }
                ],
                "resolved_locations": resolved,
                "excluded_locations": [],
                "allow_nationwide": False,
                "unsupported_locations": [],
                "notes": [],
            }
        )
    if purpose == "data_gap_profile":
        return fake_gemini_result(
            {
                "gaps": [],
                "coverage": {"total_items": 3, "gap_count": 0, "gap_counts": {}},
                "reasoning_summary": "기본 TourAPI 근거로 상품화를 진행할 수 있습니다.",
                "needs_review": [],
            }
        )
    if purpose == "api_capability_routing":
        return fake_gemini_result({"family_routes": [], "skipped_routes": [], "routing_reasoning": "추가 보강 호출 없음"})
    if purpose in {"tourapi_detail_planning", "visual_data_planning", "route_signal_planning", "theme_data_planning"}:
        return fake_gemini_result(
            {
                "planned_calls": [],
                "skipped_calls": [],
                "budget_summary": {"max_call_budget": 6, "planned": 0, "skipped": 0},
                "planning_reasoning": "배정된 gap 없음",
            }
        )
    if purpose == "evidence_fusion":
        return fake_gemini_result(
            {
                "evidence_profile": {"entities": [{"content_id": "TEST-BUSAN-001", "title": "부산 전통시장 야간 먹거리 골목"}]},
                "productization_advice": {"usable_claims": ["장소명과 주소는 근거 기반으로 사용할 수 있습니다."], "needs_review_fields": []},
                "data_coverage": {"total_items": 3, "gap_count": 0},
                "unresolved_gaps": [],
                "source_confidence": 0.8,
                "ui_highlights": [{"title": "근거 확인", "body": "TourAPI 근거를 기준으로 상품화를 진행합니다.", "severity": "info", "related_gap_types": []}],
            }
        )
    if purpose == "research_synthesis":
        return fake_gemini_result(
            {
                "research_brief": "부산 야간 관광 근거를 바탕으로 외국인 대상 상품을 구성합니다.",
                "usable_claims": ["장소명과 주소는 근거 기반으로 사용할 수 있습니다."],
                "restricted_claims": ["가격, 예약 가능 여부, 운영 시간은 확인 후 게시해야 합니다."],
                "operational_unknowns": ["가격", "예약"],
                "unresolved_gaps": [],
                "product_generation_guidance": ["각 상품은 source_ids와 연결합니다."],
                "qa_risk_notes": ["운영시간과 가격을 단정하지 않습니다."],
                "region_insights": [{"claim": "부산 관광 후보", "evidence_source_ids": ["doc:tourapi:test"], "confidence": 0.8}],
            }
        )
    if purpose in {"product_generation", "product_generation_repair"}:
        products = []
        for index, title in enumerate(
            [
                "부산 야간 미식 투어",
                "광안리 야간 해변 산책",
                "부산 로컬 축제 체험",
                "부산 역사 산책",
                "부산 해변 액티비티",
            ],
            start=1,
        ):
            products.append(
                {
                    "id": f"product_{index}",
                    "title": title,
                    "one_liner": f"{title}를 외국인 대상 상품으로 구성합니다.",
                    "target_customer": "외국인",
                    "core_value": ["야간 관광", "로컬 경험"],
                    "itinerary": [{"order": 1, "name": title, "source_id": "doc:tourapi:test"}],
                    "estimated_duration": "3시간",
                    "operation_difficulty": "보통",
                    "source_ids": ["doc:tourapi:test"],
                    "assumptions": ["가격과 운영시간은 확인 후 게시합니다."],
                    "not_to_claim": ["가격 확정", "상시 운영"],
                    "evidence_summary": ["TourAPI 후보 근거 기반"],
                    "needs_review": ["가격", "운영시간"],
                    "coverage_notes": ["직접 연결된 근거를 기준으로 게시 전 세부 정보를 확인합니다."],
                    "claim_limits": ["가격 확정 금지"],
                }
            )
        return fake_gemini_result(
            {
                "products": products
            }
        )
    if purpose in {"marketing_generation", "marketing_generation_repair"}:
        assets = []
        for index, title in enumerate(
            [
                "부산 야간 미식 투어",
                "광안리 야간 해변 산책",
                "부산 로컬 축제 체험",
                "부산 역사 산책",
                "부산 해변 액티비티",
            ],
            start=1,
        ):
            assets.append(
                {
                    "product_id": f"product_{index}",
                    "sales_copy": {
                        "headline": title,
                        "subheadline": "부산의 야간 관광과 로컬 경험을 가볍게 둘러보는 코스",
                        "sections": [{"title": "추천 포인트", "body": "야간 관광과 로컬 경험을 함께 구성합니다."}],
                        "disclaimer": "가격과 운영시간은 공식 확인 후 게시합니다.",
                    },
                    "faq": [
                        {
                            "question": "누구에게 추천하나요?",
                            "answer": "부산의 로컬 분위기를 가볍게 경험하고 싶은 외국인 관광객에게 추천합니다.",
                        },
                        {"question": "운영시간은 확정인가요?", "answer": "운영시간은 공식 확인 후 안내합니다."},
                    ],
                    "sns_campaign": {
                        "campaign_angles": [{"angle": title, "rationale": "대표 SNS 각도"}],
                        "posts": [{"format": "feed", "hook": title, "body": title, "hashtags": ["#부산여행"]}],
                        "visual_direction": ["대표 장면"],
                    },
                    "search_keywords": ["부산", "야간 관광", "외국인"],
                    "evidence_disclaimer": "TourAPI 근거 기반",
                    "claim_limits": ["가격 확정 금지"],
                }
            )
        return fake_gemini_result(
            {
                "marketing_assets": assets
            }
        )
    if purpose == "qa_review":
        return fake_gemini_result(
            {
                "overall_status": "needs_review",
                "summary": "게시 전 가격과 운영시간 확인이 필요합니다.",
                "issues": [
                    {
                        "product_id": "product_1",
                        "severity": "medium",
                        "type": "operational_unknown",
                        "message": "가격과 운영시간은 공식 확인 후 게시해야 합니다.",
                        "field_path": "sales_copy.disclaimer",
                        "suggested_fix": "가격과 운영시간 확인 필요 문구를 유지하세요.",
                    }
                ],
                "pass_count": 0,
                "needs_review_count": 1,
                "fail_count": 0,
            }
        )
    if purpose == "qa_targeted_revision_review":
        return fake_gemini_result(
            {
                "summary": "선택된 QA 이슈 재검수를 완료했습니다.",
                "items": [
                    {
                        "original_issue_index": 0,
                        "status": "resolved",
                        "message": "선택된 문제 문구가 수정되었습니다.",
                        "suggested_fix": "",
                    }
                ],
            }
        )
    if purpose == "revision_patch":
        return fake_gemini_result({"product_patches": [], "marketing_patches": [], "notes": ["필요한 필드만 유지합니다."]})
    raise AssertionError(f"Unexpected Gemini purpose: {purpose}")


def test_gemini_schema_validation_allows_null_for_optional_fields():
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "optional_id": {"type": "string"},
        },
    }

    _validate_json_schema({"name": "ok", "optional_id": None}, schema)
    with pytest.raises(GeminiGatewayError, match=r"\$\.name must be a string"):
        _validate_json_schema({"name": None, "optional_id": "x"}, schema)


def test_geo_scope_keyword_filters_locality_inside_resolved_signgu():
    geo_scope = {
        "locations": [
            {
                "name": "인천광역시 옹진군",
                "ldong_regn_cd": "28",
                "ldong_signgu_cd": "720",
                "keyword": "대청도",
                "sub_area_terms": [],
            }
        ],
        "allow_nationwide": False,
    }
    daecheong = TourismItem(
        id="tourapi:test:daecheong",
        source="tourapi",
        content_id="DCH",
        content_type="attraction",
        title="대청도 해변 산책",
        region_code="2",
        ldong_regn_cd="28",
        ldong_signgu_cd="720",
        address="인천광역시 옹진군 대청면",
    )
    baengnyeong = TourismItem(
        id="tourapi:test:baengnyeong",
        source="tourapi",
        content_id="BNY",
        content_type="attraction",
        title="백령도 전망대",
        region_code="2",
        ldong_regn_cd="28",
        ldong_signgu_cd="720",
        address="인천광역시 옹진군 백령면",
    )
    filtered_items = _filter_items_by_geo_scope(
        [daecheong, baengnyeong],
        geo_scope=geo_scope,
        run_id="test-run",
    )
    filtered_docs = _filter_retrieved_documents_by_geo_scope(
        [
            {
                "doc_id": "doc:daecheong",
                "title": "대청도 해변 산책",
                "content": "주소: 인천광역시 옹진군 대청면",
                "metadata": {
                    "ldong_regn_cd": "28",
                    "ldong_signgu_cd": "720",
                    "title": "대청도 해변 산책",
                },
            },
            {
                "doc_id": "doc:baengnyeong",
                "title": "백령도 전망대",
                "content": "주소: 인천광역시 옹진군 백령면",
                "metadata": {
                    "ldong_regn_cd": "28",
                    "ldong_signgu_cd": "720",
                    "title": "백령도 전망대",
                },
            },
        ],
        geo_scope=geo_scope,
        run_id="test-run",
    )

    assert [item.id for item in filtered_items] == ["tourapi:test:daecheong"]
    assert [doc["doc_id"] for doc in filtered_docs] == ["doc:daecheong"]


def test_geo_scope_expands_parent_city_to_child_signgus_for_tourapi_search():
    init_db()
    with SessionLocal() as db:
        seed_test_ldong_catalog(db)
        geo_scope = {
            "locations": [
                {
                    "role": "primary",
                    "name": "경상북도 포항시",
                    "base_name": "경상북도 포항시",
                    "ldong_regn_cd": "47",
                    "ldong_regn_nm": "경상북도",
                    "ldong_signgu_cd": "110",
                    "ldong_signgu_nm": "포항시",
                }
            ],
            "allow_nationwide": False,
        }

        expanded = _geo_scope_with_tourapi_child_locations(db, geo_scope)

    locations = expanded["locations"]
    assert [location["ldong_signgu_cd"] for location in locations] == ["111", "113"]
    assert [location["name"] for location in locations] == ["경상북도 포항시 남구", "경상북도 포항시 북구"]
    assert all(location["expanded_from_name"] == "경상북도 포항시" for location in locations)


def test_tourapi_keyword_queries_use_short_known_terms_without_hallucinated_landmarks():
    normalized = {
        "target_customer": "외국인",
        "preferred_themes": ["자연", "해변"],
    }
    geo_scope = {
        "locations": [
            {
                "role": "primary",
                "name": "경상북도 포항시 북구",
                "base_name": "경상북도 포항시",
                "matched_text": "포항",
                "ldong_regn_cd": "47",
                "ldong_signgu_cd": "113",
            }
        ],
        "allow_nationwide": False,
    }

    queries = _tourapi_keyword_queries(normalized, geo_scope, geo_scope["locations"][0])

    assert queries == ["포항", "자연", "해변", "포항 자연", "포항 해변"]
    assert "경상북도 포항시 외국인 자연 해변 액티비티" not in queries
    assert all(term not in " ".join(queries) for term in ["영일대", "호미곶"])


def test_gemini_prompt_debug_log_writes_full_prompt_and_output(monkeypatch, tmp_path):
    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"answer":"ok"}'}]},
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 12,
                    "candidatesTokenCount": 3,
                    "totalTokenCount": 15,
                },
            },
        )

    monkeypatch.setattr("app.llm.gemini_gateway.httpx.post", fake_post)
    settings = Settings(
        gemini_api_key="fake-key",
        llm_prompt_debug_log_enabled=True,
        llm_prompt_debug_log_dir=str(tmp_path),
    )

    with TestClient(app):
        with SessionLocal() as db:
            run = models.WorkflowRun(
                template_id="default_product_planning",
                input={"message": "프롬프트 로그 테스트"},
            )
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id = run.id
            step = models.AgentStep(
                run_id=run_id,
                agent_name="DebugPromptAgent",
                step_type="debug_prompt",
                status="running",
                input={"purpose": "debug"},
            )
            db.add(step)
            db.commit()
            db.refresh(step)
            step_id = step.id

            result = call_gemini_json(
                db=db,
                run_id=run_id,
                step_id=step_id,
                purpose="debug_prompt",
                prompt='{"task":"full prompt should be logged"}',
                response_schema={
                    "type": "object",
                    "required": ["answer"],
                    "properties": {"answer": {"type": "string"}},
                },
                settings=settings,
            )

    json_files = list((tmp_path / run_id).glob("*.json"))
    markdown_files = list((tmp_path / run_id).glob("*.md"))
    assert result.data == {"answer": "ok"}
    assert len(json_files) == 1
    assert len(markdown_files) == 1
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["run_id"] == run_id
    assert payload["step_id"] == step_id
    assert payload["agent_name"] == "DebugPromptAgent"
    assert payload["purpose"] == "debug_prompt"
    assert payload["status"] == "succeeded"
    assert "full prompt should be logged" in payload["request"]["input_prompt"]
    assert "JSON 스키마" in payload["request"]["full_prompt"]
    assert payload["response"]["raw_text"] == '{"answer":"ok"}'
    assert payload["response"]["parsed_json"] == {"answer": "ok"}
    markdown = markdown_files[0].read_text(encoding="utf-8")
    assert "# DebugPromptAgent / debug_prompt" in markdown
    assert "## Input Prompt" in markdown
    assert '{"task":"full prompt should be logged"}' in markdown
    assert "## Full Prompt Sent To Gemini" in markdown
    assert "JSON 스키마" in markdown
    assert "## Raw Output" in markdown
    assert '{"answer":"ok"}' in markdown


def test_preflight_rejects_natural_language_product_count_above_limit():
    with TestClient(app) as client:
        with SessionLocal() as db:
            before_count = db.query(models.WorkflowRun).count()
        response = client.post(
            "/api/workflow-runs",
            json={
                "template_id": "default_product_planning",
                "input": {
                    "message": "이번 달 서울에서 외국인 대상 관광 상품을 스물한 개 기획해줘",
                    "period": "2026-05",
                    "target_customer": "외국인",
                    "product_count": 20,
                    "preferences": ["야간 관광"],
                    "avoid": [],
                    "output_language": "ko",
                },
            },
        )
        with SessionLocal() as db:
            after_count = db.query(models.WorkflowRun).count()

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "PREFLIGHT_VALIDATION_FAILED"
    assert body["error"]["details"]["preflight"]["reason_code"] == "product_count_exceeds_limit"
    assert body["error"]["details"]["preflight"]["requested_product_count"] == 21
    assert after_count == before_count


def test_preflight_rejects_unsupported_non_tourism_prompt():
    with TestClient(app) as client:
        with SessionLocal() as db:
            before_count = db.query(models.WorkflowRun).count()
        response = client.post(
            "/api/workflow-runs",
            json={
                "template_id": "default_product_planning",
                "input": {
                    "message": "된장찌개 레시피 뭐야?",
                    "period": "2026-05",
                    "target_customer": "외국인",
                    "product_count": 1,
                    "preferences": [],
                    "avoid": [],
                    "output_language": "ko",
                },
            },
        )
        with SessionLocal() as db:
            after_count = db.query(models.WorkflowRun).count()

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "PREFLIGHT_VALIDATION_FAILED"
    assert body["error"]["details"]["preflight"]["reason_code"] == "unsupported_scope"
    assert after_count == before_count


def test_delete_workflow_runs_removes_selected_rows_and_revisions():
    with TestClient(app) as client:
        with SessionLocal() as db:
            parent = models.WorkflowRun(
                template_id="default_product_planning",
                status="failed",
                input={"message": "삭제할 parent"},
            )
            db.add(parent)
            db.flush()
            revision = models.WorkflowRun(
                template_id="default_product_planning",
                parent_run_id=parent.id,
                revision_number=1,
                revision_mode="manual_save",
                status="awaiting_approval",
                input={"message": "삭제할 revision"},
            )
            db.add(revision)
            db.flush()
            db.add(
                models.AgentStep(
                    run_id=parent.id,
                    agent_name="Test",
                    step_type="delete_test",
                    status="succeeded",
                    input={},
                )
            )
            parent_id = parent.id
            revision_id = revision.id
            db.commit()

        deleted = unwrap(client.post("/api/workflow-runs/delete", json={"run_ids": [parent_id]}))

        with SessionLocal() as db:
            remaining_parent = db.get(models.WorkflowRun, parent_id)
            remaining_revision = db.get(models.WorkflowRun, revision_id)
            remaining_steps = db.query(models.AgentStep).filter(models.AgentStep.run_id == parent_id).count()

    assert deleted["deleted_count"] == 2
    assert set(deleted["deleted_run_ids"]) == {parent_id, revision_id}
    assert remaining_parent is None
    assert remaining_revision is None
    assert remaining_steps == 0


def test_delete_workflow_runs_rejects_active_rows():
    with TestClient(app) as client:
        with SessionLocal() as db:
            run = models.WorkflowRun(
                template_id="default_product_planning",
                status="running",
                input={"message": "실행 중 삭제 불가"},
            )
            db.add(run)
            db.commit()
            run_id = run.id

        response = client.post("/api/workflow-runs/delete", json={"run_ids": [run_id]})

        with SessionLocal() as db:
            still_exists = db.get(models.WorkflowRun, run_id)

    assert response.status_code == 409
    assert still_exists is not None


def test_cancel_workflow_run_marks_active_run_as_cancelled():
    with TestClient(app) as client:
        with SessionLocal() as db:
            run = models.WorkflowRun(
                template_id="default_product_planning",
                status="running",
                input={"message": "실행 중지 테스트"},
            )
            db.add(run)
            db.commit()
            run_id = run.id

        result = unwrap(client.post(f"/api/workflow-runs/{run_id}/cancel"))

        with SessionLocal() as db:
            updated = db.get(models.WorkflowRun, run_id)
            cancel_step = (
                db.query(models.AgentStep)
                .filter(models.AgentStep.run_id == run_id, models.AgentStep.step_type == "workflow_cancelled")
                .first()
            )

    assert result["cancellation_requested"] is True
    assert result["run"]["status"] == "cancelled"
    assert updated is not None
    assert updated.status == "cancelled"
    assert updated.error["type"] == "CancellationRequested"
    assert updated.final_output["status"] == "cancelled"
    assert cancel_step is not None
    assert cancel_step.status == "succeeded"


def test_cancel_workflow_run_rejects_completed_run():
    with TestClient(app) as client:
        with SessionLocal() as db:
            run = models.WorkflowRun(
                template_id="default_product_planning",
                status="awaiting_approval",
                input={"message": "완료된 run"},
            )
            db.add(run)
            db.commit()
            run_id = run.id

        response = client.post(f"/api/workflow-runs/{run_id}/cancel")

    assert response.status_code == 409


def test_list_workflow_runs_hides_evaluation_runs():
    with TestClient(app) as client:
        with SessionLocal() as db:
            normal = models.WorkflowRun(
                template_id="default_product_planning",
                status="failed",
                input={"message": "일반 run"},
            )
            evaluation = models.WorkflowRun(
                template_id="default_product_planning",
                status="awaiting_approval",
                input={
                    "message": "평가 run",
                    "_evaluation": {"eval_id": "eval_test", "case_id": "case_1"},
                },
            )
            db.add_all([normal, evaluation])
            db.commit()
            normal_id = normal.id
            evaluation_id = evaluation.id

        runs = unwrap(client.get("/api/workflow-runs"))

    run_ids = {run["id"] for run in runs}
    assert normal_id in run_ids
    assert evaluation_id not in run_ids


def legacy_area_from_ldong(ldong_regn_cd, fallback):
    return {
        "26": "6",
        "30": "3",
    }.get(str(ldong_regn_cd or ""), fallback)


class TestTourApiProvider:
    def area_code(self, region=None):
        return [{"code": "6", "name": "부산"}]

    def ldong_code(
        self,
        *,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        list_yn="N",
        page_no=1,
        limit=100,
    ):
        if ldong_regn_cd == "26":
            return [{"lDongRegnCd": "26", "lDongRegnNm": "부산광역시"}]
        return [{"lDongRegnCd": "26", "lDongRegnNm": "부산광역시"}]

    def lcls_system_code(
        self,
        *,
        lcls_systm_1=None,
        lcls_systm_2=None,
        lcls_systm_3=None,
        list_yn="N",
        page_no=1,
        limit=1000,
    ):
        return [{"lclsSystm1": "VE", "lclsSystm1Nm": "볼거리"}]

    def area_based_list(
        self,
        *,
        region_code=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        content_type=None,
        keyword=None,
        limit=20,
        **kwargs,
    ):
        return self.search_keyword(
            query=keyword or "부산",
            region_code=region_code,
            ldong_regn_cd=ldong_regn_cd,
            ldong_signgu_cd=ldong_signgu_cd,
            limit=limit,
        )

    def search_keyword(
        self,
        *,
        query,
        region_code=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        limit=20,
        **kwargs,
    ):
        region_code = region_code or legacy_area_from_ldong(ldong_regn_cd, "6")
        return [
            TourismItem(
                id="tourapi:test:busan:night-market",
                source="tourapi",
                content_id="TEST-BUSAN-001",
                content_type="attraction",
                title="부산 전통시장 야간 먹거리 골목",
                region_code=region_code or "6",
                sigungu_code="16",
                legacy_area_code=region_code or "6",
                legacy_sigungu_code="16",
                ldong_regn_cd=ldong_regn_cd or "26",
                ldong_signgu_cd=ldong_signgu_cd,
                address="부산광역시 중구",
                overview="야간 시간대 외국인 대상 먹거리 동선으로 검토할 수 있는 시장 후보입니다.",
                license_type="TourAPI test response",
            )
        ][:limit]

    def search_festival(
        self,
        *,
        region_code=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        start_date=None,
        end_date=None,
        limit=20,
        **kwargs,
    ):
        region_code = region_code or legacy_area_from_ldong(ldong_regn_cd, "6")
        return [
            TourismItem(
                id="tourapi:test:busan:drone-show",
                source="tourapi",
                content_id="TEST-BUSAN-002",
                content_type="event",
                title="광안리 M 드론 라이트쇼",
                region_code=region_code or "6",
                sigungu_code="12",
                legacy_area_code=region_code or "6",
                legacy_sigungu_code="12",
                ldong_regn_cd=ldong_regn_cd or "26",
                ldong_signgu_cd=ldong_signgu_cd,
                address="부산광역시 수영구 광안해변로",
                overview="광안리 해변에서 진행되는 야간 드론 라이트쇼입니다.",
                event_start_date="20260501",
                event_end_date="20260531",
                license_type="TourAPI test response",
            )
        ][:limit]

    def search_stay(
        self,
        *,
        region_code=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        limit=20,
        **kwargs,
    ):
        region_code = region_code or legacy_area_from_ldong(ldong_regn_cd, "6")
        return [
            TourismItem(
                id="tourapi:test:busan:hotel",
                source="tourapi",
                content_id="TEST-BUSAN-003",
                content_type="accommodation",
                title="그랜드 조선 부산",
                region_code=region_code or "6",
                sigungu_code="16",
                legacy_area_code=region_code or "6",
                legacy_sigungu_code="16",
                ldong_regn_cd=ldong_regn_cd or "26",
                ldong_signgu_cd=ldong_signgu_cd,
                address="부산광역시 해운대구",
                overview="해운대 권역 숙박 후보입니다.",
                license_type="TourAPI test response",
            )
        ][:limit]

    def detail_common(self, *, content_id):
        content_type_id = {
            "TEST-BUSAN-001": "12",
            "TEST-BUSAN-002": "15",
            "TEST-BUSAN-003": "32",
        }.get(content_id, "12")
        title = {
            "TEST-BUSAN-001": "부산 전통시장 야간 먹거리 골목",
            "TEST-BUSAN-002": "광안리 M 드론 라이트쇼",
            "TEST-BUSAN-003": "그랜드 조선 부산",
        }.get(content_id, "부산 관광 후보")
        return {
            "contentid": content_id,
            "contenttypeid": content_type_id,
            "title": title,
            "areacode": "6",
            "sigungucode": "16",
            "lDongRegnCd": "26",
            "lDongSignguCd": "110",
            "addr1": "부산광역시 테스트구",
            "addr2": "상세 주소",
            "mapx": "129.1",
            "mapy": "35.1",
            "tel": "051-000-0000",
            "homepage": "https://example.com",
            "overview": f"{title} 상세 개요입니다.",
            "firstimage": f"https://example.com/{content_id}.jpg",
        }

    def detail_intro(self, *, content_id, content_type_id):
        return {
            "contentid": content_id,
            "contenttypeid": content_type_id,
            "infocenter": "문의처 확인 필요",
            "usetime": "운영 시간은 공식 안내 확인 필요",
        }

    def detail_info(self, *, content_id, content_type_id):
        return [
            {"infoname": "이용시간", "infotext": "운영 시간은 공식 안내 확인 필요"},
            {"infoname": "주차", "infotext": "주차 가능 여부 확인 필요"},
        ]

    def detail_images(self, *, content_id):
        return [
            {
                "serialnum": "1",
                "imgname": "대표 이미지 후보",
                "originimgurl": f"https://example.com/{content_id}-detail.jpg",
                "smallimageurl": f"https://example.com/{content_id}-thumb.jpg",
            }
        ]

    def category_code(self, *, cat1=None, cat2=None, cat3=None, limit=100):
        return [{"code": "A01", "name": "자연"}]

    def location_based_list(
        self,
        *,
        map_x,
        map_y,
        radius=1000,
        content_type=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        limit=20,
        **kwargs,
    ):
        return self.search_keyword(
            query="주변",
            region_code="6",
            ldong_regn_cd=ldong_regn_cd or "26",
            ldong_signgu_cd=ldong_signgu_cd,
            limit=limit,
        )


class DaejeonTourApiProvider(TestTourApiProvider):
    def area_code(self, region=None):
        return [{"code": "3", "name": "대전"}]

    def ldong_code(
        self,
        *,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        list_yn="N",
        page_no=1,
        limit=100,
    ):
        if ldong_regn_cd == "30":
            return [
                {
                    "lDongRegnCd": "30",
                    "lDongRegnNm": "대전광역시",
                    "lDongSignguCd": "200",
                    "lDongSignguNm": "유성구",
                }
            ]
        return [{"lDongRegnCd": "30", "lDongRegnNm": "대전광역시"}]

    def area_based_list(
        self,
        *,
        region_code=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        content_type=None,
        keyword=None,
        limit=20,
        **kwargs,
    ):
        content_type = content_type or "12"
        title = "대전 원도심 과학문화 산책" if content_type == "12" else "대전 갑천 레저 체험"
        item_type = "attraction" if content_type == "12" else "leisure"
        return [
            self._daejeon_item(
                suffix=f"area-{content_type}",
                content_id=f"TEST-DAEJEON-{content_type}",
                content_type=item_type,
                title=title,
                region_code=region_code,
                ldong_regn_cd=ldong_regn_cd,
                ldong_signgu_cd=ldong_signgu_cd,
            )
        ][:limit]

    def search_keyword(
        self,
        *,
        query,
        region_code=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        limit=20,
        **kwargs,
    ):
        return [
            self._daejeon_item(
                suffix="night-market",
                content_id="TEST-DAEJEON-001",
                content_type="attraction",
                title="대전 중앙시장 야간 미식 투어",
                region_code=region_code,
                ldong_regn_cd=ldong_regn_cd,
                ldong_signgu_cd=ldong_signgu_cd,
            )
        ][:limit]

    def search_festival(
        self,
        *,
        region_code=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        start_date=None,
        end_date=None,
        limit=20,
        **kwargs,
    ):
        item = self._daejeon_item(
            suffix="festival",
            content_id="TEST-DAEJEON-002",
            content_type="event",
            title="대전 외국인 문화 교류 축제",
            region_code=region_code,
            ldong_regn_cd=ldong_regn_cd,
            ldong_signgu_cd=ldong_signgu_cd,
        )
        item.event_start_date = "20260501"
        item.event_end_date = "20260531"
        return [item][:limit]

    def search_stay(
        self,
        *,
        region_code=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        limit=20,
        **kwargs,
    ):
        return [
            self._daejeon_item(
                suffix="hotel",
                content_id="TEST-DAEJEON-003",
                content_type="accommodation",
                title="대전역 관광호텔",
                region_code=region_code,
                ldong_regn_cd=ldong_regn_cd,
                ldong_signgu_cd=ldong_signgu_cd,
            )
        ][:limit]

    def detail_common(self, *, content_id):
        return {
            "contentid": content_id,
            "contenttypeid": "15" if content_id == "TEST-DAEJEON-002" else "12",
            "title": f"{content_id} 상세",
            "areacode": "3",
            "sigungucode": "1",
            "lDongRegnCd": "30",
            "lDongSignguCd": "200",
            "addr1": "대전광역시 중구",
            "addr2": "테스트 주소",
            "mapx": "127.4",
            "mapy": "36.3",
            "tel": "042-000-0000",
            "homepage": "https://example.com/daejeon",
            "overview": "대전 지역 외국인 대상 관광 후보 상세 개요입니다.",
            "firstimage": f"https://example.com/{content_id}.jpg",
        }

    def location_based_list(
        self,
        *,
        map_x,
        map_y,
        radius=1000,
        content_type=None,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        limit=20,
        **kwargs,
    ):
        return self.search_keyword(
            query="주변",
            region_code="3",
            ldong_regn_cd=ldong_regn_cd or "30",
            ldong_signgu_cd=ldong_signgu_cd,
            limit=limit,
        )

    def _daejeon_item(
        self,
        *,
        suffix,
        content_id,
        content_type,
        title,
        region_code,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
    ):
        region_code = region_code or legacy_area_from_ldong(ldong_regn_cd, "3")
        return TourismItem(
            id=f"tourapi:test:daejeon:{suffix}",
            source="tourapi",
            content_id=content_id,
            content_type=content_type,
            title=title,
            region_code=region_code or "3",
            sigungu_code="1",
            legacy_area_code=region_code or "3",
            legacy_sigungu_code="1",
            ldong_regn_cd=ldong_regn_cd or "30",
            ldong_signgu_cd=ldong_signgu_cd,
            address="대전광역시 중구",
            overview=f"{title}는 외국인 대상 대전 액티비티 후보입니다.",
            license_type="TourAPI test response",
        )


class EmptyTourApiProvider(TestTourApiProvider):
    def area_based_list(self, **kwargs):
        return []

    def search_keyword(self, **kwargs):
        return []

    def search_festival(self, **kwargs):
        return []

    def search_stay(self, **kwargs):
        return []


def use_test_tourapi_provider(monkeypatch, *, fake_gemini: bool = True):
    init_db()
    with SessionLocal() as db:
        seed_test_ldong_catalog(db)
    if fake_gemini:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        get_settings.cache_clear()
        monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_workflow_gemini_result)
    monkeypatch.setattr(
        "app.agents.workflow.get_tourism_provider",
        lambda: TestTourApiProvider(),
    )
    monkeypatch.setattr(
        "app.api.routes_data.get_tourism_provider",
        lambda: TestTourApiProvider(),
    )


def use_daejeon_tourapi_provider(monkeypatch, *, fake_gemini: bool = True):
    init_db()
    with SessionLocal() as db:
        seed_test_ldong_catalog(db)
    if fake_gemini:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        get_settings.cache_clear()
        monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_workflow_gemini_result)
    monkeypatch.setattr(
        "app.agents.workflow.get_tourism_provider",
        lambda: DaejeonTourApiProvider(),
    )
    monkeypatch.setattr(
        "app.api.routes_data.get_tourism_provider",
        lambda: DaejeonTourApiProvider(),
    )


def use_empty_tourapi_provider(monkeypatch, *, fake_gemini: bool = True):
    init_db()
    with SessionLocal() as db:
        seed_test_ldong_catalog(db)
    if fake_gemini:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        get_settings.cache_clear()
        monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_workflow_gemini_result)
    monkeypatch.setattr(
        "app.agents.workflow.get_tourism_provider",
        lambda: EmptyTourApiProvider(),
    )
    monkeypatch.setattr(
        "app.api.routes_data.get_tourism_provider",
        lambda: EmptyTourApiProvider(),
    )


def test_health():
    with TestClient(app) as client:
        data = unwrap(client.get("/api/health"))
    assert data["status"] == "ok"
    assert data["db"] == "ok"


def test_data_source_capabilities_show_phase8_foundation(monkeypatch):
    monkeypatch.setenv("TOURAPI_ENABLED", "true")
    monkeypatch.setenv("TOURAPI_SERVICE_KEY", "")
    monkeypatch.setenv("KTO_PHOTO_CONTEST_ENABLED", "false")
    monkeypatch.setenv("OFFICIAL_WEB_SEARCH_ENABLED", "false")
    get_settings.cache_clear()

    with TestClient(app) as client:
        data = unwrap(client.get("/api/data/sources/capabilities"))

    get_settings.cache_clear()

    source_families = {source["source_family"]: source for source in data["sources"]}
    assert "kto_tourapi_kor" in source_families
    assert "kto_photo_contest" in source_families
    assert "official_web" in source_families

    tourapi = source_families["kto_tourapi_kor"]
    assert tourapi["enabled"] is False
    assert tourapi["missing_env_vars"] == ["TOURAPI_SERVICE_KEY"]
    assert any(
        operation["tool_name"] == "tourapi_search_keyword"
        and operation["implemented"] is True
        for operation in tourapi["operations"]
    )
    assert any(
        operation["tool_name"] == "kto_tour_detail_common"
        and operation["implemented"] is True
        and operation["workflow_enabled"] is False
        for operation in tourapi["operations"]
    )
    assert data["implemented_operation_count"] >= 11


def test_data_source_overview_returns_operator_summary(monkeypatch):
    monkeypatch.setenv("TOURAPI_ENABLED", "true")
    monkeypatch.setenv("TOURAPI_SERVICE_KEY", "")
    monkeypatch.setenv("KTO_PHOTO_CONTEST_ENABLED", "false")
    get_settings.cache_clear()

    with TestClient(app) as client:
        data = unwrap(client.get("/api/data/sources/overview"))

    get_settings.cache_clear()

    assert data["purpose"] == "운영자가 관광 데이터 API와 실제 저장 데이터를 확인하는 화면"
    assert data["summary"]["total_sources"] >= 1
    assert data["documents"]["status"] in {"empty", "ready", "pending", "attention"}
    assert {catalog["key"] for catalog in data["catalogs"]} == {"tourapi_ldong", "tourapi_lcls"}
    assert {profile["key"] for profile in data["purpose_profiles"]} >= {"all", "visual", "pet", "walking"}

    source_families = {source["source_family"]: source for source in data["sources"]}
    tourapi = source_families["kto_tourapi_kor"]
    assert tourapi["readiness_status"] == "setup_required"
    assert tourapi["status_label"] == "키 연결 필요"
    assert "inventory" in tourapi
    assert "지역 코드" in tourapi["input_fields"]
    assert "관광지명" in tourapi["output_fields"]
    assert tourapi["stored_count"] >= 0
    assert tourapi["evidence_count"] >= 0


def test_data_source_browsers_return_operator_catalogs():
    with TestClient(app) as client:
        documents = unwrap(client.get("/api/data/sources/documents?limit=5"))
        tourism_items = unwrap(client.get("/api/data/sources/tourism-items?limit=5"))
        catalogs = unwrap(client.get("/api/data/sources/catalogs/browser?limit=5"))

    assert documents["limit"] == 5
    assert isinstance(documents["items"], list)
    assert tourism_items["limit"] == 5
    assert isinstance(tourism_items["items"], list)
    assert catalogs["limit"] == 5
    assert isinstance(catalogs["regions"], list)
    assert isinstance(catalogs["classifications"], list)


def test_phase8_tables_are_created():
    with TestClient(app):
        table_names = set(inspect(engine).get_table_names())

    assert {
        "tourism_entities",
        "tourism_visual_assets",
        "tourism_route_assets",
        "tourism_signal_records",
        "enrichment_runs",
        "enrichment_tool_calls",
        "web_evidence_documents",
    } <= table_names


def test_source_document_includes_enrichment_metadata():
    document = build_source_document(
        TourismItem(
            id="tourapi:test:source-doc",
            source="tourapi",
            content_id="TEST-001",
            content_type="event",
            title="테스트 행사",
            region_code="6",
            sigungu_code="16",
            address="부산광역시",
            overview="테스트 개요",
            event_start_date="2026-05-01",
            license_type="TourAPI test response",
        )
    )

    metadata = document["document_metadata"]
    assert metadata["source_family"] == "kto_tourapi_kor"
    assert metadata["trust_level"] == 0.9
    assert metadata["retrieved_at"]
    assert "missing_image_asset" in metadata["data_quality_flags"]
    assert metadata["license_note"] == "TourAPI test response"


def test_tourism_detail_enrichment_api_stores_entity_visual_asset_and_source_doc(monkeypatch):
    use_test_tourapi_provider(monkeypatch)

    with SessionLocal() as db:
        item = models.TourismItem(
            id="tourapi:test:phase9",
            source="tourapi",
            content_id="TEST-BUSAN-001",
            content_type="attraction",
            title="부산 전통시장 야간 먹거리 골목",
            region_code="6",
            sigungu_code="16",
            address="부산광역시 중구",
            overview="기본 개요",
            raw={},
        )
        db.merge(item)
        db.commit()

    with TestClient(app) as client:
        data = unwrap(
            client.post(
                "/api/data/tourism/details/enrich",
                json={"item_ids": ["tourapi:test:phase9"], "limit": 1},
            )
        )

    assert data["summary"]["enriched_items"] == 1
    assert data["summary"]["visual_assets"] == 1
    assert data["entities"][0]["canonical_name"] == "부산 전통시장 야간 먹거리 골목"
    assert data["visual_assets"][0]["usage_status"] == "candidate"
    assert data["source_documents"] == 1

    with SessionLocal() as db:
        stored_item = db.get(models.TourismItem, "tourapi:test:phase9")
        source_doc = db.get(models.SourceDocument, "doc:tourapi:test:phase9")
        assert stored_item.raw["detail_common"]["contentid"] == "TEST-BUSAN-001"
        assert stored_item.raw["detail_info"][0]["infoname"] == "이용시간"
        assert source_doc.document_metadata["detail_common_available"] is True
        assert source_doc.document_metadata["detail_info_count"] == 2


def test_create_and_read_workflow_run(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "이번 달 부산에서 외국인 대상 액티비티 상품을 5개 기획해줘",
            "region": "부산",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 5,
            "preferences": ["야간 관광", "축제"],
        },
    }
    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))
        fetched = unwrap(client.get(f"/api/workflow-runs/{created['id']}"))
        steps = unwrap(client.get(f"/api/workflow-runs/{created['id']}/steps"))
        tool_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/tool-calls"))
        enrichment = unwrap(client.get(f"/api/workflow-runs/{created['id']}/enrichment"))
        llm_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/llm-calls"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))

    assert created["status"] == "pending"
    assert created["input"]["region"] == "부산"
    assert fetched["status"] == "awaiting_approval"
    assert fetched["final_output"]["status"] == "awaiting_approval"
    assert fetched["id"] == created["id"]
    assert len(result["products"]) == 3
    assert {step["agent_name"] for step in steps} >= {
        "PlannerAgent",
        "GeoResolverAgent",
        "BaselineDataAgent",
        "DataGapProfilerAgent",
        "ResearchSynthesisAgent",
        "ProductAgent",
        "MarketingAgent",
        "QAComplianceAgent",
        "HumanApprovalNode",
    }
    assert {call["tool_name"] for call in tool_calls} >= {
        "tourapi_search_keyword",
        "tourapi_search_festival",
        "tourapi_search_stay",
        "vector_search",
    }
    if enrichment["latest"]:
        assert enrichment["latest"]["status"] == "completed"
    assert isinstance(result["evidence_profile"], dict)
    assert result["data_coverage"]["total_items"] >= 1
    assert isinstance(llm_calls, list)
    assert all(call["purpose"] != "data_summary" for call in llm_calls)


def test_workflow_resolves_non_busan_ldong_scope_from_prompt(monkeypatch):
    use_daejeon_tourapi_provider(monkeypatch)
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "이번 달 대전에서 외국인 대상 액티비티 상품을 3개 기획해줘",
            "region": "대전",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 3,
            "preferences": ["야간 관광", "축제"],
        },
    }

    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))
        tool_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/tool-calls"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))

    calls_by_name = {}
    for call in tool_calls:
        calls_by_name.setdefault(call["tool_name"], []).append(call)

    assert calls_by_name["tourapi_search_keyword"][0]["arguments"]["ldong_regn_cd"] == "30"
    assert calls_by_name["tourapi_search_festival"][0]["arguments"]["ldong_regn_cd"] == "30"
    assert calls_by_name["tourapi_search_stay"][0]["arguments"]["ldong_regn_cd"] == "30"
    assert calls_by_name["vector_search"][0]["arguments"]["filters"]["ldong_regn_cd"] == "30"
    assert result["normalized_request"]["ldong_regn_cd"] == "30"
    assert result["geo_scope"]["locations"][0]["ldong_regn_cd"] == "30"
    assert result["retrieved_documents"]
    assert {
        document["metadata"]["ldong_regn_cd"]
        for document in result["retrieved_documents"]
    } == {"30"}


def test_workflow_returns_insufficient_source_data_when_tourapi_has_no_items(monkeypatch):
    use_empty_tourapi_provider(monkeypatch)
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "부산 부산진구에서 외국인 대상 야간 관광 상품 3개 기획해줘",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 3,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))
        fetched = unwrap(client.get(f"/api/workflow-runs/{created['id']}"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))
        tool_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/tool-calls"))

    assert fetched["status"] == "failed"
    assert fetched["error"] is None
    assert result["status"] == "insufficient_source_data"
    assert result["reason"] == "insufficient_source_data"
    assert result["retrieval_diagnostics"]["tourapi_raw_collected_count"] == 0
    assert result["retrieval_diagnostics"]["geo_filtered_item_count"] == 0
    assert result["retrieval_diagnostics"]["reason"] == "tourapi_empty_for_resolved_geo_scope"
    assert result["suggested_next_requests"]
    assert result["products"] == []
    assert result["qa_report"]["overall_status"] == "not_run"
    assert any(call["tool_name"].startswith("tourapi_search") for call in tool_calls)


def test_workflow_returns_insufficient_source_data_when_vector_search_is_empty(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    monkeypatch.setattr(
        "app.agents.workflow.search_source_documents_with_diagnostics",
        lambda **kwargs: {
            "results": [],
            "retrieval_diagnostics": {
                "query": kwargs.get("query"),
                "filters": kwargs.get("filters"),
                "result_count": 0,
                "fallback_applied": False,
                "reason": "test_empty",
            },
        },
    )
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "부산 부산진구에서 외국인 대상 야간 관광 상품 3개 기획해줘",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 3,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))
        fetched = unwrap(client.get(f"/api/workflow-runs/{created['id']}"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))
        steps = unwrap(client.get(f"/api/workflow-runs/{created['id']}/steps"))

    assert fetched["status"] == "failed"
    assert fetched["error"] is None
    assert result["status"] == "insufficient_source_data"
    assert result["retrieval_diagnostics"]["geo_filtered_item_count"] > 0
    assert result["retrieval_diagnostics"]["source_document_upsert_count"] > 0
    assert result["retrieval_diagnostics"]["indexed_document_count"] > 0
    assert result["retrieval_diagnostics"]["vector_search_result_count"] == 0
    assert result["retrieval_diagnostics"]["post_geo_filter_result_count"] == 0
    assert result["retrieval_diagnostics"]["reason"] == "vector_search_empty_for_resolved_geo_scope"
    assert not any(step["step_type"] == "product_generation" for step in steps)


def test_workflow_keeps_chroma_exception_as_system_error(monkeypatch):
    use_test_tourapi_provider(monkeypatch)

    def fail_search(**kwargs):
        raise RuntimeError("chroma down")

    monkeypatch.setattr("app.agents.workflow.search_source_documents_with_diagnostics", fail_search)
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "부산 부산진구에서 외국인 대상 야간 관광 상품 3개 기획해줘",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 3,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))
        fetched = unwrap(client.get(f"/api/workflow-runs/{created['id']}"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))
        tool_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/tool-calls"))

    assert fetched["status"] == "failed"
    assert fetched["error"]["type"] == "RuntimeError"
    assert "chroma down" in fetched["error"]["message"]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "RuntimeError"
    vector_call = next(call for call in tool_calls if call["tool_name"] == "vector_search")
    assert vector_call["status"] == "failed"
    assert vector_call["error"]["type"] == "RuntimeError"


def test_workflow_blocks_unresolved_region_without_nationwide_fallback(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "없는지역에서 외국인 대상 액티비티 상품을 1개 기획해줘",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 1,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))
        fetched = unwrap(client.get(f"/api/workflow-runs/{created['id']}"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))
        steps = unwrap(client.get(f"/api/workflow-runs/{created['id']}/steps"))
        tool_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/tool-calls"))

    assert fetched["status"] == "failed"
    assert fetched["error"] is None
    assert result["status"] == "failed"
    assert result["geo_scope"]["needs_clarification"] is True
    assert any(step["step_type"] == "geo_scope_exit" for step in steps)
    assert all(not call["tool_name"].startswith("tourapi_search") for call in tool_calls)


def test_workflow_shows_candidates_for_ambiguous_region_with_failed_status(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "중구 야간 관광 상품을 만들어줘",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 1,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))
        fetched = unwrap(client.get(f"/api/workflow-runs/{created['id']}"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))
        tool_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/tool-calls"))

    assert fetched["status"] == "failed"
    assert fetched["error"] is None
    assert result["status"] == "failed"
    assert result["user_message"]["title"] == "지역을 하나로 좁혀 주세요"
    assert result["geo_scope"]["needs_clarification"] is True
    assert isinstance(result["geo_scope"]["candidates"], list)
    assert all(not call["tool_name"].startswith("tourapi_search") for call in tool_calls)


def test_workflow_blocks_route_or_multi_region_request_before_tourapi_search(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "부산에서 시작해서 양산에서 끝나는 외국인 대상 관광 상품을 만들어줘",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 1,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))
        fetched = unwrap(client.get(f"/api/workflow-runs/{created['id']}"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))
        steps = unwrap(client.get(f"/api/workflow-runs/{created['id']}/steps"))
        tool_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/tool-calls"))

    assert fetched["status"] == "failed"
    assert fetched["error"] is None
    assert result["status"] == "failed"
    assert result["user_message"]["title"] in {"단일 지역만 지원합니다", "지역을 하나로 좁혀 주세요"}
    assert result["geo_scope"]["mode"] in {"unsupported_multi_region", "clarification_required"}
    assert result["geo_scope"]["needs_clarification"] is True
    assert isinstance(result["geo_scope"]["candidates"], list)
    assert any(step["step_type"] == "geo_scope_exit" for step in steps)
    assert all(not call["tool_name"].startswith("tourapi_search") for call in tool_calls)


def test_workflow_blocks_foreign_destination_before_tourapi_search(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    get_settings.cache_clear()

    def fake_call_gemini_json(**kwargs):
        purpose = kwargs["purpose"]
        if purpose == "planner":
            return fake_gemini_result(
                {
                    "user_intent": "도쿄에서 외국인 대상 액티비티 상품을 기획합니다.",
                    "request_type": "tourism_product_generation",
                    "product_count": 1,
                    "target_customer": "외국인",
                    "preferred_themes": ["야간 관광"],
                    "avoid": [],
                    "period": "2026-05",
                    "output_language": "ko",
                    "product_generation_constraints": ["상품 개수는 최대 20개입니다."],
                    "evidence_requirements": ["각 상품은 실제 근거 문서와 연결되어야 합니다."],
                }
            )
        if purpose == "geo_resolution":
            return fake_gemini_result(
                {
                    "locations": [
                        {
                            "text": "도쿄",
                            "normalized_text": "도쿄",
                            "role": "primary",
                            "is_foreign": True,
                        }
                    ],
                    "resolved_locations": [],
                    "clarification_candidates": [],
                    "excluded_locations": [],
                    "allow_nationwide": False,
                    "unsupported_locations": ["도쿄"],
                    "notes": [],
                }
            )
        raise AssertionError(f"unexpected Gemini purpose: {purpose}")

    monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_call_gemini_json)
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "도쿄에서 외국인 대상 액티비티 상품을 1개 기획해줘",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 1,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))
        fetched = unwrap(client.get(f"/api/workflow-runs/{created['id']}"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))
        steps = unwrap(client.get(f"/api/workflow-runs/{created['id']}/steps"))
        tool_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/tool-calls"))

    assert fetched["status"] == "unsupported"
    assert fetched["error"] is None
    assert result["status"] == "unsupported"
    assert result["user_message"]["message"] == "PARAVOCA는 현재 국내 관광 데이터만 지원합니다."
    geo_step = next(step for step in steps if step["agent_name"] == "GeoResolverAgent")
    assert geo_step["output"]["geo_scope"]["status"] == "unsupported"
    assert geo_step["output"]["geo_scope"]["resolution_strategy"] == "llm_foreign_destination_detected"
    assert any(step["step_type"] == "geo_scope_exit" for step in steps)
    assert all(not call["tool_name"].startswith("tourapi_search") for call in tool_calls)
    get_settings.cache_clear()


def test_create_workflow_run_rejects_invalid_period():
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "부산 외국인 액티비티 검토",
            "region": "부산",
            "period": "2026-13",
            "target_customer": "외국인",
            "product_count": 2,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        response = client.post("/api/workflow-runs", json=payload)

    assert response.status_code == 422
    assert "period must use YYYY-MM format" in response.text


def test_validate_qa_report_hides_internal_field_paths_and_fills_fix():
    products = [{"id": "product_1", "title": "부산 야경 투어"}]
    payload = {
        "overall_status": "needs_review",
        "summary": "",
        "issues": [
            {
                "product_id": "product_1",
                "severity": "medium",
                "type": "price_claim",
                "message": "상세 설명에 문제 문구 '가격은 10,000원입니다'가 있습니다. 가격 단정 표현입니다.",
                "field_path": "sales_copy.sections[0].body",
                "suggested_fix": "",
            }
        ],
        "pass_count": 0,
        "needs_review_count": 1,
        "fail_count": 0,
    }

    report = validate_qa_report(payload, products)

    assert report["summary"] == "QA 검수에서 추가 확인이 필요한 이슈 1건이 발견되었습니다."
    assert "sales_copy" not in report["issues"][0]["message"]
    assert "상세 설명" in report["issues"][0]["message"]
    assert report["issues"][0]["suggested_fix"] == "표현을 완화하고, 운영자가 확인 가능한 조건형 문장으로 수정하세요."


def test_validate_qa_report_splits_message_and_suggested_fix():
    products = [{"id": "product_1", "title": "부산 야경 투어"}]
    payload = {
        "overall_status": "needs_review",
        "summary": "추가 확인이 필요합니다.",
        "issues": [
            {
                "product_id": "product_1",
                "severity": "medium",
                "type": "general",
                "message": (
                    "상품의 'sales_copy.sections[0].body'에 '항상 최저가를 보장합니다'라는 문구가 포함되어 있습니다. "
                    "'항상 최저가를 보장합니다'라는 표현은 가격 보장 표현으로 간주될 수 있으므로, "
                    "'가격은 운영자가 최종 확인한 뒤 안내합니다'와 같이 수정하는 것을 권장합니다."
                ),
                "field_path": "sales_copy.sections[0].body",
                "suggested_fix": "",
            }
        ],
    }

    report = validate_qa_report(payload, products)

    assert "수정하는 것을 권장" not in report["issues"][0]["message"]
    assert report["issues"][0]["suggested_fix"] == "'가격은 운영자가 최종 확인한 뒤 안내합니다'처럼 완화된 표현으로 수정하세요."


def test_validate_qa_report_cites_problem_phrase_for_deterministic_operating_hours_issue():
    products = [
        {
            "id": "product_1",
            "title": "포항 경상북도수목원 힐링 & 자연 체험",
            "one_liner": "숲에서 쉬어 가는 자연 체험입니다.",
            "core_value": [],
            "itinerary": [],
            "estimated_duration": "상시 운영",
            "operation_difficulty": "보통",
            "source_ids": ["doc_1"],
        }
    ]
    payload = {"overall_status": "pass", "summary": "", "issues": []}
    report = validate_qa_report(
        payload,
        products,
        docs=[{"doc_id": "doc_1"}],
        evidence_context={"unresolved_gaps": [{"gap_type": "missing_operating_hours"}]},
        marketing_assets=[],
    )

    issue = report["issues"][0]
    assert issue["type"] == "operating_hours_claim"
    assert issue["field_path"] == "estimated_duration"
    assert "예상 소요 시간" in issue["message"]
    assert "'상시 운영'" in issue["message"]


def test_validate_qa_report_checks_strategy_pack_usable_claims():
    products = [
        {
            "id": "product_1",
            "title": "예약 확정 투어",
            "one_liner": "근거 기반 상품",
            "core_value": [],
            "itinerary": [],
            "estimated_duration": "1일",
            "operation_difficulty": "보통",
            "source_ids": ["doc_1"],
        }
    ]
    marketing_assets = [
        {
            "product_id": "product_1",
            "sales_copy": {"headline": "제목", "subheadline": "부제", "sections": [], "disclaimer": "확인"},
            "faq": [],
            "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
            "search_keywords": [],
            "claim_strategy": {
                "usable_claims": [
                    {"claim": "예약 즉시 확정되는 액티비티입니다.", "evidence_basis": "근거 없음"}
                ],
                "caution_phrasing": [{"phrase": "예약 즉시 확정", "reason": "예약 근거 없음"}],
            },
        }
    ]

    report = validate_qa_report(
        {"overall_status": "pass", "summary": "", "issues": []},
        products,
        docs=[{"doc_id": "doc_1"}],
        evidence_context={"unresolved_gaps": [{"gap_type": "missing_booking_info"}]},
        marketing_assets=marketing_assets,
    )

    issue = report["issues"][0]
    assert issue["type"] == "booking_claim"
    assert issue["field_path"] == "claim_strategy.usable_claims[0].claim"
    assert "활용 가능한 주장" in issue["message"]


def test_validate_qa_report_filters_source_metadata_noise_and_enriches_title_fix():
    products = [
        {"id": "product_1", "title": "광안리 야경 투어222222222"},
        {"id": "product_2", "title": "부산 해변 휴식"},
    ]
    payload = {
        "overall_status": "fail",
        "summary": "상품 정보에 일부 문제가 발견되었습니다.",
        "issues": [
            {
                "product_id": None,
                "severity": "medium",
                "type": "general",
                "message": "상품 '광안리 야경 투어222222222'의 제목에 불필요한 문자가 포함되어 있습니다.",
                "suggested_fix": "상품 제목에서 불필요한 문자를 제거해 주세요.",
            },
            {
                "product_id": None,
                "severity": "medium",
                "type": "general",
                "message": "상품 '부산 해변 휴식'의 '그랜드 조선 부산' 관련 근거 문서에 이벤트 기간 정보가 누락되었습니다.",
                "suggested_fix": "이벤트 기간 정보를 포함하여 근거 문서를 업데이트해 주세요.",
            },
            {
                "product_id": "product_1",
                "severity": "medium",
                "type": "general",
                "message": (
                    "FAQ 답변 필드에 '운영 시간은 현장 상황에 따라 변동될 수 있습니다.'라는 문구가 포함되어 있습니다. "
                    "이는 가격, 확정 일정, 예약 가능 여부, 안전 보장을 단정하지 말라는 규칙을 위반합니다."
                ),
                "suggested_fix": "FAQ 답변 필드를 수정하여 단정적인 표현을 제거하세요.",
            },
        ],
        "pass_count": 0,
        "needs_review_count": 2,
        "fail_count": 1,
    }

    report = validate_qa_report(payload, products)

    assert len(report["issues"]) == 1
    assert report["issues"][0]["product_id"] == "product_1"
    assert report["issues"][0]["suggested_fix"] == "상품 제목을 '광안리 야경 투어'로 수정하세요."


def test_validate_qa_report_resets_summary_and_counts_when_all_issues_are_filtered():
    products = [
        {"id": "product_1", "title": "광안리 M 드론 라이트쇼 야경 투어"},
        {"id": "product_2", "title": "해운대 야경과 미식 탐방"},
        {"id": "product_3", "title": "송도 해상 케이블카와 밤바다 감상"},
    ]
    payload = {
        "overall_status": "fail",
        "summary": "상품 3개에서 금지 표현이 발견되었습니다.",
        "issues": [
            {
                "product_id": "product_1",
                "severity": "medium",
                "type": "general",
                "message": "상품 설명에 '환상적인 드론 라이트쇼'라는 표현이 사용되었습니다.",
                "suggested_fix": "드론 라이트쇼의 운영 가능성을 언급하는 방향으로 수정하세요.",
            }
        ],
        "pass_count": 2,
        "needs_review_count": 0,
        "fail_count": 3,
    }

    report = validate_qa_report(payload, products)

    assert report == {
        "overall_status": "pass",
        "summary": "QA 검수 완료. 차단 수준의 이슈가 없습니다.",
        "issues": [],
        "pass_count": 3,
        "needs_review_count": 0,
        "fail_count": 0,
    }


def test_validate_qa_report_separates_internal_diagnostics_and_copy_quality():
    products = [{"id": "product_1", "title": "부산 야경 투어", "source_ids": ["doc_1"]}]
    payload = {
        "overall_status": "needs_review",
        "summary": "추가 확인이 필요합니다.",
        "issues": [
            {
                "product_id": "product_1",
                "severity": "medium",
                "type": "general",
                "message": "상품의 매력을 상세히 설명하고 고객의 이해를 돕기 위한 정보가 부족합니다.",
                "suggested_fix": "상품의 특징과 장점을 구체적으로 설명하세요.",
            },
            {
                "product_id": "product_1",
                "severity": "medium",
                "type": "missing_pet_policy",
                "message": "needs_review[2]의 missing_pet_policy 근거가 부족해 source_id 확인이 필요합니다.",
                "field_path": "needs_review[2]",
                "suggested_fix": "source_id를 다시 확인하세요.",
            },
            {
                "product_id": "product_1",
                "severity": "medium",
                "type": "general",
                "message": "FAQ 답변에 '운영 시간은 현장 상황에 따라 변동될 수 있습니다.'라는 문구가 포함되어 있습니다.",
                "suggested_fix": "FAQ 답변을 수정하세요.",
            },
            {
                "product_id": "product_1",
                "severity": "high",
                "type": "general",
                "message": "상세 설명에 문제 문구 '예약 즉시 확정'이 있습니다. 예약 가능 여부를 단정하고 있습니다.",
                "suggested_fix": "예약 가능 여부는 운영자 확인 필요 문구로 바꾸세요.",
            },
        ],
    }

    report = validate_qa_report(payload, products, docs=[{"doc_id": "doc_1"}])

    assert len(report["issues"]) == 1
    assert report["issues"][0]["type"] == "operational_uncertainty"
    assert "예약 즉시 확정" in report["issues"][0]["message"]
    assert "source_id" not in report["issues"][0]["message"]
    assert len(report["internal_diagnostics"]) == 1
    assert report["internal_diagnostics"][0]["type"] == "internal_diagnostic"


def test_targeted_revision_qa_report_only_tracks_selected_issue_status():
    selected_issues = [
        {
            "product_id": "product_1",
            "severity": "high",
            "type": "price_claim",
            "field_path": "sales_copy.sections[0].body",
            "message": "상세 설명에 문제 문구 '가격은 10,000원입니다'가 있습니다.",
            "suggested_fix": "가격은 운영자 확인 필요 문구로 바꾸세요.",
        },
        {
            "product_id": "product_1",
            "severity": "medium",
            "type": "booking_claim",
            "field_path": "faq[0].answer",
            "message": "FAQ 답변에 문제 문구 '예약 즉시 확정'이 있습니다.",
            "suggested_fix": "예약 가능 여부는 확인 필요 문구로 바꾸세요.",
        },
    ]
    qa_report = validate_targeted_revision_qa_report(
        {
            "summary": "선택된 QA 이슈만 재검수했습니다.",
            "items": [
                {"status": "resolved", "message": "가격 단정 표현이 사라졌습니다."},
                {
                    "status": "still_open",
                    "message": "FAQ 답변에 문제 문구 '예약 즉시 확정'이 아직 있습니다.",
                    "suggested_fix": "예약 가능 여부는 확인 필요 문구로 바꾸세요.",
                },
            ],
        },
        selected_issues,
        [{"id": "product_1", "title": "부산 야경 투어"}],
        source_output={
            "qa_report": {
                "issues": [
                    *selected_issues,
                    {
                        "product_id": "product_2",
                        "severity": "medium",
                        "type": "safety_claim",
                        "field_path": "sales_copy.sections[0].body",
                        "message": "상세 설명에 문제 문구 '100% 안전'이 있습니다.",
                        "suggested_fix": "절대적 안전 보장 표현을 완화하세요.",
                    },
                ]
            }
        },
    )

    assert qa_report["targeted_recheck"] is True
    assert len(qa_report["issues"]) == 2
    assert any(issue["type"] == "booking_claim" for issue in qa_report["issues"])
    assert any(issue.get("revision_carryover") is True for issue in qa_report["issues"])
    assert qa_report["revision_issue_results"][0]["status"] == "resolved"
    assert qa_report["revision_issue_results"][1]["status"] == "still_open"


def test_targeted_revision_qa_report_overrides_still_open_when_problem_quote_removed():
    selected_issues = [
        {
            "product_id": "product_1",
            "severity": "medium",
            "type": "source_missing",
            "field_path": "sales_copy.sections[0].body",
            "message": "상품 설명에 '문제 표현 A'라는 문구가 근거 문서에 명확히 확인되지 않는 주장으로 남아 있습니다.",
            "suggested_fix": "해당 문구를 삭제하는 것이 좋습니다.",
        }
    ]

    qa_report = validate_targeted_revision_qa_report(
        {
            "summary": "선택된 QA 이슈만 재검수했습니다.",
            "items": [
                {
                    "status": "still_open",
                    "message": "상품 설명에 '문제 표현 A'라는 문구가 여전히 남아 있습니다.",
                    "suggested_fix": "해당 문구를 삭제하세요.",
                }
            ],
        },
        selected_issues,
        [{"id": "product_1", "title": "테스트 상품"}],
        marketing_assets=[
            {
                "product_id": "product_1",
                "sales_copy": {
                    "headline": "테스트 상품 소개",
                    "subheadline": "문제가 제거된 설명",
                    "sections": [
                        {
                            "title": "수정된 상세 설명",
                            "body": "해당 표현을 제거한 새로운 상세 설명입니다.",
                        }
                    ],
                    "disclaimer": "운영 정보는 확인 후 안내합니다.",
                },
                "faq": [],
                "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
                "search_keywords": [],
            }
        ],
    )

    assert qa_report["issues"] == []
    assert qa_report["revision_issue_results"][0]["status"] == "resolved"
    assert qa_report["revision_issue_results"][0]["server_resolved_reason"] == "problem_quote_removed_from_target_field"


def test_targeted_revision_still_open_message_quotes_current_problem_text():
    selected_issues = [
        {
            "product_id": "product_1",
            "severity": "medium",
            "type": "source_missing",
            "field_path": "faq[0].answer",
            "message": "FAQ 답변에 '예약 없이 모든 체험에 참여할 수 있습니다.'라는 문구가 근거 문서에 명확히 확인되지 않는 주장으로 남아 있습니다.",
            "suggested_fix": "예약 필요 여부를 확인 필요 문구로 바꾸세요.",
        }
    ]

    qa_report = validate_targeted_revision_qa_report(
        {
            "summary": "선택된 QA 이슈만 재검수했습니다.",
            "items": [
                {
                    "status": "still_open",
                    "message": "체험 프로그램별 예약 필요 여부에 대한 정확한 정보 확인 후 답변을 수정해야 합니다.",
                    "suggested_fix": "모든 체험 프로그램의 예약 필요 여부에 대한 정확한 정보 확인 후 답변을 수정해야 합니다.",
                }
            ],
        },
        selected_issues,
        [{"id": "product_1", "title": "테스트 상품"}],
        marketing_assets=[
            {
                "product_id": "product_1",
                "sales_copy": {
                    "headline": "테스트 상품",
                    "subheadline": "테스트",
                    "sections": [],
                    "disclaimer": "운영 정보는 확인 후 안내합니다.",
                },
                "faq": [
                    {
                        "question": "예약이 필요한가요?",
                        "answer": "예약 없이 모든 체험에 참여할 수 있습니다.",
                    }
                ],
                "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
                "search_keywords": [],
            }
        ],
    )

    assert len(qa_report["issues"]) == 1
    assert "예약 없이 모든 체험에 참여할 수 있습니다." in qa_report["issues"][0]["message"]
    assert "FAQ 답변" in qa_report["issues"][0]["message"]


def test_targeted_revision_carryover_issue_quotes_current_problem_text():
    selected_issues = [
        {
            "product_id": "product_1",
            "severity": "medium",
            "type": "price_claim",
            "field_path": "sales_copy.sections[0].body",
            "message": "상세 설명에 문제 문구 '가격은 10,000원입니다.'가 있습니다.",
            "suggested_fix": "가격은 확인 필요 문구로 바꾸세요.",
        }
    ]
    carryover_issue = {
        "product_id": "product_1",
        "severity": "medium",
        "type": "source_missing",
        "field_path": "faq[0].answer",
        "message": "체험 프로그램별 예약 필요 여부에 대한 정확한 정보 확인 후 답변을 수정해야 합니다.",
        "suggested_fix": "모든 체험 프로그램의 예약 필요 여부에 대한 정확한 정보 확인 후 답변을 수정해야 합니다.",
    }

    qa_report = validate_targeted_revision_qa_report(
        {
            "summary": "선택된 QA 이슈만 재검수했습니다.",
            "items": [{"status": "resolved", "message": "가격 단정 표현이 사라졌습니다."}],
        },
        selected_issues,
        [{"id": "product_1", "title": "테스트 상품"}],
        marketing_assets=[
            {
                "product_id": "product_1",
                "sales_copy": {
                    "headline": "테스트 상품",
                    "subheadline": "테스트",
                    "sections": [{"title": "소개", "body": "가격은 운영자 확인 후 안내합니다."}],
                    "disclaimer": "운영 정보는 확인 후 안내합니다.",
                },
                "faq": [
                    {
                        "question": "예약이 필요한가요?",
                        "answer": "예약 없이 모든 체험에 참여할 수 있습니다.",
                    }
                ],
                "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
                "search_keywords": [],
            }
        ],
        source_output={"qa_report": {"issues": [selected_issues[0], carryover_issue]}},
    )

    assert len(qa_report["issues"]) == 1
    assert qa_report["issues"][0]["revision_carryover"] is True
    assert "예약 없이 모든 체험에 참여할 수 있습니다." in qa_report["issues"][0]["message"]
    assert "FAQ 답변" in qa_report["issues"][0]["message"]


def test_apply_revision_patch_only_applies_allowed_issue_field():
    products = [{"id": "product_1", "title": "부산 야경 투어", "one_liner": "원본 한 줄 설명"}]
    marketing_assets = [
        {
            "product_id": "product_1",
            "sales_copy": {
                "headline": "원본 헤드라인",
                "subheadline": "원본 보조 문구",
                "sections": [{"title": "소개", "body": "가격은 10,000원입니다."}],
                "disclaimer": "원본 유의 문구",
            },
            "faq": [{"question": "예약은요?", "answer": "예약 즉시 확정됩니다."}],
            "sns_campaign": {
                "campaign_angles": [{"angle": "원본 SNS", "rationale": "원본 SNS 각도"}],
                "posts": [{"format": "feed", "hook": "원본 SNS", "body": "원본 SNS", "hashtags": ["#부산"]}],
                "visual_direction": ["원본 장면"],
            },
            "search_keywords": ["부산"],
        }
    ]

    patched_products, patched_assets = apply_revision_patch(
        {
            "product_patches": [
                {"product_id": "product_1", "fields": {"one_liner": "바뀌면 안 되는 한 줄 설명"}}
            ],
            "marketing_patches": [
                {
                    "product_id": "product_1",
                    "sales_copy": {
                        "headline": "바뀌면 안 되는 헤드라인",
                        "sections": [{"index": 0, "body": "가격은 운영자 확인 후 안내합니다."}],
                    },
                    "faq": [{"index": 0, "answer": "바뀌면 안 되는 FAQ"}],
                }
            ],
        },
        products,
        marketing_assets,
        allowed_patch_scope={"product_1": {"sales_copy.sections[0].body"}},
    )

    assert patched_products[0]["one_liner"] == "원본 한 줄 설명"
    assert patched_assets[0]["sales_copy"]["headline"] == "원본 헤드라인"
    assert patched_assets[0]["sales_copy"]["sections"][0]["body"] == "가격은 운영자 확인 후 안내합니다."
    assert patched_assets[0]["faq"][0]["answer"] == "예약 즉시 확정됩니다."




def test_apply_revision_patch_updates_allowed_marketing_strategy_field_only():
    products = [{"id": "product_1", "title": "부산 야경 투어", "one_liner": "원본"}]
    marketing_assets = [
        {
            "product_id": "product_1",
            "sales_copy": {"headline": "원본", "subheadline": "원본", "sections": [], "disclaimer": "원본"},
            "faq": [],
            "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
            "search_keywords": [],
            "faq_strategy": {
                "operation_faq": [{"question": "운영시간은요?", "answer": "방문 전 확인하세요."}]
            },
            "claim_strategy": {
                "usable_claims": [{"claim": "광안리 야경 산책을 소개할 수 있습니다.", "evidence_basis": "근거 있음"}],
                "caution_phrasing": [],
            },
        }
    ]

    _, patched_assets = apply_revision_patch(
        {
            "marketing_field_patches": [
                {
                    "product_id": "product_1",
                    "field_path": "faq_strategy.operation_faq[0].answer",
                    "value": "근거에 있는 행사 날짜는 본문에 쓰고, 운영시간은 게시 전 확인하도록 안내합니다.",
                },
                {
                    "product_id": "product_1",
                    "field_path": "claim_strategy.needs_confirmation[0].claim",
                    "value": "생성되면 안 되는 필드",
                },
            ]
        },
        products,
        marketing_assets,
        allowed_patch_scope={"product_1": {"faq_strategy.operation_faq[0].answer", "claim_strategy.needs_confirmation[0].claim"}},
    )

    assert patched_assets[0]["faq_strategy"]["operation_faq"][0]["answer"].startswith("근거에 있는 행사 날짜")
    assert "needs_confirmation" not in patched_assets[0]["claim_strategy"]


def test_ai_revision_change_review_tracks_strategy_pack_field_paths():
    source_output = {
        "products": [{"id": "product_1", "title": "상품", "one_liner": "소개"}],
        "marketing_assets": [
            {
                "product_id": "product_1",
                "sales_copy": {"headline": "제목", "subheadline": "부제", "sections": [], "disclaimer": "확인"},
                "faq": [],
                "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
                "search_keywords": [],
                "faq_strategy": {"operation_faq": [{"question": "운영시간은요?", "answer": "방문 전 확인하세요."}]},
            }
        ],
    }
    selected_issue = {
        "product_id": "product_1",
        "type": "operational_uncertainty",
        "severity": "medium",
        "field_path": "faq_strategy.operation_faq[0].answer",
        "message": "FAQ 답변에 문제 문구 '방문 전 확인하세요.'가 있습니다.",
        "suggested_fix": "근거 기반으로 답변하세요.",
    }

    review = _build_ai_revision_change_review(
        {"source_final_output": source_output, "qa_issues": [selected_issue]},
        {
            "product_ideas": source_output["products"],
            "marketing_assets": [
                {
                    "product_id": "product_1",
                    "sales_copy": {"headline": "제목", "subheadline": "부제", "sections": [], "disclaimer": "확인"},
                    "faq": [],
                    "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
                    "search_keywords": [],
                    "faq_strategy": {"operation_faq": [{"question": "운영시간은요?", "answer": "행사 날짜는 근거에 맞춰 안내하고 운영시간은 확인을 요청합니다."}]},
                }
            ],
        },
        "llm_partial_rewrite",
    )

    assert review["enabled"] is True
    assert review["pending_count"] == 1
    assert review["items"][0]["field_path"] == "faq_strategy.operation_faq[0].answer"
    assert review["items"][0]["field_label"] == "운영 확인 FAQ 답변"
    assert review["items"][0]["qa_issue"]["message"] == selected_issue["message"]


def test_revision_source_stability_preserves_parent_source_fields():
    source_products = [
        {
            "id": "product_1",
            "title": "원본 상품",
            "one_liner": "원본 설명",
            "source_ids": ["doc:tourapi:content:1"],
            "evidence_summary": "원본 근거 요약",
            "itinerary": [{"order": 1, "name": "원본 일정", "source_id": "doc:tourapi:content:1"}],
        }
    ]
    edited_products = [
        {
            "id": "product_1",
            "title": "수정 상품",
            "one_liner": "수정 설명",
            "source_ids": ["doc:invalid"],
            "evidence_summary": "수정하면 안 되는 근거 요약",
            "itinerary": [{"order": 1, "name": "수정 일정", "source_id": "doc:invalid"}],
        }
    ]

    products, source_stability = _preserve_revision_source_state(
        {"source_final_output": {"products": source_products}},
        edited_products,
        mode="manual_edit",
    )

    assert products[0]["title"] == "수정 상품"
    assert products[0]["one_liner"] == "수정 설명"
    assert products[0]["source_ids"] == ["doc:tourapi:content:1"]
    assert products[0]["evidence_summary"] == "원본 근거 요약"
    assert products[0]["itinerary"][0]["name"] == "수정 일정"
    assert products[0]["itinerary"][0]["source_id"] == "doc:tourapi:content:1"
    assert source_stability["source_stability_mode"] == "preserve_parent_sources_after_manual_edit"
    assert source_stability["evidence_recomputed"] is False
    assert "products[product_1].source_ids" in source_stability["source_fields_changed"]


def test_ai_revision_change_review_tracks_changed_fields_and_related_issue():
    source_output = {
        "products": [{"id": "product_1", "title": "이전 상품명", "one_liner": "이전 소개"}],
        "marketing_assets": [
            {
                "product_id": "product_1",
                "sales_copy": {
                    "headline": "이전 제목",
                    "subheadline": "이전 부제목",
                    "sections": [{"title": "소개", "body": "이전 본문"}],
                    "disclaimer": "확인 후 안내합니다.",
                },
                "faq": [],
                "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
                "search_keywords": [],
            }
        ],
    }
    selected_issue = {
        "product_id": "product_1",
        "type": "source_missing",
        "severity": "medium",
        "field_path": "sales_copy.sections[0].body",
        "message": "상세 설명에 문제 문구 '이전 본문'이 있습니다.",
        "suggested_fix": "상세 설명을 수정하세요.",
    }

    review = _build_ai_revision_change_review(
        {"source_final_output": source_output, "qa_issues": [selected_issue]},
        {
            "product_ideas": [{"id": "product_1", "title": "이전 상품명", "one_liner": "이전 소개"}],
            "marketing_assets": [
                {
                    "product_id": "product_1",
                    "sales_copy": {
                        "headline": "이전 제목",
                        "subheadline": "이전 부제목",
                        "sections": [{"title": "소개", "body": "수정 본문"}],
                        "disclaimer": "확인 후 안내합니다.",
                    },
                    "faq": [],
                    "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
                    "search_keywords": [],
                }
            ],
        },
        "llm_partial_rewrite",
    )

    assert review["enabled"] is True
    assert review["pending_count"] == 1
    assert review["items"][0]["field_path"] == "sales_copy.sections[0].body"
    assert review["items"][0]["before"] == "이전 본문"
    assert review["items"][0]["after"] == "수정 본문"
    assert review["items"][0]["qa_issue"]["message"] == selected_issue["message"]


def test_targeted_revision_diff_counts_resolved_selected_and_unselected_carryover():
    selected_issues = [
        {
            "product_id": "product_1",
            "severity": "medium",
            "type": "price_claim",
            "field_path": "sales_copy.sections[0].body",
            "message": f"선택 이슈 {index}",
            "suggested_fix": "수정",
        }
        for index in range(3)
    ]
    carryover_issues = [
        {
            "product_id": "product_1",
            "severity": "medium",
            "type": "booking_claim",
            "field_path": f"faq[{index}].answer",
            "message": f"미선택 이슈 {index}",
            "suggested_fix": "유지",
            "revision_carryover": True,
        }
        for index in range(3)
    ]

    diff = _build_targeted_revision_qa_diff_summary(
        selected_issues,
        {
            "targeted_recheck": True,
            "issues": carryover_issues,
            "revision_issue_results": [
                {"status": "resolved"},
                {"status": "resolved"},
                {"status": "resolved"},
            ],
        },
        revision_mode="llm_partial_rewrite",
    )

    assert diff["counts"]["resolved"] == 3
    assert diff["counts"]["still_open"] == 3


def test_delete_run_qa_issues_updates_report(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "부산 외국인 액티비티 검토",
            "region": "부산",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 1,
            "preferences": ["야간 관광"],
            "avoid": ["가격 단정 표현"],
        },
    }

    with TestClient(app) as client:
        created = unwrap(client.post("/api/workflow-runs", json=payload))

    with SessionLocal() as db:
        run = db.get(models.WorkflowRun, created["id"])
        final_output = dict(run.final_output)
        final_output["qa_report"] = {
            "overall_status": "needs_review",
            "summary": "QA 이슈 2건이 발견되었습니다.",
            "issues": [
                {
                    "product_id": "product_1",
                    "severity": "medium",
                    "type": "general",
                    "message": "삭제할 리뷰입니다.",
                    "suggested_fix": "삭제 확인",
                },
                {
                    "product_id": "product_1",
                    "severity": "medium",
                    "type": "price_claim",
                    "message": "남길 리뷰입니다.",
                    "suggested_fix": "가격 단정 표현을 완화하세요.",
                },
            ],
            "pass_count": 0,
            "needs_review_count": 2,
            "fail_count": 0,
        }
        run.final_output = final_output
        db.commit()

    with TestClient(app) as client:
        deleted = unwrap(
            client.post(
                f"/api/workflow-runs/{created['id']}/qa-issues/delete",
                json={"issue_indices": [0]},
            )
        )
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))

    assert deleted["removed_count"] == 1
    assert len(result["qa_report"]["issues"]) == 1
    assert result["qa_report"]["issues"][0]["message"] == "남길 리뷰입니다."
    assert len(result["qa_report"]["dismissed_issues"]) == 1


def test_ai_revision_change_decisions_accept_or_revert_without_new_revision():
    final_output = {
        "status": "awaiting_approval",
        "products": [{"id": "product_1", "title": "상품", "source_ids": []}],
        "marketing_assets": [
            {
                "product_id": "product_1",
                "sales_copy": {
                    "headline": "수정된 제목",
                    "subheadline": "수정된 부제목",
                    "sections": [],
                    "disclaimer": "확인 후 안내합니다.",
                },
                "faq": [],
                "sns_campaign": {"campaign_angles": [], "posts": [], "visual_direction": []},
                "search_keywords": [],
            }
        ],
        "qa_report": {
            "overall_status": "pass",
            "summary": "선택한 QA 이슈가 해결되었습니다.",
            "issues": [],
            "pass_count": 1,
            "needs_review_count": 0,
            "fail_count": 0,
        },
        "revision": {
            "revision_mode": "llm_partial_rewrite",
            "change_review": {
                "enabled": True,
                "status": "pending",
                "pending_count": 2,
                "items": [
                    {
                        "id": "change_accept",
                        "entity": "marketing",
                        "product_id": "product_1",
                        "field_path": "sales_copy.headline",
                        "field_label": "홍보 제목",
                        "before": "이전 제목",
                        "after": "수정된 제목",
                        "status": "pending",
                        "qa_issue": {
                            "product_id": "product_1",
                            "severity": "medium",
                            "type": "source_missing",
                            "message": "홍보 제목에 문제 문구 '이전 제목'이 있습니다.",
                            "suggested_fix": "홍보 제목을 수정하세요.",
                        },
                    },
                    {
                        "id": "change_revert",
                        "entity": "marketing",
                        "product_id": "product_1",
                        "field_path": "sales_copy.subheadline",
                        "field_label": "홍보 부제목",
                        "before": "이전 부제목",
                        "after": "수정된 부제목",
                        "status": "pending",
                        "qa_issue": {
                            "product_id": "product_1",
                            "severity": "medium",
                            "type": "unsupported_claim",
                            "message": "홍보 부제목에 문제 문구 '이전 부제목'이 있습니다.",
                            "suggested_fix": "홍보 부제목을 수정하세요.",
                        },
                    },
                ],
            },
        },
    }

    with SessionLocal() as db:
        run = models.WorkflowRun(
            template_id="default_product_planning",
            parent_run_id="run_parent_change_review",
            revision_number=1,
            revision_mode="llm_partial_rewrite",
            status="awaiting_approval",
            input={"message": "테스트"},
            final_output=final_output,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id

    with TestClient(app) as client:
        response = unwrap(
            client.post(
                f"/api/workflow-runs/{run_id}/revision-changes/decide",
                json={
                    "decisions": [
                        {"change_id": "change_accept", "action": "accept"},
                        {"change_id": "change_revert", "action": "revert"},
                    ]
                },
            )
        )
        result = unwrap(client.get(f"/api/workflow-runs/{run_id}/result"))
        fetched_run = unwrap(client.get(f"/api/workflow-runs/{run_id}"))

    asset = result["marketing_assets"][0]
    assert asset["sales_copy"]["headline"] == "수정된 제목"
    assert asset["sales_copy"]["subheadline"] == "이전 부제목"
    statuses = {
        item["id"]: item["status"]
        for item in result["revision"]["change_review"]["items"]
    }
    assert statuses == {"change_accept": "accepted", "change_revert": "reverted"}
    assert result["revision"]["change_review"]["pending_count"] == 0
    assert len(result["qa_report"]["issues"]) == 1
    assert result["qa_report"]["issues"][0]["message"] == "홍보 부제목에 문제 문구 '이전 부제목'이 있습니다."
    assert fetched_run["revision_number"] == 1
    assert response["run"]["id"] == run_id


def test_gemini_high_demand_response_is_retryable():
    response = httpx.Response(
        503,
        json={
            "error": {
                "message": "This model is currently experiencing high demand. Please try again later."
            }
        },
    )

    assert _is_retryable_response(response)


def test_gemini_retry_delay_respects_retry_after_header():
    settings = get_settings()
    response = httpx.Response(503, headers={"retry-after": "2"})

    assert _retry_delay_seconds(attempt=0, response=response, settings=settings) == 2


def test_gemini_retry_settings_are_configurable():
    settings = Settings(
        gemini_max_retries=5,
        gemini_retry_base_seconds=2,
        gemini_retry_max_seconds=30,
    )

    assert settings.gemini_max_retries == 5
    assert _retry_delay_seconds(attempt=4, response=None, settings=settings) <= 30


def test_tourapi_request_retries_read_timeout(monkeypatch):
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ReadTimeout("read timed out")
        return httpx.Response(
            200,
            json={"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": []}}}},
            request=httpx.Request("GET", "https://example.com/areaBasedList2"),
        )

    monkeypatch.setattr("app.tools.tourism.httpx.get", fake_get)
    monkeypatch.setattr("app.tools.tourism.time.sleep", lambda *_: None)
    settings = Settings(
        tourapi_service_key="test-key",
        tourapi_timeout_seconds=1,
        tourapi_max_retries=1,
        tourapi_retry_base_seconds=0.1,
        tourapi_retry_max_seconds=0.1,
    )

    response = _get_with_retries(
        url="https://example.com/areaBasedList2",
        params={"serviceKey": "test-key"},
        settings=settings,
        operation="areaBasedList2",
    )

    assert response.status_code == 200
    assert calls["count"] == 2


def test_parse_json_uses_first_object_when_gemini_appends_extra_json():
    payload = _parse_json('{"products": []}\n{"ignored": true}')

    assert payload == {"products": []}


def test_approval_actions_update_run_status_and_history(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    base_payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "부산 외국인 액티비티 검토",
            "region": "부산",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 2,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        approve_run = unwrap(client.post("/api/workflow-runs", json=base_payload))
        approved = unwrap(
            client.post(
                f"/api/workflow-runs/{approve_run['id']}/approve",
                json={"reviewer": "ops", "comment": "Looks ready"},
            )
        )
        approve_history = unwrap(client.get(f"/api/workflow-runs/{approve_run['id']}/approvals"))

        changes_run = unwrap(client.post("/api/workflow-runs", json=base_payload))
        changes = unwrap(
            client.post(
                f"/api/workflow-runs/{changes_run['id']}/request-changes",
                json={
                    "reviewer": "ops",
                    "comment": "Need clearer meeting point",
                    "requested_changes": ["집결지 보강"],
                },
            )
        )
        changes_result = unwrap(client.get(f"/api/workflow-runs/{changes_run['id']}/result"))

        manual_products = [dict(product) for product in changes_result["products"]]
        manual_marketing_assets = [dict(asset) for asset in changes_result["marketing_assets"]]
        original_source_ids = list(manual_products[0].get("source_ids") or [])
        manual_products[0]["one_liner"] = "운영자가 직접 수정한 설명입니다."
        manual_products[0]["source_ids"] = ["doc:invalid-manual-edit"]
        manual_revision = unwrap(
            client.post(
                f"/api/workflow-runs/{changes_run['id']}/revisions",
                json={
                    "revision_mode": "manual_edit",
                    "comment": "직접 수정 후 QA 재검수",
                    "requested_changes": ["집결지 보강"],
                    "products": manual_products,
                    "marketing_assets": manual_marketing_assets,
                },
            )
        )
        manual_revision_run = unwrap(client.get(f"/api/workflow-runs/{manual_revision['id']}"))
        manual_revision_result = unwrap(client.get(f"/api/workflow-runs/{manual_revision['id']}/result"))
        manual_revision_steps = unwrap(client.get(f"/api/workflow-runs/{manual_revision['id']}/steps"))

        saved_revision = unwrap(
            client.post(
                f"/api/workflow-runs/{changes_run['id']}/revisions",
                json={
                    "revision_mode": "manual_save",
                    "comment": "QA 없이 저장",
                    "products": manual_products,
                    "marketing_assets": manual_marketing_assets,
                },
            )
        )
        saved_revision_run = unwrap(client.get(f"/api/workflow-runs/{saved_revision['id']}"))
        saved_revision_steps = unwrap(client.get(f"/api/workflow-runs/{saved_revision['id']}/steps"))

        rewrite_revision = unwrap(
            client.post(
                f"/api/workflow-runs/{manual_revision['id']}/revisions",
                json={
                    "revision_mode": "llm_partial_rewrite",
                    "comment": "수정 요청 반영",
                    "requested_changes": ["과장 표현 완화", "집결지 안내 보강"],
                    "qa_issues": [
                        {
                            "product_id": manual_products[0]["id"],
                            "severity": "medium",
                            "type": "general",
                            "message": "선택한 QA 이슈",
                            "suggested_fix": "필요한 필드만 수정",
                        }
                    ],
                },
            )
        )
        rewrite_revision_run = unwrap(client.get(f"/api/workflow-runs/{rewrite_revision['id']}"))
        rewrite_revision_result = unwrap(client.get(f"/api/workflow-runs/{rewrite_revision['id']}/result"))
        rewrite_revision_steps = unwrap(client.get(f"/api/workflow-runs/{rewrite_revision['id']}/steps"))

        qa_revision = unwrap(
            client.post(
                f"/api/workflow-runs/{changes_run['id']}/revisions",
                json={"revision_mode": "qa_only", "requested_changes": ["QA만 다시 실행"]},
            )
        )
        qa_revision_run = unwrap(client.get(f"/api/workflow-runs/{qa_revision['id']}"))
        qa_revision_steps = unwrap(client.get(f"/api/workflow-runs/{qa_revision['id']}/steps"))

        reject_run = unwrap(client.post("/api/workflow-runs", json=base_payload))
        rejected = unwrap(
            client.post(
                f"/api/workflow-runs/{reject_run['id']}/reject",
                json={"reviewer": "ops", "comment": "Not viable"},
            )
        )

    assert approved["run"]["status"] == "approved"
    assert approved["approval"]["decision"] == "approve"
    assert approve_history[0]["decision"] == "approve"
    assert changes["run"]["status"] == "changes_requested"
    assert changes["approval"]["approval_metadata"]["requested_changes"] == ["집결지 보강"]
    assert manual_revision_run["status"] == "awaiting_approval"
    assert manual_revision_run["parent_run_id"] == changes_run["id"]
    assert manual_revision_run["revision_number"] == 1
    assert manual_revision_run["revision_mode"] == "manual_edit"
    assert manual_revision_result["products"][0]["one_liner"] == "운영자가 직접 수정한 설명입니다."
    assert manual_revision_result["products"][0]["source_ids"] == original_source_ids
    assert manual_revision_result["revision"]["source_run_id"] == changes_run["id"]
    assert manual_revision_result["revision"]["qa_recheck_mode"] == "qa_only_recheck"
    assert manual_revision_result["revision"]["source_stability"]["source_stability_mode"] == "preserve_parent_sources_after_manual_edit"
    assert manual_revision_result["revision"]["source_stability"]["evidence_recomputed"] is False
    assert "qa_diff_summary" in manual_revision_result["revision"]
    assert manual_revision_result["revision"]["approval_history"][0]["decision"] == "request_changes"
    assert {step["agent_name"] for step in manual_revision_steps} >= {
        "RevisionContextAgent",
        "QAComplianceAgent",
        "HumanApprovalNode",
    }
    assert "ProductAgent" not in {step["agent_name"] for step in manual_revision_steps}
    assert "MarketingAgent" not in {step["agent_name"] for step in manual_revision_steps}
    assert saved_revision_run["status"] == "awaiting_approval"
    assert saved_revision_run["parent_run_id"] == changes_run["id"]
    assert saved_revision_run["revision_number"] == 2
    assert saved_revision_run["revision_mode"] == "manual_save"
    assert {step["agent_name"] for step in saved_revision_steps} >= {
        "RevisionContextAgent",
        "HumanApprovalNode",
    }
    assert "QAComplianceAgent" not in {step["agent_name"] for step in saved_revision_steps}
    assert rewrite_revision_run["status"] == "awaiting_approval"
    assert rewrite_revision_run["parent_run_id"] == changes_run["id"]
    assert rewrite_revision_run["revision_number"] == 3
    assert rewrite_revision_run["revision_mode"] == "llm_partial_rewrite"
    assert len(rewrite_revision_result["products"]) >= 2
    assert rewrite_revision_result["revision"]["qa_recheck_mode"] == "ai_partial_rewrite_recheck"
    assert rewrite_revision_result["revision"]["source_stability"]["source_stability_mode"] == "preserve_parent_sources_after_ai_patch"
    assert rewrite_revision_result["revision"]["source_stability"]["evidence_recomputed"] is False
    assert "qa_diff_summary" in rewrite_revision_result["revision"]
    assert {step["agent_name"] for step in rewrite_revision_steps} >= {
        "RevisionContextAgent",
        "RevisionPatchAgent",
        "QAComplianceAgent",
        "HumanApprovalNode",
    }
    assert "ProductAgent" not in {step["agent_name"] for step in rewrite_revision_steps}
    assert "MarketingAgent" not in {step["agent_name"] for step in rewrite_revision_steps}
    assert qa_revision_run["status"] == "awaiting_approval"
    assert qa_revision_run["parent_run_id"] == changes_run["id"]
    assert qa_revision_run["revision_number"] == 4
    qa_revision_result = unwrap(client.get(f"/api/workflow-runs/{qa_revision['id']}/result"))
    assert qa_revision_result["products"][0]["source_ids"] == changes_result["products"][0]["source_ids"]
    assert qa_revision_result["revision"]["source_stability"]["source_stability_mode"] == "preserve_parent_sources_for_qa_only"
    assert qa_revision_result["revision"]["source_stability"]["evidence_recomputed"] is False
    assert "ProductAgent" not in {step["agent_name"] for step in qa_revision_steps}
    assert "MarketingAgent" not in {step["agent_name"] for step in qa_revision_steps}
    assert rejected["run"]["status"] == "rejected"
    assert rejected["approval"]["decision"] == "reject"


def test_llm_key_check_reports_missing_keys_in_test_env():
    with TestClient(app) as client:
        data = unwrap(client.post("/api/llm/key-check", json={}))

    assert data["total_estimated_cost_usd"] == 0
    assert {result["status"] for result in data["results"]} == {"failed"}


def test_gemini_mode_fails_and_logs_when_key_missing(monkeypatch):
    use_test_tourapi_provider(monkeypatch, fake_gemini=False)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()

    payload = {
        "template_id": "default_product_planning",
        "input": {
            "message": "부산 외국인 액티비티 검토",
            "region": "부산",
            "period": "2026-05",
            "target_customer": "외국인",
            "product_count": 1,
            "preferences": ["야간 관광"],
        },
    }

    with TestClient(app) as client:
        response = client.post("/api/workflow-runs", json=payload)
        body = response.json()
        assert response.status_code == 200
        assert body["error"] is None
        run_id = body["data"]["id"]
        run = unwrap(client.get(f"/api/workflow-runs/{run_id}"))
        steps = unwrap(client.get(f"/api/workflow-runs/{run_id}/steps"))
        llm_calls = unwrap(client.get(f"/api/workflow-runs/{run_id}/llm-calls"))

    get_settings.cache_clear()

    assert body["data"]["status"] == "pending"
    assert run["status"] == "failed"
    assert run["error"]["message"] == "GEMINI_API_KEY is not configured"
    assert any(step["agent_name"] == "PlannerAgent" and step["status"] == "failed" for step in steps)
    assert any(call["provider"] == "gemini" and call["purpose"] == "planner_failed" for call in llm_calls)
