from fastapi.testclient import TestClient

from app.agents.data_enrichment import (
    build_api_capability_router_prompt,
    build_data_gap_profile_prompt,
    build_evidence_fusion_prompt,
    build_tourapi_detail_planner_prompt,
    capability_brief_for_prompt,
    capability_matrix_for_prompt,
    create_enrichment_run,
    execute_enrichment_plan,
    fuse_evidence,
    normalize_tourapi_detail_planner_payload,
    profile_data_gaps,
    route_gap_plan,
)
from app.agents.workflow import (
    api_capability_router_agent,
    data_gap_profiler_agent,
    evidence_fusion_agent,
    route_signal_planner_agent,
    theme_data_planner_agent,
    tourapi_detail_planner_agent,
    visual_data_planner_agent,
)
from app.core.config import Settings, get_settings
from app.db import models
from app.db.session import SessionLocal
from app.llm.gemini_gateway import GeminiJsonResult
from app.main import app


class DetailProvider:
    def detail_common(self, *, content_id):
        return {
            "contentid": content_id,
            "contenttypeid": "12",
            "title": "대전 중앙시장 야간 미식 투어",
            "areacode": "3",
            "sigungucode": "1",
            "lDongRegnCd": "30",
            "lDongSignguCd": "140",
            "addr1": "대전광역시 중구",
            "addr2": "중앙로",
            "mapx": "127.4",
            "mapy": "36.3",
            "tel": "042-000-0000",
            "homepage": "https://example.com",
            "overview": "대전 중앙시장 야간 미식 투어 상세 개요입니다.",
            "firstimage": f"https://example.com/{content_id}.jpg",
        }

    def detail_intro(self, *, content_id, content_type_id):
        return {
            "contentid": content_id,
            "contenttypeid": content_type_id,
            "usetime": "운영시간은 공식 안내 확인 필요",
            "usefee": "요금은 운영자 확인 필요",
            "reservation": "예약 조건은 운영자 확인 필요",
        }

    def detail_info(self, *, content_id, content_type_id):
        return [
            {"infoname": "이용시간", "infotext": "운영시간은 공식 안내 확인 필요"},
            {"infoname": "이용요금", "infotext": "요금은 운영자 확인 필요"},
            {"infoname": "예약안내", "infotext": "예약 조건은 운영자 확인 필요"},
        ]

    def detail_images(self, *, content_id):
        return [
            {
                "serialnum": "1",
                "imgname": "야간 미식 투어 이미지",
                "originimgurl": f"https://example.com/{content_id}-detail.jpg",
                "smallimageurl": f"https://example.com/{content_id}-thumb.jpg",
            }
        ]


class FailingDetailProvider(DetailProvider):
    def detail_common(self, *, content_id):
        raise RuntimeError("detailCommon2 unavailable")


def test_gap_profiler_detects_missing_image_and_operating_fields():
    item = {
        "id": "tourapi:test:gap:item",
        "source": "tourapi",
        "content_id": "TEST-GAP-001",
        "content_type": "attraction",
        "title": "이미지 없는 관광지",
        "region_code": "3",
        "overview": "기본 개요만 있습니다.",
        "raw": {},
    }

    report = profile_data_gaps(source_items=[item])
    gap_types = {gap["gap_type"] for gap in report["gaps"]}

    assert "missing_image_asset" in gap_types
    assert "missing_operating_hours" in gap_types
    assert "missing_price_or_fee" in gap_types
    assert "missing_booking_info" in gap_types


def test_gap_profiler_skips_unnecessary_gaps_when_detail_is_sufficient():
    item = {
        "id": "tourapi:test:complete:item",
        "source": "tourapi",
        "content_id": "TEST-COMPLETE-001",
        "content_type": "attraction",
        "title": "상세정보 있는 관광지",
        "region_code": "3",
        "image_url": "https://example.com/complete.jpg",
        "overview": "예약과 요금 안내가 포함된 관광지입니다.",
        "raw": {
            "detail_info": [
                {"infoname": "이용시간", "infotext": "10:00-18:00"},
                {"infoname": "이용요금", "infotext": "현장 확인 필요"},
                {"infoname": "예약안내", "infotext": "사전 예약 권장"},
            ]
        },
    }

    report = profile_data_gaps(source_items=[item])
    gap_types = {gap["gap_type"] for gap in report["gaps"]}

    assert "missing_detail_info" not in gap_types
    assert "missing_image_asset" not in gap_types
    assert "missing_operating_hours" not in gap_types
    assert "missing_price_or_fee" not in gap_types
    assert "missing_booking_info" not in gap_types


