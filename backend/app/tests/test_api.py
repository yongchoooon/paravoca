from fastapi.testclient import TestClient
import pytest
import httpx

from app.agents.workflow import validate_qa_report
from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal
from app.llm.gemini_gateway import _is_retryable_response, _parse_json, _retry_delay_seconds
from app.main import app
from app.tools.tourism import TourismItem


def unwrap(response):
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    return body["data"]


def require_tourapi_key():
    if not get_settings().tourapi_service_key:
        pytest.skip("TOURAPI_SERVICE_KEY is required for workflow tests")


class TestTourApiProvider:
    def area_code(self, region=None):
        return [{"code": "6", "name": "부산"}]

    def area_based_list(self, *, region_code=None, content_type=None, keyword=None, limit=20):
        return self.search_keyword(query=keyword or "부산", region_code=region_code, limit=limit)

    def search_keyword(self, *, query, region_code=None, limit=20):
        return [
            TourismItem(
                id="tourapi:test:busan:night-market",
                source="tourapi",
                content_id="TEST-BUSAN-001",
                content_type="attraction",
                title="부산 전통시장 야간 먹거리 골목",
                region_code=region_code or "6",
                sigungu_code="16",
                address="부산광역시 중구",
                overview="야간 시간대 외국인 대상 먹거리 동선으로 검토할 수 있는 시장 후보입니다.",
                license_type="TourAPI test response",
            )
        ][:limit]

    def search_festival(self, *, region_code=None, start_date=None, end_date=None, limit=20):
        return [
            TourismItem(
                id="tourapi:test:busan:drone-show",
                source="tourapi",
                content_id="TEST-BUSAN-002",
                content_type="event",
                title="광안리 M 드론 라이트쇼",
                region_code=region_code or "6",
                sigungu_code="12",
                address="부산광역시 수영구 광안해변로",
                overview="광안리 해변에서 진행되는 야간 드론 라이트쇼입니다.",
                event_start_date="20260501",
                event_end_date="20260531",
                license_type="TourAPI test response",
            )
        ][:limit]

    def search_stay(self, *, region_code=None, limit=20):
        return [
            TourismItem(
                id="tourapi:test:busan:hotel",
                source="tourapi",
                content_id="TEST-BUSAN-003",
                content_type="accommodation",
                title="그랜드 조선 부산",
                region_code=region_code or "6",
                sigungu_code="16",
                address="부산광역시 해운대구",
                overview="해운대 권역 숙박 후보입니다.",
                license_type="TourAPI test response",
            )
        ][:limit]


def use_test_tourapi_provider(monkeypatch):
    monkeypatch.setattr(
        "app.agents.workflow.get_tourism_provider",
        lambda: TestTourApiProvider(),
    )


def test_health():
    with TestClient(app) as client:
        data = unwrap(client.get("/api/health"))
    assert data["status"] == "ok"
    assert data["db"] == "ok"


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
        llm_calls = unwrap(client.get(f"/api/workflow-runs/{created['id']}/llm-calls"))
        result = unwrap(client.get(f"/api/workflow-runs/{created['id']}/result"))

    assert created["status"] == "pending"
    assert created["input"]["region"] == "부산"
    assert fetched["status"] == "awaiting_approval"
    assert fetched["final_output"]["status"] == "awaiting_approval"
    assert fetched["id"] == created["id"]
    assert len(result["products"]) == 5
    assert {step["agent_name"] for step in steps} >= {
        "PlannerAgent",
        "DataAgent",
        "ResearchAgent",
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
    assert len(llm_calls) >= 6


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
                "message": "상품의 'sales_copy.sections[0].body'에 가격 단정 표현이 있습니다.",
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
        manual_products[0]["one_liner"] = "운영자가 직접 수정한 설명입니다."
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
    assert manual_revision_result["revision"]["source_run_id"] == changes_run["id"]
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
    assert len(rewrite_revision_result["products"]) == 2
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
    assert "ProductAgent" not in {step["agent_name"] for step in qa_revision_steps}
    assert "MarketingAgent" not in {step["agent_name"] for step in qa_revision_steps}
    assert rejected["run"]["status"] == "rejected"
    assert rejected["approval"]["decision"] == "reject"


def test_llm_key_check_skips_missing_keys_in_test_env():
    with TestClient(app) as client:
        data = unwrap(client.post("/api/llm/key-check", json={}))

    assert data["total_estimated_cost_usd"] == 0
    assert {result["status"] for result in data["results"]} == {"skipped"}


def test_gemini_mode_fails_and_logs_when_key_missing(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    monkeypatch.setenv("LLM_ENABLED", "true")
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
    assert any(step["agent_name"] == "ProductAgent" and step["status"] == "failed" for step in steps)
    assert any(call["provider"] == "gemini" and call["purpose"] == "product_generation_failed" for call in llm_calls)
