from __future__ import annotations

import time
import json
from collections import defaultdict
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import models
from app.rag.chroma_store import index_source_documents
from app.rag.source_documents import upsert_source_documents_from_items
from app.tools.kto_capabilities import list_kto_capabilities
from app.tools.route_signals import (
    RouteSignalProvider,
    execute_route_signal_search,
    get_route_signal_provider,
)
from app.tools.themes import ThemeDataProvider, execute_theme_search, get_theme_provider
from app.tools.tourism import TourismDataProvider
from app.tools.tourism_enrichment import (
    detail_info_to_lines,
    detail_intro_to_lines,
    enrich_items_with_tourapi_details,
)
from app.tools.visuals import VisualDataProvider, execute_visual_search, get_visual_provider


DETAIL_GAP_TYPES = {
    "missing_detail_info",
    "missing_operating_hours",
    "missing_price_or_fee",
    "missing_booking_info",
    "missing_image_asset",
}
VISUAL_SOURCE_FAMILIES = {"kto_tourism_photo", "kto_photo_contest"}
VISUAL_GAP_TYPES = {"missing_image_asset", "missing_visual_reference"}
ROUTE_SIGNAL_SOURCE_FAMILIES = {
    "kto_durunubi",
    "kto_related_places",
    "kto_tourism_bigdata",
    "kto_crowding_forecast",
    "kto_regional_tourism_demand",
}
ROUTE_SIGNAL_GAP_TYPES = {
    "missing_route_context",
    "missing_related_places",
    "missing_demand_signal",
    "missing_crowding_signal",
    "missing_regional_demand_signal",
}
THEME_SOURCE_FAMILIES = {"kto_wellness", "kto_pet", "kto_audio", "kto_eco", "kto_medical"}
THEME_GAP_TYPES = {
    "missing_theme_specific_data",
    "missing_pet_policy",
    "missing_wellness_attributes",
    "missing_medical_context",
    "missing_story_asset",
    "missing_sustainability_context",
    "missing_multilingual_story",
}

DATA_GAP_PROFILE_MAX_GAPS = 24
DATA_GAP_PROFILE_MAX_NEEDS_REVIEW = 8

GAP_TYPE_ALIASES = {
    "missing_overview": "missing_detail_info",
}

FUTURE_SOURCE_BY_GAP = {
    "missing_related_places": "kto_related_places",
    "missing_route_context": "kto_durunubi",
    "missing_demand_signal": "kto_tourism_bigdata",
    "missing_crowding_signal": "kto_crowding_forecast",
    "missing_regional_demand_signal": "kto_regional_tourism_demand",
    "missing_theme_specific_data": "kto_wellness",
    "missing_pet_policy": "kto_pet",
    "missing_wellness_attributes": "kto_wellness",
    "missing_story_asset": "kto_audio",
    "missing_multilingual_story": "kto_audio",
    "missing_sustainability_context": "kto_eco",
    "missing_medical_context": "kto_medical",
}

THEME_SOURCE_HINTS = {
    "반려": "kto_pet",
    "펫": "kto_pet",
    "강아지": "kto_pet",
    "웰니스": "kto_wellness",
    "힐링": "kto_wellness",
    "오디오": "kto_audio",
    "해설": "kto_audio",
    "생태": "kto_eco",
    "친환경": "kto_eco",
    "의료": "kto_medical",
    "메디컬": "kto_medical",
}

PLANNER_DEFINITIONS: dict[str, dict[str, Any]] = {
    "tourapi_detail": {
        "agent_name": "TourApiDetailPlannerAgent",
        "purpose": "tourapi_detail_planning",
        "display_name": "KorService2 상세 Planner",
        "source_families": ["kto_tourapi_kor"],
        "gap_types": sorted(DETAIL_GAP_TYPES),
        "phase10_2_execution": "implemented",
    },
    "visual_data": {
        "agent_name": "VisualDataPlannerAgent",
        "purpose": "visual_data_planning",
        "display_name": "시각 자료 Planner",
        "source_families": ["kto_tourism_photo", "kto_photo_contest"],
        "gap_types": ["missing_image_asset", "missing_visual_reference"],
        "phase10_2_execution": "implemented_when_enabled",
    },
    "route_signal": {
        "agent_name": "RouteSignalPlannerAgent",
        "purpose": "route_signal_planning",
        "display_name": "동선/신호 Planner",
        "source_families": [
            "kto_durunubi",
            "kto_related_places",
            "kto_tourism_bigdata",
            "kto_crowding_forecast",
            "kto_regional_tourism_demand",
        ],
        "gap_types": [
            "missing_route_context",
            "missing_related_places",
            "missing_demand_signal",
            "missing_crowding_signal",
            "missing_regional_demand_signal",
        ],
        "phase10_2_execution": "phase12_2_implemented_when_enabled",
    },
    "theme_data": {
        "agent_name": "ThemeDataPlannerAgent",
        "purpose": "theme_data_planning",
        "display_name": "테마 데이터 Planner",
        "source_families": ["kto_wellness", "kto_pet", "kto_audio", "kto_eco", "kto_medical"],
        "gap_types": [
            "missing_theme_specific_data",
            "missing_pet_policy",
            "missing_wellness_attributes",
            "missing_medical_context",
            "missing_story_asset",
            "missing_sustainability_context",
            "missing_multilingual_story",
        ],
        "phase10_2_execution": "phase12_3_implemented_when_enabled",
    },
}

GAP_TYPES = {
    "missing_detail_info",
    "missing_image_asset",
    "missing_operating_hours",
    "missing_price_or_fee",
    "missing_booking_info",
    "missing_related_places",
    "missing_route_context",
    "missing_theme_specific_data",
    "missing_pet_policy",
    "missing_wellness_attributes",
    "missing_medical_context",
    "missing_story_asset",
    "missing_sustainability_context",
    "missing_demand_signal",
    "missing_crowding_signal",
    "missing_regional_demand_signal",
    "missing_visual_reference",
    "missing_multilingual_story",
}

KTO_API_CAPABILITY_MATRIX: list[dict[str, Any]] = [
    {
        "source_family": "kto_tourapi_kor",
        "document": "99_01_KTO_TOURAPI_KORSERVICE2_V44_SPEC.md",
        "operations": [
            "areaBasedList2",
            "locationBasedList2",
            "searchKeyword2",
            "searchFestival2",
            "searchStay2",
            "detailCommon2",
            "detailIntro2",
            "detailInfo2",
            "detailImage2",
            "detailPetTour2",
        ],
        "fills_gaps": [
            "missing_detail_info",
            "missing_image_asset",
            "missing_operating_hours",
            "missing_price_or_fee",
            "missing_booking_info",
            "missing_related_places",
            "missing_pet_policy",
        ],
        "request_fields": [
            "contentId",
            "contentTypeId",
            "lDongRegnCd",
            "lDongSignguCd",
            "lclsSystm1/2/3",
            "mapX/mapY",
            "eventStartDate",
            "eventEndDate",
        ],
        "response_fields": [
            "title",
            "addr1/addr2",
            "overview",
            "homepage",
            "tel",
            "mapx/mapy",
            "firstimage",
            "infoname/infotext",
            "originimgurl/smallimageurl",
            "cpyrhtDivCd",
        ],
        "db_targets": ["tourism_items", "tourism_entities", "tourism_visual_assets", "source_documents"],
        "ui_use": "장소 기본정보, 상세 이용조건, 이미지 후보, 운영자 확인 필요 항목을 표시합니다.",
        "phase10_2_status": "implemented",
    },
    {
        "source_family": "kto_photo_contest",
        "document": "99_02_KTO_PHOTO_CONTEST_AWARD_SPEC.md",
        "operations": ["ldongCode", "phokoAwrdList", "phokoAwrdSyncList"],
        "fills_gaps": ["missing_image_asset", "missing_visual_reference"],
        "request_fields": ["keyword", "lDongRegnCd", "numOfRows", "pageNo"],
        "response_fields": ["koTitle", "koFilmst", "filmDay", "koCmanNm", "koKeyWord", "orgImage", "thumbImage", "cpyrhtDivCd"],
        "db_targets": ["tourism_visual_assets", "source_documents"],
        "ui_use": "게시 후보가 아니라 시각 참고/이미지 후보로 표시하고 저작권 확인을 요구합니다.",
        "phase10_2_status": "phase12_1_implemented_when_enabled",
    },
    {
        "source_family": "kto_wellness",
        "document": "99_03_KTO_WELLNESS_TOURISM_SPEC.md",
        "operations": [
            "areaBasedList",
            "locationBasedList",
            "searchKeyword",
            "wellnessTursmSyncList",
            "detailCommon",
            "detailIntro",
            "detailInfo",
            "detailImage",
        ],
        "fills_gaps": [
            "missing_theme_specific_data",
            "missing_wellness_attributes",
            "missing_image_asset",
            "missing_operating_hours",
            "missing_price_or_fee",
            "missing_booking_info",
        ],
        "request_fields": ["지역, 좌표, 키워드, contentId"],
        "response_fields": ["baseAddr", "mapX/mapY", "orgImage", "thumbImage", "operationtime*", "detail info"],
        "db_targets": ["tourism_entities", "tourism_visual_assets", "source_documents"],
        "ui_use": "웰니스 테마 적합성과 운영 조건을 표시하되 건강효능 claim은 금지합니다.",
        "phase10_2_status": "phase12_3_implemented_when_enabled",
    },
    {
        "source_family": "kto_medical",
        "document": "99_04_KTO_MEDICAL_TOURISM_SPEC.md",
        "operations": [
            "areaBasedList",
            "locationBasedList",
            "searchKeyword",
            "mdclTursmSyncList",
            "detailCommon",
            "detailIntro",
            "detailMdclTursm",
            "detailInfo",
            "detailImage",
        ],
        "fills_gaps": ["missing_theme_specific_data", "missing_medical_context", "missing_image_asset"],
        "request_fields": ["지역, 좌표, 키워드, contentId"],
        "response_fields": ["baseAddr", "mapX/mapY", "detailMdclTursm fields", "orgImage", "thumbImage"],
        "db_targets": ["tourism_entities", "source_documents", "tourism_visual_assets"],
        "ui_use": "고위험 의료관광 근거로 분리 표시하고 allow_medical_api가 꺼져 있으면 호출하지 않습니다.",
        "phase10_2_status": "phase12_3_medical_flag_required",
    },
    {
        "source_family": "kto_pet",
        "document": "99_05_KTO_PET_TOUR_SPEC.md",
        "operations": [
            "areaBasedList2",
            "searchKeyword2",
            "locationBasedList2",
            "detailCommon2",
            "detailIntro2",
            "detailInfo2",
            "detailImage2",
            "detailPetTour2",
        ],
        "fills_gaps": [
            "missing_theme_specific_data",
            "missing_pet_policy",
            "missing_image_asset",
            "missing_operating_hours",
            "missing_price_or_fee",
            "missing_booking_info",
        ],
        "request_fields": ["areaCode/lDong, keyword, mapx/mapy, contentId/contentTypeId"],
        "response_fields": ["addr1", "mapx/mapy", "detailIntro2 pet fields", "detailPetTour2 fields"],
        "db_targets": ["tourism_entities", "source_documents", "tourism_visual_assets"],
        "ui_use": "반려동물 동반 가능 조건, 제한, 필요사항을 운영 확인 항목으로 표시합니다.",
        "phase10_2_status": "phase12_3_implemented_when_enabled",
    },
    {
        "source_family": "kto_durunubi",
        "document": "99_06_KTO_DURUNUBI_SPEC.md",
        "operations": ["courseList", "routeList"],
        "fills_gaps": ["missing_route_context", "missing_route_asset"],
        "request_fields": ["지역/코스 조건, paging"],
        "response_fields": ["course name", "distance", "difficulty", "route/path fields"],
        "db_targets": ["tourism_route_assets", "source_documents"],
        "ui_use": "route형 상품의 거리, 난이도, 코스 근거로 표시합니다.",
        "phase10_2_status": "phase12_2_implemented_when_enabled",
    },
    {
        "source_family": "kto_audio",
        "document": "99_07_KTO_AUDIO_GUIDE_SPEC.md",
        "operations": [
            "themeBasedList",
            "themeLocationBasedList",
            "themeSearchList",
            "storyBasedList",
            "storyLocationBasedList",
            "storySearchList",
        ],
        "fills_gaps": ["missing_story_asset", "missing_multilingual_story", "missing_theme_specific_data"],
        "request_fields": ["theme, location, keyword, paging"],
        "response_fields": ["title", "script/story summary", "audio/image URL", "language fields"],
        "db_targets": ["source_documents", "tourism_entities"],
        "ui_use": "스토리텔링/해설 후보로 요약 표시하고 원문 장문 복제는 피합니다.",
        "phase10_2_status": "phase12_3_implemented_when_enabled",
    },
    {
        "source_family": "kto_eco",
        "document": "99_08_KTO_ECO_TOURISM_SPEC.md",
        "operations": ["areaBasedList1", "areaBasedSyncList1", "areaCode1"],
        "fills_gaps": ["missing_sustainability_context", "missing_theme_specific_data"],
        "request_fields": ["areaCode, paging"],
        "response_fields": ["생태 관광명, 주소/지역, 설명 계열 field"],
        "db_targets": ["tourism_entities", "source_documents"],
        "ui_use": "생태/친환경 테마 적합성만 표시하고 정량 ESG 효과는 claim하지 않습니다.",
        "phase10_2_status": "phase12_3_implemented_when_enabled",
    },
    {
        "source_family": "kto_tourism_photo",
        "document": "99_09_KTO_TOURISM_PHOTO_SPEC.md",
        "operations": ["galleryList1", "galleryDetailList1", "gallerySyncDetailList1", "gallerySearchList1"],
        "fills_gaps": ["missing_image_asset", "missing_visual_reference"],
        "request_fields": ["keyword, gallery id, paging"],
        "response_fields": ["galTitle", "galPhotographyLocation", "galWebImageUrl", "galSearchKeyword"],
        "db_targets": ["tourism_visual_assets", "source_documents"],
        "ui_use": "상세페이지/포스터 시각 후보로 표시하고 사용 조건 확인을 요구합니다.",
        "phase10_2_status": "phase12_1_implemented_when_enabled",
    },
    {
        "source_family": "kto_tourism_bigdata",
        "document": "99_10_KTO_TOURISM_BIGDATA_SPEC.md",
        "operations": ["metcoRegnVisitrDDList", "locgoRegnVisitrDDList"],
        "fills_gaps": ["missing_demand_signal"],
        "request_fields": ["광역/기초 지자체, 일자/기간"],
        "response_fields": ["방문자수/집계 일자/지역 코드"],
        "db_targets": ["tourism_signal_records", "source_documents"],
        "ui_use": "수요 신호와 후보 ranking 보조 지표로 표시하되 판매량으로 단정하지 않습니다.",
        "phase10_2_status": "phase12_2_implemented_when_enabled",
    },
    {
        "source_family": "kto_crowding_forecast",
        "document": "99_11_KTO_CROWDING_FORECAST_SPEC.md",
        "operations": ["tatsCnctrRatedList"],
        "fills_gaps": ["missing_crowding_signal"],
        "request_fields": ["관광지/예측 기준, paging"],
        "response_fields": ["향후 30일 집중률/혼잡 예측 field"],
        "db_targets": ["tourism_signal_records", "source_documents"],
        "ui_use": "혼잡 리스크와 대체 시간 검토 신호로 표시합니다.",
        "phase10_2_status": "phase12_2_implemented_when_enabled",
    },
    {
        "source_family": "kto_related_places",
        "document": "99_12_KTO_RELATED_PLACES_SPEC.md",
        "operations": ["areaBasedList1", "searchKeyword1"],
        "fills_gaps": ["missing_related_places", "missing_route_context"],
        "request_fields": ["지역, 키워드, paging"],
        "response_fields": ["관광지명, 연관 순위/분류/지역 fields"],
        "db_targets": ["tourism_signal_records", "tourism_entities", "source_documents"],
        "ui_use": "주변/대체 후보와 코스 확장 근거로 표시합니다.",
        "phase10_2_status": "phase12_2_implemented_when_enabled",
    },
    {
        "source_family": "kto_regional_tourism_demand",
        "document": "99_13_KTO_REGIONAL_TOURISM_DEMAND_SPEC.md",
        "operations": ["areaTarSvcDemList", "areaCulResDemList"],
        "fills_gaps": ["missing_regional_demand_signal", "missing_demand_signal"],
        "request_fields": ["지역, paging"],
        "response_fields": ["관광 서비스 수요, 문화 자원 수요 fields"],
        "db_targets": ["tourism_signal_records", "source_documents"],
        "ui_use": "지역 매력도와 수요 보조 신호로 표시하되 예약/판매 가능성으로 단정하지 않습니다.",
        "phase10_2_status": "phase12_2_implemented_when_enabled",
    },
]

DATA_GAP_PROFILE_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["gaps", "coverage", "reasoning_summary", "needs_review"],
    "properties": {
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "gap_type", "severity", "reason", "suggested_source_family", "needs_review"],
                "properties": {
                    "id": {"type": "string"},
                    "gap_type": {"type": "string"},
                    "severity": {"type": "string"},
                    "reason": {"type": "string"},
                    "target_entity_id": {"type": "string"},
                    "target_content_id": {"type": "string"},
                    "target_item_id": {"type": "string"},
                    "source_item_title": {"type": "string"},
                    "suggested_source_family": {"type": "string"},
                    "needs_review": {"type": "boolean"},
                    "productization_impact": {"type": "string"},
                },
            },
        },
        "coverage": {"type": "object"},
        "reasoning_summary": {"type": "string"},
        "needs_review": {"type": "array", "items": {"type": "string"}},
    },
}

API_CAPABILITY_ROUTING_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["family_routes", "routing_reasoning"],
    "properties": {
        "family_routes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["planner", "gap_ids", "source_families", "reason"],
                "properties": {
                    "planner": {"type": "string"},
                    "gap_ids": {"type": "array", "items": {"type": "string"}},
                    "source_families": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "priority": {"type": "string"},
                },
            },
        },
        "skipped_routes": {"type": "array", "items": {"type": "object"}},
        "routing_reasoning": {"type": "string"},
    },
}

API_FAMILY_PLANNER_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["planned_calls", "skipped_calls", "budget_summary", "planning_reasoning"],
    "properties": {
        "planned_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "source_family", "tool_name", "operation", "gap_ids", "reason", "arguments"],
                "properties": {
                    "id": {"type": "string"},
                    "source_family": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "operation": {"type": "string"},
                    "gap_ids": {"type": "array", "items": {"type": "string"}},
                    "gap_types": {"type": "array", "items": {"type": "string"}},
                    "target_item_id": {"type": "string"},
                    "target_content_id": {"type": "string"},
                    "target_entity_id": {"type": "string"},
                    "reason": {"type": "string"},
                    "expected_ui": {"type": "string"},
                    "arguments": {"type": "object"},
                },
            },
        },
        "skipped_calls": {"type": "array", "items": {"type": "object"}},
        "budget_summary": {"type": "object"},
        "planning_reasoning": {"type": "string"},
    },
}

TOURAPI_DETAIL_PLANNER_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["selected_targets", "skipped_gap_ids", "planning_reasoning"],
    "properties": {
        "selected_targets": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["target_item_id", "target_content_id", "gap_ids", "priority", "reason"],
                "properties": {
                    "target_item_id": {"type": "string"},
                    "target_content_id": {"type": "string"},
                    "gap_ids": {"type": "array", "items": {"type": "string"}},
                    "priority": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "skipped_gap_ids": {"type": "array", "items": {"type": "string"}},
        "planning_reasoning": {"type": "string"},
    },
}

EVIDENCE_FUSION_RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "productization_advice",
        "unresolved_gaps",
        "source_confidence",
        "ui_highlights",
    ],
    "properties": {
        "evidence_profile": {"type": "object"},
        "productization_advice": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "candidate_interpretations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content_id": {"type": "string"},
                            "source_item_id": {"type": "string"},
                            "title": {"type": "string"},
                            "priority": {"type": "string"},
                            "product_angle": {"type": "string"},
                            "rationale": {"type": "string"},
                            "experience_hooks": {"type": "array", "items": {"type": "string"}},
                            "recommended_product_angles": {"type": "array", "items": {"type": "string"}},
                            "use_with_caution": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "global_claim_policy": {"type": "object"},
                "usable_claims": {"type": "array", "items": {"type": "string"}},
                "restricted_claims": {"type": "array", "items": {"type": "string"}},
                "candidate_recommendations": {"type": "array", "items": {"type": "object"}},
                "needs_review_fields": {"type": "array", "items": {"type": "string"}},
            },
        },
        "data_coverage": {"type": "object"},
        "unresolved_gaps": {"type": "array", "items": {"type": "object"}},
        "source_confidence": {"type": "number"},
        "ui_highlights": {"type": "array", "items": {"type": "object"}},
    },
}