def test_capability_router_maps_gaps_to_detail_calls_and_respects_budget():
    gaps = [
        {
            "id": f"gap:missing_detail_info:{index}",
            "gap_type": "missing_detail_info",
            "target_item_id": f"item-{index}",
            "target_content_id": f"content-{index}",
        }
        for index in range(3)
    ]

    plan = route_gap_plan(
        gap_report={"gaps": gaps},
        settings=Settings(tourapi_service_key="test-key"),
        max_call_budget=2,
    )

    assert len(plan["planned_calls"]) == 2
    assert len(plan["skipped_calls"]) == 1
    assert plan["planned_calls"][0]["tool_name"] == "kto_tour_detail_enrichment"
    assert plan["skipped_calls"][0]["skip_reason"] == "max_call_budget_exceeded"


def test_capability_router_excludes_medical_when_feature_flag_is_off():
    plan = route_gap_plan(
        gap_report={
            "gaps": [
                {
                    "id": "gap:medical",
                    "gap_type": "missing_theme_specific_data",
                    "suggested_source_family": "kto_medical",
                }
            ]
        },
        settings=Settings(tourapi_service_key="test-key", allow_medical_api=False),
    )

    assert plan["planned_calls"] == []
    assert plan["skipped_calls"][0]["source_family"] == "kto_medical"
    assert plan["skipped_calls"][0]["skip_reason"] == "feature_flag_disabled"


def test_api_capability_router_prompt_is_compact_for_many_gaps():
    gaps = [
        {
            "id": f"gap:missing_detail_info:item-{index}",
            "gap_type": "missing_detail_info",
            "severity": "high",
            "reason": "상품 기획에 필요한 상세 정보가 부족합니다." * 20,
            "target_item_id": f"item-{index}",
            "target_content_id": f"content-{index}",
            "source_item_title": f"후보 {index}",
            "suggested_source_family": "kto_tourapi_kor",
            "needs_review": True,
        }
        for index in range(80)
    ]
    settings = Settings(tourapi_service_key="test-key")
    prompt = build_api_capability_router_prompt(
        gap_report={"gaps": gaps, "reasoning_summary": "요약" * 500},
        capabilities=capability_matrix_for_prompt(settings),
        settings=settings,
        max_call_budget=6,
    )

    assert len(prompt) < 30000
    assert "planner_lanes" in prompt
    assert "API endpoint와 arguments를 만들지 마세요" in prompt
    assert "상품 기획에 필요한 상세 정보가 부족합니다" not in prompt
    assert "gap:missing_detail_info:item-59" in prompt
    assert "gap:missing_detail_info:item-60" not in prompt


def test_data_gap_prompt_uses_natural_language_capability_brief_not_matrix():
    source_items = [
        _source_item(item_id=f"item-{index}", content_id=f"CID-{index}")
        for index in range(4)
    ]
    prompt = build_data_gap_profile_prompt(
        source_items=source_items,
        retrieved_documents=[],
        normalized_request={"message": "대전 야간 액티비티 상품 4개", "preferred_themes": ["야간 관광"]},
        capability_brief=capability_brief_for_prompt(Settings(tourapi_service_key="test-key")),
        candidate_pool_summary={"raw_total": 52, "selected_total": 4},
    )

    assert "api_capability_brief" in prompt
    assert "kto_api_capability_matrix" not in prompt
    assert "request_fields" not in prompt
    assert "response_fields" not in prompt
    assert "KorService2 상세 API는 contentId/contentTypeId" in prompt


