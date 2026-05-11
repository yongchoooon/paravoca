from fastapi.testclient import TestClient

from app.agents.data_enrichment import (
    DATA_GAP_PROFILE_MAX_GAPS,
    build_api_capability_router_prompt,
    build_data_gap_profile_prompt,
    build_evidence_fusion_prompt,
    build_tourapi_detail_planner_prompt,
    capability_brief_for_prompt,
    capability_matrix_for_prompt,
    create_enrichment_run,
    execute_enrichment_plan,
    fuse_evidence,
    normalize_gap_profile_payload,
    normalize_family_planner_payload,
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
from app.tools.kto_capabilities import list_kto_capabilities
from app.tools.route_signals import RouteAssetCandidate, SignalRecordCandidate
from app.tools.themes import ThemeDataCandidate
from app.tools.visuals import VisualAssetCandidate


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


class VisualProvider:
    def search_tourism_photos(self, *, keyword, limit=5):
        return [
            VisualAssetCandidate(
                id="visual-candidate-1",
                source_family="kto_tourism_photo",
                operation="gallerySearchList1",
                source_item_id="GAL-1",
                title=f"{keyword} 관광사진",
                image_url="https://example.com/visual.jpg",
                thumbnail_url="https://example.com/visual-thumb.jpg",
                shooting_place="대전광역시 중구",
                photographer="한국관광공사",
                keywords=[keyword, "야간"],
                license_type="관광사진 정보_GW 이용 조건 확인 필요",
                license_note="게시 전 사용권 확인 필요",
                usage_status="needs_license_review",
                raw={"galContentId": "GAL-1"},
            )
        ][:limit]

    def search_photo_contest_awards(self, *, keyword, ldong_regn_cd=None, limit=5):
        return [
            VisualAssetCandidate(
                id="visual-candidate-2",
                source_family="kto_photo_contest",
                operation="phokoAwrdList",
                source_item_id="PHOTO-1",
                title=f"{keyword} 공모전 사진",
                image_url="https://example.com/photo-contest.jpg",
                thumbnail_url="https://example.com/photo-contest-thumb.jpg",
                shooting_place="대전광역시 중구",
                photographer="작가",
                keywords=[keyword],
                license_type="Type1",
                license_note="저작권 유형 확인 필요",
                usage_status="needs_license_review",
                raw={"contentId": "PHOTO-1", "cpyrhtDivCd": "Type1"},
            )
        ][:limit]


class FailingVisualProvider(VisualProvider):
    def search_tourism_photos(self, *, keyword, limit=5):
        raise RuntimeError("gallerySearchList1 unavailable")


class RouteSignalProvider:
    def search_durunubi_courses(self, *, keyword, limit=5):
        return [
            RouteAssetCandidate(
                id="route-candidate-1",
                source_family="kto_durunubi",
                operation="courseList",
                course_name=f"{keyword} 걷기 코스",
                path_name="야간 산책길",
                gpx_url="https://example.com/course.gpx",
                distance_km=2.4,
                estimated_duration="1시간",
                safety_notes=["운영 전 야간 안전 확인 필요"],
                raw={"routeIdx": "ROUTE-1", "crsKorNm": f"{keyword} 걷기 코스"},
            )
        ][:limit]

    def search_related_places(self, *, keyword=None, area_cd=None, signgu_cd=None, base_ym=None, limit=5):
        return [
            SignalRecordCandidate(
                id="signal-related-1",
                source_family="kto_related_places",
                operation="searchKeyword1",
                signal_type="related_places",
                region_code=area_cd,
                sigungu_code=signgu_cd,
                period_start="202605",
                period_end="202605",
                value={"target_place": keyword, "related_place": "대전 원도심", "related_rank": "1"},
                interpretation_note="연관 관광지 신호는 동선 확장 참고용입니다.",
                raw={"tAtsNm": keyword, "rlteTatsNm": "대전 원도심"},
            )
        ][:limit]

    def search_tourism_bigdata_visitors(self, *, area_cd=None, signgu_cd=None, base_ymd=None, limit=5):
        return [
            SignalRecordCandidate(
                id="signal-bigdata-1",
                source_family="kto_tourism_bigdata",
                operation="locgoRegnVisitrDDList",
                signal_type="visitor_demand",
                region_code=area_cd,
                sigungu_code=signgu_cd,
                period_start=base_ymd or "20260501",
                period_end=base_ymd or "20260501",
                value={"visitor_count": "1200", "visitor_type": "전체"},
                interpretation_note="방문자 수는 수요 보조 신호입니다.",
                raw={"touNum": "1200"},
            )
        ][:limit]

    def search_crowding_forecast(self, *, keyword=None, area_cd=None, signgu_cd=None, limit=5):
        return [
            SignalRecordCandidate(
                id="signal-crowding-1",
                source_family="kto_crowding_forecast",
                operation="tatsCnctrRatedList",
                signal_type="crowding_forecast",
                region_code=area_cd,
                sigungu_code=signgu_cd,
                period_start="20260510",
                period_end="20260510",
                value={"attraction_name": keyword, "crowding_rate": "0.42"},
                interpretation_note="혼잡 예측은 보조 지표입니다.",
                raw={"cnctrRate": "0.42"},
            )
        ][:limit]

    def search_regional_tourism_demand(self, *, area_cd=None, signgu_cd=None, base_ym=None, limit=5):
        return [
            SignalRecordCandidate(
                id="signal-regional-1",
                source_family="kto_regional_tourism_demand",
                operation="areaTarSvcDemList",
                signal_type="regional_service_demand",
                region_code=area_cd,
                sigungu_code=signgu_cd,
                period_start=base_ym or "202605",
                period_end=base_ym or "202605",
                value={"index_name": "관광서비스", "index_value": "70"},
                interpretation_note="지역 수요 지수는 보조 신호입니다.",
                raw={"tarSvcDemIxVal": "70"},
            )
        ][:limit]


class FailingRouteSignalProvider(RouteSignalProvider):
    def search_durunubi_courses(self, *, keyword, limit=5):
        raise RuntimeError("courseList unavailable")


class ThemeProvider:
    def search_wellness(self, *, keyword, ldong_regn_cd=None, ldong_signgu_cd=None, limit=5):
        return [
            ThemeDataCandidate(
                id="theme-wellness-1",
                source_family="kto_wellness",
                operation="searchKeyword",
                title=f"{keyword} 웰니스 후보",
                content_id="WELLNESS-1",
                address="대전광역시 중구",
                image_url="https://example.com/wellness.jpg",
                thumbnail_url="https://example.com/wellness-thumb.jpg",
                theme_attributes={"wellness_theme_code": "EX050400"},
                needs_review=["웰니스 효과를 단정하지 마세요."],
                raw={"contentId": "WELLNESS-1"},
            )
        ][:limit]

    def search_pet(self, *, keyword, ldong_regn_cd=None, ldong_signgu_cd=None, limit=5):
        return [
            ThemeDataCandidate(
                id="theme-pet-1",
                source_family="kto_pet",
                operation="searchKeyword2",
                title=f"{keyword} 반려동물 후보",
                content_id="PET-1",
                address="대전광역시 중구",
                image_url="https://example.com/pet.jpg",
                thumbnail_url="https://example.com/pet-thumb.jpg",
                theme_attributes={
                    "pet_tour_candidate": True,
                    "allowed_animals": "소형견",
                    "companion_requirements": "목줄 착용",
                },
                needs_review=["반려동물 동반 조건은 방문 전 확인하세요."],
                raw={"contentid": "PET-1"},
            )
        ][:limit]

    def search_audio(self, *, keyword, limit=5):
        return [
            ThemeDataCandidate(
                id="theme-audio-1",
                source_family="kto_audio",
                operation="storySearchList",
                title=f"{keyword} 오디오 스토리",
                content_id="AUDIO-1",
                overview="지역 이야기를 들을 수 있는 오디오 해설 후보입니다.",
                theme_attributes={"language": "ko", "audio_url_available": True},
                needs_review=["오디오 제공 언어와 사용 조건은 확인 필요입니다."],
                raw={"stid": "AUDIO-1"},
            )
        ][:limit]

    def search_eco(self, *, area_code=None, sigungu_code=None, limit=5):
        return [
            ThemeDataCandidate(
                id="theme-eco-1",
                source_family="kto_eco",
                operation="areaBasedList1",
                title="대전 생태관광 후보",
                content_id="ECO-1",
                address="대전광역시 중구",
                overview="생태 해설 맥락 후보입니다.",
                theme_attributes={"subtitle": "생태 탐방"},
                needs_review=["생태 효과를 정량 보장하지 마세요."],
                raw={"contentid": "ECO-1"},
            )
        ][:limit]

    def search_medical(self, *, keyword, ldong_regn_cd=None, ldong_signgu_cd=None, limit=5):
        return [
            ThemeDataCandidate(
                id="theme-medical-1",
                source_family="kto_medical",
                operation="searchKeyword",
                title=f"{keyword} 의료관광 후보",
                content_id="MEDICAL-1",
                address="대전광역시 중구",
                theme_attributes={"medical_context": True},
                needs_review=["의료 효과와 안전성을 단정하지 마세요."],
                raw={"contentId": "MEDICAL-1"},
            )
        ][:limit]


class FailingThemeProvider(ThemeProvider):
    def search_pet(self, *, keyword, ldong_regn_cd=None, ldong_signgu_cd=None, limit=5):
        raise RuntimeError("searchKeyword2 unavailable")


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


def test_visual_capabilities_are_workflow_enabled_only_when_flags_are_on():
    disabled = {
        item["source_family"]: item
        for item in list_kto_capabilities(
            Settings(
                tourapi_service_key="test-key",
                kto_tourism_photo_enabled=False,
                kto_photo_contest_enabled=False,
            )
        )
        if item["source_family"] in {"kto_tourism_photo", "kto_photo_contest"}
    }
    assert not any(
        operation["workflow_enabled"]
        for operation in disabled["kto_tourism_photo"]["operations"]
        if operation["operation"] == "gallerySearchList1"
    )
    assert not any(
        operation["workflow_enabled"]
        for operation in disabled["kto_photo_contest"]["operations"]
        if operation["operation"] == "phokoAwrdList"
    )

    enabled = {
        item["source_family"]: item
        for item in list_kto_capabilities(
            Settings(
                tourapi_service_key="test-key",
                kto_tourism_photo_enabled=True,
                kto_photo_contest_enabled=True,
            )
        )
        if item["source_family"] in {"kto_tourism_photo", "kto_photo_contest"}
    }

    assert any(
        operation["workflow_enabled"]
        for operation in enabled["kto_tourism_photo"]["operations"]
        if operation["operation"] == "gallerySearchList1"
    )
    assert any(
        operation["workflow_enabled"]
        for operation in enabled["kto_photo_contest"]["operations"]
        if operation["operation"] == "phokoAwrdList"
    )


def test_visual_planner_normalization_creates_calls_only_when_enabled():
    gap = {
        "id": "gap:missing_image_asset:item-visual",
        "gap_type": "missing_image_asset",
        "severity": "medium",
        "reason": "이미지 후보가 부족합니다.",
        "target_item_id": "item-visual",
        "target_content_id": "CID-VISUAL",
        "source_item_title": "대전 야간 산책",
        "suggested_source_family": "kto_tourism_photo",
        "needs_review": True,
    }
    routing = {
        "family_routes": [
            {
                "planner": "visual_data",
                "gap_ids": [gap["id"]],
                "source_families": ["kto_tourism_photo"],
            }
        ]
    }

    disabled = normalize_family_planner_payload(
        {"planned_calls": [], "skipped_calls": [], "budget_summary": {}, "planning_reasoning": ""},
        planner_key="visual_data",
        capability_routing=routing,
        gap_report={"gaps": [gap]},
        settings=Settings(tourapi_service_key="test-key", kto_tourism_photo_enabled=False),
        max_call_budget=1,
    )
    assert disabled["planned_calls"] == []
    assert disabled["skipped_calls"][0]["skip_reason"] == "feature_flag_disabled"

    enabled = normalize_family_planner_payload(
        {"planned_calls": [], "skipped_calls": [], "budget_summary": {}, "planning_reasoning": ""},
        planner_key="visual_data",
        capability_routing=routing,
        gap_report={"gaps": [gap]},
        settings=Settings(tourapi_service_key="test-key", kto_tourism_photo_enabled=True),
        max_call_budget=1,
    )
    assert enabled["planned_calls"][0]["source_family"] == "kto_tourism_photo"
    assert enabled["planned_calls"][0]["tool_name"] == "kto_tourism_photo_search"
    assert enabled["planned_calls"][0]["operation"] == "gallerySearchList1"


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


def test_data_gap_prompt_caps_output_and_blocks_missing_overview():
    source_items = [
        _source_item(item_id=f"item-{index}", content_id=f"CID-{index}")
        for index in range(30)
    ]
    prompt = build_data_gap_profile_prompt(
        source_items=source_items,
        retrieved_documents=[],
        normalized_request={"message": "대청도 액티비티 상품 3개", "preferred_themes": ["액티비티"]},
        capability_brief=capability_brief_for_prompt(Settings(tourapi_service_key="test-key")),
        candidate_pool_summary={"raw_total": 80, "selected_total": 30},
    )

    assert f"gaps는 반드시 {DATA_GAP_PROFILE_MAX_GAPS}개 이하" in prompt
    assert "missing_overview는 허용 gap_type이 아닙니다" in prompt
    assert "하나의 target_item_id에는 item-level gap을 최대 1개" in prompt


def test_gap_profile_normalization_recovers_item_id_from_content_id():
    source_item = _source_item(item_id="tourapi:content:CID-RECOVER", content_id="CID-RECOVER")
    payload = {
        "gaps": [
            {
                "id": "gap:missing_detail_info:tourapi:content:CID-RECOVER",
                "gap_type": "missing_detail_info",
                "severity": "low",
                "reason": "상세 정보가 부족합니다.",
                "target_entity_id": "tourapi:content:CID-RECOVER",
                "target_content_id": "CID-RECOVER",
                "target_item_id": None,
                "source_item_title": "대전 중앙시장 야간 미식 투어",
                "suggested_source_family": "kto_tourapi_kor",
                "needs_review": False,
            }
        ],
        "coverage": {},
    }

    normalized = normalize_gap_profile_payload(payload, source_items=[source_item])

    assert normalized["gaps"][0]["target_content_id"] == "CID-RECOVER"
    assert normalized["gaps"][0]["target_item_id"] == "tourapi:content:CID-RECOVER"


def test_gap_profile_normalization_adds_wellness_request_gap_when_gemini_omits_it():
    source_items = [
        _source_item(item_id=f"tourapi:content:{index}", content_id=str(index))
        for index in range(20)
    ]
    payload = {
        "gaps": [
            {
                "id": f"gap:missing_detail_info:tourapi:content:{index}",
                "gap_type": "missing_detail_info",
                "severity": "medium",
                "reason": "상세 정보가 부족합니다.",
                "target_item_id": f"tourapi:content:{index}",
                "target_content_id": str(index),
                "suggested_source_family": "kto_tourapi_kor",
            }
            for index in range(20)
        ]
        + [
            {
                "id": f"gap:missing_image_asset:tourapi:content:{index}",
                "gap_type": "missing_image_asset",
                "severity": "medium",
                "reason": "이미지 후보가 부족합니다.",
                "target_item_id": f"tourapi:content:{index}",
                "target_content_id": str(index),
                "suggested_source_family": "kto_tourapi_kor",
            }
            for index in range(4)
        ],
        "coverage": {},
    }

    normalized = normalize_gap_profile_payload(
        payload,
        source_items=source_items,
        normalized_request={
            "message": "부산에서 외국인 대상 웰니스 관광 상품 3개 기획해줘.",
            "preferred_themes": ["웰니스"],
            "geo_scope": {
                "locations": [
                    {
                        "ldong_regn_cd": "26",
                        "ldong_signgu_cd": None,
                    }
                ]
            },
        },
    )

    wellness_gap = next(
        gap for gap in normalized["gaps"] if gap["suggested_source_family"] == "kto_wellness"
    )
    assert wellness_gap["gap_type"] == "missing_theme_specific_data"
    assert wellness_gap["search_keyword"] == "웰니스"
    assert wellness_gap["ldong_regn_cd"] == "26"
    assert len(normalized["gaps"]) <= DATA_GAP_PROFILE_MAX_GAPS


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
    assert "evidence_profile" in prompt
    assert "entities" in prompt
    assert "candidate_evidence_cards" in prompt
    assert "다시 출력하지 마세요" in prompt
    assert "candidate_interpretations" in prompt
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


def test_evidence_fusion_interpretation_delta_preserves_base_cards():
    from app.agents.data_enrichment import normalize_evidence_fusion_payload

    base_fusion = {
        "evidence_profile": {"entities": []},
        "productization_advice": {
            "candidate_evidence_cards": [
                {
                    "content_id": "CID-1",
                    "source_item_id": "item-1",
                    "title": "부산 요트투어",
                    "usable_facts": [{"field": "주소", "value": "부산광역시", "source": "TourAPI"}],
                    "visual_candidates": [{"image_url": "https://example.com/a.jpg", "usage_status": "candidate"}],
                    "recommended_product_angles": ["해양 체험"],
                    "experience_hooks": [],
                    "restricted_claims": ["요금 단정 금지"],
                    "evidence_document_ids": ["doc-1"],
                }
            ],
            "usable_claims": ["장소명과 주소 사용 가능"],
        },
        "data_coverage": {"total_items": 1},
        "unresolved_gaps": [],
        "source_confidence": 0.8,
    }
    payload = {
        "productization_advice": {
            "summary": "요트 체험 후보가 강합니다.",
            "candidate_interpretations": [
                {
                    "content_id": "CID-1",
                    "title": "부산 요트투어",
                    "priority": "high",
                    "product_angle": "외국인 대상 해양 감성 체험",
                    "rationale": "이미지와 장소 근거가 있어 체험 상품화에 적합합니다.",
                    "experience_hooks": ["해운대 바다 경험"],
                    "recommended_product_angles": ["사진 촬영 중심"],
                    "use_with_caution": ["이미지 사용권 확인 필요"],
                }
            ],
        },
        "unresolved_gaps": [],
        "source_confidence": 0.81,
        "ui_highlights": [],
    }

    fusion = normalize_evidence_fusion_payload(payload, base_fusion=base_fusion)
    card = fusion["productization_advice"]["candidate_evidence_cards"][0]

    assert card["usable_facts"] == base_fusion["productization_advice"]["candidate_evidence_cards"][0]["usable_facts"]
    assert card["visual_candidates"] == base_fusion["productization_advice"]["candidate_evidence_cards"][0]["visual_candidates"]
    assert "외국인 대상 해양 감성 체험" in card["recommended_product_angles"]
    assert "해운대 바다 경험" in card["experience_hooks"]
    assert "이미지 사용권 확인 필요" in card["restricted_claims"]
    assert card["fusion_interpretation"]["priority"] == "high"


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


def test_enrichment_execution_falls_back_to_content_id_when_item_id_missing():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase10:content-id-fallback"
    content_id = "TEST-PHASE10-CONTENT-ID-FALLBACK"
    source_item = _source_item(item_id=item_id, content_id=content_id)
    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()

        gap_report = {
            "gaps": [
                {
                    "id": "gap:missing_detail_info:content-id-fallback",
                    "gap_type": "missing_detail_info",
                    "severity": "medium",
                    "reason": "상세 정보가 부족합니다.",
                    "target_entity_id": f"tourapi:content:{content_id}",
                    "target_item_id": None,
                    "target_content_id": content_id,
                    "source_item_title": "대전 중앙시장 야간 미식 투어",
                    "suggested_source_family": "kto_tourapi_kor",
                    "needs_review": True,
                }
            ]
        }
        plan = {
            "planned_calls": [
                {
                    "id": "plan:tourapi-detail:content-id-fallback",
                    "source_family": "kto_tourapi_kor",
                    "tool_name": "kto_tour_detail_enrichment",
                    "operation": "detailCommon2/detailIntro2/detailInfo2/detailImage2",
                    "gap_ids": ["gap:missing_detail_info:content-id-fallback"],
                    "gap_types": ["missing_detail_info"],
                    "target_entity_id": f"tourapi:content:{content_id}",
                    "target_item_id": None,
                    "target_content_id": content_id,
                    "reason": "content_id만 있는 상세 보강 계획입니다.",
                    "arguments": {"item_id": None, "content_id": content_id},
                }
            ],
            "skipped_calls": [],
        }
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

        assert summary["executed_calls"] == 1
        assert summary["failed_calls"] == 0
        assert enrichment_run.tool_calls[0].status == "succeeded"


def test_visual_enrichment_execution_saves_candidate_assets_and_source_documents():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase12:visual"
    source_item = _source_item(item_id=item_id, content_id="TEST-PHASE12-VISUAL")
    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()

        gap_report = {
            "gaps": [
                {
                    "id": "gap:missing_image_asset:phase12",
                    "gap_type": "missing_image_asset",
                    "severity": "medium",
                    "reason": "이미지 후보가 부족합니다.",
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-VISUAL",
                    "source_item_title": "대전 중앙시장 야간 미식 투어",
                    "suggested_source_family": "kto_tourism_photo",
                    "needs_review": True,
                }
            ]
        }
        plan = {
            "planned_calls": [
                {
                    "id": "plan:visual:test",
                    "source_family": "kto_tourism_photo",
                    "tool_name": "kto_tourism_photo_search",
                    "operation": "gallerySearchList1",
                    "gap_ids": ["gap:missing_image_asset:phase12"],
                    "gap_types": ["missing_image_asset"],
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-VISUAL",
                    "reason": "이미지 후보를 확인합니다.",
                    "arguments": {"item_id": item_id, "content_id": "TEST-PHASE12-VISUAL", "query": "대전 중앙시장", "limit": 2},
                }
            ],
            "skipped_calls": [],
        }
        enrichment_run = create_enrichment_run(
            db=db,
            workflow_run_id="",
            gap_report=gap_report,
            plan=plan,
        )
        summary = execute_enrichment_plan(
            db=db,
            provider=DetailProvider(),
            visual_provider=VisualProvider(),
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

        asset = db.query(models.TourismVisualAsset).filter_by(source_item_id=item_id).one()
        document = db.query(models.SourceDocument).filter_by(source_item_id=item_id, source="kto_tourism_photo").one()

        assert summary["executed_calls"] == 1
        assert summary["visual_assets"] == 1
        assert summary["indexed_documents"] >= 1
        assert asset.usage_status == "needs_license_review"
        assert asset.license_note == "게시 전 사용권 확인 필요"
        assert document.document_metadata["source_family"] == "kto_tourism_photo"
        assert document.document_metadata["image_candidates"][0]["usage_status"] == "needs_license_review"
        entity = fusion["evidence_profile"]["entities"][0]
        assert entity["visual_asset_count"] == 1
        assert entity["visual_candidates"][0]["source_family"] == "kto_tourism_photo"
        assert fusion["unresolved_gaps"] == []
        card = fusion["productization_advice"]["candidate_evidence_cards"][0]
        assert card["visual_candidates"][0]["usage_status"] == "needs_license_review"
        assert any("이미지는 후보 상태" in claim for claim in card["restricted_claims"])


def test_visual_api_failure_records_failed_call_without_breaking_other_execution():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase12:visual-failed"
    source_item = _source_item(item_id=item_id, content_id="TEST-PHASE12-VISUAL-FAILED")
    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()

        plan = {
            "planned_calls": [
                {
                    "id": "plan:visual:failed",
                    "source_family": "kto_tourism_photo",
                    "tool_name": "kto_tourism_photo_search",
                    "operation": "gallerySearchList1",
                    "gap_ids": ["gap:missing_image_asset:failed"],
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-VISUAL-FAILED",
                    "reason": "이미지 후보를 확인합니다.",
                    "arguments": {"item_id": item_id, "content_id": "TEST-PHASE12-VISUAL-FAILED", "query": "대전", "limit": 2},
                }
            ],
            "skipped_calls": [],
        }
        enrichment_run = create_enrichment_run(
            db=db,
            workflow_run_id="",
            gap_report={"gaps": []},
            plan=plan,
        )
        summary = execute_enrichment_plan(
            db=db,
            provider=DetailProvider(),
            visual_provider=FailingVisualProvider(),
            enrichment_run=enrichment_run,
            source_items=[source_item],
            run_id="",
            step_id=None,
        )

        assert summary["failed_calls"] == 1
        assert enrichment_run.status == "completed_with_errors"
        assert enrichment_run.tool_calls[0].status == "failed"
        assert enrichment_run.tool_calls[0].error["message"] == "gallerySearchList1 unavailable"


def test_route_signal_capabilities_are_workflow_enabled_only_when_flags_are_on():
    disabled = list_kto_capabilities(
        Settings(
            tourapi_service_key="test-key",
            kto_durunubi_enabled=False,
            kto_related_places_enabled=False,
            kto_bigdata_enabled=False,
            kto_crowding_enabled=False,
            kto_regional_tourism_demand_enabled=False,
        )
    )
    disabled_by_family = {item["source_family"]: item for item in disabled}

    enabled = list_kto_capabilities(
        Settings(
            tourapi_service_key="test-key",
            kto_durunubi_enabled=True,
            kto_related_places_enabled=True,
            kto_bigdata_enabled=True,
            kto_crowding_enabled=True,
            kto_regional_tourism_demand_enabled=True,
        )
    )
    enabled_by_family = {item["source_family"]: item for item in enabled}

    for family in [
        "kto_durunubi",
        "kto_related_places",
        "kto_tourism_bigdata",
        "kto_crowding_forecast",
        "kto_regional_tourism_demand",
    ]:
        assert not disabled_by_family[family]["enabled"]
        assert not any(op["workflow_enabled"] for op in disabled_by_family[family]["operations"])
        assert enabled_by_family[family]["enabled"]
        assert any(op["workflow_enabled"] for op in enabled_by_family[family]["operations"])


def test_route_signal_planner_executes_enabled_source_family_and_respects_budget():
    gap_report = {
        "gaps": [
            {
                "id": "gap:missing_route_context:request",
                "gap_type": "missing_route_context",
                "severity": "medium",
                "reason": "코스형 요청이라 동선 근거가 필요합니다.",
                "target_item_id": "item-1",
                "target_content_id": "CID-1",
                "source_item_title": "대전 중앙시장 야간 미식 투어",
                "suggested_source_family": "kto_durunubi",
                "needs_review": True,
            },
            {
                "id": "gap:missing_demand_signal:request",
                "gap_type": "missing_demand_signal",
                "severity": "low",
                "reason": "수요 보조 신호가 필요합니다.",
                "target_item_id": "item-1",
                "target_content_id": "CID-1",
                "source_item_title": "대전 중앙시장 야간 미식 투어",
                "suggested_source_family": "kto_tourism_bigdata",
                "needs_review": True,
            },
        ]
    }
    capability_routing = {
        "family_routes": [
            {
                "planner": "route_signal",
                "gap_ids": [
                    "gap:missing_route_context:request",
                    "gap:missing_demand_signal:request",
                ],
                "source_families": ["kto_durunubi", "kto_tourism_bigdata"],
                "reason": "route/signal planner로 보냅니다.",
            }
        ]
    }

    fragment = normalize_family_planner_payload(
        {"planned_calls": [], "skipped_calls": []},
        planner_key="route_signal",
        capability_routing=capability_routing,
        gap_report=gap_report,
        settings=Settings(
            tourapi_service_key="test-key",
            kto_durunubi_enabled=True,
            kto_bigdata_enabled=True,
        ),
        max_call_budget=1,
    )

    assert len(fragment["planned_calls"]) == 1
    assert len(fragment["skipped_calls"]) == 1
    assert fragment["planned_calls"][0]["source_family"] == "kto_durunubi"
    assert fragment["planned_calls"][0]["tool_name"] == "kto_durunubi_course_list"
    assert fragment["skipped_calls"][0]["skip_reason"] == "max_call_budget_exceeded"


def test_route_signal_planner_recovers_executable_gap_from_bad_future_skip():
    gap_report = {
        "gaps": [
            {
                "id": "gap:missing_crowding_signal:request",
                "gap_type": "missing_crowding_signal",
                "severity": "medium",
                "reason": "혼잡 회피 요청이라 혼잡 예측 신호가 필요합니다.",
                "target_item_id": "",
                "target_content_id": "",
                "source_item_title": "",
                "suggested_source_family": "kto_crowding_forecast",
                "needs_review": True,
            }
        ]
    }
    capability_routing = {
        "family_routes": [
            {
                "planner": "route_signal",
                "gap_ids": ["gap:missing_crowding_signal:request"],
                "source_families": ["kto_crowding_forecast"],
                "reason": "route/signal planner로 보냅니다.",
            }
        ]
    }

    fragment = normalize_family_planner_payload(
        {
            "planned_calls": [],
            "skipped_calls": [
                {
                    "gap_ids": ["gap:missing_crowding_signal:request"],
                    "source_family": "kto_crowding_forecast",
                    "skip_reason": "future_provider_not_implemented",
                }
            ],
        },
        planner_key="route_signal",
        capability_routing=capability_routing,
        gap_report=gap_report,
        settings=Settings(
            tourapi_service_key="test-key",
            kto_crowding_enabled=True,
        ),
        max_call_budget=1,
    )

    assert len(fragment["planned_calls"]) == 1
    assert fragment["planned_calls"][0]["source_family"] == "kto_crowding_forecast"
    assert fragment["planned_calls"][0]["tool_name"] == "kto_attraction_crowding_forecast"
    assert fragment["skipped_calls"] == []


def test_route_signal_enrichment_saves_route_assets_signals_and_source_documents():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase12:route-signal"
    source_item = _source_item(item_id=item_id, content_id="TEST-PHASE12-ROUTE-SIGNAL")
    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()

        gap_report = {
            "gaps": [
                {
                    "id": "gap:missing_route_context:phase12",
                    "gap_type": "missing_route_context",
                    "severity": "medium",
                    "reason": "동선 근거가 부족합니다.",
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-ROUTE-SIGNAL",
                    "source_item_title": "대전 중앙시장 야간 미식 투어",
                    "suggested_source_family": "kto_durunubi",
                    "needs_review": True,
                },
                {
                    "id": "gap:missing_demand_signal:phase12",
                    "gap_type": "missing_demand_signal",
                    "severity": "low",
                    "reason": "수요 보조 신호가 필요합니다.",
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-ROUTE-SIGNAL",
                    "source_item_title": "대전 중앙시장 야간 미식 투어",
                    "suggested_source_family": "kto_tourism_bigdata",
                    "needs_review": True,
                },
            ]
        }
        plan = {
            "planned_calls": [
                {
                    "id": "plan:route:test",
                    "source_family": "kto_durunubi",
                    "tool_name": "kto_durunubi_course_list",
                    "operation": "courseList",
                    "gap_ids": ["gap:missing_route_context:phase12"],
                    "gap_types": ["missing_route_context"],
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-ROUTE-SIGNAL",
                    "reason": "동선 후보를 확인합니다.",
                    "arguments": {"item_id": item_id, "content_id": "TEST-PHASE12-ROUTE-SIGNAL", "query": "대전 원도심", "limit": 2},
                },
                {
                    "id": "plan:signal:test",
                    "source_family": "kto_tourism_bigdata",
                    "tool_name": "kto_tourism_bigdata_locgo_visitors",
                    "operation": "locgoRegnVisitrDDList",
                    "gap_ids": ["gap:missing_demand_signal:phase12"],
                    "gap_types": ["missing_demand_signal"],
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-ROUTE-SIGNAL",
                    "reason": "수요 신호를 확인합니다.",
                    "arguments": {"item_id": item_id, "content_id": "TEST-PHASE12-ROUTE-SIGNAL", "limit": 2},
                },
            ],
            "skipped_calls": [],
        }
        enrichment_run = create_enrichment_run(
            db=db,
            workflow_run_id="",
            gap_report=gap_report,
            plan=plan,
        )
        summary = execute_enrichment_plan(
            db=db,
            provider=DetailProvider(),
            route_signal_provider=RouteSignalProvider(),
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

        entity_id = "entity:tourapi:content:TEST-PHASE12-ROUTE-SIGNAL"
        route_asset = db.query(models.TourismRouteAsset).filter_by(entity_id=entity_id).one()
        signal_record = db.query(models.TourismSignalRecord).filter_by(entity_id=entity_id).one()
        route_doc = db.query(models.SourceDocument).filter_by(source_item_id=item_id, source="kto_durunubi").one()
        signal_doc = db.query(models.SourceDocument).filter_by(source_item_id=item_id, source="kto_tourism_bigdata").one()

        assert summary["executed_calls"] == 2
        assert summary["route_assets"] == 1
        assert summary["signal_records"] == 1
        assert route_asset.source_family == "kto_durunubi"
        assert signal_record.signal_type == "visitor_demand"
        assert route_doc.document_metadata["content_type"] == "route"
        assert signal_doc.document_metadata["content_type"] == "signal"
        entity = fusion["evidence_profile"]["entities"][0]
        assert entity["route_asset_count"] == 1
        assert entity["signal_record_count"] == 1
        assert fusion["unresolved_gaps"] == []
        card = fusion["productization_advice"]["candidate_evidence_cards"][0]
        assert card["route_assets"][0]["source_family"] == "kto_durunubi"
        assert card["signal_records"][0]["signal_type"] == "visitor_demand"
        assert any("판매량" in claim for claim in card["restricted_claims"])


def test_route_signal_api_failure_records_failed_call_without_breaking_workflow():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase12:route-failed"
    source_item = _source_item(item_id=item_id, content_id="TEST-PHASE12-ROUTE-FAILED")
    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()

        plan = {
            "planned_calls": [
                {
                    "id": "plan:route:failed",
                    "source_family": "kto_durunubi",
                    "tool_name": "kto_durunubi_course_list",
                    "operation": "courseList",
                    "gap_ids": ["gap:missing_route_context:failed"],
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-ROUTE-FAILED",
                    "reason": "동선 후보를 확인합니다.",
                    "arguments": {"item_id": item_id, "content_id": "TEST-PHASE12-ROUTE-FAILED", "query": "대전", "limit": 2},
                }
            ],
            "skipped_calls": [],
        }
        enrichment_run = create_enrichment_run(
            db=db,
            workflow_run_id="",
            gap_report={"gaps": []},
            plan=plan,
        )
        summary = execute_enrichment_plan(
            db=db,
            provider=DetailProvider(),
            route_signal_provider=FailingRouteSignalProvider(),
            enrichment_run=enrichment_run,
            source_items=[source_item],
            run_id="",
            step_id=None,
        )

        assert summary["failed_calls"] == 1
        assert enrichment_run.status == "completed_with_errors"
        assert enrichment_run.tool_calls[0].status == "failed"
        assert enrichment_run.tool_calls[0].error["message"] == "courseList unavailable"


def test_theme_capabilities_are_workflow_enabled_only_when_flags_are_on():
    disabled = list_kto_capabilities(
        Settings(
            tourapi_service_key="test-key",
            kto_wellness_enabled=False,
            kto_pet_enabled=False,
            kto_audio_enabled=False,
            kto_eco_enabled=False,
            allow_medical_api=False,
        )
    )
    disabled_by_family = {item["source_family"]: item for item in disabled}

    enabled = list_kto_capabilities(
        Settings(
            tourapi_service_key="test-key",
            kto_wellness_enabled=True,
            kto_pet_enabled=True,
            kto_audio_enabled=True,
            kto_eco_enabled=True,
            allow_medical_api=False,
        )
    )
    enabled_by_family = {item["source_family"]: item for item in enabled}

    for family in ["kto_wellness", "kto_pet", "kto_audio", "kto_eco"]:
        assert not disabled_by_family[family]["enabled"]
        assert not any(op["workflow_enabled"] for op in disabled_by_family[family]["operations"])
        assert enabled_by_family[family]["enabled"]
        assert any(op["workflow_enabled"] for op in enabled_by_family[family]["operations"])

    assert not enabled_by_family["kto_medical"]["enabled"]
    assert not any(op["workflow_enabled"] for op in enabled_by_family["kto_medical"]["operations"])

    medical_enabled = list_kto_capabilities(
        Settings(tourapi_service_key="test-key", allow_medical_api=True)
    )
    medical = {item["source_family"]: item for item in medical_enabled}["kto_medical"]
    assert medical["enabled"]
    assert any(
        op["tool_name"] == "kto_medical_keyword_search" and op["workflow_enabled"]
        for op in medical["operations"]
    )


def test_theme_planner_executes_enabled_source_family_and_respects_budget():
    gap_report = {
        "gaps": [
            {
                "id": "gap:missing_pet_policy:request",
                "gap_type": "missing_pet_policy",
                "severity": "medium",
                "reason": "반려동물 동반 조건 근거가 필요합니다.",
                "target_item_id": "item-1",
                "target_content_id": "CID-1",
                "source_item_title": "대전 중앙시장 야간 미식 투어",
                "suggested_source_family": "kto_pet",
                "needs_review": True,
            },
            {
                "id": "gap:missing_wellness_attributes:request",
                "gap_type": "missing_wellness_attributes",
                "severity": "low",
                "reason": "웰니스 속성 근거가 필요합니다.",
                "target_item_id": "item-1",
                "target_content_id": "CID-1",
                "source_item_title": "대전 중앙시장 야간 미식 투어",
                "suggested_source_family": "kto_wellness",
                "needs_review": True,
            },
        ]
    }
    capability_routing = {
        "family_routes": [
            {
                "planner": "theme_data",
                "gap_ids": [
                    "gap:missing_pet_policy:request",
                    "gap:missing_wellness_attributes:request",
                ],
                "source_families": ["kto_pet", "kto_wellness"],
                "reason": "theme planner로 보냅니다.",
            }
        ]
    }

    fragment = normalize_family_planner_payload(
        {"planned_calls": [], "skipped_calls": []},
        planner_key="theme_data",
        capability_routing=capability_routing,
        gap_report=gap_report,
        settings=Settings(
            tourapi_service_key="test-key",
            kto_pet_enabled=True,
            kto_wellness_enabled=True,
        ),
        max_call_budget=1,
    )

    assert len(fragment["planned_calls"]) == 1
    assert len(fragment["skipped_calls"]) == 1
    assert fragment["planned_calls"][0]["source_family"] == "kto_pet"
    assert fragment["planned_calls"][0]["tool_name"] == "kto_pet_keyword_search"
    assert fragment["skipped_calls"][0]["skip_reason"] == "max_call_budget_exceeded"


def test_theme_planner_recovers_executable_gap_from_bad_future_skip():
    gap_report = {
        "gaps": [
            {
                "id": "gap:missing_multilingual_story:request",
                "gap_type": "missing_multilingual_story",
                "severity": "low",
                "reason": "외국인 대상 요청이라 오디오/스토리 후보가 필요합니다.",
                "target_item_id": "",
                "target_content_id": "",
                "source_item_title": "해운대 야간 관광",
                "suggested_source_family": "kto_audio",
                "needs_review": True,
            }
        ]
    }
    capability_routing = {
        "family_routes": [
            {
                "planner": "theme_data",
                "gap_ids": ["gap:missing_multilingual_story:request"],
                "source_families": ["kto_audio"],
                "reason": "theme planner로 보냅니다.",
            }
        ]
    }

    fragment = normalize_family_planner_payload(
        {
            "planned_calls": [],
            "skipped_calls": [
                {
                    "gap_ids": ["gap:missing_multilingual_story:request"],
                    "source_family": "kto_audio",
                    "skip_reason": "future_provider_not_implemented",
                }
            ],
        },
        planner_key="theme_data",
        capability_routing=capability_routing,
        gap_report=gap_report,
        settings=Settings(
            tourapi_service_key="test-key",
            kto_audio_enabled=True,
        ),
        max_call_budget=1,
    )

    assert len(fragment["planned_calls"]) == 1
    assert fragment["planned_calls"][0]["source_family"] == "kto_audio"
    assert fragment["planned_calls"][0]["tool_name"] == "kto_audio_story_search"
    assert fragment["skipped_calls"] == []


def test_theme_enrichment_saves_candidates_entities_visuals_source_documents_and_fusion():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase12:theme"
    source_item = _source_item(item_id=item_id, content_id="TEST-PHASE12-THEME")
    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()

        gap_report = {
            "gaps": [
                {
                    "id": "gap:missing_pet_policy:phase12",
                    "gap_type": "missing_pet_policy",
                    "severity": "medium",
                    "reason": "반려동물 동반 조건 근거가 필요합니다.",
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-THEME",
                    "source_item_title": "대전 중앙시장 야간 미식 투어",
                    "suggested_source_family": "kto_pet",
                    "needs_review": True,
                },
            ]
        }
        plan = {
            "planned_calls": [
                {
                    "id": "plan:theme:test",
                    "source_family": "kto_pet",
                    "tool_name": "kto_pet_keyword_search",
                    "operation": "searchKeyword2",
                    "gap_ids": ["gap:missing_pet_policy:phase12"],
                    "gap_types": ["missing_pet_policy"],
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-THEME",
                    "reason": "반려동물 테마 후보를 확인합니다.",
                    "arguments": {"item_id": item_id, "content_id": "TEST-PHASE12-THEME", "query": "대전 중앙시장", "limit": 2},
                }
            ],
            "skipped_calls": [],
        }
        enrichment_run = create_enrichment_run(
            db=db,
            workflow_run_id="",
            gap_report=gap_report,
            plan=plan,
        )
        summary = execute_enrichment_plan(
            db=db,
            provider=DetailProvider(),
            theme_provider=ThemeProvider(),
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

        document = db.query(models.SourceDocument).filter_by(source_item_id=item_id, source="kto_pet").one()
        entity = db.query(models.TourismEntity).filter_by(primary_source_item_id=item_id).one()
        visual = db.query(models.TourismVisualAsset).filter_by(source_item_id=item_id, source_family="kto_pet").one()

        assert summary["executed_calls"] == 1
        assert summary["theme_candidates"] == 1
        assert summary["visual_assets"] == 1
        assert document.document_metadata["content_type"] == "theme"
        assert document.document_metadata["theme_source_family"] == "kto_pet"
        assert entity.entity_metadata["source_family"] == "kto_pet"
        assert visual.usage_status == "needs_license_review"

        fused_entity = fusion["evidence_profile"]["entities"][0]
        assert fused_entity["theme_candidate_count"] == 1
        assert fusion["unresolved_gaps"] == []
        card = fusion["productization_advice"]["candidate_evidence_cards"][0]
        assert card["theme_candidates"][0]["source_family"] == "kto_pet"
        assert any("반려동물" in claim for claim in card["restricted_claims"])


def test_theme_api_failure_records_failed_call_without_breaking_workflow():
    with TestClient(app):
        pass

    item_id = "tourapi:test:phase12:theme-failed"
    source_item = _source_item(item_id=item_id, content_id="TEST-PHASE12-THEME-FAILED")
    with SessionLocal() as db:
        db.merge(models.TourismItem(**source_item))
        db.commit()

        plan = {
            "planned_calls": [
                {
                    "id": "plan:theme:failed",
                    "source_family": "kto_pet",
                    "tool_name": "kto_pet_keyword_search",
                    "operation": "searchKeyword2",
                    "gap_ids": ["gap:missing_pet_policy:failed"],
                    "target_item_id": item_id,
                    "target_content_id": "TEST-PHASE12-THEME-FAILED",
                    "reason": "반려동물 테마 후보를 확인합니다.",
                    "arguments": {"item_id": item_id, "content_id": "TEST-PHASE12-THEME-FAILED", "query": "대전", "limit": 2},
                }
            ],
            "skipped_calls": [],
        }
        enrichment_run = create_enrichment_run(
            db=db,
            workflow_run_id="",
            gap_report={"gaps": []},
            plan=plan,
        )
        summary = execute_enrichment_plan(
            db=db,
            provider=DetailProvider(),
            theme_provider=FailingThemeProvider(),
            enrichment_run=enrichment_run,
            source_items=[source_item],
            run_id="",
            step_id=None,
        )

        assert summary["failed_calls"] == 1
        assert enrichment_run.status == "completed_with_errors"
        assert enrichment_run.tool_calls[0].status == "failed"
        assert enrichment_run.tool_calls[0].error["message"] == "searchKeyword2 unavailable"


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
