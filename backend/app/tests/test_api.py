import json

from fastapi.testclient import TestClient
import pytest
import httpx
from sqlalchemy import inspect

from app.agents.workflow import (
    _filter_items_by_geo_scope,
    _filter_retrieved_documents_by_geo_scope,
    validate_qa_report,
)
from app.core.config import Settings, get_settings
from app.db import models
from app.db.session import SessionLocal, engine, init_db
from app.llm.gemini_gateway import (
    GeminiGatewayError,
    call_gemini_json,
    _is_retryable_response,
    _parse_json,
    _retry_delay_seconds,
    _validate_json_schema,
)
from app.main import app
from app.rag.source_documents import build_source_document
from app.tests.geo_catalog_helpers import seed_test_ldong_catalog
from app.tools.tourism import TourismItem


def unwrap(response):
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    return body["data"]


def require_tourapi_key():
    if not get_settings().tourapi_service_key:
        pytest.skip("TOURAPI_SERVICE_KEY is required for workflow tests")


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


def use_test_tourapi_provider(monkeypatch):
    init_db()
    with SessionLocal() as db:
        seed_test_ldong_catalog(db)
    monkeypatch.setattr(
        "app.agents.workflow.get_tourism_provider",
        lambda: TestTourApiProvider(),
    )
    monkeypatch.setattr(
        "app.api.routes_data.get_tourism_provider",
        lambda: TestTourApiProvider(),
    )


def use_daejeon_tourapi_provider(monkeypatch):
    init_db()
    with SessionLocal() as db:
        seed_test_ldong_catalog(db)
    monkeypatch.setattr(
        "app.agents.workflow.get_tourism_provider",
        lambda: DaejeonTourApiProvider(),
    )
    monkeypatch.setattr(
        "app.api.routes_data.get_tourism_provider",
        lambda: DaejeonTourApiProvider(),
    )


def use_empty_tourapi_provider(monkeypatch):
    init_db()
    with SessionLocal() as db:
        seed_test_ldong_catalog(db)
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
    assert 1 <= len(result["products"]) <= 5
    if len(result["products"]) < 5:
        assert any(
            "사용 가능한 근거 데이터가" in note
            for note in result["products"][0].get("coverage_notes", [])
        )
    assert {step["agent_name"] for step in steps} >= {
        "PlannerAgent",
        "GeoResolverAgent",
        "BaselineDataAgent",
        "DataGapProfilerAgent",
        "ApiCapabilityRouterAgent",
        "TourApiDetailPlannerAgent",
        "EnrichmentExecutor",
        "EvidenceFusionAgent",
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
    assert enrichment["latest"]["status"] == "completed"
    assert result["evidence_profile"]["entities"]
    assert result["data_coverage"]["total_items"] >= 1
    assert len(llm_calls) >= 5
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
    assert all(
        call["arguments"].get("ldong_regn_cd") == "26"
        for call in tool_calls
        if call["tool_name"].startswith("tourapi_")
    )


def test_workflow_returns_insufficient_source_data_when_vector_search_is_empty(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
    monkeypatch.setattr("app.agents.workflow.search_source_documents", lambda **kwargs: [])
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

    monkeypatch.setattr("app.agents.workflow.search_source_documents", fail_search)
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
    assert len(result["geo_scope"]["candidates"]) >= 2
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
    assert result["user_message"]["title"] == "단일 지역만 지원합니다"
    assert result["geo_scope"]["mode"] == "unsupported_multi_region"
    assert result["geo_scope"]["needs_clarification"] is True
    assert len(result["geo_scope"]["candidates"]) >= 2
    assert any(step["step_type"] == "geo_scope_exit" for step in steps)
    assert all(not call["tool_name"].startswith("tourapi_search") for call in tool_calls)


def test_workflow_blocks_foreign_destination_before_tourapi_search(monkeypatch):
    use_test_tourapi_provider(monkeypatch)
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
    assert any(step["step_type"] == "geo_scope_exit" for step in steps)
    assert all(not call["tool_name"].startswith("tourapi_search") for call in tool_calls)


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
    assert any(step["agent_name"] == "PlannerAgent" and step["status"] == "failed" for step in steps)
    assert any(call["provider"] == "gemini" and call["purpose"] == "planner_failed" for call in llm_calls)