def test_tourapi_detail_planner_uses_compact_target_selection():
    gaps = [
        {
            "id": f"gap:missing_detail_info:item-{index}",
            "gap_type": "missing_detail_info",
            "severity": "low",
            "reason": "상품 기획에 필요한 상세 정보가 부족합니다." * 10,
            "target_item_id": f"item-{index}",
            "target_content_id": f"content-{index}",
            "source_item_title": f"후보 {index}",
            "suggested_source_family": "kto_tourapi_kor",
            "needs_review": False,
        }
        for index in range(14)
    ]
    gaps.extend(
        [
            {
                "id": "gap:missing_operating_hours:request",
                "gap_type": "missing_operating_hours",
                "severity": "medium",
                "reason": "운영시간이 부족합니다.",
                "suggested_source_family": "kto_tourapi_kor",
                "needs_review": True,
            },
            {
                "id": "gap:missing_price_or_fee:request",
                "gap_type": "missing_price_or_fee",
                "severity": "medium",
                "reason": "요금 정보가 부족합니다.",
                "suggested_source_family": "kto_tourapi_kor",
                "needs_review": True,
            },
        ]
    )
    gap_report = {"gaps": gaps}
    capability_routing = {
        "family_routes": [
            {
                "planner": "tourapi_detail",
                "gap_ids": [gap["id"] for gap in gaps],
                "source_families": ["kto_tourapi_kor"],
                "reason": "KorService2 상세 보강",
                "priority": "medium",
            }
        ]
    }

    prompt = build_tourapi_detail_planner_prompt(
        capability_routing=capability_routing,
        gap_report=gap_report,
        max_call_budget=6,
        existing_planned_count=0,
    )
    fragment = normalize_tourapi_detail_planner_payload(
        {
            "selected_targets": [
                {
                    "target_item_id": f"item-{index}",
                    "target_content_id": f"content-{index}",
                    "gap_ids": [f"gap:missing_detail_info:item-{index}"],
                    "priority": "medium",
                    "reason": "상세 정보 우선 확인",
                }
                for index in range(6)
            ],
            "skipped_gap_ids": [gap["id"] for gap in gaps[6:]],
            "planning_reasoning": "상세 보강 가능한 대상만 예산 안에서 선택했습니다.",
        },
        capability_routing=capability_routing,
        gap_report=gap_report,
        settings=Settings(tourapi_service_key="test-key"),
        max_call_budget=6,
        existing_planned_count=0,
    )

    assert len(prompt) < 12000
    assert "planned_calls" not in prompt
    assert "tool_name" not in prompt
    assert len(fragment["planned_calls"]) == 6
    assert fragment["planned_calls"][0]["tool_name"] == "kto_tour_detail_enrichment"
    assert any(call["skip_reason"] == "requires_item_target" for call in fragment["skipped_calls"])


def test_tourapi_detail_planner_auto_includes_all_executable_targets_within_budget():
    gaps = [
        {
            "id": f"gap:missing_detail_info:item-{index}",
            "gap_type": "missing_detail_info",
            "severity": "low",
            "reason": "상세 정보가 부족합니다.",
            "target_item_id": f"item-{index}",
            "target_content_id": f"content-{index}",
            "source_item_title": f"후보 {index}",
            "suggested_source_family": "kto_tourapi_kor",
            "needs_review": False,
        }
        for index in range(12)
    ]
    capability_routing = {
        "family_routes": [
            {
                "planner": "tourapi_detail",
                "gap_ids": [gap["id"] for gap in gaps],
                "source_families": ["kto_tourapi_kor"],
                "reason": "KorService2 상세 보강",
                "priority": "medium",
            }
        ]
    }

    fragment = normalize_tourapi_detail_planner_payload(
        {
            "selected_targets": [
                {
                    "target_item_id": "item-0",
                    "target_content_id": "content-0",
                    "gap_ids": ["gap:missing_detail_info:item-0"],
                    "priority": "medium",
                    "reason": "상세 정보 확인",
                }
            ],
            "skipped_gap_ids": [],
            "planning_reasoning": "Gemini가 일부만 선택해도 실행 가능한 대상은 정책상 보강합니다.",
        },
        capability_routing=capability_routing,
        gap_report={"gaps": gaps},
        settings=Settings(tourapi_service_key="test-key"),
        max_call_budget=12,
        existing_planned_count=0,
    )

    assert len(fragment["planned_calls"]) == 12
    assert fragment["skipped_calls"] == []


