from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class KtoOperationDefinition:
    tool_name: str
    operation: str
    purpose: str
    implemented: bool = False
    workflow_enabled: bool = False
    required_for_phase: str = "Phase 9+"


@dataclass(frozen=True)
class KtoCapabilityDefinition:
    source_family: str
    display_name: str
    category: str
    supported_gaps: tuple[str, ...]
    default_ttl_hours: int
    risk_level: str
    operations: tuple[KtoOperationDefinition, ...]
    source_setting_attr: str | None = None
    source_setting_env: str | None = None
    requires_service_key: bool = True
    required_env_vars: tuple[str, ...] = ("TOURAPI_SERVICE_KEY",)
    notes: tuple[str, ...] = ()


def list_kto_capabilities(settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    return [_resolve_capability(definition, settings) for definition in KTO_CAPABILITIES]


def _resolve_capability(
    definition: KtoCapabilityDefinition,
    settings: Settings,
) -> dict[str, Any]:
    disabled_reasons: list[str] = []
    source_setting_enabled = True
    if definition.source_setting_attr:
        source_setting_enabled = bool(getattr(settings, definition.source_setting_attr))
        if not source_setting_enabled:
            disabled_reasons.append(
                f"{definition.source_setting_env or definition.source_setting_attr} is disabled"
            )

    configured_env_vars: list[str] = []
    missing_env_vars: list[str] = []
    if definition.requires_service_key:
        for env_var in definition.required_env_vars:
            if _env_var_is_configured(env_var, settings):
                configured_env_vars.append(env_var)
            else:
                missing_env_vars.append(env_var)
                disabled_reasons.append(f"{env_var} is not configured")

    enabled = not disabled_reasons
    operations = [
        {
            "tool_name": operation.tool_name,
            "operation": operation.operation,
            "purpose": operation.purpose,
            "implemented": operation.implemented,
            "workflow_enabled": operation.workflow_enabled and enabled,
            "required_for_phase": operation.required_for_phase,
        }
        for operation in definition.operations
    ]

    return {
        "source_family": definition.source_family,
        "display_name": definition.display_name,
        "category": definition.category,
        "enabled": enabled,
        "requires_service_key": definition.requires_service_key,
        "required_env_vars": list(definition.required_env_vars),
        "configured_env_vars": configured_env_vars,
        "missing_env_vars": missing_env_vars,
        "source_setting_env": definition.source_setting_env,
        "source_setting_enabled": source_setting_enabled,
        "supported_gaps": list(definition.supported_gaps),
        "default_ttl_hours": definition.default_ttl_hours,
        "risk_level": definition.risk_level,
        "operations": operations,
        "disabled_reasons": disabled_reasons,
        "notes": list(definition.notes),
    }


def _env_var_is_configured(env_var: str, settings: Settings) -> bool:
    if env_var == "TOURAPI_SERVICE_KEY":
        return bool(settings.tourapi_service_key)
    return False


KTO_CAPABILITIES: tuple[KtoCapabilityDefinition, ...] = (
    KtoCapabilityDefinition(
        source_family="kto_tourapi_kor",
        display_name="국문 관광정보 서비스_GW",
        category="core_tourism",
        source_setting_attr="tourapi_enabled",
        source_setting_env="TOURAPI_ENABLED",
        supported_gaps=(
            "missing_detail_common",
            "missing_detail_info",
            "missing_image_asset",
            "missing_related_places",
        ),
        default_ttl_hours=168,
        risk_level="low",
        operations=(
            KtoOperationDefinition(
                "tourapi_area_code",
                "areaCode2",
                "지역명을 지역 코드로 변환",
                implemented=True,
                workflow_enabled=False,
                required_for_phase="backward_compatibility",
            ),
            KtoOperationDefinition(
                "tourapi_ldong_code",
                "ldongCode2",
                "TourAPI v4.4 법정동 지역 catalog 조회",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "tourapi_lcls_system_code",
                "lclsSystmCode2",
                "TourAPI v4.4 신분류체계 catalog 조회",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "tourapi_area_based_list",
                "areaBasedList2",
                "지역 기반 관광정보 후보 조회",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "tourapi_search_keyword",
                "searchKeyword2",
                "키워드 기반 관광지 후보 조회",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "tourapi_search_festival",
                "searchFestival2",
                "행사/축제 후보 조회",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "tourapi_search_stay",
                "searchStay2",
                "숙박 후보 조회",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "kto_tour_detail_common",
                "detailCommon2",
                "주소, 개요, 홈페이지, 좌표, 대표 이미지 보강",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "kto_tour_detail_intro",
                "detailIntro2",
                "content type별 소개 정보 보강",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "kto_tour_detail_info",
                "detailInfo2",
                "이용 시간, 주차, 요금, 문의 등 반복 정보 보강",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "kto_tour_detail_image",
                "detailImage2",
                "상세 이미지 후보 보강",
                implemented=True,
                workflow_enabled=True,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "kto_tour_location_based_list",
                "locationBasedList2",
                "좌표 기반 주변 관광지 후보 조회",
                implemented=True,
                workflow_enabled=False,
                required_for_phase="implemented",
            ),
            KtoOperationDefinition(
                "kto_tour_category_code",
                "categoryCode2",
                "테마/콘텐츠 유형 기반 검색 정교화",
                implemented=True,
                workflow_enabled=False,
                required_for_phase="implemented",
            ),
        ),
        notes=("Phase 9에서 detail 계열은 workflow에 연결하고 category/location은 provider method만 준비합니다.",),
    ),
    KtoCapabilityDefinition(
        source_family="kto_photo_contest",
        display_name="관광공모전 사진 수상작 정보",
        category="visual",
        source_setting_attr="kto_photo_contest_enabled",
        source_setting_env="KTO_PHOTO_CONTEST_ENABLED",
        supported_gaps=("missing_image_asset",),
        default_ttl_hours=168,
        risk_level="medium",
        operations=(
            KtoOperationDefinition("kto_photo_contest_search", "photoContestSearch", "공모전 사진 후보 조회"),
            KtoOperationDefinition("kto_photo_contest_sync", "photoContestSync", "공모전 사진 동기화"),
        ),
        notes=("이미지 게시 가능성과 prompt 참고 용도를 분리해야 합니다.",),
    ),
    KtoCapabilityDefinition(
        source_family="kto_wellness",
        display_name="웰니스관광정보",
        category="theme",
        source_setting_attr="kto_wellness_enabled",
        source_setting_env="KTO_WELLNESS_ENABLED",
        supported_gaps=("missing_wellness_attributes", "missing_image_asset"),
        default_ttl_hours=168,
        risk_level="medium",
        operations=(
            KtoOperationDefinition("kto_wellness_keyword_search", "searchKeyword", "웰니스 키워드 검색"),
            KtoOperationDefinition("kto_wellness_detail", "detailCommon/detailIntro/detailInfo", "웰니스 상세 보강"),
            KtoOperationDefinition("kto_wellness_image", "detailImage", "웰니스 이미지 후보 보강"),
        ),
        notes=("건강 개선, 치료, 효능을 확정 표현하지 않습니다.",),
    ),
    KtoCapabilityDefinition(
        source_family="kto_medical",
        display_name="의료관광정보",
        category="theme",
        source_setting_attr="allow_medical_api",
        source_setting_env="ALLOW_MEDICAL_API",
        supported_gaps=("missing_medical_context",),
        default_ttl_hours=168,
        risk_level="high",
        operations=(
            KtoOperationDefinition("kto_medical_keyword_search", "searchKeyword", "의료관광 키워드 검색"),
            KtoOperationDefinition("kto_medical_detail", "detailCommon/detailIntro/detailInfo", "의료관광 상세 보강"),
        ),
        notes=("의료관광 API는 별도 설정이 켜졌을 때만 사용합니다.",),
    ),
    KtoCapabilityDefinition(
        source_family="kto_pet",
        display_name="반려동물 동반여행 서비스",
        category="theme",
        source_setting_attr="kto_pet_enabled",
        source_setting_env="KTO_PET_ENABLED",
        supported_gaps=("missing_pet_policy",),
        default_ttl_hours=168,
        risk_level="medium",
        operations=(
            KtoOperationDefinition("kto_pet_area_search", "areaBasedList", "반려동물 동반 가능 후보 조회"),
            KtoOperationDefinition("kto_pet_location_search", "locationBasedList", "위치 기반 반려동물 동반 후보 조회"),
            KtoOperationDefinition("kto_pet_detail", "detail", "반려동물 동반 조건 상세 보강"),
        ),
    ),
    KtoCapabilityDefinition(
        source_family="kto_durunubi",
        display_name="두루누비 정보 서비스_GW",
        category="route",
        source_setting_attr="kto_durunubi_enabled",
        source_setting_env="KTO_DURUNUBI_ENABLED",
        supported_gaps=("missing_route_asset",),
        default_ttl_hours=168,
        risk_level="medium",
        operations=(
            KtoOperationDefinition("kto_durunubi_course_list", "courseList", "걷기길/코스 후보 조회"),
            KtoOperationDefinition("kto_durunubi_path_list", "pathList", "코스 경로/GPX 후보 조회"),
        ),
    ),
    KtoCapabilityDefinition(
        source_family="kto_audio",
        display_name="관광지 오디오 가이드정보_GW",
        category="story",
        source_setting_attr="kto_audio_enabled",
        source_setting_env="KTO_AUDIO_ENABLED",
        supported_gaps=("missing_story_asset",),
        default_ttl_hours=168,
        risk_level="low",
        operations=(
            KtoOperationDefinition("kto_audio_keyword_search", "searchKeyword", "오디오 가이드 키워드 검색"),
            KtoOperationDefinition("kto_audio_location_search", "locationBasedList", "위치 기반 오디오 가이드 조회"),
            KtoOperationDefinition("kto_audio_detail", "detail", "오디오 가이드 상세 보강"),
        ),
    ),
    KtoCapabilityDefinition(
        source_family="kto_eco",
        display_name="생태 관광 정보_GW",
        category="theme",
        source_setting_attr="kto_eco_enabled",
        source_setting_env="KTO_ECO_ENABLED",
        supported_gaps=("missing_sustainability_context",),
        default_ttl_hours=168,
        risk_level="medium",
        operations=(
            KtoOperationDefinition("kto_eco_tourism_search", "search", "생태 관광 후보 조회"),
            KtoOperationDefinition("kto_eco_tourism_detail", "detail", "생태 관광 상세 보강"),
        ),
        notes=("친환경 효과를 정량 보장하지 않습니다.",),
    ),
    KtoCapabilityDefinition(
        source_family="kto_tourism_photo",
        display_name="관광사진 정보_GW",
        category="visual",
        source_setting_attr="kto_tourism_photo_enabled",
        source_setting_env="KTO_TOURISM_PHOTO_ENABLED",
        supported_gaps=("missing_image_asset",),
        default_ttl_hours=168,
        risk_level="medium",
        operations=(
            KtoOperationDefinition("kto_tourism_photo_search", "tourismPhotoSearch", "관광사진 후보 조회"),
            KtoOperationDefinition("kto_tourism_photo_sync", "tourismPhotoSync", "관광사진 동기화"),
        ),
        notes=("이미지 이용 조건과 게시 가능 여부를 별도 검토합니다.",),
    ),
    KtoCapabilityDefinition(
        source_family="kto_tourism_bigdata",
        display_name="관광빅데이터 정보서비스_GW",
        category="signal",
        source_setting_attr="kto_bigdata_enabled",
        source_setting_env="KTO_BIGDATA_ENABLED",
        supported_gaps=("missing_demand_signal",),
        default_ttl_hours=24,
        risk_level="medium",
        operations=(
            KtoOperationDefinition("kto_tourism_bigdata_visitors", "visitorStatistics", "지역/기간별 방문 수요 신호 조회"),
        ),
        notes=("방문 수요는 판매량 또는 예약 가능성을 보장하지 않습니다.",),
    ),
    KtoCapabilityDefinition(
        source_family="kto_crowding_forecast",
        display_name="관광지 집중률 방문자 추이 예측 정보",
        category="signal",
        source_setting_attr="kto_crowding_enabled",
        source_setting_env="KTO_CROWDING_ENABLED",
        supported_gaps=("missing_crowding_signal",),
        default_ttl_hours=24,
        risk_level="medium",
        operations=(
            KtoOperationDefinition("kto_attraction_crowding_forecast", "crowdingForecast", "관광지 집중률 예측 신호 조회"),
        ),
        notes=("집중률은 운영 판단 보조 신호로만 사용합니다.",),
    ),
    KtoCapabilityDefinition(
        source_family="kto_related_places",
        display_name="관광지별 연관 관광지 정보",
        category="signal",
        source_setting_attr="kto_related_places_enabled",
        source_setting_env="KTO_RELATED_PLACES_ENABLED",
        supported_gaps=("missing_related_places",),
        default_ttl_hours=168,
        risk_level="medium",
        operations=(
            KtoOperationDefinition("kto_related_places_area", "relatedPlacesArea", "지역 기반 연관 관광지 조회"),
            KtoOperationDefinition("kto_related_places_keyword", "relatedPlacesKeyword", "키워드 기반 연관 관광지 조회"),
        ),
        notes=("연관성은 내비게이션 이동 기반 참고 신호로만 사용합니다.",),
    ),
    KtoCapabilityDefinition(
        source_family="official_web",
        display_name="공식 웹 근거 검색",
        category="web_evidence",
        source_setting_attr="official_web_search_enabled",
        source_setting_env="OFFICIAL_WEB_SEARCH_ENABLED",
        requires_service_key=False,
        required_env_vars=(),
        supported_gaps=("missing_user_business_info",),
        default_ttl_hours=24,
        risk_level="high",
        operations=(
            KtoOperationDefinition("official_web_search", "official_web_search", "공식 홈페이지/예약 페이지/공지 검색"),
            KtoOperationDefinition("official_page_extract", "official_page_extract", "공식 페이지 내용 추출"),
            KtoOperationDefinition("user_detail_request", "user_detail_request", "남은 운영 정보 사용자 확인 요청"),
        ),
        notes=("사용자에게 묻기 전에 공식 웹 근거를 먼저 확인합니다.",),
    ),
)