def capability_matrix_for_prompt(settings: Settings | None = None) -> list[dict[str, Any]]:
    runtime = {item["source_family"]: item for item in list_kto_capabilities(settings)}
    matrix: list[dict[str, Any]] = []
    for item in KTO_API_CAPABILITY_MATRIX:
        source_family = item["source_family"]
        runtime_item = runtime.get(source_family) or {}
        matrix.append(
            {
                **item,
                "runtime_enabled": bool(runtime_item.get("enabled")),
                "runtime_disabled_reasons": runtime_item.get("disabled_reasons") or [],
                "provider_implemented_operations": [
                    operation["operation"]
                    for operation in runtime_item.get("operations") or []
                    if operation.get("implemented")
                ],
                "workflow_enabled_operations": [
                    operation["operation"]
                    for operation in runtime_item.get("operations") or []
                    if operation.get("workflow_enabled")
                ],
            }
        )
    return matrix


def capability_brief_for_prompt(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    flags = {
        "사진 공모전/관광사진": settings.kto_photo_contest_enabled or settings.kto_tourism_photo_enabled,
        "두루누비/연관관광지/수요/혼잡 신호": (
            settings.kto_durunubi_enabled
            or settings.kto_related_places_enabled
            or settings.kto_bigdata_enabled
            or settings.kto_crowding_enabled
            or settings.kto_regional_tourism_demand_enabled
        ),
        "웰니스/반려동물/오디오/생태": (
            settings.kto_wellness_enabled
            or settings.kto_pet_enabled
            or settings.kto_audio_enabled
            or settings.kto_eco_enabled
        ),
        "의료관광": settings.allow_medical_api,
    }
    return "\n".join(
        [
            "KorService2 상세 API는 contentId/contentTypeId로 개요, 홈페이지, 문의처, 이용시간, 요금성 정보, 예약/이용 안내, 상세 이미지 후보를 보강할 수 있습니다. 현재 workflow에서 실제 실행 가능한 core 보강입니다.",
            "사진 공모전/관광사진 API는 장소나 지역 키워드로 시각 참고 이미지를 찾을 수 있습니다. KTO_TOURISM_PHOTO_ENABLED 또는 KTO_PHOTO_CONTEST_ENABLED가 켜져 있고 서비스키가 있으면 workflow에서 실제 이미지 후보를 조회합니다.",
            "두루누비, 연관관광지, 관광빅데이터, 혼잡 예측, 지역 관광수요 API는 동선, 주변 장소, 수요/혼잡 신호를 줄 수 있습니다. Phase 12.2부터 관련 feature flag와 서비스키가 있으면 workflow에서 실제 보조 근거를 조회합니다.",
            "웰니스, 반려동물, 오디오, 생태 API는 테마 특화 조건과 스토리 소재를 줄 수 있습니다. Phase 12.3부터 관련 feature flag와 서비스키가 있으면 workflow에서 실제 테마 후보를 조회합니다.",
            "의료관광 API는 고위험 정보이므로 allow_medical_api가 true일 때만 실제 호출하고, false이면 호출 대상으로 만들지 않습니다.",
            "현재 feature flag: "
            + ", ".join(f"{name}={'on' if enabled else 'off'}" for name, enabled in flags.items()),
        ]
    )


def select_enrichment_candidate_items(
    *,
    source_items: list[dict[str, Any]],
    retrieved_documents: list[dict[str, Any]],
    normalized_request: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return list(source_items)
    retrieved_rank = _retrieved_content_rank(retrieved_documents)
    scored = [
        (
            _candidate_relevance_score(item, normalized_request, retrieved_rank),
            index,
            item,
        )
        for index, item in enumerate(source_items)
    ]
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in scored[:limit]]


def summarize_candidate_pool(
    *,
    raw_source_items: list[dict[str, Any]],
    selected_items: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_by_type = _count_by_key(raw_source_items, "content_type")
    selected_by_type = _count_by_key(selected_items, "content_type")
    return {
        "raw_total": len(raw_source_items),
        "selected_total": len(selected_items),
        "raw_by_content_type": raw_by_type,
        "selected_by_content_type": selected_by_type,
        "selection_note": "raw TourAPI 후보 전체를 LLM에 넘기지 않고 요청 관련 후보 shortlist만 gap profiling/enrichment에 사용합니다.",
    }


def build_data_gap_profile_prompt(
    *,
    source_items: list[dict[str, Any]],
    retrieved_documents: list[dict[str, Any]],
    normalized_request: dict[str, Any],
    capability_brief: str,
    candidate_pool_summary: dict[str, Any] | None = None,
) -> str:
    max_gap_count = min(DATA_GAP_PROFILE_MAX_GAPS, max(8, len(source_items) + 4))
    context = {
        "역할": "DataGapProfilerAgent",
        "목표": "shortlist 후보를 보고 상품 기획에 필요한 근거 중 부족한 항목만 구조화합니다.",
        "사용자_요청": normalized_request,
        "후보_pool_요약": candidate_pool_summary or {},
        "source_items": [_compact_item(item) for item in source_items],
        "retrieved_documents": [_compact_document(doc) for doc in retrieved_documents[:10]],
        "api_capability_brief": capability_brief,
        "허용_gap_type": sorted(GAP_TYPES),
        "출력_상한": {
            "max_gap_count": max_gap_count,
            "max_item_level_gaps": min(len(source_items), max_gap_count),
            "max_request_level_gaps": 4,
            "max_needs_review": DATA_GAP_PROFILE_MAX_NEEDS_REVIEW,
        },
        "판단_기준": [
            "입력 source_items는 이미 raw 후보에서 추린 shortlist입니다. shortlist 밖 후보는 개별 gap으로 만들지 마세요.",
            "모든 후보의 누락 항목을 전부 펼치는 보고서가 아니라, 이후 API planner가 실행할 우선순위 gap report를 만듭니다.",
            "상품 상세페이지에 직접 노출할 수 있는 사실과 운영자가 확인해야 하는 정보를 분리하세요.",
            "요청 상품 유형과 무관한 gap을 만들지 마세요.",
            "근거에 없는 운영시간, 요금, 예약정보, 언어지원, 동선, 반려동물 정책을 추측하지 마세요.",
            "이미 상세 정보가 있으면 동일 gap을 반복 생성하지 마세요.",
            "같은 target_item_id에 여러 detail 계열 누락이 있으면 하나의 대표 gap만 만드세요. KorService2 상세 보강은 한 번의 호출로 상세/이미지/운영정보 후보를 함께 확인할 수 있습니다.",
            "overview가 없다는 이유만으로 missing_overview를 만들지 마세요. missing_overview는 허용 gap_type이 아닙니다. 개요/상세 설명 부족은 missing_detail_info로 통합하세요.",
            "낮은 심각도의 반복 gap은 개별 gaps로 모두 만들지 말고 coverage.gap_counts와 reasoning_summary에 요약하세요.",
            "코스/동선형 요청이면 route context가 필요한지 판단하세요.",
            "웰니스/반려동물/생태/오디오/의료 같은 테마 요청은 api_capability_brief에서 설명한 source family와 연결하세요.",
            "의료관광은 고위험 정보이므로 needs_review를 true로 두세요.",
        ],
        "출력_규칙": [
            f"gaps는 반드시 {max_gap_count}개 이하로 작성하세요. 이 상한을 넘기면 실패입니다.",
            "gaps[].id는 gap:<gap_type>:<target_item_id 또는 request> 형식으로 작성하세요.",
            "target_item_id는 입력 source_items에 실제 있는 id만 사용하세요. request-level gap이면 빈 문자열로 두세요.",
            "하나의 target_item_id에는 item-level gap을 최대 1개만 작성하세요.",
            "gap_type은 허용_gap_type 중 하나만 쓰세요. missing_overview는 절대 쓰지 마세요.",
            "severity는 high, medium, low 중 하나만 쓰세요.",
            "reason은 80자 이내, productization_impact는 100자 이내로 쓰세요.",
            "coverage에는 total_items, gap_count, detail_info_coverage, image_coverage, operating_hours_coverage, price_or_fee_coverage, booking_info_coverage, gap_counts를 포함하세요.",
            f"needs_review에는 운영자가 확인해야 하는 핵심 항목만 최대 {DATA_GAP_PROFILE_MAX_NEEDS_REVIEW}개 한국어 문장으로 넣으세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def build_api_capability_router_prompt(
    *,
    gap_report: dict[str, Any],
    capabilities: list[dict[str, Any]],
    settings: Settings,
    max_call_budget: int,
) -> str:
    context = {
        "역할": "ApiCapabilityRouterAgent",
        "목표": "data gap을 직접 API 호출 계획으로 만들지 말고, 담당 planner lane으로 분류합니다.",
        "gap_report_summary": _compact_gap_report_for_router(gap_report),
        "planner_lanes": _planner_lanes_for_prompt(capabilities),
        "max_call_budget_for_later_execution": max_call_budget,
        "feature_flags": {
            "tourapi_enabled": settings.tourapi_enabled,
            "kto_photo_contest_enabled": settings.kto_photo_contest_enabled,
            "kto_wellness_enabled": settings.kto_wellness_enabled,
            "kto_pet_enabled": settings.kto_pet_enabled,
            "kto_durunubi_enabled": settings.kto_durunubi_enabled,
            "kto_audio_enabled": settings.kto_audio_enabled,
            "kto_eco_enabled": settings.kto_eco_enabled,
            "kto_tourism_photo_enabled": settings.kto_tourism_photo_enabled,
            "kto_bigdata_enabled": settings.kto_bigdata_enabled,
            "kto_crowding_enabled": settings.kto_crowding_enabled,
            "kto_related_places_enabled": settings.kto_related_places_enabled,
            "kto_regional_tourism_demand_enabled": getattr(settings, "kto_regional_tourism_demand_enabled", False),
            "allow_medical_api": settings.allow_medical_api,
        },
        "라우팅_규칙": [
            "API endpoint와 arguments를 만들지 마세요. 그것은 각 planner가 담당합니다.",
            "각 gap_id를 가장 적절한 planner 하나에만 배정하세요.",
            "tourapi_detail은 실제 실행 가능한 KorService2 상세 보강 lane입니다.",
            "visual_data는 Phase 12.1부터 사진 공모전/관광사진 feature flag가 켜진 경우 실제 실행 가능한 lane입니다.",
            "route_signal은 Phase 12.2부터 feature flag와 서비스키가 있으면 실제 실행 가능한 lane입니다.",
            "theme_data는 Phase 12.3부터 feature flag와 서비스키가 있으면 실제 실행 가능한 lane입니다.",
            "의료관광 source family는 allow_medical_api가 false면 호출 대상으로 만들지 말고 비활성 route/skipped 이유를 남기세요.",
            "family_routes[].reason은 80자 이내, routing_reasoning은 240자 이내로 제한하세요.",
            "gap_report_summary.gaps에 없는 gap_id를 만들지 마세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def build_api_family_planner_prompt(
    *,
    planner_key: str,
    capability_routing: dict[str, Any],
    gap_report: dict[str, Any],
    capabilities: list[dict[str, Any]],
    settings: Settings,
    max_call_budget: int,
    existing_planned_count: int = 0,
) -> str:
    definition = PLANNER_DEFINITIONS[planner_key]
    route = _route_for_planner(capability_routing, planner_key)
    context = {
        "역할": definition["agent_name"],
        "목표": "배정된 gap만 보고 이 planner lane 안에서 필요한 보강 계획을 만듭니다.",
        "planner": {
            "key": planner_key,
            "display_name": definition["display_name"],
            "source_families": definition["source_families"],
            "gap_types": definition["gap_types"],
            "phase10_2_execution": definition["phase10_2_execution"],
        },
        "assigned_route": route,
        "assigned_gaps": _gaps_for_ids(gap_report, route.get("gap_ids") or []),
        "capabilities": _capabilities_for_families(capabilities, definition["source_families"]),
        "budget": {
            "max_call_budget": max_call_budget,
            "existing_planned_count": existing_planned_count,
            "remaining_budget": max(0, max_call_budget - existing_planned_count),
        },
        "feature_flags": {
            "tourapi_enabled": settings.tourapi_enabled,
            "allow_medical_api": settings.allow_medical_api,
            "kto_photo_contest_enabled": settings.kto_photo_contest_enabled,
            "kto_tourism_photo_enabled": settings.kto_tourism_photo_enabled,
            "kto_durunubi_enabled": settings.kto_durunubi_enabled,
            "kto_related_places_enabled": settings.kto_related_places_enabled,
            "kto_bigdata_enabled": settings.kto_bigdata_enabled,
            "kto_crowding_enabled": settings.kto_crowding_enabled,
            "kto_regional_tourism_demand_enabled": getattr(settings, "kto_regional_tourism_demand_enabled", False),
            "kto_wellness_enabled": settings.kto_wellness_enabled,
            "kto_pet_enabled": settings.kto_pet_enabled,
            "kto_audio_enabled": settings.kto_audio_enabled,
            "kto_eco_enabled": settings.kto_eco_enabled,
        },
        "출력_규칙": [
            "assigned_gaps에 있는 gap_id만 사용하세요.",
            "reason은 80자 이내, planning_reasoning은 240자 이내로 작성하세요.",
            "tourapi_detail planner는 실제 planned_calls를 만들 수 있습니다.",
            "tourapi_detail planned call은 tool_name=kto_tour_detail_enrichment, operation=detailCommon2/detailIntro2/detailInfo2/detailImage2로 묶으세요.",
            "visual_data planner는 KTO_TOURISM_PHOTO_ENABLED 또는 KTO_PHOTO_CONTEST_ENABLED가 켜진 source family에 대해서만 planned_calls를 만들 수 있습니다.",
            "visual_data planned call은 kto_tourism_photo_search/gallerySearchList1 또는 kto_photo_contest_award_list/phokoAwrdList 중 하나를 사용하세요.",
            "route_signal planner는 두루누비/연관관광지/수요/혼잡/지역수요 source family가 workflow_enabled이면 planned_calls를 만들 수 있습니다.",
            "route_signal planned call은 kto_durunubi_course_list/courseList, kto_related_places_keyword/searchKeyword1, kto_related_places_area/areaBasedList1, kto_tourism_bigdata_locgo_visitors/locgoRegnVisitrDDList, kto_tourism_bigdata_metco_visitors/metcoRegnVisitrDDList, kto_attraction_crowding_forecast/tatsCnctrRatedList, kto_regional_tourism_demand_area/areaTarSvcDemList 중 하나를 사용하세요.",
            "theme_data planner는 웰니스/반려동물/오디오/생태/의료 source family가 workflow_enabled이면 planned_calls를 만들 수 있습니다.",
            "theme_data planned call은 kto_wellness_keyword_search/searchKeyword, kto_pet_keyword_search/searchKeyword2, kto_audio_story_search/storySearchList, kto_audio_theme_search/themeSearchList, kto_eco_area_search/areaBasedList1, kto_medical_keyword_search/searchKeyword 중 하나를 사용하세요.",
            "의료관광은 allow_medical_api가 false이면 반드시 skipped_calls에 feature_flag_disabled로 남기세요.",
            "remaining_budget을 넘기지 마세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def build_tourapi_detail_planner_prompt(
    *,
    capability_routing: dict[str, Any],
    gap_report: dict[str, Any],
    max_call_budget: int,
    existing_planned_count: int = 0,
) -> str:
    route = _route_for_planner(capability_routing, "tourapi_detail")
    assigned_gaps = _gaps_for_ids(gap_report, route.get("gap_ids") or [])
    remaining_budget = max(0, max_call_budget - existing_planned_count)
    candidates = _detail_target_candidates(assigned_gaps)
    request_level_gaps = [
        {
            "id": gap.get("id"),
            "gap_type": gap.get("gap_type"),
            "reason": str(gap.get("reason") or "")[:120],
        }
        for gap in assigned_gaps
        if not (gap.get("target_item_id") or gap.get("target_content_id"))
    ]
    context = {
        "역할": "TourApiDetailPlannerAgent",
        "목표": "KorService2 상세 보강을 실행할 대상만 짧게 고릅니다. 전체 tool call JSON은 쓰지 않습니다.",
        "assigned_route": {
            "planner": route.get("planner"),
            "reason": str(route.get("reason") or "")[:120],
            "priority": route.get("priority"),
            "assigned_gap_count": len(route.get("gap_ids") or []),
        },
        "candidate_targets": candidates,
        "request_level_gaps": request_level_gaps,
        "budget": {
            "max_call_budget": max_call_budget,
            "existing_planned_count": existing_planned_count,
            "remaining_budget": remaining_budget,
        },
        "실행_가능_범위": [
            "Phase 10.2에서 실제 실행 가능한 것은 KorService2 detailCommon2/detailIntro2/detailInfo2/detailImage2 묶음입니다.",
            "content_id 또는 target_item_id가 있는 candidate_targets만 selected_targets에 넣으세요.",
            "request_level_gaps는 특정 content_id가 없어 직접 상세 호출할 수 없으므로 selected_targets에 넣지 마세요.",
        ],
        "출력_규칙": [
            "candidate_targets에 있는 실행 가능한 대상은 remaining_budget 안에서 모두 selected_targets에 넣으세요.",
            "각 selected_targets[].gap_ids는 candidate_targets[].gap_ids에 있는 값만 사용하세요.",
            "reason은 60자 이내 한국어로 쓰세요.",
            "skipped_gap_ids에는 선택하지 않은 gap_id와 request_level_gaps의 id를 넣으세요.",
            "실제 호출 도구명, endpoint, 상세 인자는 출력하지 말고 대상 선택만 출력하세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def build_evidence_fusion_prompt(
    *,
    base_fusion: dict[str, Any],
    retrieved_documents: list[dict[str, Any]],
    gap_report: dict[str, Any],
    enrichment_summary: dict[str, Any],
) -> str:
    context = {
        "역할": "EvidenceFusionAgent",
        "목표": "코드가 이미 묶어 둔 후보별 근거를 재작성하지 말고, Product/Marketing/QA가 참고할 짧은 상품화 해석 델타와 claim policy만 작성합니다.",
        "base_evidence_summary": _compact_base_fusion_for_prompt(base_fusion),
        "retrieved_documents": [_compact_document(doc) for doc in retrieved_documents[:6]],
        "gap_summary": _compact_gap_report_for_router(gap_report),
        "enrichment_execution_summary": _compact_enrichment_summary_for_fusion(enrichment_summary),
        "claim_policy": [
            "근거가 있는 장소명, 주소, 개요, 행사 기간, 홈페이지, 문의처만 usable claim으로 분리하세요.",
            "운영시간, 요금, 예약 가능 여부, 반려동물 동반 조건, 언어지원, 의료/웰니스 효능은 근거가 없으면 unresolved_gaps 또는 needs_review로 남기세요.",
            "이미지 후보는 candidate이며 게시 가능/변형 가능 claim을 하지 마세요.",
            "수요/혼잡/연관 관광지 API는 보조 신호이며 예약/판매 가능성을 보장하지 않습니다.",
        ],
        "출력_규칙": [
            "evidence_profile, entities, candidate_evidence_cards, usable_facts, visual_candidates, route_assets, signal_records, theme_candidates를 다시 출력하지 마세요.",
            "각 후보의 원본 facts와 API 결과는 코드가 이미 보존합니다. 당신은 그 정보를 복사하지 말고 content_id/source_item_id로 참조하는 해석만 출력하세요.",
            "productization_advice.candidate_interpretations에는 우선순위 판단이 필요한 후보만 최대 8개 작성하세요. 모든 후보를 반드시 다 쓰지 마세요.",
            "각 candidate_interpretation에는 content_id, source_item_id, title, priority(high|medium|low), product_angle, rationale, experience_hooks, recommended_product_angles, use_with_caution만 넣으세요.",
            "experience_hooks, recommended_product_angles, use_with_caution은 각각 최대 3개, 각 문장은 80자 이내로 제한하세요.",
            "productization_advice.global_claim_policy에는 전체 run에 적용할 allowed, needs_review, forbidden_without_evidence를 짧게 작성하세요.",
            "candidate_recommendations는 전체 우선순위 판단용으로 최대 8개만 작성하세요.",
            "unresolved_gaps는 아직 남아 있는 핵심 gap만 요약하세요.",
            "ui_highlights는 사용자에게 보여줄 3~5개 요약만 작성하세요.",
        ],
        "ui_출력_규칙": [
            "ui_highlights에는 사용자가 이해할 수 있는 한국어 요약을 넣으세요.",
            "각 highlight는 title, body, severity(info|warning|success), related_gap_types를 포함하세요.",
            "내부 코드(ldong/lcls)는 사용자 문구에 노출하지 마세요.",
        ],
    }
    return json.dumps(context, ensure_ascii=False)


def normalize_gap_profile_payload(
    payload: dict[str, Any],
    *,
    source_items: list[Any],
    retrieved_documents: list[dict[str, Any]] | None = None,
    normalized_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_item_ids = {str(_get(item, "id")) for item in source_items if _get(item, "id")}
    source_item_id_by_content_id = {
        str(_get(item, "content_id")): str(_get(item, "id"))
        for item in source_items
        if _get(item, "content_id") and _get(item, "id")
    }
    gaps: list[dict[str, Any]] = []
    for raw_gap in payload.get("gaps") or []:
        if not isinstance(raw_gap, dict):
            continue
        gap_type = str(raw_gap.get("gap_type") or "")
        gap_type = GAP_TYPE_ALIASES.get(gap_type, gap_type)
        if gap_type not in GAP_TYPES:
            continue
        target_content_id = _string_or_none(raw_gap.get("target_content_id")) or _content_id_from_entity_id(
            raw_gap.get("target_entity_id")
        )
        target_item_id = str(raw_gap.get("target_item_id") or "")
        mapped_item_id = source_item_id_by_content_id.get(target_content_id or "", "")
        if not target_item_id and mapped_item_id:
            target_item_id = mapped_item_id
        if target_item_id and target_item_id not in source_item_ids and mapped_item_id:
            target_item_id = mapped_item_id
        if target_item_id and target_item_id not in source_item_ids:
            continue
        gap_id = str(raw_gap.get("id") or f"gap:{gap_type}:{target_item_id or 'request'}")
        gaps.append(
            {
                "id": gap_id,
                "gap_type": gap_type,
                "severity": _normalize_severity(raw_gap.get("severity")),
                "reason": str(raw_gap.get("reason") or "근거가 부족해 운영자 확인이 필요합니다."),
                "target_entity_id": _string_or_none(raw_gap.get("target_entity_id")),
                "target_content_id": target_content_id,
                "target_item_id": target_item_id or None,
                "source_item_title": _string_or_none(raw_gap.get("source_item_title")),
                "suggested_source_family": str(raw_gap.get("suggested_source_family") or "kto_tourapi_kor"),
                "needs_review": raw_gap.get("needs_review") is not False,
                "productization_impact": str(raw_gap.get("productization_impact") or ""),
            }
        )
    gaps = _merge_required_request_level_gaps(
        gaps,
        source_items=source_items,
        normalized_request=normalized_request or {},
    )
    gaps = _prioritize_gaps(_dedupe_gaps(gaps))[:DATA_GAP_PROFILE_MAX_GAPS]
    coverage = _normalize_coverage(payload.get("coverage"), source_items, gaps)
    return {
        "gaps": gaps,
        "coverage": coverage,
        "retrieved_document_count": len(retrieved_documents or []),
        "reasoning_summary": str(payload.get("reasoning_summary") or ""),
        "needs_review": _string_list(payload.get("needs_review"))[:DATA_GAP_PROFILE_MAX_NEEDS_REVIEW],
        "summary": {
            "total_gaps": len(gaps),
            "high_severity_gaps": sum(1 for gap in gaps if gap["severity"] == "high"),
            "needs_review_gaps": sum(1 for gap in gaps if gap.get("needs_review")),
        },
    }


def normalize_routing_payload(
    payload: dict[str, Any],
    *,
    gap_report: dict[str, Any],
    settings: Settings | None = None,
    max_call_budget: int | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    budget = max_call_budget if max_call_budget is not None else settings.enrichment_max_call_budget
    capabilities = {item["source_family"]: item for item in list_kto_capabilities(settings)}
    gaps_by_id = {str(gap.get("id")): gap for gap in gap_report.get("gaps") or [] if gap.get("id")}
    planned_calls: list[dict[str, Any]] = []
    skipped_calls: list[dict[str, Any]] = []

    for raw_call in payload.get("planned_calls") or []:
        if not isinstance(raw_call, dict):
            continue
        source_family = str(raw_call.get("source_family") or "")
        gap_ids = [gap_id for gap_id in _string_list(raw_call.get("gap_ids")) if gap_id in gaps_by_id]
        if not gap_ids:
            continue
        representative_gap = gaps_by_id[gap_ids[0]]
        if source_family == "kto_medical" and not settings.allow_medical_api:
            skipped_calls.append(_skipped_call(representative_gap, source_family, "feature_flag_disabled"))
            continue
        capability = capabilities.get(source_family) or {}
        if not _can_execute_workflow_call(raw_call, capability):
            skipped_calls.append(
                _skipped_call(
                    representative_gap,
                    source_family or str(representative_gap.get("suggested_source_family") or "unknown"),
                    "future_provider_not_implemented",
                    display_name=capability.get("display_name"),
                )
            )
            continue
        if len(planned_calls) >= budget:
            skipped_calls.append(_skipped_call(representative_gap, source_family, "max_call_budget_exceeded"))
            continue
        planned_calls.append(_normalize_planned_call(raw_call, representative_gap, len(planned_calls) + 1, gap_ids))

    for raw_call in (payload.get("skipped_calls") or [])[:24]:
        if not isinstance(raw_call, dict):
            continue
        gap_ids = _string_list(raw_call.get("gap_ids"))
        representative_gap = next((gaps_by_id.get(gap_id) for gap_id in gap_ids if gaps_by_id.get(gap_id)), None)
        source_family = str(raw_call.get("source_family") or (representative_gap or {}).get("suggested_source_family") or "unknown")
        if representative_gap:
            skipped = _skipped_call(
                representative_gap,
                source_family,
                str(raw_call.get("skip_reason") or "future_provider_not_implemented"),
                display_name=str(raw_call.get("display_name") or "") or None,
            )
            skipped["reason"] = str(raw_call.get("reason") or skipped["skip_reason"])
            skipped_calls.append(skipped)
        elif gap_ids:
            skipped_calls.append(
                {
                    "id": str(raw_call.get("id") or f"skip:{source_family}:{len(skipped_calls) + 1}"),
                    "status": "skipped",
                    "source_family": source_family,
                    "tool_name": _future_tool_name(source_family),
                    "operation": str(raw_call.get("operation") or "future"),
                    "gap_ids": gap_ids,
                    "gap_types": _string_list(raw_call.get("gap_types")),
                    "skip_reason": str(raw_call.get("skip_reason") or "future_provider_not_implemented"),
                    "reason": str(raw_call.get("reason") or raw_call.get("skip_reason") or ""),
                    "arguments": raw_call.get("arguments") if isinstance(raw_call.get("arguments"), dict) else {},
                }
            )

    seen_plan_gap_ids = {gap_id for call in planned_calls for gap_id in call.get("gap_ids", [])}
    seen_skip_gap_ids = {gap_id for call in skipped_calls for gap_id in call.get("gap_ids", [])}
    for gap_id, gap in gaps_by_id.items():
        if gap_id in seen_plan_gap_ids or gap_id in seen_skip_gap_ids:
            continue
        reason = "max_call_budget_exceeded" if _is_detail_gap(gap) and len(planned_calls) >= budget else "not_selected_by_gemini_router"
        skipped_calls.append(_skipped_call(gap, str(gap.get("suggested_source_family") or "unknown"), reason))

    return {
        "max_call_budget": budget,
        "planned_calls": planned_calls,
        "skipped_calls": _dedupe_calls(skipped_calls),
        "budget_summary": payload.get("budget_summary") or {},
        "routing_reasoning": str(payload.get("routing_reasoning") or ""),
        "summary": {
            "planned": len(planned_calls),
            "skipped": len(_dedupe_calls(skipped_calls)),
            "budget_remaining": max(0, budget - len(planned_calls)),
        },
    }


def normalize_family_routing_payload(
    payload: dict[str, Any],
    *,
    gap_report: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    gaps_by_id = {str(gap.get("id")): gap for gap in gap_report.get("gaps") or [] if gap.get("id")}
    routes: list[dict[str, Any]] = []
    assigned_gap_ids: set[str] = set()
    for raw_route in payload.get("family_routes") or []:
        if not isinstance(raw_route, dict):
            continue
        planner = str(raw_route.get("planner") or "")
        if planner not in PLANNER_DEFINITIONS:
            continue
        gap_ids = [gap_id for gap_id in _string_list(raw_route.get("gap_ids")) if gap_id in gaps_by_id]
        if not gap_ids:
            continue
        definition = PLANNER_DEFINITIONS[planner]
        routes.append(
            {
                "planner": planner,
                "agent_name": definition["agent_name"],
                "gap_ids": gap_ids,
                "source_families": _string_list(raw_route.get("source_families")) or definition["source_families"],
                "reason": str(raw_route.get("reason") or _default_route_reason(planner)),
                "priority": str(raw_route.get("priority") or _route_priority(planner, gap_ids, gaps_by_id, settings)),
            }
        )
        assigned_gap_ids.update(gap_ids)

    for gap_id, gap in gaps_by_id.items():
        if gap_id in assigned_gap_ids:
            continue
        planner = _planner_for_gap(gap, settings)
        existing = next((route for route in routes if route["planner"] == planner), None)
        if existing:
            existing["gap_ids"].append(gap_id)
            continue
        definition = PLANNER_DEFINITIONS[planner]
        routes.append(
            {
                "planner": planner,
                "agent_name": definition["agent_name"],
                "gap_ids": [gap_id],
                "source_families": definition["source_families"],
                "reason": _default_route_reason(planner),
                "priority": _route_priority(planner, [gap_id], gaps_by_id, settings),
            }
        )
    routes = _dedupe_family_routes(routes)
    return {
        "family_routes": routes,
        "skipped_routes": [
            item for item in payload.get("skipped_routes") or [] if isinstance(item, dict)
        ],
        "routing_reasoning": str(payload.get("routing_reasoning") or "Gap을 API family planner별로 분배했습니다."),
        "summary": {
            "route_count": len(routes),
            "assigned_gap_count": sum(len(route.get("gap_ids") or []) for route in routes),
        },
    }


def plan_family_deterministic(
    *,
    planner_key: str,
    capability_routing: dict[str, Any],
    gap_report: dict[str, Any],
    settings: Settings | None = None,
    max_call_budget: int | None = None,
    existing_planned_count: int = 0,
) -> dict[str, Any]:
    settings = settings or get_settings()
    max_budget = max_call_budget if max_call_budget is not None else settings.enrichment_max_call_budget
    route = _route_for_planner(capability_routing, planner_key)
    assigned_gaps = _gaps_for_ids(gap_report, route.get("gap_ids") or [])
    if planner_key == "tourapi_detail":
        plan = route_gap_plan(
            gap_report={"gaps": assigned_gaps},
            settings=settings,
            max_call_budget=max(0, max_budget - existing_planned_count),
        )
        return {
            **plan,
            "planner": planner_key,
            "planning_reasoning": "KorService2 상세/이미지 보강으로 실행 가능한 gap만 계획했습니다.",
        }
    if planner_key == "visual_data":
        remaining_budget = max(0, max_budget - existing_planned_count)
        planned_calls: list[dict[str, Any]] = []
        skipped_calls: list[dict[str, Any]] = []
        for gap in assigned_gaps:
            source_family = _visual_source_family_for_gap(gap, settings)
            if not source_family:
                skipped_calls.append(
                    _skipped_call(
                        gap,
                        str(gap.get("suggested_source_family") or "kto_tourism_photo"),
                        "feature_flag_disabled",
                    )
                )
                continue
            if len(planned_calls) >= remaining_budget:
                skipped_calls.append(_skipped_call(gap, source_family, "max_call_budget_exceeded"))
                continue
            planned_calls.append(_planned_visual_call(gap, source_family, len(planned_calls) + 1))
        return {
            "planner": planner_key,
            "max_call_budget": max_budget,
            "planned_calls": planned_calls,
            "skipped_calls": skipped_calls,
            "budget_summary": {
                "planned": len(planned_calls),
                "skipped": len(skipped_calls),
                "budget_remaining": max(0, max_budget - existing_planned_count - len(planned_calls)),
            },
            "planning_reasoning": "활성화된 Visual API source family만 이미지 후보 보강 대상으로 계획했습니다.",
            "summary": {"planned": len(planned_calls), "skipped": len(skipped_calls)},
        }
    if planner_key == "route_signal":
        remaining_budget = max(0, max_budget - existing_planned_count)
        planned_calls = []
        skipped_calls = []
        for gap in assigned_gaps:
            source_family = _route_signal_source_family_for_gap(gap, settings)
            if not source_family:
                skipped_calls.append(
                    _skipped_call(
                        gap,
                        str(gap.get("suggested_source_family") or "kto_related_places"),
                        "feature_flag_disabled",
                    )
                )
                continue
            if len(planned_calls) >= remaining_budget:
                skipped_calls.append(_skipped_call(gap, source_family, "max_call_budget_exceeded"))
                continue
            planned_calls.append(_planned_route_signal_call(gap, source_family, len(planned_calls) + 1))
        return {
            "planner": planner_key,
            "max_call_budget": max_budget,
            "planned_calls": planned_calls,
            "skipped_calls": skipped_calls,
            "budget_summary": {
                "planned": len(planned_calls),
                "skipped": len(skipped_calls),
                "budget_remaining": max(0, max_budget - existing_planned_count - len(planned_calls)),
            },
            "planning_reasoning": "활성화된 route/signal API source family만 동선·수요 보조 근거 대상으로 계획했습니다.",
            "summary": {"planned": len(planned_calls), "skipped": len(skipped_calls)},
        }
    if planner_key == "theme_data":
        remaining_budget = max(0, max_budget - existing_planned_count)
        planned_calls = []
        skipped_calls = []
        for gap in assigned_gaps:
            source_family = _theme_source_family_for_gap(gap, settings)
            if not source_family:
                skipped_calls.append(
                    _skipped_call(
                        gap,
                        str(gap.get("suggested_source_family") or _source_family_for_future_gap(gap)),
                        "feature_flag_disabled",
                    )
                )
                continue
            if len(planned_calls) >= remaining_budget:
                skipped_calls.append(_skipped_call(gap, source_family, "max_call_budget_exceeded"))
                continue
            planned_calls.append(_planned_theme_call(gap, source_family, len(planned_calls) + 1))
        return {
            "planner": planner_key,
            "max_call_budget": max_budget,
            "planned_calls": planned_calls,
            "skipped_calls": skipped_calls,
            "budget_summary": {
                "planned": len(planned_calls),
                "skipped": len(skipped_calls),
                "budget_remaining": max(0, max_budget - existing_planned_count - len(planned_calls)),
            },
            "planning_reasoning": "활성화된 Theme API source family만 테마 보조 근거 대상으로 계획했습니다.",
            "summary": {"planned": len(planned_calls), "skipped": len(skipped_calls)},
        }
    skipped = [
        _skipped_call(
            gap,
            _source_family_for_future_gap(gap),
            _future_skip_reason_for_gap(gap, settings),
        )
        for gap in assigned_gaps
    ]
    return {
        "planner": planner_key,
        "max_call_budget": max_budget,
        "planned_calls": [],
        "skipped_calls": skipped,
        "budget_summary": {
            "planned": 0,
            "skipped": len(skipped),
            "budget_remaining": max(0, max_budget - existing_planned_count),
        },
        "planning_reasoning": "이 planner의 source family는 아직 provider/executor가 없어 future로 기록했습니다.",
        "summary": {"planned": 0, "skipped": len(skipped)},
    }


def normalize_family_planner_payload(
    payload: dict[str, Any],
    *,
    planner_key: str,
    capability_routing: dict[str, Any],
    gap_report: dict[str, Any],
    settings: Settings | None = None,
    max_call_budget: int | None = None,
    existing_planned_count: int = 0,
) -> dict[str, Any]:
    settings = settings or get_settings()
    max_budget = max_call_budget if max_call_budget is not None else settings.enrichment_max_call_budget
    route = _route_for_planner(capability_routing, planner_key)
    assigned_gap_ids = set(_string_list(route.get("gap_ids")))
    gaps_by_id = {
        str(gap.get("id")): gap
        for gap in gap_report.get("gaps") or []
        if gap.get("id") and str(gap.get("id")) in assigned_gap_ids
    }
    capabilities = {item["source_family"]: item for item in list_kto_capabilities(settings)}
    planned_calls: list[dict[str, Any]] = []
    skipped_calls: list[dict[str, Any]] = []
    remaining_budget = max(0, max_budget - existing_planned_count)

    for raw_call in payload.get("planned_calls") or []:
        if not isinstance(raw_call, dict):
            continue
        gap_ids = [gap_id for gap_id in _string_list(raw_call.get("gap_ids")) if gap_id in gaps_by_id]
        if not gap_ids:
            continue
        representative_gap = gaps_by_id[gap_ids[0]]
        source_family = str(raw_call.get("source_family") or "")
        capability = capabilities.get(source_family) or {}
        if not _can_execute_workflow_call(raw_call, capability):
            if _executable_source_family_for_planner_gap(planner_key, representative_gap, settings):
                continue
            skipped_calls.append(
                _skipped_call(
                    representative_gap,
                    source_family or _source_family_for_future_gap(representative_gap),
                    _future_skip_reason_for_gap(representative_gap, settings),
                    display_name=capability.get("display_name"),
                )
            )
            continue
        if len(planned_calls) >= remaining_budget:
            skipped_calls.append(_skipped_call(representative_gap, source_family, "max_call_budget_exceeded"))
            continue
        planned_calls.append(_normalize_planned_call(raw_call, representative_gap, len(planned_calls) + 1, gap_ids))

    for raw_call in (payload.get("skipped_calls") or [])[:24]:
        if not isinstance(raw_call, dict):
            continue
        gap_ids = [gap_id for gap_id in _string_list(raw_call.get("gap_ids")) if gap_id in gaps_by_id]
        for gap_id in gap_ids[:8]:
            gap = gaps_by_id[gap_id]
            source_family = str(raw_call.get("source_family") or gap.get("suggested_source_family") or _source_family_for_future_gap(gap))
            if _executable_source_family_for_planner_gap(planner_key, gap, settings):
                continue
            skipped = _skipped_call(
                gap,
                source_family,
                str(raw_call.get("skip_reason") or _future_skip_reason_for_gap(gap, settings)),
            )
            skipped["reason"] = str(raw_call.get("reason") or skipped["skip_reason"])
            skipped_calls.append(skipped)

    seen_gap_ids = {
        gap_id
        for call in [*planned_calls, *skipped_calls]
        for gap_id in _string_list(call.get("gap_ids"))
    }
    for gap_id, gap in gaps_by_id.items():
        if gap_id in seen_gap_ids:
            continue
        if planner_key == "tourapi_detail" and len(planned_calls) < remaining_budget and _is_detail_gap(gap):
            planned_calls.append(_planned_detail_call(gap, len(planned_calls) + 1))
        elif planner_key == "visual_data":
            source_family = _visual_source_family_for_gap(gap, settings)
            if source_family and len(planned_calls) < remaining_budget:
                planned_calls.append(_planned_visual_call(gap, source_family, len(planned_calls) + 1))
            else:
                reason = "max_call_budget_exceeded" if source_family else "feature_flag_disabled"
                skipped_calls.append(
                    _skipped_call(
                        gap,
                        source_family or str(gap.get("suggested_source_family") or "kto_tourism_photo"),
                        reason,
                    )
                )
        elif planner_key == "route_signal":
            source_family = _route_signal_source_family_for_gap(gap, settings)
            if source_family and len(planned_calls) < remaining_budget:
                planned_calls.append(_planned_route_signal_call(gap, source_family, len(planned_calls) + 1))
            else:
                reason = "max_call_budget_exceeded" if source_family else "feature_flag_disabled"
                skipped_calls.append(
                    _skipped_call(
                        gap,
                        source_family or str(gap.get("suggested_source_family") or _source_family_for_future_gap(gap)),
                        reason,
                    )
                )
        elif planner_key == "theme_data":
            source_family = _theme_source_family_for_gap(gap, settings)
            if source_family and len(planned_calls) < remaining_budget:
                planned_calls.append(_planned_theme_call(gap, source_family, len(planned_calls) + 1))
            else:
                reason = "max_call_budget_exceeded" if source_family else "feature_flag_disabled"
                skipped_calls.append(
                    _skipped_call(
                        gap,
                        source_family or str(gap.get("suggested_source_family") or _source_family_for_future_gap(gap)),
                        reason,
                    )
                )
        else:
            reason = "max_call_budget_exceeded" if planner_key == "tourapi_detail" else _future_skip_reason_for_gap(gap, settings)
            skipped_calls.append(_skipped_call(gap, str(gap.get("suggested_source_family") or _source_family_for_future_gap(gap)), reason))

    planned_calls = _dedupe_calls(planned_calls)
    skipped_calls = _dedupe_calls(skipped_calls)
    return {
        "planner": planner_key,
        "max_call_budget": max_budget,
        "planned_calls": planned_calls,
        "skipped_calls": skipped_calls,
        "budget_summary": payload.get("budget_summary") if isinstance(payload.get("budget_summary"), dict) else {},
        "planning_reasoning": str(payload.get("planning_reasoning") or _default_route_reason(planner_key)),
        "summary": {
            "planned": len(planned_calls),
            "skipped": len(skipped_calls),
            "budget_remaining": max(0, max_budget - existing_planned_count - len(planned_calls)),
        },
    }


def normalize_tourapi_detail_planner_payload(
    payload: dict[str, Any],
    *,
    capability_routing: dict[str, Any],
    gap_report: dict[str, Any],
    settings: Settings | None = None,
    max_call_budget: int | None = None,
    existing_planned_count: int = 0,
) -> dict[str, Any]:
    settings = settings or get_settings()
    max_budget = max_call_budget if max_call_budget is not None else settings.enrichment_max_call_budget
    remaining_budget = max(0, max_budget - existing_planned_count)
    route = _route_for_planner(capability_routing, "tourapi_detail")
    assigned_gap_ids = set(_string_list(route.get("gap_ids")))
    assigned_gaps = [
        gap
        for gap in gap_report.get("gaps") or []
        if isinstance(gap, dict) and str(gap.get("id")) in assigned_gap_ids
    ]
    gaps_by_id = {str(gap.get("id")): gap for gap in assigned_gaps if gap.get("id")}
    gaps_by_target = _gaps_by_detail_target(assigned_gaps)
    planned_calls: list[dict[str, Any]] = []
    skipped_calls: list[dict[str, Any]] = []
    selected_gap_ids: set[str] = set()

    for raw_target in payload.get("selected_targets") or []:
        if not isinstance(raw_target, dict) or len(planned_calls) >= remaining_budget:
            continue
        target_key = _detail_target_key(raw_target)
        target_gaps = gaps_by_target.get(target_key, [])
        raw_gap_ids = [gap_id for gap_id in _string_list(raw_target.get("gap_ids")) if gap_id in gaps_by_id]
        if raw_gap_ids:
            selected_gaps = [gaps_by_id[gap_id] for gap_id in raw_gap_ids if _detail_target_key(gaps_by_id[gap_id]) == target_key]
            if not selected_gaps:
                selected_gaps = [gaps_by_id[gap_id] for gap_id in raw_gap_ids]
        else:
            selected_gaps = target_gaps
        selected_gaps = [gap for gap in selected_gaps if _is_executable_detail_gap(gap)]
        if not selected_gaps:
            continue
        call = _planned_detail_call(selected_gaps[0], len(planned_calls) + 1)
        call["gap_ids"] = [str(gap["id"]) for gap in selected_gaps if gap.get("id")]
        call["gap_types"] = sorted({str(gap.get("gap_type") or "missing_detail_info") for gap in selected_gaps})
        call["reason"] = str(raw_target.get("reason") or call["reason"])[:120]
        planned_calls.append(call)
        selected_gap_ids.update(call["gap_ids"])

    explicit_skipped = set(_string_list(payload.get("skipped_gap_ids")))
    for gap in assigned_gaps:
        gap_id = str(gap.get("id") or "")
        if not gap_id or gap_id in selected_gap_ids:
            continue
        if not _is_executable_detail_gap(gap):
            skipped_calls.append(_skipped_call(gap, "kto_tourapi_kor", "requires_item_target"))
            continue
        if len(planned_calls) < remaining_budget:
            call = _planned_detail_call(gap, len(planned_calls) + 1)
            call["reason"] = "실행 가능한 KorService2 상세 보강 대상이라 정책상 자동 포함했습니다."
            planned_calls.append(call)
            selected_gap_ids.update(call["gap_ids"])
            continue
        if len(planned_calls) >= remaining_budget:
            reason = "max_call_budget_exceeded"
        elif gap_id in explicit_skipped:
            reason = "not_selected_by_gemini_planner"
        else:
            reason = "not_selected_by_gemini_planner"
        skipped_calls.append(_skipped_call(gap, "kto_tourapi_kor", reason))

    planned_calls = _dedupe_calls(planned_calls)
    skipped_calls = _dedupe_calls(skipped_calls)
    return {
        "planner": "tourapi_detail",
        "max_call_budget": max_budget,
        "planned_calls": planned_calls,
        "skipped_calls": skipped_calls,
        "budget_summary": {
            "planned": len(planned_calls),
            "skipped": len(skipped_calls),
            "budget_remaining": max(0, max_budget - existing_planned_count - len(planned_calls)),
        },
        "planning_reasoning": str(payload.get("planning_reasoning") or "Gemini가 KorService2 상세 보강 대상을 짧게 선택했습니다."),
        "summary": {
            "planned": len(planned_calls),
            "skipped": len(skipped_calls),
            "budget_remaining": max(0, max_budget - existing_planned_count - len(planned_calls)),
        },
    }


def count_tourapi_detail_targets(capability_routing: dict[str, Any], gap_report: dict[str, Any]) -> int:
    route = _route_for_planner(capability_routing, "tourapi_detail")
    assigned_gap_ids = set(_string_list(route.get("gap_ids")))
    assigned_gaps = [
        gap
        for gap in gap_report.get("gaps") or []
        if isinstance(gap, dict) and str(gap.get("id")) in assigned_gap_ids
    ]
    return len(_detail_target_candidates(assigned_gaps))


def merge_enrichment_plan_fragments(
    fragments: list[dict[str, Any]],
    *,
    max_call_budget: int,
) -> dict[str, Any]:
    planned_calls: list[dict[str, Any]] = []
    skipped_calls: list[dict[str, Any]] = []
    planner_summaries: list[dict[str, Any]] = []
    for fragment in fragments:
        planner = str(fragment.get("planner") or "unknown")
        for call in fragment.get("planned_calls") or []:
            if len(planned_calls) < max_call_budget:
                planned_calls.append({**call, "planner": planner})
            else:
                skipped_calls.append(_skipped_from_plan_call(call, planner, "max_call_budget_exceeded"))
        for call in fragment.get("skipped_calls") or []:
            skipped_calls.append({**call, "planner": planner})
        planner_summaries.append(
            {
                "planner": planner,
                "planned": len(fragment.get("planned_calls") or []),
                "skipped": len(fragment.get("skipped_calls") or []),
                "reasoning": fragment.get("planning_reasoning"),
            }
        )
    planned_calls = _dedupe_calls(planned_calls)
    skipped_calls = _dedupe_calls(skipped_calls)
    return {
        "max_call_budget": max_call_budget,
        "planned_calls": planned_calls,
        "skipped_calls": skipped_calls,
        "planner_summaries": planner_summaries,
        "routing_reasoning": "ApiCapabilityRouterAgent가 family lane을 나누고 각 planner가 세부 계획을 만들었습니다.",
        "summary": {
            "planned": len(planned_calls),
            "skipped": len(skipped_calls),
            "budget_remaining": max(0, max_call_budget - len(planned_calls)),
        },
    }


def normalize_evidence_fusion_payload(
    payload: dict[str, Any],
    *,
    base_fusion: dict[str, Any],
) -> dict[str, Any]:
    base_advice = (
        base_fusion.get("productization_advice")
        if isinstance(base_fusion.get("productization_advice"), dict)
        else {}
    )
    payload_advice = (
        payload.get("productization_advice")
        if isinstance(payload.get("productization_advice"), dict)
        else {}
    )
    payload_unresolved = payload.get("unresolved_gaps") if isinstance(payload.get("unresolved_gaps"), list) else []
    base_unresolved = (
        base_fusion.get("unresolved_gaps")
        if isinstance(base_fusion.get("unresolved_gaps"), list)
        else []
    )
    ui_highlights = payload.get("ui_highlights") if isinstance(payload.get("ui_highlights"), list) else []
    return {
        "evidence_profile": base_fusion.get("evidence_profile", {}),
        "productization_advice": _merge_productization_advice(base_advice, payload_advice),
        "data_coverage": base_fusion.get("data_coverage", {}),
        "unresolved_gaps": _merge_unresolved_gaps(base_unresolved, payload_unresolved),
        "source_confidence": _number_or_default(payload.get("source_confidence"), base_fusion.get("source_confidence", 0.0)),
        "ui_highlights": [item for item in ui_highlights if isinstance(item, dict)],
    }


def profile_data_gaps(
    *,
    source_items: list[Any],
    retrieved_documents: list[dict[str, Any]] | None = None,
    normalized_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_request = normalized_request or {}
    gaps: list[dict[str, Any]] = []
    for item in source_items:
        gaps.extend(_item_gaps(item))

    route_gap = _route_gap(source_items, normalized_request)
    if route_gap:
        gaps.append(route_gap)

    theme_gap = _theme_gap(source_items, normalized_request)
    if theme_gap:
        gaps.append(theme_gap)

    gaps = _dedupe_gaps(gaps)
    coverage = _coverage_summary(source_items, gaps)
    return {
        "gaps": gaps,
        "coverage": coverage,
        "retrieved_document_count": len(retrieved_documents or []),
        "summary": {
            "total_gaps": len(gaps),
            "high_severity_gaps": sum(1 for gap in gaps if gap["severity"] == "high"),
            "needs_review_gaps": sum(1 for gap in gaps if gap.get("needs_review")),
        },
    }


def route_gap_plan(
    *,
    gap_report: dict[str, Any],
    settings: Settings | None = None,
    max_call_budget: int | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    budget = max_call_budget if max_call_budget is not None else settings.enrichment_max_call_budget
    capabilities = {item["source_family"]: item for item in list_kto_capabilities(settings)}
    planned_calls: list[dict[str, Any]] = []
    skipped_calls: list[dict[str, Any]] = []
    executable_count = 0
    detail_targets: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for gap in gap_report.get("gaps") or []:
        gap_type = str(gap.get("gap_type") or "")
        if gap_type in DETAIL_GAP_TYPES:
            target_key = str(gap.get("target_item_id") or gap.get("target_content_id") or gap["id"])
            detail_targets[target_key].append(gap)
            continue

        source_family = _source_family_for_future_gap(gap)
        if source_family == "kto_medical" and not settings.allow_medical_api:
            skipped_calls.append(_skipped_call(gap, source_family, "feature_flag_disabled"))
            continue
        capability = capabilities.get(source_family) or {}
        skipped_calls.append(
            _skipped_call(
                gap,
                source_family,
                "future_provider_not_implemented",
                display_name=capability.get("display_name"),
            )
        )

    for target_key, gaps in detail_targets.items():
        gap = gaps[0]
        if executable_count >= budget:
            skipped_calls.append(_skipped_call(gap, "kto_tourapi_kor", "max_call_budget_exceeded"))
            continue
        executable_count += 1
        planned_calls.append(
            {
                "id": f"plan:{len(planned_calls) + 1}",
                "status": "planned",
                "source_family": "kto_tourapi_kor",
                "tool_name": "kto_tour_detail_enrichment",
                "operation": "detailCommon2/detailIntro2/detailInfo2/detailImage2",
                "gap_ids": [item["id"] for item in gaps],
                "gap_types": sorted({str(item.get("gap_type")) for item in gaps}),
                "target_item_id": gap.get("target_item_id"),
                "target_content_id": gap.get("target_content_id"),
                "target_entity_id": gap.get("target_entity_id"),
                "reason": "KorService2 상세/이미지 보강으로 여러 gap을 한 번에 확인합니다.",
                "arguments": {
                    "item_id": gap.get("target_item_id"),
                    "content_id": gap.get("target_content_id"),
                },
            }
        )

    return {
        "max_call_budget": budget,
        "planned_calls": planned_calls,
        "skipped_calls": skipped_calls,
        "summary": {
            "planned": len(planned_calls),
            "skipped": len(skipped_calls),
            "budget_remaining": max(0, budget - executable_count),
        },
    }


def create_enrichment_run(
    *,
    db: Session,
    workflow_run_id: str,
    gap_report: dict[str, Any],
    plan: dict[str, Any],
    trigger_type: str = "workflow",
) -> models.EnrichmentRun:
    enrichment_run = models.EnrichmentRun(
        workflow_run_id=workflow_run_id,
        trigger_type=trigger_type,
        status="running",
        gap_report=gap_report,
        plan=plan,
        result_summary={},
        started_at=models.utcnow(),
    )
    db.add(enrichment_run)
    db.commit()
    db.refresh(enrichment_run)
    return enrichment_run


def execute_enrichment_plan(
    *,
    db: Session,
    provider: TourismDataProvider,
    visual_provider: VisualDataProvider | None = None,
    route_signal_provider: RouteSignalProvider | None = None,
    theme_provider: ThemeDataProvider | None = None,
    enrichment_run: models.EnrichmentRun,
    source_items: list[dict[str, Any]],
    run_id: str,
    step_id: str | None,
) -> dict[str, Any]:
    item_by_id = {str(item.get("id")): item for item in source_items if item.get("id")}
    executed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    enriched_item_ids: set[str] = set()
    indexed_documents = 0
    visual_asset_count = 0
    route_asset_count = 0
    signal_record_count = 0
    theme_candidate_count = 0

    for plan_call in enrichment_run.plan.get("planned_calls") or []:
        started = time.perf_counter()
        tool_record = _create_enrichment_tool_call(
            db=db,
            enrichment_run=enrichment_run,
            plan_call=plan_call,
            run_id=run_id,
            status="running",
        )
        try:
            item_id = str(plan_call.get("target_item_id") or "")
            source_item = item_by_id.get(item_id)
            source_family = str(plan_call.get("source_family") or "")
            model_item = _resolve_model_item_for_plan_call(
                db=db,
                plan_call=plan_call,
                source_item=source_item,
                source_items=source_items,
                allow_fallback=source_family in {*ROUTE_SIGNAL_SOURCE_FAMILIES, *THEME_SOURCE_FAMILIES},
            )
            if not model_item:
                lookup_value = item_id or _plan_call_content_id(plan_call)
                raise ValueError(f"Tourism item not found for enrichment: {lookup_value}")
            if source_family in VISUAL_SOURCE_FAMILIES:
                summary = execute_visual_search(
                    db=db,
                    provider=visual_provider or get_visual_provider(),
                    plan_call=plan_call,
                    target_item=model_item,
                    run_id=run_id,
                    step_id=step_id,
                )
                indexed_documents += int(summary.get("indexed_documents") or 0)
                visual_asset_count += int(summary.get("visual_assets") or 0)
                enriched_item_ids.add(model_item.id)
            elif source_family in ROUTE_SIGNAL_SOURCE_FAMILIES:
                summary = execute_route_signal_search(
                    db=db,
                    provider=route_signal_provider or get_route_signal_provider(),
                    plan_call=plan_call,
                    target_item=model_item,
                    fallback_source_item_id=str(plan_call.get("id") or "route_signal"),
                    run_id=run_id,
                    step_id=step_id,
                )
                indexed_documents += int(summary.get("indexed_documents") or 0)
                route_asset_count += int(summary.get("route_assets") or 0)
                signal_record_count += int(summary.get("signal_records") or 0)
                enriched_item_ids.add(model_item.id)
            elif source_family in THEME_SOURCE_FAMILIES:
                summary = execute_theme_search(
                    db=db,
                    provider=theme_provider or get_theme_provider(),
                    plan_call=plan_call,
                    target_item=model_item,
                    fallback_source_item_id=str(plan_call.get("id") or "theme_data"),
                    run_id=run_id,
                    step_id=step_id,
                )
                indexed_documents += int(summary.get("indexed_documents") or 0)
                visual_asset_count += int(summary.get("visual_assets") or 0)
                theme_candidate_count += int(summary.get("theme_entities") or summary.get("theme_candidates_found") or 0)
                enriched_item_ids.add(model_item.id)
            else:
                result = enrich_items_with_tourapi_details(
                    db=db,
                    provider=provider,
                    items=[model_item],
                    run_id=run_id,
                    step_id=step_id,
                    limit=1,
                )
                documents = upsert_source_documents_from_items(db, result["items"])
                indexed_documents += index_source_documents(db, documents)
                enriched_item_ids.update(item.id for item in result["items"])
                visual_asset_count += int(result["summary"]["visual_assets"] or 0)
                summary = {
                    "enriched_items": result["summary"]["enriched_items"],
                    "visual_assets": result["summary"]["visual_assets"],
                    "source_documents": len(documents),
                    "reason": plan_call.get("reason"),
                    "expected_ui": plan_call.get("expected_ui"),
                }
            tool_record.status = "succeeded"
            tool_record.response_summary = summary
            tool_record.latency_ms = int((time.perf_counter() - started) * 1000)
            db.add(tool_record)
            db.commit()
            executed.append({**plan_call, "status": "succeeded", "response_summary": summary})
        except Exception as exc:
            tool_record.status = "failed"
            tool_record.error = {"type": exc.__class__.__name__, "message": str(exc)}
            tool_record.latency_ms = int((time.perf_counter() - started) * 1000)
            db.add(tool_record)
            db.commit()
            failed.append({**plan_call, "status": "failed", "error": tool_record.error})

    for skipped_call in enrichment_run.plan.get("skipped_calls") or []:
        tool_record = _create_enrichment_tool_call(
            db=db,
            enrichment_run=enrichment_run,
            plan_call=skipped_call,
            run_id=run_id,
            status="skipped",
        )
        tool_record.response_summary = {
            "reason": skipped_call.get("skip_reason"),
            "detail": skipped_call.get("reason"),
            "display_name": skipped_call.get("display_name"),
        }
        db.add(tool_record)
        skipped.append(skipped_call)

    result_summary = {
        "executed_calls": len(executed),
        "skipped_calls": len(skipped),
        "failed_calls": len(failed),
        "enriched_item_ids": sorted(enriched_item_ids),
        "indexed_documents": indexed_documents,
        "visual_assets": visual_asset_count,
        "route_assets": route_asset_count,
        "signal_records": signal_record_count,
        "theme_candidates": theme_candidate_count,
        "executed": executed,
        "skipped": skipped,
        "failed": failed,
    }
    enrichment_run.status = "completed_with_errors" if failed else "completed"
    enrichment_run.result_summary = result_summary
    enrichment_run.finished_at = models.utcnow()
    db.add(enrichment_run)
    db.commit()
    db.refresh(enrichment_run)
    return result_summary


def fuse_evidence(
    *,
    db: Session,
    source_items: list[dict[str, Any]],
    retrieved_documents: list[dict[str, Any]],
    gap_report: dict[str, Any],
    enrichment_summary: dict[str, Any],
) -> dict[str, Any]:
    item_ids = [str(item.get("id")) for item in source_items if item.get("id")]
    stored_items = {
        item.id: item
        for item in db.query(models.TourismItem).filter(models.TourismItem.id.in_(item_ids)).all()
    } if item_ids else {}
    documents_by_item = _documents_by_item(db, item_ids, retrieved_documents)
    entities: list[dict[str, Any]] = []
    unresolved_gaps: list[dict[str, Any]] = []

    for raw_item in source_items:
        item_id = str(raw_item.get("id") or "")
        item = stored_items.get(item_id)
        item_payload = _model_item_to_payload(item) if item else raw_item
        item_gaps = [gap for gap in gap_report.get("gaps") or [] if gap.get("target_item_id") == item_id]
        doc_ids = [doc.id for doc in documents_by_item.get(item_id, [])]
        detail_facts = _detail_facts_from_payload(item_payload)
        visual_assets = _visual_assets_for_item(db, item_payload)
        route_assets = _route_assets_for_item(db, item_payload)
        signal_records = _signal_records_for_item(db, item_payload)
        theme_candidates = _theme_candidates_for_item(db, item_payload)
        unresolved = [
            gap
            for gap in item_gaps
            if not _gap_resolved(
                gap,
                item_payload,
                visual_asset_count=len(visual_assets),
                route_asset_count=len(route_assets),
                signal_records=signal_records,
                theme_candidates=theme_candidates,
            )
        ]
        unresolved_gaps.extend(unresolved)
        entities.append(
            {
                "entity_id": f"entity:tourapi:content:{item_payload.get('content_id')}",
                "content_id": item_payload.get("content_id"),
                "source_item_id": item_id,
                "title": item_payload.get("title"),
                "content_type": item_payload.get("content_type"),
                "address": item_payload.get("address"),
                "evidence_document_ids": doc_ids,
                "detail_available": _has_detail_info(item_payload),
                "visual_asset_count": len(visual_assets),
                "visual_candidates": _compact_visual_assets(visual_assets),
                "route_asset_count": len(route_assets),
                "route_assets": _compact_route_assets(route_assets),
                "signal_record_count": len(signal_records),
                "signal_records": _compact_signal_records(signal_records),
                "theme_candidate_count": len(theme_candidates),
                "theme_candidates": _compact_theme_candidates(theme_candidates),
                "source_confidence": _source_confidence(item_payload, unresolved),
                "unresolved_gap_types": sorted({gap["gap_type"] for gap in unresolved}),
                "key_facts": {
                    "overview": item_payload.get("overview"),
                    "homepage": item_payload.get("homepage"),
                    "tel": item_payload.get("tel"),
                    "event_start_date": item_payload.get("event_start_date"),
                    "event_end_date": item_payload.get("event_end_date"),
                },
                "detail_facts": detail_facts,
            }
        )

    coverage = _coverage_summary(list(stored_items.values()) or source_items, unresolved_gaps)
    productization_advice = _productization_advice(entities, unresolved_gaps, enrichment_summary)
    confidence_values = [entity["source_confidence"] for entity in entities]
    source_confidence = round(sum(confidence_values) / len(confidence_values), 3) if confidence_values else 0.0
    return {
        "evidence_profile": {
            "entities": entities,
            "source_document_count": sum(len(value) for value in documents_by_item.values()),
        },
        "productization_advice": productization_advice,
        "data_coverage": coverage,
        "unresolved_gaps": unresolved_gaps,
        "source_confidence": source_confidence,
    }


def enrichment_run_to_dict(enrichment_run: models.EnrichmentRun) -> dict[str, Any]:
    return {
        "id": enrichment_run.id,
        "workflow_run_id": enrichment_run.workflow_run_id,
        "trigger_type": enrichment_run.trigger_type,
        "status": enrichment_run.status,
        "gap_report": enrichment_run.gap_report,
        "plan": enrichment_run.plan,
        "result_summary": enrichment_run.result_summary,
        "created_at": enrichment_run.created_at.isoformat() if enrichment_run.created_at else None,
        "started_at": enrichment_run.started_at.isoformat() if enrichment_run.started_at else None,
        "finished_at": enrichment_run.finished_at.isoformat() if enrichment_run.finished_at else None,
        "tool_calls": [
            {
                "id": call.id,
                "plan_id": call.plan_id,
                "tool_name": call.tool_name,
                "source_family": call.source_family,
                "arguments": call.arguments,
                "status": call.status,
                "response_summary": call.response_summary,
                "error": call.error,
                "cache_hit": call.cache_hit,
                "latency_ms": call.latency_ms,
                "created_at": call.created_at.isoformat() if call.created_at else None,
            }
            for call in enrichment_run.tool_calls
        ],
    }


def _item_gaps(item: Any) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if not _has_detail_info(item):
        gaps.append(_gap(item, "missing_detail_info", "high", "상세 이용정보가 없어 운영 조건을 확정할 수 없습니다."))
    if not _has_image_asset(item):
        gaps.append(_gap(item, "missing_image_asset", "medium", "대표/상세 이미지 후보가 부족합니다."))
    if not _text_has_any(item, ("이용시간", "운영시간", "usetime", "opentime", "이용 시간")):
        gaps.append(_gap(item, "missing_operating_hours", "medium", "운영 시간 근거가 부족합니다."))
    if not _text_has_any(item, ("요금", "입장료", "가격", "이용료", "usefee", "fee")):
        gaps.append(_gap(item, "missing_price_or_fee", "low", "요금/가격 근거가 부족합니다."))
    if not _text_has_any(item, ("예약", "예매", "booking", "reservation")):
        gaps.append(_gap(item, "missing_booking_info", "low", "예약/예매 조건 근거가 부족합니다."))
    if _eligible_for_related_places(item):
        gaps.append(
            _gap(
                item,
                "missing_related_places",
                "low",
                "주변/연관 관광지 신호가 없어 코스 조합 근거가 부족합니다.",
                source_family="kto_related_places",
            )
        )
    return gaps


def _gap(
    item: Any,
    gap_type: str,
    severity: str,
    reason: str,
    *,
    source_family: str = "kto_tourapi_kor",
) -> dict[str, Any]:
    item_id = _get(item, "id")
    content_id = _get(item, "content_id")
    return {
        "id": f"gap:{gap_type}:{item_id or content_id}",
        "gap_type": gap_type,
        "severity": severity,
        "reason": reason,
        "target_entity_id": f"entity:tourapi:content:{content_id}" if content_id else None,
        "target_content_id": content_id,
        "target_item_id": item_id,
        "source_item_title": _get(item, "title"),
        "suggested_source_family": source_family,
        "needs_review": True,
    }


def _route_gap(source_items: list[Any], normalized_request: dict[str, Any]) -> dict[str, Any] | None:
    text = " ".join(
        str(value or "")
        for value in [
            normalized_request.get("message"),
            " ".join(normalized_request.get("preferred_themes") or []),
            (normalized_request.get("geo_scope") or {}).get("mode") if isinstance(normalized_request.get("geo_scope"), dict) else "",
        ]
    )
    if not any(token in text for token in ["코스", "동선", "도보", "걷기", "트레킹", "시작", "끝나는"]):
        return None
    return {
        "id": "gap:missing_route_context:request",
        "gap_type": "missing_route_context",
        "severity": "medium",
        "reason": "요청이 동선/코스형 상품을 암시하지만 route asset 근거가 아직 없습니다.",
        "target_entity_id": None,
        "target_content_id": None,
        "target_item_id": None,
        "source_item_title": None,
        "suggested_source_family": "kto_durunubi",
        "needs_review": True,
    }


def _theme_gap(source_items: list[Any], normalized_request: dict[str, Any]) -> dict[str, Any] | None:
    text = " ".join(
        str(value or "")
        for value in [
            normalized_request.get("message"),
            normalized_request.get("user_intent"),
            " ".join(normalized_request.get("preferred_themes") or []),
            " ".join(normalized_request.get("evidence_requirements") or []),
        ]
    )
    for token, source_family in THEME_SOURCE_HINTS.items():
        if token not in text:
            continue
        geo_scope = normalized_request.get("geo_scope") if isinstance(normalized_request.get("geo_scope"), dict) else {}
        locations = geo_scope.get("locations") if isinstance(geo_scope.get("locations"), list) else []
        first_location = locations[0] if locations and isinstance(locations[0], dict) else {}
        return {
            "id": f"gap:missing_theme_specific_data:{source_family}",
            "gap_type": "missing_theme_specific_data",
            "severity": "medium" if source_family != "kto_medical" else "high",
            "reason": f"{token} 테마 요청에 맞는 특화 KTO source 근거가 아직 없습니다.",
            "target_entity_id": None,
            "target_content_id": None,
            "target_item_id": None,
            "source_item_title": None,
            "suggested_source_family": source_family,
            "search_keyword": token,
            "ldong_regn_cd": first_location.get("ldong_regn_cd"),
            "ldong_signgu_cd": first_location.get("ldong_signgu_cd"),
            "needs_review": True,
        }
    return None


def _merge_required_request_level_gaps(
    gaps: list[dict[str, Any]],
    *,
    source_items: list[Any],
    normalized_request: dict[str, Any],
) -> list[dict[str, Any]]:
    merged = list(gaps)
    required = [
        gap
        for gap in [
            _route_gap(source_items, normalized_request),
            _theme_gap(source_items, normalized_request),
        ]
        if gap
    ]
    existing_ids = {str(gap.get("id") or "") for gap in merged}
    existing_theme_families = {
        str(gap.get("suggested_source_family") or "")
        for gap in merged
        if str(gap.get("gap_type") or "") in THEME_GAP_TYPES
    }
    existing_route_types = {
        str(gap.get("gap_type") or "")
        for gap in merged
        if str(gap.get("gap_type") or "") in ROUTE_SIGNAL_GAP_TYPES
    }
    for gap in required:
        gap_id = str(gap.get("id") or "")
        gap_type = str(gap.get("gap_type") or "")
        family = str(gap.get("suggested_source_family") or "")
        if gap_id in existing_ids:
            continue
        if gap_type in THEME_GAP_TYPES and family in existing_theme_families:
            continue
        if gap_type in ROUTE_SIGNAL_GAP_TYPES and gap_type in existing_route_types:
            continue
        merged.append(gap)
    return merged


def _dedupe_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for gap in gaps:
        if gap["id"] in seen:
            continue
        seen.add(gap["id"])
        deduped.append(gap)
    return deduped


def _prioritize_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    indexed = list(enumerate(gaps))
    indexed.sort(
        key=lambda row: (
            severity_rank.get(str(row[1].get("severity") or ""), 3),
            0 if _is_request_strategy_gap(row[1]) else 1,
            0 if row[1].get("target_item_id") or row[1].get("target_content_id") else 1,
            row[0],
        )
    )
    return [gap for _, gap in indexed]


def _is_request_strategy_gap(gap: dict[str, Any]) -> bool:
    gap_type = str(gap.get("gap_type") or "")
    return not (gap.get("target_item_id") or gap.get("target_content_id")) and (
        gap_type in THEME_GAP_TYPES or gap_type in ROUTE_SIGNAL_GAP_TYPES
    )


def _coverage_summary(source_items: list[Any], gaps: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(source_items)
    gap_types = [str(gap.get("gap_type")) for gap in gaps]
    return {
        "total_items": total,
        "gap_count": len(gaps),
        "detail_info_coverage": _coverage_ratio(total, gap_types.count("missing_detail_info")),
        "image_coverage": _coverage_ratio(total, gap_types.count("missing_image_asset")),
        "operating_hours_coverage": _coverage_ratio(total, gap_types.count("missing_operating_hours")),
        "price_or_fee_coverage": _coverage_ratio(total, gap_types.count("missing_price_or_fee")),
        "booking_info_coverage": _coverage_ratio(total, gap_types.count("missing_booking_info")),
        "gap_counts": dict(sorted((gap_type, gap_types.count(gap_type)) for gap_type in set(gap_types))),
    }


def _coverage_ratio(total: int, missing_count: int) -> float:
    if total <= 0:
        return 1.0
    return round(max(0.0, (total - missing_count) / total), 3)


def _source_family_for_future_gap(gap: dict[str, Any]) -> str:
    explicit = str(gap.get("suggested_source_family") or "")
    if explicit:
        return explicit
    return FUTURE_SOURCE_BY_GAP.get(str(gap.get("gap_type") or ""), "kto_tourapi_kor")


def _planner_for_gap(gap: dict[str, Any], settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    gap_type = str(gap.get("gap_type") or "")
    source_family = _source_family_for_future_gap(gap)
    if gap_type in VISUAL_GAP_TYPES and _visual_enabled_families(settings):
        return "visual_data"
    if source_family == "kto_tourapi_kor" and gap_type in DETAIL_GAP_TYPES:
        if gap.get("target_item_id") or gap.get("target_content_id"):
            return "tourapi_detail"
    for planner_key, definition in PLANNER_DEFINITIONS.items():
        if source_family in definition["source_families"]:
            return planner_key
    for planner_key, definition in PLANNER_DEFINITIONS.items():
        if gap_type in definition["gap_types"]:
            return planner_key
    return "tourapi_detail"


def _route_priority(
    planner: str,
    gap_ids: list[str],
    gaps_by_id: dict[str, dict[str, Any]],
    settings: Settings,
) -> str:
    severities = {str((gaps_by_id.get(gap_id) or {}).get("severity") or "") for gap_id in gap_ids}
    if planner == "theme_data" and any(
        str((gaps_by_id.get(gap_id) or {}).get("suggested_source_family")) == "kto_medical"
        for gap_id in gap_ids
    ) and not settings.allow_medical_api:
        return "low"
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def _default_route_reason(planner: str) -> str:
    return {
        "tourapi_detail": "KorService2 상세/이미지 API로 확인 가능한 gap입니다.",
        "visual_data": "시각 자료 API가 필요한 이미지/visual gap입니다.",
        "route_signal": "동선, 연관 장소, 수요/혼잡 신호 API가 필요한 gap입니다.",
        "theme_data": "테마 특화 KTO API가 필요한 gap입니다.",
    }.get(planner, "해당 planner가 처리할 gap입니다.")


def _dedupe_family_routes(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_planner: dict[str, dict[str, Any]] = {}
    for route in routes:
        planner = str(route.get("planner") or "")
        if planner not in PLANNER_DEFINITIONS:
            continue
        existing = by_planner.setdefault(
            planner,
            {
                **route,
                "gap_ids": [],
                "source_families": route.get("source_families") or PLANNER_DEFINITIONS[planner]["source_families"],
            },
        )
        for gap_id in _string_list(route.get("gap_ids")):
            if gap_id not in existing["gap_ids"]:
                existing["gap_ids"].append(gap_id)
    return [route for route in by_planner.values() if route.get("gap_ids")]


def _future_skip_reason_for_gap(gap: dict[str, Any], settings: Settings) -> str:
    source_family = _source_family_for_future_gap(gap)
    if source_family == "kto_medical" and not settings.allow_medical_api:
        return "feature_flag_disabled"
    if source_family in ROUTE_SIGNAL_SOURCE_FAMILIES and source_family not in _route_signal_enabled_families(settings):
        return "feature_flag_disabled"
    if source_family in THEME_SOURCE_FAMILIES and source_family not in _theme_enabled_families(settings):
        return "feature_flag_disabled"
    if source_family == "kto_tourism_photo" and not settings.kto_tourism_photo_enabled:
        return "feature_flag_disabled"
    if source_family == "kto_photo_contest" and not settings.kto_photo_contest_enabled:
        return "feature_flag_disabled"
    if str(gap.get("gap_type") or "") in VISUAL_GAP_TYPES and not _visual_enabled_families(settings):
        return "feature_flag_disabled"
    if str(gap.get("gap_type") or "") in ROUTE_SIGNAL_GAP_TYPES and not _route_signal_enabled_families(settings):
        return "feature_flag_disabled"
    if str(gap.get("gap_type") or "") in THEME_GAP_TYPES and not _theme_enabled_families(settings):
        return "feature_flag_disabled"
    return "future_provider_not_implemented"


def _executable_source_family_for_planner_gap(planner_key: str, gap: dict[str, Any], settings: Settings) -> str | None:
    if planner_key == "visual_data":
        return _visual_source_family_for_gap(gap, settings)
    if planner_key == "route_signal":
        return _route_signal_source_family_for_gap(gap, settings)
    if planner_key == "theme_data":
        return _theme_source_family_for_gap(gap, settings)
    return None


def _skipped_call(
    gap: dict[str, Any],
    source_family: str,
    reason: str,
    *,
    display_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"skip:{gap.get('id')}",
        "status": "skipped",
        "source_family": source_family,
        "tool_name": _future_tool_name(source_family),
        "operation": "future",
        "gap_ids": [gap.get("id")],
        "gap_types": [gap.get("gap_type")],
        "target_item_id": gap.get("target_item_id"),
        "target_content_id": gap.get("target_content_id"),
        "target_entity_id": gap.get("target_entity_id"),
        "skip_reason": reason,
        "display_name": display_name,
        "arguments": {
            "content_id": gap.get("target_content_id"),
            "item_id": gap.get("target_item_id"),
        },
    }


def _planned_detail_call(gap: dict[str, Any], index: int) -> dict[str, Any]:
    gap_id = str(gap.get("id") or f"gap:detail:{index}")
    return {
        "id": f"plan:tourapi_detail:{index}",
        "status": "planned",
        "source_family": "kto_tourapi_kor",
        "tool_name": "kto_tour_detail_enrichment",
        "operation": "detailCommon2/detailIntro2/detailInfo2/detailImage2",
        "gap_ids": [gap_id],
        "gap_types": [str(gap.get("gap_type") or "missing_detail_info")],
        "target_item_id": gap.get("target_item_id"),
        "target_content_id": gap.get("target_content_id"),
        "target_entity_id": gap.get("target_entity_id"),
        "reason": "KorService2 상세/이미지 보강으로 확인합니다.",
        "expected_ui": "Data Coverage와 Evidence에 상세정보 보강 결과를 표시합니다.",
        "arguments": {
            "item_id": gap.get("target_item_id"),
            "content_id": gap.get("target_content_id"),
        },
    }


def _planned_visual_call(gap: dict[str, Any], source_family: str, index: int) -> dict[str, Any]:
    gap_id = str(gap.get("id") or f"gap:visual:{index}")
    query = str(gap.get("source_item_title") or gap.get("target_content_id") or gap.get("target_item_id") or "").strip()
    tool_name = _visual_tool_name(source_family)
    operation = _visual_operation(source_family)
    return {
        "id": f"plan:visual_data:{source_family}:{index}",
        "status": "planned",
        "source_family": source_family,
        "tool_name": tool_name,
        "operation": operation,
        "gap_ids": [gap_id],
        "gap_types": [str(gap.get("gap_type") or "missing_image_asset")],
        "target_item_id": gap.get("target_item_id"),
        "target_content_id": gap.get("target_content_id"),
        "target_entity_id": gap.get("target_entity_id"),
        "reason": "Visual API로 이미지 후보를 조회하고 사용권 확인 필요 상태로 저장합니다.",
        "expected_ui": "Evidence와 Product card에 이미지 후보/사용권 확인 필요 상태로 표시합니다.",
        "arguments": {
            "item_id": gap.get("target_item_id"),
            "content_id": gap.get("target_content_id"),
            "query": query,
            "limit": 5,
        },
    }


def _planned_route_signal_call(gap: dict[str, Any], source_family: str, index: int) -> dict[str, Any]:
    gap_id = str(gap.get("id") or f"gap:route_signal:{index}")
    query = str(gap.get("source_item_title") or gap.get("target_content_id") or gap.get("target_item_id") or "").strip()
    tool_name = _route_signal_tool_name(source_family, gap)
    operation = _route_signal_operation(source_family, gap)
    return {
        "id": f"plan:route_signal:{source_family}:{index}",
        "status": "planned",
        "source_family": source_family,
        "tool_name": tool_name,
        "operation": operation,
        "gap_ids": [gap_id],
        "gap_types": [str(gap.get("gap_type") or "missing_route_context")],
        "target_item_id": gap.get("target_item_id"),
        "target_content_id": gap.get("target_content_id"),
        "target_entity_id": gap.get("target_entity_id"),
        "reason": "Route/Signal API로 동선·연관 장소·수요/혼잡 보조 근거를 조회합니다.",
        "expected_ui": "Evidence와 Data Coverage에 보조 신호로 표시하고 판매량/예약/안전 보장 claim은 제한합니다.",
        "arguments": {
            "item_id": gap.get("target_item_id"),
            "content_id": gap.get("target_content_id"),
            "query": query,
            "limit": 5,
        },
    }


def _planned_theme_call(gap: dict[str, Any], source_family: str, index: int) -> dict[str, Any]:
    gap_id = str(gap.get("id") or f"gap:theme:{index}")
    query = str(
        gap.get("search_keyword")
        or gap.get("source_item_title")
        or gap.get("target_content_id")
        or gap.get("reason")
        or ""
    ).strip()
    tool_name = _theme_tool_name(source_family)
    operation = _theme_operation(source_family)
    return {
        "id": f"plan:theme_data:{source_family}:{index}",
        "status": "planned",
        "source_family": source_family,
        "tool_name": tool_name,
        "operation": operation,
        "gap_ids": [gap_id],
        "gap_types": [str(gap.get("gap_type") or "missing_theme_specific_data")],
        "target_item_id": gap.get("target_item_id"),
        "target_content_id": gap.get("target_content_id"),
        "target_entity_id": gap.get("target_entity_id"),
        "reason": "Theme API로 테마 후보와 운영자 확인 필요 항목을 조회합니다.",
        "expected_ui": "Evidence와 Product card에 테마 후보/운영자 확인 필요 상태로 표시합니다.",
        "arguments": {
            "item_id": gap.get("target_item_id"),
            "content_id": gap.get("target_content_id"),
            "query": query,
            "ldong_regn_cd": gap.get("ldong_regn_cd"),
            "ldong_signgu_cd": gap.get("ldong_signgu_cd"),
            "limit": 5,
        },
    }


def _skipped_from_plan_call(call: dict[str, Any], planner: str, reason: str) -> dict[str, Any]:
    return {
        **call,
        "id": f"skip:{call.get('id')}",
        "status": "skipped",
        "planner": planner,
        "skip_reason": reason,
        "reason": reason,
    }


def _future_tool_name(source_family: str) -> str:
    return {
        "kto_tourism_photo": "kto_tourism_photo_search",
        "kto_photo_contest": "kto_photo_contest_award_list",
        "kto_related_places": "kto_related_places_area",
        "kto_durunubi": "kto_durunubi_course_list",
        "kto_tourism_bigdata": "kto_tourism_bigdata_locgo_visitors",
        "kto_crowding_forecast": "kto_attraction_crowding_forecast",
        "kto_regional_tourism_demand": "kto_regional_tourism_demand_area",
        "kto_medical": "kto_medical_keyword_search",
        "kto_pet": "kto_pet_keyword_search",
        "kto_wellness": "kto_wellness_keyword_search",
        "kto_audio": "kto_audio_story_search",
        "kto_eco": "kto_eco_area_search",
    }.get(source_family, f"{source_family}_future")


def _create_enrichment_tool_call(
    *,
    db: Session,
    enrichment_run: models.EnrichmentRun,
    plan_call: dict[str, Any],
    run_id: str,
    status: str,
) -> models.EnrichmentToolCall:
    tool_record = models.EnrichmentToolCall(
        enrichment_run_id=enrichment_run.id,
        workflow_run_id=run_id,
        plan_id=str(plan_call.get("id") or ""),
        tool_name=str(plan_call.get("tool_name") or "unknown"),
        source_family=str(plan_call.get("source_family") or "unknown"),
        arguments=plan_call.get("arguments") or {},
        status=status,
        cache_hit=False,
    )
    db.add(tool_record)
    db.commit()
    db.refresh(tool_record)
    return tool_record


def _resolve_model_item_for_plan_call(
    *,
    db: Session,
    plan_call: dict[str, Any],
    source_item: dict[str, Any] | None,
    source_items: list[dict[str, Any]],
    allow_fallback: bool,
) -> models.TourismItem | None:
    item_id = str(plan_call.get("target_item_id") or _plan_call_arguments(plan_call).get("item_id") or "")
    if item_id:
        return db.get(models.TourismItem, item_id)
    if source_item and source_item.get("id"):
        return db.get(models.TourismItem, str(source_item["id"]))
    content_id = _plan_call_content_id(plan_call)
    if content_id:
        for raw_item in source_items:
            if str(raw_item.get("content_id") or "") != content_id:
                continue
            candidate_id = str(raw_item.get("id") or "")
            if candidate_id:
                model_item = db.get(models.TourismItem, candidate_id)
                if model_item:
                    return model_item
        return (
            db.query(models.TourismItem)
            .filter(models.TourismItem.content_id == content_id)
            .order_by(models.TourismItem.updated_at.desc())
            .first()
        )
    if not allow_fallback:
        return None
    for raw_item in source_items:
        candidate_id = str(raw_item.get("id") or "")
        if not candidate_id:
            continue
        model_item = db.get(models.TourismItem, candidate_id)
        if model_item:
            return model_item
    return None


def _plan_call_arguments(plan_call: dict[str, Any]) -> dict[str, Any]:
    arguments = plan_call.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def _plan_call_content_id(plan_call: dict[str, Any]) -> str:
    content_id = str(plan_call.get("target_content_id") or _plan_call_arguments(plan_call).get("content_id") or "")
    return content_id.strip()


def _documents_by_item(
    db: Session,
    item_ids: list[str],
    retrieved_documents: list[dict[str, Any]],
) -> dict[str, list[models.SourceDocument]]:
    docs = (
        db.query(models.SourceDocument)
        .filter(models.SourceDocument.source_item_id.in_(item_ids))
        .all()
        if item_ids
        else []
    )
    result: dict[str, list[models.SourceDocument]] = defaultdict(list)
    for doc in docs:
        result[doc.source_item_id].append(doc)
    retrieved_by_item = {
        str((doc.get("metadata") or {}).get("source_item_id")): doc
        for doc in retrieved_documents
        if (doc.get("metadata") or {}).get("source_item_id")
    }
    for item_id, retrieved in retrieved_by_item.items():
        if result.get(item_id):
            continue
        result[item_id] = [
            models.SourceDocument(
                id=str(retrieved.get("doc_id")),
                source=str((retrieved.get("metadata") or {}).get("source") or "tourapi"),
                source_item_id=item_id,
                title=str(retrieved.get("title") or ""),
                content=str(retrieved.get("content") or retrieved.get("snippet") or ""),
                document_metadata=retrieved.get("metadata") or {},
            )
        ]
    return result


def _model_item_to_payload(item: models.TourismItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "source": item.source,
        "content_id": item.content_id,
        "content_type": item.content_type,
        "title": item.title,
        "address": item.address,
        "overview": item.overview,
        "homepage": item.homepage,
        "tel": item.tel,
        "image_url": item.image_url,
        "event_start_date": item.event_start_date,
        "event_end_date": item.event_end_date,
        "raw": item.raw or {},
    }


def _gap_resolved(
    gap: dict[str, Any],
    item: Any,
    *,
    visual_asset_count: int = 0,
    route_asset_count: int = 0,
    signal_records: list[models.TourismSignalRecord] | None = None,
    theme_candidates: list[models.SourceDocument] | None = None,
) -> bool:
    gap_type = gap.get("gap_type")
    signal_types = {record.signal_type for record in signal_records or []}
    theme_source_families = {
        str((candidate.document_metadata or {}).get("theme_source_family") or candidate.source)
        for candidate in theme_candidates or []
    }
    if gap_type == "missing_detail_info":
        return _has_detail_info(item)
    if gap_type == "missing_image_asset":
        return _has_image_asset(item) or visual_asset_count > 0
    if gap_type == "missing_operating_hours":
        return _text_has_any(item, ("이용시간", "운영시간", "usetime", "opentime", "이용 시간"))
    if gap_type == "missing_price_or_fee":
        return _text_has_any(item, ("요금", "입장료", "가격", "이용료", "usefee", "fee"))
    if gap_type == "missing_booking_info":
        return _text_has_any(item, ("예약", "예매", "booking", "reservation"))
    if gap_type == "missing_route_context":
        return route_asset_count > 0 or "related_places" in signal_types
    if gap_type == "missing_related_places":
        return "related_places" in signal_types
    if gap_type == "missing_demand_signal":
        return bool({"visitor_demand", "regional_service_demand", "regional_culture_resource_demand"} & signal_types)
    if gap_type == "missing_crowding_signal":
        return "crowding_forecast" in signal_types
    if gap_type == "missing_regional_demand_signal":
        return bool({"regional_service_demand", "regional_culture_resource_demand"} & signal_types)
    if gap_type == "missing_theme_specific_data":
        return bool(theme_source_families)
    if gap_type == "missing_pet_policy":
        return "kto_pet" in theme_source_families
    if gap_type == "missing_wellness_attributes":
        return "kto_wellness" in theme_source_families
    if gap_type == "missing_story_asset":
        return "kto_audio" in theme_source_families
    if gap_type == "missing_multilingual_story":
        return "kto_audio" in theme_source_families
    if gap_type == "missing_sustainability_context":
        return "kto_eco" in theme_source_families
    if gap_type == "missing_medical_context":
        return "kto_medical" in theme_source_families
    return False


def _visual_asset_count(db: Session, item: dict[str, Any]) -> int:
    return len(_visual_assets_for_item(db, item))


def _visual_assets_for_item(db: Session, item: dict[str, Any]) -> list[models.TourismVisualAsset]:
    content_id = item.get("content_id")
    item_id = item.get("id")
    filters = []
    if content_id:
        filters.append(models.TourismVisualAsset.entity_id == f"entity:tourapi:content:{content_id}")
    if item_id:
        filters.append(models.TourismVisualAsset.source_item_id == str(item_id))
    if not filters:
        return []
    assets = db.query(models.TourismVisualAsset).filter(or_(*filters)).all()
    deduped: dict[str, models.TourismVisualAsset] = {}
    for asset in assets:
        deduped[asset.id] = asset
    return list(deduped.values())


def _compact_visual_assets(assets: list[models.TourismVisualAsset]) -> list[dict[str, Any]]:
    return [
        {
            "visual_asset_id": asset.id,
            "source_family": asset.source_family,
            "title": asset.title,
            "image_url": asset.image_url,
            "thumbnail_url": asset.thumbnail_url,
            "shooting_place": asset.shooting_place,
            "shooting_date": asset.shooting_date,
            "photographer": asset.photographer,
            "keywords": asset.keywords or [],
            "license_type": asset.license_type,
            "license_note": asset.license_note,
            "usage_status": asset.usage_status,
        }
        for asset in assets[:5]
    ]


def _route_assets_for_item(db: Session, item: dict[str, Any]) -> list[models.TourismRouteAsset]:
    content_id = item.get("content_id")
    if not content_id:
        return []
    return (
        db.query(models.TourismRouteAsset)
        .filter(models.TourismRouteAsset.entity_id == f"entity:tourapi:content:{content_id}")
        .all()
    )


def _signal_records_for_item(db: Session, item: dict[str, Any]) -> list[models.TourismSignalRecord]:
    content_id = item.get("content_id")
    if not content_id:
        return []
    return (
        db.query(models.TourismSignalRecord)
        .filter(models.TourismSignalRecord.entity_id == f"entity:tourapi:content:{content_id}")
        .all()
    )


def _theme_candidates_for_item(db: Session, item: dict[str, Any]) -> list[models.SourceDocument]:
    item_id = item.get("id")
    if not item_id:
        return []
    return (
        db.query(models.SourceDocument)
        .filter(
            models.SourceDocument.source_item_id == str(item_id),
            models.SourceDocument.source.in_(sorted(THEME_SOURCE_FAMILIES)),
        )
        .all()
    )


def _compact_route_assets(assets: list[models.TourismRouteAsset]) -> list[dict[str, Any]]:
    return [
        {
            "route_asset_id": asset.id,
            "source_family": asset.source_family,
            "course_name": asset.course_name,
            "path_name": asset.path_name,
            "distance_km": float(asset.distance_km) if asset.distance_km is not None else None,
            "estimated_duration": asset.estimated_duration,
            "gpx_url": asset.gpx_url,
            "safety_notes": asset.safety_notes or [],
        }
        for asset in assets[:5]
    ]


def _compact_signal_records(records: list[models.TourismSignalRecord]) -> list[dict[str, Any]]:
    return [
        {
            "signal_record_id": record.id,
            "source_family": record.source_family,
            "signal_type": record.signal_type,
            "period_start": record.period_start,
            "period_end": record.period_end,
            "value": record.value,
            "interpretation_note": record.interpretation_note,
        }
        for record in records[:10]
    ]


def _compact_theme_candidates(documents: list[models.SourceDocument]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for document in documents[:10]:
        metadata = document.document_metadata or {}
        candidates.append(
            {
                "document_id": document.id,
                "source_family": metadata.get("theme_source_family") or document.source,
                "title": document.title,
                "theme_content_id": metadata.get("theme_content_id"),
                "theme_attributes": metadata.get("theme_attributes") or {},
                "needs_review_notes": metadata.get("needs_review_notes") or [],
                "image_url": metadata.get("image_url"),
                "usage_status": metadata.get("usage_status"),
                "trust_level": metadata.get("trust_level"),
            }
        )
    return candidates


def _source_confidence(item: dict[str, Any], unresolved: list[dict[str, Any]]) -> float:
    confidence = 0.9 if item.get("source") == "tourapi" else 0.7
    confidence -= min(0.4, len(unresolved) * 0.07)
    return round(max(0.1, confidence), 3)


def _productization_advice(
    entities: list[dict[str, Any]],
    unresolved_gaps: list[dict[str, Any]],
    enrichment_summary: dict[str, Any],
) -> dict[str, Any]:
    unresolved_types = sorted({str(gap.get("gap_type")) for gap in unresolved_gaps})
    execution = enrichment_summary.get("summary") if isinstance(enrichment_summary.get("summary"), dict) else enrichment_summary
    return {
        "summary": "상세/이미지 근거는 확인된 항목만 상품화 근거로 사용하고, 남은 공백은 운영자 확인 문구로 분리합니다.",
        "usable_claims": [
            "TourAPI에 있는 장소명, 주소, 개요, 행사 기간은 근거 문서와 함께 사용할 수 있습니다.",
            "상세 이미지 후보는 candidate 상태이며 게시 전 라이선스와 원 출처 확인이 필요합니다.",
            "두루누비/연관관광지/수요/혼잡 신호는 동선과 우선순위 판단의 보조 근거로만 사용할 수 있습니다.",
            "테마 API 근거는 웰니스/반려동물/오디오/생태/의료 후보를 보조하되 인증, 효능, 안전, 허용 조건을 단정하지 않습니다.",
        ],
        "candidate_evidence_cards": [_candidate_evidence_card(entity) for entity in entities],
        "needs_review_fields": unresolved_types,
        "enrichment_execution": {
            "executed_calls": execution.get("executed_calls", 0),
            "failed_calls": execution.get("failed_calls", 0),
            "skipped_calls": execution.get("skipped_calls", 0),
        },
        "entity_count": len(entities),
    }


def _detail_facts_from_payload(item_payload: dict[str, Any]) -> dict[str, Any]:
    raw = item_payload.get("raw") if isinstance(item_payload.get("raw"), dict) else {}
    detail_intro = raw.get("detail_intro") if isinstance(raw.get("detail_intro"), dict) else {}
    detail_info = raw.get("detail_info") if isinstance(raw.get("detail_info"), list) else []
    detail_images = raw.get("detail_images") if isinstance(raw.get("detail_images"), list) else []
    return {
        "detail_common_available": bool(raw.get("detail_common")),
        "detail_intro_available": bool(detail_intro),
        "detail_info_count": len(detail_info),
        "detail_image_count": len(detail_images),
        "detail_intro_lines": detail_intro_to_lines(detail_intro)[:10],
        "detail_info_lines": detail_info_to_lines(detail_info)[:14],
        "image_candidate_count": len(detail_images) + (1 if item_payload.get("image_url") else 0),
        "image_candidates": [
            _compact_detail_image(image)
            for image in detail_images[:5]
            if isinstance(image, dict)
        ],
    }


def _compact_detail_image(image: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _truncate_text(image.get("imgname") or image.get("title"), 120),
        "source": "detailImage2",
        "has_origin_url": bool(image.get("originimgurl") or image.get("imageurl")),
        "has_thumbnail_url": bool(image.get("smallimageurl")),
    }


def _candidate_evidence_card(entity: dict[str, Any]) -> dict[str, Any]:
    unresolved_gap_types = [str(value) for value in entity.get("unresolved_gap_types") or []]
    usable_facts = _usable_facts_from_entity(entity)
    restricted_claims = _restricted_claims_from_unresolved(unresolved_gap_types)
    if entity.get("visual_asset_count"):
        restricted_claims.append("이미지는 후보 상태이므로 게시 전 공공데이터 이용 조건과 원 출처를 확인해야 합니다.")
    if entity.get("route_asset_count"):
        restricted_claims.append("동선 후보는 운영 확정 코스가 아니므로 안전, 날씨, 집결/해산 지점을 확인해야 합니다.")
    if entity.get("signal_record_count"):
        restricted_claims.append("수요/혼잡/연관 장소 신호를 판매량, 예약 가능성, 안전 보장으로 표현하지 마세요.")
    if entity.get("theme_candidate_count"):
        restricted_claims.append("테마 후보는 보조 근거이며 인증, 효능, 안전, 허용 조건을 단정하지 마세요.")
        theme_sources = {
            str(candidate.get("source_family") or "")
            for candidate in entity.get("theme_candidates") or []
            if isinstance(candidate, dict)
        }
        if "kto_medical" in theme_sources or "kto_wellness" in theme_sources:
            restricted_claims.append("의료/웰니스 효과, 치료, 건강 개선을 확정 표현하지 마세요.")
        if "kto_pet" in theme_sources:
            restricted_claims.append("반려동물 동반 가능 여부와 제한 조건은 운영자 확인 없이 단정하지 마세요.")
        if "kto_eco" in theme_sources:
            restricted_claims.append("생태/친환경 효과를 정량 보장하거나 인증처럼 표현하지 마세요.")
        if "kto_audio" in theme_sources:
            restricted_claims.append("오디오/외국어 해설 제공 여부는 실제 운영 확인 없이 단정하지 마세요.")
    visual_candidates = entity.get("visual_candidates") if isinstance(entity.get("visual_candidates"), list) else []
    route_assets = entity.get("route_assets") if isinstance(entity.get("route_assets"), list) else []
    signal_records = entity.get("signal_records") if isinstance(entity.get("signal_records"), list) else []
    theme_candidates = entity.get("theme_candidates") if isinstance(entity.get("theme_candidates"), list) else []
    return {
        "content_id": _string_or_none(entity.get("content_id")) or "",
        "source_item_id": _string_or_none(entity.get("source_item_id")) or "",
        "title": _string_or_none(entity.get("title")) or "",
        "content_type": _string_or_none(entity.get("content_type")) or "",
        "address": _string_or_none(entity.get("address")) or "",
        "evidence_strength": _evidence_strength(entity, usable_facts, unresolved_gap_types),
        "usable_facts": usable_facts,
        "experience_hooks": _experience_hooks_from_entity(entity),
        "recommended_product_angles": _product_angles_from_entity(entity),
        "operational_unknowns": unresolved_gap_types,
        "restricted_claims": restricted_claims,
        "visual_candidates": visual_candidates[:5],
        "visual_usage_status": "needs_license_review" if visual_candidates else None,
        "route_assets": route_assets[:5],
        "signal_records": signal_records[:10],
        "theme_candidates": theme_candidates[:10],
        "evidence_document_ids": [str(value) for value in entity.get("evidence_document_ids") or []],
        "source_confidence": entity.get("source_confidence"),
    }


def _usable_facts_from_entity(entity: dict[str, Any]) -> list[dict[str, Any]]:
    key_facts = entity.get("key_facts") if isinstance(entity.get("key_facts"), dict) else {}
    detail_facts = entity.get("detail_facts") if isinstance(entity.get("detail_facts"), dict) else {}
    facts: list[dict[str, Any]] = []
    if entity.get("title"):
        facts.append({"field": "장소명", "value": str(entity["title"]), "source": "TourAPI"})
    if entity.get("address"):
        facts.append({"field": "주소", "value": str(entity["address"]), "source": "TourAPI"})
    if key_facts.get("overview"):
        facts.append({"field": "개요", "value": _truncate_text(key_facts.get("overview"), 900), "source": "detailCommon2/list"})
    if key_facts.get("event_start_date") or key_facts.get("event_end_date"):
        facts.append(
            {
                "field": "기간",
                "value": f"{key_facts.get('event_start_date') or ''}~{key_facts.get('event_end_date') or ''}",
                "source": "TourAPI",
            }
        )
    if key_facts.get("homepage"):
        facts.append({"field": "홈페이지", "value": _truncate_text(key_facts.get("homepage"), 260), "source": "detailCommon2"})
    if key_facts.get("tel"):
        facts.append({"field": "문의처", "value": _truncate_text(key_facts.get("tel"), 180), "source": "detailCommon2"})
    for line in detail_facts.get("detail_intro_lines") or []:
        facts.append({"field": "상세 소개", "value": _truncate_text(line, 360), "source": "detailIntro2"})
    for line in detail_facts.get("detail_info_lines") or []:
        facts.append({"field": "이용 정보", "value": _truncate_text(line, 360), "source": "detailInfo2"})
    if detail_facts.get("image_candidate_count") or entity.get("visual_asset_count"):
        count = int(detail_facts.get("image_candidate_count") or 0) + int(entity.get("visual_asset_count") or 0)
        visual_sources = sorted(
            {
                str(candidate.get("source_family") or "")
                for candidate in (entity.get("visual_candidates") or [])
                if isinstance(candidate, dict) and candidate.get("source_family")
            }
        )
        source = "detailImage2/detailCommon2"
        if visual_sources:
            source = f"{source}/{'/'.join(visual_sources)}"
        facts.append({"field": "이미지 후보", "value": f"{count}개 후보", "source": source})
    if entity.get("route_asset_count"):
        route_names = [
            str(route.get("course_name") or route.get("path_name") or "동선 후보")
            for route in entity.get("route_assets") or []
            if isinstance(route, dict)
        ]
        facts.append(
            {
                "field": "동선 후보",
                "value": f"{int(entity.get('route_asset_count') or 0)}개 후보: {', '.join(route_names[:3])}",
                "source": "kto_durunubi",
            }
        )
    if entity.get("signal_record_count"):
        signal_types = sorted(
            {
                str(record.get("signal_type") or "")
                for record in entity.get("signal_records") or []
                if isinstance(record, dict) and record.get("signal_type")
            }
        )
        facts.append(
            {
                "field": "보조 신호",
                "value": f"{int(entity.get('signal_record_count') or 0)}개 신호: {', '.join(signal_types[:5])}",
                "source": "KTO route/signal APIs",
            }
        )
    if entity.get("theme_candidate_count"):
        theme_sources = sorted(
            {
                str(candidate.get("source_family") or "")
                for candidate in entity.get("theme_candidates") or []
                if isinstance(candidate, dict) and candidate.get("source_family")
            }
        )
        theme_titles = [
            str(candidate.get("title") or "테마 후보")
            for candidate in entity.get("theme_candidates") or []
            if isinstance(candidate, dict)
        ]
        facts.append(
            {
                "field": "테마 후보",
                "value": f"{int(entity.get('theme_candidate_count') or 0)}개 후보: {', '.join(theme_titles[:3])}",
                "source": "/".join(theme_sources) or "KTO theme APIs",
            }
        )
    return facts[:14]


def _experience_hooks_from_entity(entity: dict[str, Any]) -> list[str]:
    facts = _usable_facts_from_entity(entity)
    hooks: list[str] = []
    for fact in facts:
        value = str(fact.get("value") or "")
        if fact.get("field") in {"개요", "상세 소개", "이용 정보"} and value:
            hooks.append(_truncate_text(value, 140))
        if len(hooks) >= 3:
            break
    return hooks


def _product_angles_from_entity(entity: dict[str, Any]) -> list[str]:
    title = str(entity.get("title") or "해당 후보")
    content_type = str(entity.get("content_type") or "")
    angles = [f"{title}의 공식 관광정보 기반 체험 포인트를 중심으로 구성"]
    if content_type == "event":
        angles.append("행사 기간과 장소가 확인되는 경우 기간 한정 상품으로 구성")
    elif content_type == "leisure":
        angles.append("체험/액티비티 요소를 전면에 두고 안전/이용 조건은 별도 확인")
    elif content_type == "restaurant":
        angles.append("미식 동선의 한 지점으로 활용하되 영업시간은 확인 필요")
    if entity.get("visual_asset_count"):
        angles.append("이미지 후보는 내부 검수 후 썸네일/상세페이지 소재로 활용")
    if entity.get("route_asset_count"):
        angles.append("두루누비 코스 후보는 동선 설계 참고로만 사용하고 운영 조건은 확인")
    if entity.get("signal_record_count"):
        angles.append("수요/혼잡/연관 장소 신호는 후보 우선순위와 리스크 검토에만 활용")
    if entity.get("theme_candidate_count"):
        angles.append("테마 API 후보는 상품 콘셉트 보조 근거로 쓰고 세부 조건은 확인 항목으로 분리")
    return angles[:3]


def _evidence_strength(entity: dict[str, Any], usable_facts: list[dict[str, Any]], unresolved_gap_types: list[str]) -> str:
    if not usable_facts:
        return "insufficient_evidence"
    if entity.get("detail_available") and not unresolved_gap_types:
        return "strong"
    if (
        entity.get("detail_available")
        or entity.get("visual_asset_count")
        or entity.get("route_asset_count")
        or entity.get("signal_record_count")
        or entity.get("theme_candidate_count")
    ):
        return "moderate"
    return "basic"


def _restricted_claims_from_unresolved(unresolved_gap_types: list[str]) -> list[str]:
    mapping = {
        "missing_operating_hours": "운영시간을 확정 표현으로 쓰지 마세요.",
        "missing_price_or_fee": "요금/무료 여부를 단정하지 마세요.",
        "missing_booking_info": "예약 가능 여부를 단정하지 마세요.",
        "missing_related_places": "주변 장소 추천을 근거 없이 확장하지 마세요.",
        "missing_route_context": "이동 동선과 소요시간을 근거 없이 단정하지 마세요.",
        "missing_demand_signal": "수요 신호를 판매량이나 예약 가능성으로 단정하지 마세요.",
        "missing_crowding_signal": "혼잡 예측이 없으면 한산함이나 안전성을 단정하지 마세요.",
        "missing_regional_demand_signal": "지역 수요를 시장성 보장으로 표현하지 마세요.",
        "missing_theme_specific_data": "테마 적합성을 공식 인증처럼 표현하지 마세요.",
        "missing_pet_policy": "반려동물 동반 가능 여부와 제한 조건을 단정하지 마세요.",
        "missing_wellness_attributes": "웰니스 효능이나 건강 개선을 단정하지 마세요.",
        "missing_story_asset": "스토리/해설 소재를 근거 없이 새로 만들지 마세요.",
        "missing_multilingual_story": "외국어 또는 오디오 해설 제공을 단정하지 마세요.",
        "missing_sustainability_context": "생태/친환경 효과를 정량 보장하지 마세요.",
        "missing_medical_context": "의료 효과, 치료, 안전성을 단정하지 마세요.",
    }
    return [mapping[gap_type] for gap_type in unresolved_gap_types if gap_type in mapping]


def _merge_productization_advice(base_advice: dict[str, Any], payload_advice: dict[str, Any]) -> dict[str, Any]:
    merged = {**base_advice, **payload_advice}
    base_cards = [card for card in base_advice.get("candidate_evidence_cards") or [] if isinstance(card, dict)]
    payload_cards = [card for card in payload_advice.get("candidate_evidence_cards") or [] if isinstance(card, dict)]
    interpretations = [
        item
        for item in payload_advice.get("candidate_interpretations") or []
        if isinstance(item, dict)
    ]
    if payload_cards:
        cards = _merge_candidate_evidence_cards(base_cards, payload_cards)
    elif base_cards:
        cards = base_cards
    else:
        cards = []
    if cards:
        merged["candidate_evidence_cards"] = _apply_candidate_interpretations(cards, interpretations)
    if interpretations:
        merged["candidate_interpretations"] = interpretations
    return merged


def _apply_candidate_interpretations(
    cards: list[dict[str, Any]],
    interpretations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    interpretations_by_key: dict[str, dict[str, Any]] = {}
    for interpretation in interpretations:
        key = _candidate_card_key(interpretation)
        if key:
            interpretations_by_key[key] = interpretation

    merged_cards: list[dict[str, Any]] = []
    for card in cards:
        interpretation = interpretations_by_key.get(_candidate_card_key(card))
        if not interpretation:
            merged_cards.append(card)
            continue
        enriched = {**card, "fusion_interpretation": _compact_candidate_interpretation(interpretation)}
        angle_values = _string_list(interpretation.get("recommended_product_angles"))
        if interpretation.get("product_angle"):
            angle_values.insert(0, str(interpretation.get("product_angle")))
        hook_values = _string_list(interpretation.get("experience_hooks"))
        caution_values = _string_list(interpretation.get("use_with_caution"))
        enriched["recommended_product_angles"] = _merge_list_values(
            card.get("recommended_product_angles"),
            angle_values[:3],
        )
        enriched["experience_hooks"] = _merge_list_values(card.get("experience_hooks"), hook_values[:3])
        enriched["restricted_claims"] = _merge_list_values(card.get("restricted_claims"), caution_values[:3])
        merged_cards.append(enriched)
    return merged_cards


def _compact_candidate_interpretation(interpretation: dict[str, Any]) -> dict[str, Any]:
    return {
        "priority": str(interpretation.get("priority") or "").strip(),
        "product_angle": _truncate_text(interpretation.get("product_angle"), 160),
        "rationale": _truncate_text(interpretation.get("rationale"), 240),
        "use_with_caution": _string_list(interpretation.get("use_with_caution"))[:3],
    }


def _merge_candidate_evidence_cards(base_cards: list[dict[str, Any]], payload_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for card in base_cards:
        key = _candidate_card_key(card)
        if not key:
            continue
        by_key[key] = card
        order.append(key)
    for card in payload_cards:
        key = _candidate_card_key(card)
        if not key:
            continue
        if key not in by_key:
            order.append(key)
            by_key[key] = card
            continue
        by_key[key] = _merge_candidate_card(by_key[key], card)
    return [by_key[key] for key in order if key in by_key]


def _merge_candidate_card(base_card: dict[str, Any], payload_card: dict[str, Any]) -> dict[str, Any]:
    merged = {**base_card, **payload_card}
    for key in (
        "usable_facts",
        "experience_hooks",
        "recommended_product_angles",
        "operational_unknowns",
        "restricted_claims",
        "visual_candidates",
        "route_assets",
        "signal_records",
        "theme_candidates",
    ):
        merged[key] = _merge_list_values(base_card.get(key), payload_card.get(key))
    return merged


def _candidate_card_key(card: dict[str, Any]) -> str:
    return str(card.get("content_id") or card.get("source_item_id") or card.get("title") or "").strip()


def _merge_list_values(base_value: Any, payload_value: Any) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for value in (base_value if isinstance(base_value, list) else []) + (
        payload_value if isinstance(payload_value, list) else []
    ):
        key = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, dict) else str(value)
        if key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return merged


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _has_detail_info(item: Any) -> bool:
    raw = _raw(item)
    detail_info = raw.get("detail_info")
    return isinstance(detail_info, list) and len(detail_info) > 0


def _has_image_asset(item: Any) -> bool:
    if _get(item, "image_url"):
        return True
    raw = _raw(item)
    detail_images = raw.get("detail_images")
    return isinstance(detail_images, list) and len(detail_images) > 0


def _eligible_for_related_places(item: Any) -> bool:
    content_type = str(_get(item, "content_type") or "")
    if content_type not in {"attraction", "leisure", "event"}:
        return False
    return bool(_get(item, "map_x") and _get(item, "map_y"))


def _text_has_any(item: Any, needles: tuple[str, ...]) -> bool:
    raw = _raw(item)
    haystack = " ".join(
        str(value or "")
        for value in [
            _get(item, "overview"),
            _get(item, "homepage"),
            _get(item, "tel"),
            raw.get("detail_intro"),
            raw.get("detail_info"),
            raw.get("detail_common"),
        ]
    ).lower()
    return any(needle.lower() in haystack for needle in needles)


def _raw(item: Any) -> dict[str, Any]:
    value = _get(item, "raw")
    return value if isinstance(value, dict) else {}


def _get(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _compact_item(item: Any) -> dict[str, Any]:
    raw = _raw(item)
    return {
        "id": _get(item, "id"),
        "content_id": _get(item, "content_id"),
        "content_type": _get(item, "content_type"),
        "title": _get(item, "title"),
        "address": _get(item, "address"),
        "overview": str(_get(item, "overview") or "")[:300],
        "homepage": _get(item, "homepage"),
        "tel": _get(item, "tel"),
        "image_url": _get(item, "image_url"),
        "event_start_date": _get(item, "event_start_date"),
        "event_end_date": _get(item, "event_end_date"),
        "has_detail_common": bool(raw.get("detail_common")),
        "detail_info_count": len(raw.get("detail_info") or []) if isinstance(raw.get("detail_info"), list) else 0,
        "detail_image_count": len(raw.get("detail_images") or []) if isinstance(raw.get("detail_images"), list) else 0,
    }


def _retrieved_content_rank(retrieved_documents: list[dict[str, Any]]) -> dict[str, int]:
    ranked: dict[str, int] = {}
    for index, doc in enumerate(retrieved_documents):
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        content_id = str(metadata.get("content_id") or "").strip()
        if content_id and content_id not in ranked:
            ranked[content_id] = index
    return ranked


def _candidate_relevance_score(
    item: dict[str, Any],
    normalized_request: dict[str, Any],
    retrieved_rank: dict[str, int],
) -> float:
    text = " ".join(
        [
            str(normalized_request.get("message") or ""),
            str(normalized_request.get("target_customer") or ""),
            " ".join(str(theme) for theme in normalized_request.get("preferred_themes") or []),
            str(item.get("title") or ""),
            str(item.get("address") or ""),
        ]
    )
    content_type = str(item.get("content_type") or "")
    score = 0.0
    if item.get("content_id"):
        score += 10
    if item.get("image_url"):
        score += 3
    if item.get("overview"):
        score += 5
    if content_type == "event":
        score += 24 if _contains_any(text, ["축제", "행사", "이벤트", "페스티벌"]) else 8
    elif content_type == "leisure":
        score += 22 if _contains_any(text, ["액티비티", "체험", "레저", "야간", "투어"]) else 10
    elif content_type in {"attraction", "culture", "course"}:
        score += 10
    elif content_type == "accommodation":
        score += 8 if _contains_any(text, ["숙박", "호텔", "스테이"]) else -20
    elif content_type in {"restaurant", "shopping"}:
        score += 6

    if item.get("event_start_date") or item.get("event_end_date"):
        score += 8
    title = str(item.get("title") or "")
    for term in normalized_request.get("preferred_themes") or []:
        if term and str(term) in title:
            score += 6
    content_id = str(item.get("content_id") or "")
    if content_id in retrieved_rank:
        score += max(0, 18 - retrieved_rank[content_id] * 2)
    return score


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _compact_base_fusion_for_prompt(base_fusion: dict[str, Any]) -> dict[str, Any]:
    profile = base_fusion.get("evidence_profile") if isinstance(base_fusion.get("evidence_profile"), dict) else {}
    entities = profile.get("entities") if isinstance(profile.get("entities"), list) else []
    enriched_entities = [
        _compact_fusion_entity(entity)
        for entity in entities
        if isinstance(entity, dict)
        and (
            entity.get("detail_available")
            or entity.get("visual_asset_count")
            or entity.get("route_asset_count")
            or entity.get("signal_record_count")
            or entity.get("theme_candidate_count")
        )
    ]
    unresolved_entities = [
        _compact_fusion_entity(entity)
        for entity in entities
        if isinstance(entity, dict) and entity.get("unresolved_gap_types")
    ]
    return {
        "entity_count": len(entities),
        "source_document_count": profile.get("source_document_count"),
        "data_coverage": base_fusion.get("data_coverage") or {},
        "source_confidence": base_fusion.get("source_confidence"),
        "enriched_entities": enriched_entities[:12],
        "unresolved_entities": unresolved_entities[:12],
        "truncated": len(enriched_entities) > 12 or len(unresolved_entities) > 12,
    }


def _compact_fusion_entity(entity: dict[str, Any]) -> dict[str, Any]:
    key_facts = entity.get("key_facts") if isinstance(entity.get("key_facts"), dict) else {}
    detail_facts = entity.get("detail_facts") if isinstance(entity.get("detail_facts"), dict) else {}
    visual_candidates = entity.get("visual_candidates") if isinstance(entity.get("visual_candidates"), list) else []
    route_assets = entity.get("route_assets") if isinstance(entity.get("route_assets"), list) else []
    signal_records = entity.get("signal_records") if isinstance(entity.get("signal_records"), list) else []
    theme_candidates = entity.get("theme_candidates") if isinstance(entity.get("theme_candidates"), list) else []
    return {
        "content_id": entity.get("content_id"),
        "source_item_id": entity.get("source_item_id"),
        "title": entity.get("title"),
        "content_type": entity.get("content_type"),
        "address": entity.get("address"),
        "evidence_document_ids": entity.get("evidence_document_ids") or [],
        "detail_available": bool(entity.get("detail_available")),
        "visual_asset_count": entity.get("visual_asset_count"),
        "route_asset_count": entity.get("route_asset_count"),
        "signal_record_count": entity.get("signal_record_count"),
        "theme_candidate_count": entity.get("theme_candidate_count"),
        "source_confidence": entity.get("source_confidence"),
        "unresolved_gap_types": entity.get("unresolved_gap_types") or [],
        "visual_summary": {
            "candidate_count": len(visual_candidates),
            "usage_statuses": sorted({str(candidate.get("usage_status") or "") for candidate in visual_candidates if isinstance(candidate, dict) and candidate.get("usage_status")}),
            "sample_titles": [
                _truncate_text(candidate.get("title"), 80)
                for candidate in visual_candidates
                if isinstance(candidate, dict) and candidate.get("title")
            ][:2],
        },
        "route_summary": {
            "candidate_count": len(route_assets),
            "sample_names": [
                _truncate_text(route.get("course_name") or route.get("path_name"), 80)
                for route in route_assets
                if isinstance(route, dict) and (route.get("course_name") or route.get("path_name"))
            ][:2],
        },
        "signal_summary": {
            "record_count": len(signal_records),
            "signal_types": sorted({str(record.get("signal_type") or "") for record in signal_records if isinstance(record, dict) and record.get("signal_type")}),
        },
        "theme_summary": {
            "candidate_count": len(theme_candidates),
            "source_families": sorted({str(candidate.get("source_family") or "") for candidate in theme_candidates if isinstance(candidate, dict) and candidate.get("source_family")}),
            "sample_titles": [
                _truncate_text(candidate.get("title"), 80)
                for candidate in theme_candidates
                if isinstance(candidate, dict) and candidate.get("title")
            ][:2],
        },
        "key_facts": {
            "overview": _truncate_text(key_facts.get("overview"), 360),
            "homepage": key_facts.get("homepage"),
            "tel": key_facts.get("tel"),
            "event_start_date": key_facts.get("event_start_date"),
            "event_end_date": key_facts.get("event_end_date"),
        },
        "detail_facts": {
            "detail_common_available": bool(detail_facts.get("detail_common_available")),
            "detail_intro_available": bool(detail_facts.get("detail_intro_available")),
            "detail_info_count": detail_facts.get("detail_info_count", 0),
            "detail_image_count": detail_facts.get("detail_image_count", 0),
            "detail_intro_lines": [
                _truncate_text(line, 180)
                for line in detail_facts.get("detail_intro_lines") or []
            ][:3],
            "detail_info_lines": [
                _truncate_text(line, 180)
                for line in detail_facts.get("detail_info_lines") or []
            ][:3],
            "image_candidate_count": detail_facts.get("image_candidate_count", 0),
        },
    }


def _compact_enrichment_summary_for_fusion(enrichment_summary: dict[str, Any]) -> dict[str, Any]:
    summary = enrichment_summary.get("summary") if isinstance(enrichment_summary.get("summary"), dict) else {}
    skipped = summary.get("skipped") if isinstance(summary.get("skipped"), list) else []
    skip_counts: dict[str, int] = {}
    for call in skipped:
        if not isinstance(call, dict):
            continue
        reason = str(call.get("skip_reason") or "unknown")
        skip_counts[reason] = skip_counts.get(reason, 0) + 1
    return {
        "status": enrichment_summary.get("status"),
        "executed_calls": summary.get("executed_calls", 0),
        "skipped_calls": summary.get("skipped_calls", 0),
        "failed_calls": summary.get("failed_calls", 0),
        "enriched_item_ids": summary.get("enriched_item_ids") or [],
        "indexed_documents": summary.get("indexed_documents", 0),
        "visual_assets": summary.get("visual_assets", 0),
        "route_assets": summary.get("route_assets", 0),
        "signal_records": summary.get("signal_records", 0),
        "theme_candidates": summary.get("theme_candidates", 0),
        "skip_reason_counts": dict(sorted(skip_counts.items())),
    }


def _compact_document(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    return {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title"),
        "snippet": str(doc.get("snippet") or doc.get("content") or "")[:360],
        "score": doc.get("score"),
        "metadata": {
            "source_family": metadata.get("source_family"),
            "content_id": metadata.get("content_id"),
            "content_type": metadata.get("content_type"),
            "detail_common_available": metadata.get("detail_common_available"),
            "detail_info_count": metadata.get("detail_info_count"),
            "visual_asset_count": metadata.get("visual_asset_count"),
            "route_asset_count": metadata.get("route_asset_count"),
            "signal_record_count": metadata.get("signal_record_count"),
            "signal_type": metadata.get("signal_type"),
            "theme_candidate_count": metadata.get("theme_candidate_count"),
            "theme_source_family": metadata.get("theme_source_family"),
            "theme_attributes": metadata.get("theme_attributes"),
            "data_quality_flags": metadata.get("data_quality_flags"),
            "trust_level": metadata.get("trust_level"),
            "retrieved_at": metadata.get("retrieved_at"),
        },
    }


def _compact_gap_report_for_router(gap_report: dict[str, Any]) -> dict[str, Any]:
    gaps = gap_report.get("gaps") if isinstance(gap_report.get("gaps"), list) else []
    compact_gaps: list[dict[str, Any]] = []
    for gap in gaps[:60]:
        if not isinstance(gap, dict):
            continue
        compact_gaps.append(
            {
                "id": gap.get("id"),
                "gap_type": gap.get("gap_type"),
                "severity": gap.get("severity"),
                "target_item_id": gap.get("target_item_id"),
                "target_content_id": gap.get("target_content_id"),
                "source_item_title": gap.get("source_item_title"),
                "suggested_source_family": gap.get("suggested_source_family"),
                "needs_review": bool(gap.get("needs_review")),
            }
        )
    return {
        "gaps": compact_gaps,
        "total_gap_count": len(gaps),
        "coverage": gap_report.get("coverage") if isinstance(gap_report.get("coverage"), dict) else {},
        "summary": gap_report.get("summary") if isinstance(gap_report.get("summary"), dict) else {},
        "reasoning_summary": str(gap_report.get("reasoning_summary") or "")[:500],
        "truncated": len(gaps) > len(compact_gaps),
    }


def _compact_capabilities_for_router(capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for capability in capabilities:
        source_family = str(capability.get("source_family") or "")
        operations = [
            {
                "operation": operation.get("operation"),
                "implemented": bool(operation.get("implemented")),
                "workflow_enabled": bool(operation.get("workflow_enabled")),
            }
            for operation in capability.get("operations") or []
            if isinstance(operation, dict)
        ]
        compact.append(
            {
                "source_family": source_family,
                "fills_gaps": capability.get("fills_gaps") or capability.get("supported_gaps") or [],
                "phase10_2_status": capability.get("phase10_2_status"),
                "runtime_enabled": bool(capability.get("runtime_enabled")),
                "runtime_disabled_reasons": capability.get("runtime_disabled_reasons") or [],
                "workflow_enabled_operations": capability.get("workflow_enabled_operations") or [],
                "operations": operations[:8],
            }
        )
    return compact


def _planner_lanes_for_prompt(capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    capability_by_family = {str(item.get("source_family")): item for item in capabilities}
    lanes: list[dict[str, Any]] = []
    for planner, definition in PLANNER_DEFINITIONS.items():
        lanes.append(
            {
                "planner": planner,
                "agent_name": definition["agent_name"],
                "source_families": definition["source_families"],
                "gap_types": definition["gap_types"],
                "phase10_2_execution": definition["phase10_2_execution"],
                "semantic_capabilities": [
                    {
                        "source_family": family,
                        "can_fill": capability_by_family.get(family, {}).get("fills_gaps") or [],
                        "phase10_2_status": capability_by_family.get(family, {}).get("phase10_2_status"),
                    }
                    for family in definition["source_families"]
                ],
            }
        )
    return lanes


def _capabilities_for_families(capabilities: list[dict[str, Any]], source_families: list[str]) -> list[dict[str, Any]]:
    allowed = set(source_families)
    return [
        item
        for item in _compact_capabilities_for_router(capabilities)
        if item.get("source_family") in allowed
    ]


def _route_for_planner(capability_routing: dict[str, Any], planner_key: str) -> dict[str, Any]:
    for route in capability_routing.get("family_routes") or []:
        if isinstance(route, dict) and route.get("planner") == planner_key:
            return route
    definition = PLANNER_DEFINITIONS[planner_key]
    return {
        "planner": planner_key,
        "agent_name": definition["agent_name"],
        "gap_ids": [],
        "source_families": definition["source_families"],
        "reason": "배정된 gap이 없습니다.",
        "priority": "low",
    }


def _gaps_for_ids(gap_report: dict[str, Any], gap_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(_string_list(gap_ids))
    return [
        _compact_gap_for_planner(gap)
        for gap in gap_report.get("gaps") or []
        if isinstance(gap, dict) and str(gap.get("id")) in wanted
    ]


def _compact_gap_for_planner(gap: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": gap.get("id"),
        "gap_type": gap.get("gap_type"),
        "severity": gap.get("severity"),
        "reason": str(gap.get("reason") or "")[:180],
        "target_item_id": gap.get("target_item_id"),
        "target_content_id": gap.get("target_content_id"),
        "source_item_title": gap.get("source_item_title"),
        "suggested_source_family": gap.get("suggested_source_family"),
        "needs_review": bool(gap.get("needs_review")),
    }


def _detail_target_candidates(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = _gaps_by_detail_target(gaps)
    candidates: list[dict[str, Any]] = []
    for target_key, target_gaps in grouped.items():
        executable_gaps = [gap for gap in target_gaps if _is_executable_detail_gap(gap)]
        if not executable_gaps:
            continue
        first = executable_gaps[0]
        candidates.append(
            {
                "target_key": target_key,
                "target_item_id": first.get("target_item_id"),
                "target_content_id": first.get("target_content_id"),
                "title": first.get("source_item_title"),
                "gap_ids": [gap.get("id") for gap in executable_gaps if gap.get("id")],
                "gap_types": sorted({str(gap.get("gap_type") or "") for gap in executable_gaps if gap.get("gap_type")}),
                "severity": _highest_severity(executable_gaps),
                "needs_review": any(bool(gap.get("needs_review")) for gap in executable_gaps),
            }
        )
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        candidates,
        key=lambda item: (
            severity_rank.get(str(item.get("severity")), 3),
            not bool(item.get("needs_review")),
            str(item.get("title") or ""),
        ),
    )


def _gaps_by_detail_target(gaps: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for gap in gaps:
        target_key = _detail_target_key(gap)
        if target_key:
            grouped[target_key].append(gap)
    return grouped


def _detail_target_key(value: dict[str, Any]) -> str:
    return str(value.get("target_item_id") or value.get("target_content_id") or "").strip()


def _is_executable_detail_gap(gap: dict[str, Any]) -> bool:
    return _is_detail_gap(gap) and bool(_detail_target_key(gap))


def _highest_severity(gaps: list[dict[str, Any]]) -> str:
    rank = {"high": 0, "medium": 1, "low": 2}
    severity = min((str(gap.get("severity") or "medium") for gap in gaps), key=lambda value: rank.get(value, 1))
    return severity if severity in rank else "medium"


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _content_id_from_entity_id(value: Any) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    for prefix in ("tourapi:content:", "entity:tourapi:content:"):
        if text.startswith(prefix):
            content_id = text.removeprefix(prefix).strip()
            return content_id or None
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_severity(value: Any) -> str:
    severity = str(value or "medium").lower()
    return severity if severity in {"high", "medium", "low"} else "medium"


def _normalize_coverage(value: Any, source_items: list[Any], gaps: list[dict[str, Any]]) -> dict[str, Any]:
    base = _coverage_summary(source_items, gaps)
    if not isinstance(value, dict):
        return base
    normalized = dict(base)
    for key in [
        "detail_info_coverage",
        "image_coverage",
        "operating_hours_coverage",
        "price_or_fee_coverage",
        "booking_info_coverage",
    ]:
        if key in value:
            normalized[key] = _number_or_default(value.get(key), normalized[key])
    normalized["gap_count"] = len(gaps)
    normalized["gap_counts"] = base["gap_counts"]
    return normalized


def _number_or_default(value: Any, default: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        try:
            return float(default)
        except (TypeError, ValueError):
            return 0.0
    return round(max(0.0, min(1.0, numeric)), 3)


def _can_execute_workflow_call(call: dict[str, Any], capability: dict[str, Any]) -> bool:
    source_family = str(call.get("source_family") or "")
    if source_family == "kto_tourapi_kor":
        if call.get("tool_name") != "kto_tour_detail_enrichment":
            return False
        if str(call.get("operation") or "") != "detailCommon2/detailIntro2/detailInfo2/detailImage2":
            return False
        return any(
            operation.get("operation") == "detailCommon2" and operation.get("workflow_enabled")
            for operation in capability.get("operations") or []
        )
    if source_family == "kto_tourism_photo":
        return (
            call.get("tool_name") == "kto_tourism_photo_search"
            and str(call.get("operation") or "") == "gallerySearchList1"
            and any(
                operation.get("operation") == "gallerySearchList1" and operation.get("workflow_enabled")
                for operation in capability.get("operations") or []
            )
        )
    if source_family == "kto_photo_contest":
        return (
            call.get("tool_name") == "kto_photo_contest_award_list"
            and str(call.get("operation") or "") == "phokoAwrdList"
            and any(
                operation.get("operation") == "phokoAwrdList" and operation.get("workflow_enabled")
                for operation in capability.get("operations") or []
            )
        )
    if source_family in ROUTE_SIGNAL_SOURCE_FAMILIES:
        operation = str(call.get("operation") or "")
        tool_name = str(call.get("tool_name") or "")
        allowed_tools = {
            "kto_durunubi": {"kto_durunubi_course_list"},
            "kto_related_places": {"kto_related_places_area", "kto_related_places_keyword"},
            "kto_tourism_bigdata": {
                "kto_tourism_bigdata_metco_visitors",
                "kto_tourism_bigdata_locgo_visitors",
            },
            "kto_crowding_forecast": {"kto_attraction_crowding_forecast"},
            "kto_regional_tourism_demand": {
                "kto_regional_tourism_demand_area",
                "kto_regional_tourism_service_demand",
                "kto_regional_culture_resource_demand",
            },
        }
        if tool_name not in allowed_tools.get(source_family, set()):
            return False
        return any(
            op.get("operation") == operation and op.get("workflow_enabled")
            for op in capability.get("operations") or []
        )
    if source_family in THEME_SOURCE_FAMILIES:
        operation = str(call.get("operation") or "")
        tool_name = str(call.get("tool_name") or "")
        allowed_tools = {
            "kto_wellness": {"kto_wellness_keyword_search", "kto_wellness_area_search"},
            "kto_pet": {"kto_pet_keyword_search", "kto_pet_area_search"},
            "kto_audio": {"kto_audio_story_search", "kto_audio_theme_search", "kto_audio_keyword_search"},
            "kto_eco": {"kto_eco_area_search"},
            "kto_medical": {"kto_medical_keyword_search", "kto_medical_area_search"},
        }
        if tool_name not in allowed_tools.get(source_family, set()):
            return False
        return any(
            op.get("operation") == operation and op.get("workflow_enabled")
            for op in capability.get("operations") or []
        )
    return False


def _is_detail_gap(gap: dict[str, Any]) -> bool:
    return str(gap.get("gap_type") or "") in DETAIL_GAP_TYPES


def _normalize_planned_call(
    call: dict[str, Any],
    representative_gap: dict[str, Any],
    index: int,
    gap_ids: list[str],
) -> dict[str, Any]:
    gap_types = sorted(
        {
            str(gap_type)
            for gap_type in _string_list(call.get("gap_types"))
            if gap_type
        }
    ) or [str(representative_gap.get("gap_type"))]
    source_family = str(call.get("source_family") or representative_gap.get("suggested_source_family") or "kto_tourapi_kor")
    if source_family in VISUAL_SOURCE_FAMILIES:
        normalized = _planned_visual_call(representative_gap, source_family, index)
        normalized.update(
            {
                "id": str(call.get("id") or normalized["id"]),
                "tool_name": str(call.get("tool_name") or normalized["tool_name"]),
                "operation": str(call.get("operation") or normalized["operation"]),
                "gap_ids": gap_ids,
                "gap_types": gap_types,
                "target_item_id": call.get("target_item_id") or representative_gap.get("target_item_id"),
                "target_content_id": call.get("target_content_id") or representative_gap.get("target_content_id"),
                "target_entity_id": call.get("target_entity_id") or representative_gap.get("target_entity_id"),
                "reason": str(call.get("reason") or normalized["reason"]),
                "expected_ui": str(call.get("expected_ui") or normalized["expected_ui"]),
                "arguments": {
                    **normalized["arguments"],
                    **(call.get("arguments") if isinstance(call.get("arguments"), dict) else {}),
                    "item_id": call.get("target_item_id") or representative_gap.get("target_item_id"),
                    "content_id": call.get("target_content_id") or representative_gap.get("target_content_id"),
                },
            }
        )
        return normalized
    if source_family in ROUTE_SIGNAL_SOURCE_FAMILIES:
        normalized = _planned_route_signal_call(representative_gap, source_family, index)
        normalized.update(
            {
                "id": str(call.get("id") or normalized["id"]),
                "tool_name": str(call.get("tool_name") or normalized["tool_name"]),
                "operation": str(call.get("operation") or normalized["operation"]),
                "gap_ids": gap_ids,
                "gap_types": gap_types,
                "target_item_id": call.get("target_item_id") or representative_gap.get("target_item_id"),
                "target_content_id": call.get("target_content_id") or representative_gap.get("target_content_id"),
                "target_entity_id": call.get("target_entity_id") or representative_gap.get("target_entity_id"),
                "reason": str(call.get("reason") or normalized["reason"]),
                "expected_ui": str(call.get("expected_ui") or normalized["expected_ui"]),
                "arguments": {
                    **normalized["arguments"],
                    **(call.get("arguments") if isinstance(call.get("arguments"), dict) else {}),
                    "item_id": call.get("target_item_id") or representative_gap.get("target_item_id"),
                    "content_id": call.get("target_content_id") or representative_gap.get("target_content_id"),
                },
            }
        )
        return normalized
    if source_family in THEME_SOURCE_FAMILIES:
        normalized = _planned_theme_call(representative_gap, source_family, index)
        normalized.update(
            {
                "id": str(call.get("id") or normalized["id"]),
                "tool_name": str(call.get("tool_name") or normalized["tool_name"]),
                "operation": str(call.get("operation") or normalized["operation"]),
                "gap_ids": gap_ids,
                "gap_types": gap_types,
                "target_item_id": call.get("target_item_id") or representative_gap.get("target_item_id"),
                "target_content_id": call.get("target_content_id") or representative_gap.get("target_content_id"),
                "target_entity_id": call.get("target_entity_id") or representative_gap.get("target_entity_id"),
                "reason": str(call.get("reason") or normalized["reason"]),
                "expected_ui": str(call.get("expected_ui") or normalized["expected_ui"]),
                "arguments": {
                    **normalized["arguments"],
                    **(call.get("arguments") if isinstance(call.get("arguments"), dict) else {}),
                    "item_id": call.get("target_item_id") or representative_gap.get("target_item_id"),
                    "content_id": call.get("target_content_id") or representative_gap.get("target_content_id"),
                },
            }
        )
        return normalized
    return {
        "id": str(call.get("id") or f"plan:{index}"),
        "status": "planned",
        "source_family": "kto_tourapi_kor",
        "tool_name": "kto_tour_detail_enrichment",
        "operation": "detailCommon2/detailIntro2/detailInfo2/detailImage2",
        "gap_ids": gap_ids,
        "gap_types": gap_types,
        "target_item_id": call.get("target_item_id") or representative_gap.get("target_item_id"),
        "target_content_id": call.get("target_content_id") or representative_gap.get("target_content_id"),
        "target_entity_id": call.get("target_entity_id") or representative_gap.get("target_entity_id"),
        "reason": str(call.get("reason") or "Gemini가 KorService2 상세/이미지 보강이 필요하다고 판단했습니다."),
        "expected_ui": str(call.get("expected_ui") or "상세정보와 이미지 후보 보강 결과를 Data Coverage와 Evidence에서 표시합니다."),
        "arguments": {
            **(call.get("arguments") if isinstance(call.get("arguments"), dict) else {}),
            "item_id": call.get("target_item_id") or representative_gap.get("target_item_id"),
            "content_id": call.get("target_content_id") or representative_gap.get("target_content_id"),
        },
    }


def _visual_source_family_for_gap(gap: dict[str, Any], settings: Settings) -> str | None:
    explicit = str(gap.get("suggested_source_family") or "")
    enabled = _visual_enabled_families(settings)
    if explicit in enabled:
        return explicit
    if explicit in VISUAL_SOURCE_FAMILIES and explicit not in enabled:
        return None
    if str(gap.get("gap_type") or "") not in VISUAL_GAP_TYPES:
        return None
    if "kto_tourism_photo" in enabled:
        return "kto_tourism_photo"
    if "kto_photo_contest" in enabled:
        return "kto_photo_contest"
    return None


def _visual_enabled_families(settings: Settings) -> set[str]:
    families: set[str] = set()
    if settings.kto_tourism_photo_enabled and settings.tourapi_service_key:
        families.add("kto_tourism_photo")
    if settings.kto_photo_contest_enabled and settings.tourapi_service_key:
        families.add("kto_photo_contest")
    return families


def _visual_tool_name(source_family: str) -> str:
    return {
        "kto_tourism_photo": "kto_tourism_photo_search",
        "kto_photo_contest": "kto_photo_contest_award_list",
    }.get(source_family, f"{source_family}_search")


def _visual_operation(source_family: str) -> str:
    return {
        "kto_tourism_photo": "gallerySearchList1",
        "kto_photo_contest": "phokoAwrdList",
    }.get(source_family, "future")


def _route_signal_source_family_for_gap(gap: dict[str, Any], settings: Settings) -> str | None:
    explicit = str(gap.get("suggested_source_family") or "")
    enabled = _route_signal_enabled_families(settings)
    if explicit in enabled:
        return explicit
    if explicit in ROUTE_SIGNAL_SOURCE_FAMILIES and explicit not in enabled:
        return None
    gap_type = str(gap.get("gap_type") or "")
    preferred = {
        "missing_route_context": ["kto_durunubi", "kto_related_places"],
        "missing_related_places": ["kto_related_places"],
        "missing_demand_signal": ["kto_tourism_bigdata", "kto_regional_tourism_demand"],
        "missing_crowding_signal": ["kto_crowding_forecast"],
        "missing_regional_demand_signal": ["kto_regional_tourism_demand"],
    }.get(gap_type, [])
    for family in preferred:
        if family in enabled:
            return family
    return None


def _route_signal_enabled_families(settings: Settings) -> set[str]:
    if not settings.tourapi_service_key:
        return set()
    families: set[str] = set()
    if settings.kto_durunubi_enabled:
        families.add("kto_durunubi")
    if settings.kto_related_places_enabled:
        families.add("kto_related_places")
    if settings.kto_bigdata_enabled:
        families.add("kto_tourism_bigdata")
    if settings.kto_crowding_enabled:
        families.add("kto_crowding_forecast")
    if settings.kto_regional_tourism_demand_enabled:
        families.add("kto_regional_tourism_demand")
    return families


def _route_signal_tool_name(source_family: str, gap: dict[str, Any]) -> str:
    if source_family == "kto_related_places":
        return "kto_related_places_keyword" if gap.get("source_item_title") else "kto_related_places_area"
    if source_family == "kto_tourism_bigdata":
        return "kto_tourism_bigdata_locgo_visitors" if gap.get("target_item_id") else "kto_tourism_bigdata_metco_visitors"
    return {
        "kto_durunubi": "kto_durunubi_course_list",
        "kto_crowding_forecast": "kto_attraction_crowding_forecast",
        "kto_regional_tourism_demand": "kto_regional_tourism_demand_area",
    }.get(source_family, f"{source_family}_search")


def _route_signal_operation(source_family: str, gap: dict[str, Any]) -> str:
    if source_family == "kto_related_places":
        return "searchKeyword1" if gap.get("source_item_title") else "areaBasedList1"
    if source_family == "kto_tourism_bigdata":
        return "locgoRegnVisitrDDList" if gap.get("target_item_id") else "metcoRegnVisitrDDList"
    return {
        "kto_durunubi": "courseList",
        "kto_crowding_forecast": "tatsCnctrRatedList",
        "kto_regional_tourism_demand": "areaTarSvcDemList",
    }.get(source_family, "future")


def _theme_source_family_for_gap(gap: dict[str, Any], settings: Settings) -> str | None:
    explicit = str(gap.get("suggested_source_family") or "")
    enabled = _theme_enabled_families(settings)
    if explicit in enabled:
        return explicit
    if explicit in THEME_SOURCE_FAMILIES and explicit not in enabled:
        return None
    gap_type = str(gap.get("gap_type") or "")
    preferred = {
        "missing_pet_policy": ["kto_pet"],
        "missing_wellness_attributes": ["kto_wellness"],
        "missing_story_asset": ["kto_audio"],
        "missing_multilingual_story": ["kto_audio"],
        "missing_sustainability_context": ["kto_eco"],
        "missing_medical_context": ["kto_medical"],
        "missing_theme_specific_data": ["kto_pet", "kto_wellness", "kto_audio", "kto_eco"],
    }.get(gap_type, [])
    text = " ".join(
        str(value or "")
        for value in [
            gap.get("reason"),
            gap.get("source_item_title"),
            gap.get("productization_impact"),
        ]
    )
    for token, family in THEME_SOURCE_HINTS.items():
        if token in text and family in enabled:
            return family
    for family in preferred:
        if family in enabled:
            return family
    return None


def _theme_enabled_families(settings: Settings) -> set[str]:
    if not settings.tourapi_service_key:
        return set()
    families: set[str] = set()
    if settings.kto_wellness_enabled:
        families.add("kto_wellness")
    if settings.kto_pet_enabled:
        families.add("kto_pet")
    if settings.kto_audio_enabled:
        families.add("kto_audio")
    if settings.kto_eco_enabled:
        families.add("kto_eco")
    if settings.allow_medical_api:
        families.add("kto_medical")
    return families


def _theme_tool_name(source_family: str) -> str:
    return {
        "kto_wellness": "kto_wellness_keyword_search",
        "kto_pet": "kto_pet_keyword_search",
        "kto_audio": "kto_audio_story_search",
        "kto_eco": "kto_eco_area_search",
        "kto_medical": "kto_medical_keyword_search",
    }.get(source_family, f"{source_family}_search")


def _theme_operation(source_family: str) -> str:
    return {
        "kto_wellness": "searchKeyword",
        "kto_pet": "searchKeyword2",
        "kto_audio": "storySearchList",
        "kto_eco": "areaBasedList1",
        "kto_medical": "searchKeyword",
    }.get(source_family, "future")


def _dedupe_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for call in calls:
        key = (
            str(call.get("id") or ""),
            str(call.get("source_family") or ""),
            ",".join(_string_list(call.get("gap_ids"))),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(call)
    return result


def _merge_unresolved_gaps(base_gaps: list[Any], payload_gaps: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_gap in [*base_gaps, *payload_gaps]:
        if not isinstance(raw_gap, dict):
            continue
        gap = dict(raw_gap)
        key = (
            str(gap.get("id") or ""),
            str(gap.get("gap_type") or ""),
            str(gap.get("target_content_id") or gap.get("target_item_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(gap)
    return result