def test_evidence_fusion_prompt_does_not_copy_full_profile_or_capability_matrix():
    base_fusion = {
        "evidence_profile": {
            "entities": [
                {
                    "content_id": f"CID-{index}",
                    "title": f"후보 {index}",
                    "content_type": "attraction",
                    "address": "대전광역시",
                    "detail_available": index < 3,
                    "visual_asset_count": 2 if index < 3 else 0,
                    "source_confidence": 0.8,
                    "unresolved_gap_types": [] if index < 3 else ["missing_detail_info"],
                    "key_facts": {"overview": "상세 개요" * 40 if index < 3 else ""},
                }
                for index in range(30)
            ],
            "source_document_count": 30,
        },
        "productization_advice": {},
        "data_coverage": {"total_items": 30},
        "unresolved_gaps": [],
        "source_confidence": 0.7,
    }
    prompt = build_evidence_fusion_prompt(
        base_fusion=base_fusion,
        retrieved_documents=[],
        gap_report={"gaps": []},
        enrichment_summary={"summary": {"executed_calls": 3, "skipped_calls": 0, "failed_calls": 0}},
    )

    assert "kto_api_capability_matrix" not in prompt
    assert "evidence_profile 전체나 entities 전체를 다시 출력하지 마세요" in prompt
    assert "candidate_evidence_cards를 반드시 작성하세요" in prompt
    assert "짧게 작성하세요" not in prompt
    assert "후보 29" not in prompt
    assert len(prompt) < 20000


def test_evidence_fusion_preserves_candidate_level_detail_facts():
    with TestClient(app):
        pass

    source_item = _source_item(item_id="item-detail", content_id="CID-DETAIL")
    source_item["raw"] = {
        "detail_common": {"contentid": "CID-DETAIL"},
        "detail_intro": {"usetime": "매일 10:00~18:00", "parking": "공영주차장 이용"},
        "detail_info": [
            {"infoname": "이용요금", "infotext": "성인 5,000원"},
            {"infoname": "예약", "infotext": "온라인 사전 예약 권장"},
        ],
        "detail_images": [{"imgname": "대표 이미지", "originimgurl": "https://example.com/a.jpg"}],
    }
    source_item["overview"] = "외국인 관광객에게 지역 체험을 소개할 수 있는 공식 개요입니다."

    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()
        base_fusion = fuse_evidence(
            db=db,
            source_items=[source_item],
            retrieved_documents=[],
            gap_report={"gaps": []},
            enrichment_summary={"summary": {"executed_calls": 1, "failed_calls": 0, "skipped_calls": 0}},
        )

    cards = base_fusion["productization_advice"]["candidate_evidence_cards"]
    assert cards[0]["content_id"] == "CID-DETAIL"
    fact_values = [str(fact.get("value")) for fact in cards[0]["usable_facts"]]
    assert any("매일 10:00~18:00" in value for value in fact_values)
    assert any("성인 5,000원" in value for value in fact_values)
    assert any("온라인 사전 예약" in value for value in fact_values)

    prompt = build_evidence_fusion_prompt(
        base_fusion=base_fusion,
        retrieved_documents=[],
        gap_report={"gaps": []},
        enrichment_summary={"summary": {"executed_calls": 1, "skipped_calls": 0, "failed_calls": 0}},
    )
    assert "매일 10:00~18:00" in prompt
    assert "성인 5,000원" in prompt


def test_enrichment_execution_records_success_and_fusion_merges_profile():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase10:success"
    source_item = _source_item(item_id=item_id, content_id="TEST-PHASE10-SUCCESS")
    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()

        gap_report = profile_data_gaps(source_items=[source_item])
        plan = route_gap_plan(
            gap_report=gap_report,
            settings=Settings(tourapi_service_key="test-key"),
            max_call_budget=1,
        )
        enrichment_run = create_enrichment_run(
            db=db,
            workflow_run_id="",
            gap_report=gap_report,
            plan=plan,
        )
        summary = execute_enrichment_plan(
            db=db,
            provider=DetailProvider(),
            enrichment_run=enrichment_run,
            source_items=[source_item],
            run_id="",
            step_id=None,
        )
        fusion = fuse_evidence(
            db=db,
            source_items=[source_item],
            retrieved_documents=[],
            gap_report=gap_report,
            enrichment_summary={"summary": summary},
        )

        assert summary["executed_calls"] == 1
        assert summary["failed_calls"] == 0
        assert enrichment_run.tool_calls[0].status == "succeeded"
        assert fusion["evidence_profile"]["entities"][0]["visual_asset_count"] == 1
        assert "missing_image_asset" not in fusion["evidence_profile"]["entities"][0]["unresolved_gap_types"]
        assert fusion["data_coverage"]["image_coverage"] == 1.0


def test_enrichment_execution_records_failed_call_without_raising():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase10:failed"
    source_item = _source_item(item_id=item_id, content_id="TEST-PHASE10-FAILED")
    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()

        gap_report = profile_data_gaps(source_items=[source_item])
        plan = route_gap_plan(
            gap_report=gap_report,
            settings=Settings(tourapi_service_key="test-key"),
            max_call_budget=1,
        )
        enrichment_run = create_enrichment_run(
            db=db,
            workflow_run_id="",
            gap_report=gap_report,
            plan=plan,
        )
        summary = execute_enrichment_plan(
            db=db,
            provider=FailingDetailProvider(),
            enrichment_run=enrichment_run,
            source_items=[source_item],
            run_id="",
            step_id=None,
        )

        assert summary["failed_calls"] == 1
        assert enrichment_run.status == "completed_with_errors"
        assert enrichment_run.tool_calls[0].status == "failed"
        assert enrichment_run.tool_calls[0].error["message"] == "detailCommon2 unavailable"


def test_phase10_2_agents_use_gemini_schema_outputs(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("TOURAPI_SERVICE_KEY", "test-key")
    get_settings.cache_clear()

    def fake_call_gemini_json(**kwargs):
        purpose = kwargs["purpose"]
        db = kwargs["db"]
        db.add(
            models.LLMCall(
                run_id=kwargs["run_id"],
                step_id=kwargs["step_id"],
                provider="gemini",
                model="gemini-test",
                purpose=purpose,
                prompt_tokens=100,
                completion_tokens=40,
                total_tokens=140,
                cost_usd=0,
                latency_ms=1,
                cache_hit=False,
            )
        )
        db.commit()
        return GeminiJsonResult(
            data=_fake_gemini_payload(purpose),
            model="gemini-test",
            prompt_tokens=100,
            completion_tokens=40,
            total_tokens=140,
            cost_usd=0.0,
            paid_tier_equivalent_cost_usd=0.0,
            latency_ms=1,
            raw_text="{}",
        )

    monkeypatch.setattr("app.agents.workflow.call_gemini_json", fake_call_gemini_json)
    monkeypatch.setattr("app.agents.workflow._refreshed_documents_after_enrichment", lambda *args, **kwargs: [])

    with TestClient(app):
        pass

    source_item = _source_item(item_id="item-1", content_id="CID-1")
    with SessionLocal() as db:
        run = models.WorkflowRun(
            template_id="default_product_planning",
            input={"message": "부산 야간 미식 상품 1개 기획", "product_count": 1},
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        state = {
            "run_id": run.id,
            "user_request": run.input,
            "normalized_request": {"message": "부산 야간 미식 상품 1개 기획"},
            "source_items": [source_item],
            "retrieved_documents": [],
            "errors": [],
            "agent_execution": [],
        }

        state.update(data_gap_profiler_agent(db, state))
        state.update(api_capability_router_agent(db, state))
        state.update(tourapi_detail_planner_agent(db, state))
        state.update(visual_data_planner_agent(db, state))
        state.update(route_signal_planner_agent(db, state))
        state.update(theme_data_planner_agent(db, state))
        state["enrichment_summary"] = {"summary": {"executed_calls": 0, "failed_calls": 0, "skipped_calls": 1}}
        state.update(evidence_fusion_agent(db, state))

        calls = db.query(models.LLMCall).filter(models.LLMCall.run_id == run.id).all()
        steps = db.query(models.AgentStep).filter(models.AgentStep.run_id == run.id).all()

    get_settings.cache_clear()

    purposes = {call.purpose for call in calls if call.provider == "gemini"}
    expected_purposes = {
        "data_gap_profile",
        "api_capability_routing",
        "tourapi_detail_planning",
        "evidence_fusion",
    }
    assert expected_purposes <= purposes
    assert not {"visual_data_planning", "route_signal_planning", "theme_data_planning"} & purposes
    assert not any(
        call.provider == "rule_based"
        and call.purpose in expected_purposes
        for call in calls
    )
    assert {step.model for step in steps} == {"gemini-test"}
    assert state["data_gap_report"]["gaps"][0]["gap_type"] == "missing_detail_info"
    assert state["capability_routing"]["family_routes"][0]["planner"] == "tourapi_detail"
    assert len(state["enrichment_plan_fragments"]) == 1
    assert state["enrichment_plan"]["planned_calls"][0]["tool_name"] == "kto_tour_detail_enrichment"
    assert state["ui_highlights"][0]["title"] == "상품화 주의"


def _source_item(*, item_id: str, content_id: str) -> dict:
    return {
        "id": item_id,
        "source": "tourapi",
        "content_id": content_id,
        "content_type": "attraction",
        "title": "대전 중앙시장 야간 미식 투어",
        "region_code": "3",
        "sigungu_code": "1",
        "legacy_area_code": "3",
        "legacy_sigungu_code": "1",
        "ldong_regn_cd": "30",
        "ldong_signgu_cd": "140",
        "address": "대전광역시 중구",
        "overview": "기본 목록 응답 개요입니다.",
        "raw": {},
    }


def _fake_gemini_payload(purpose: str) -> dict:
    if purpose == "data_gap_profile":
        return {
            "gaps": [
                {
                    "id": "gap:missing_detail_info:item-1",
                    "gap_type": "missing_detail_info",
                    "severity": "high",
                    "reason": "운영 조건을 판단할 상세 정보가 부족합니다.",
                    "target_item_id": "item-1",
                    "target_content_id": "CID-1",
                    "source_item_title": "대전 중앙시장 야간 미식 투어",
                    "suggested_source_family": "kto_tourapi_kor",
                    "needs_review": True,
                    "productization_impact": "운영시간과 예약 가능 여부를 단정하지 않아야 합니다.",
                }
            ],
            "coverage": {
                "total_items": 1,
                "gap_count": 1,
                "detail_info_coverage": 0,
                "image_coverage": 1,
                "operating_hours_coverage": 0,
                "price_or_fee_coverage": 0,
                "booking_info_coverage": 0,
                "gap_counts": {"missing_detail_info": 1},
            },
            "reasoning_summary": "요청 상품을 만들기 전에 상세 운영 조건 근거가 필요합니다.",
            "needs_review": ["운영시간과 예약정보는 운영자가 확인해야 합니다."],
        }
    if purpose == "api_capability_routing":
        return {
            "family_routes": [
                {
                    "planner": "tourapi_detail",
                    "gap_ids": ["gap:missing_detail_info:item-1"],
                    "source_families": ["kto_tourapi_kor"],
                    "reason": "KorService2 상세 planner로 보냅니다.",
                    "priority": "high",
                }
            ],
            "skipped_routes": [],
            "routing_reasoning": "상세 보강 gap만 Detail Planner로 배정했습니다.",
        }
    if purpose == "tourapi_detail_planning":
        return {
            "selected_targets": [
                {
                    "target_item_id": "item-1",
                    "target_content_id": "CID-1",
                    "gap_ids": ["gap:missing_detail_info:item-1"],
                    "priority": "high",
                    "reason": "KorService2 상세 API로 운영 조건을 확인합니다.",
                }
            ],
            "skipped_gap_ids": [],
            "planning_reasoning": "실행 가능한 KorService2 상세 보강만 계획했습니다.",
        }
    if purpose in {"visual_data_planning", "route_signal_planning", "theme_data_planning"}:
        return {
            "planned_calls": [],
            "skipped_calls": [],
            "budget_summary": {"max_call_budget": 6, "planned": 0, "skipped": 0},
            "planning_reasoning": "배정된 gap이 없어 호출하지 않습니다.",
        }
    if purpose == "evidence_fusion":
        return {
            "evidence_profile": {"entities": [{"content_id": "CID-1", "title": "대전 중앙시장 야간 미식 투어"}]},
            "productization_advice": {
                "usable_claims": ["장소명과 주소는 근거 기반으로 사용할 수 있습니다."],
                "needs_review_fields": ["운영시간"],
            },
            "data_coverage": {"total_items": 1, "detail_info_coverage": 0, "image_coverage": 1},
            "unresolved_gaps": [{"gap_type": "missing_detail_info", "target_content_id": "CID-1"}],
            "source_confidence": 0.7,
            "ui_highlights": [
                {
                    "title": "상품화 주의",
                    "body": "운영시간과 예약 가능 여부는 단정하지 말고 확인 필요로 표시해야 합니다.",
                    "severity": "warning",
                    "related_gap_types": ["missing_detail_info"],
                }
            ],
        }
    raise AssertionError(f"Unexpected Gemini purpose: {purpose}")
