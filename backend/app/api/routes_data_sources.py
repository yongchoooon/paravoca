from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.responses import ok
from app.db import models
from app.db.session import get_db
from app.rag.source_documents import source_document_role
from app.schemas.enrichment import (
    DataSourceCapabilitiesResponse,
    DataSourceCatalogBrowserResponse,
    DataSourceCatalogStatus,
    DataSourceClassificationCatalogItem,
    DataSourceDocumentBrowserResponse,
    DataSourceDocumentPreview,
    DataSourceDocumentStatus,
    DataSourceInventoryStats,
    DataSourceOverviewItem,
    DataSourceOverviewResponse,
    DataSourceOverviewSummary,
    DataSourcePurposeProfile,
    DataSourceRegionCatalogItem,
    DataSourceTourismItemBrowserResponse,
    DataSourceTourismItemPreview,
    DataSourceTourismInventory,
    KtoSourceCapability,
)
from app.tools.kto_capabilities import list_kto_capabilities

router = APIRouter(prefix="/data/sources", tags=["data-sources"])


CONTENT_TYPE_LABELS = {
    "attraction": "관광지",
    "event": "행사/축제",
    "accommodation": "숙박",
    "leisure": "레포츠",
    "culture": "문화시설",
    "shopping": "쇼핑",
    "restaurant": "음식점",
}


PURPOSE_PROFILES = (
    DataSourcePurposeProfile(key="all", label="전체 데이터"),
    DataSourcePurposeProfile(key="base", label="기본 관광 상품"),
    DataSourcePurposeProfile(key="event", label="행사/축제"),
    DataSourcePurposeProfile(key="visual", label="이미지/포스터"),
    DataSourcePurposeProfile(key="pet", label="반려동물"),
    DataSourcePurposeProfile(key="walking", label="도보/트레킹"),
    DataSourcePurposeProfile(key="wellness", label="웰니스/힐링"),
    DataSourcePurposeProfile(key="demand", label="혼잡/수요 판단"),
    DataSourcePurposeProfile(key="culture", label="문화해설/스토리"),
)


SOURCE_API_PROFILES: dict[str, dict[str, Any]] = {
    "kto_tourapi_kor": {
        "purpose": "관광지, 행사, 숙박, 음식점 같은 기본 후보를 찾고 상세 운영 정보를 채웁니다.",
        "input_fields": ["지역 코드", "관광 타입", "키워드", "콘텐츠 ID", "페이지 번호"],
        "output_fields": ["관광지명", "주소", "좌표", "대표 이미지", "콘텐츠 ID", "소개문", "운영/요금/주차 정보"],
        "example_use": "상품 후보 장소 검색과 상세 설명 생성의 기본 데이터로 사용합니다.",
        "origin_description": "TourAPI 목록/키워드/상세 API 응답을 tourism_items에 저장하고, RAG 검색 근거로 변환합니다.",
        "purpose_tags": ["base", "event", "visual", "pet"],
    },
    "kto_photo_contest": {
        "purpose": "한국관광공사 공모전 사진 수상작을 이미지 참고 후보로 찾습니다.",
        "input_fields": ["지역 코드", "키워드", "사진 콘텐츠 ID"],
        "output_fields": ["사진 제목", "촬영 장소", "이미지 URL", "촬영자", "키워드", "이용 조건"],
        "example_use": "상품 카드나 포스터에 쓸 이미지 후보를 검토할 때 사용합니다.",
        "origin_description": "사진 API 응답을 visual asset과 RAG 검색 근거로 저장합니다.",
        "purpose_tags": ["visual"],
    },
    "kto_tourism_photo": {
        "purpose": "관광사진 API에서 지역/키워드 기반 이미지 후보를 찾습니다.",
        "input_fields": ["키워드", "지역", "사진 콘텐츠 ID"],
        "output_fields": ["이미지 URL", "사진 제목", "촬영 장소", "촬영 월", "사진가", "검색 키워드"],
        "example_use": "이미지가 없는 관광 상품에 대표 이미지 후보를 붙일 때 사용합니다.",
        "origin_description": "관광사진 검색 결과를 tourism_visual_assets에 저장하고 RAG 검색 근거로 변환합니다.",
        "purpose_tags": ["visual"],
    },
    "kto_pet": {
        "purpose": "반려동물 동반 가능 여부와 제한 조건을 확인합니다.",
        "input_fields": ["지역", "키워드", "콘텐츠 ID"],
        "output_fields": ["동반 가능 여부", "제한 조건", "주의사항", "시설 정보", "이미지 후보"],
        "example_use": "반려동물 동반 상품을 만들 때 허용 조건과 안내 문구를 검증합니다.",
        "origin_description": "반려동물 API 상세 응답을 테마 근거 문서로 저장합니다.",
        "purpose_tags": ["pet"],
    },
    "kto_durunubi": {
        "purpose": "걷기길/트레킹 코스와 경로 정보를 찾습니다.",
        "input_fields": ["지역", "코스 ID", "키워드"],
        "output_fields": ["코스명", "경로명", "거리", "소요 시간", "시작/종료 지점", "GPX URL"],
        "example_use": "도보 여행, 트레킹, 산책형 상품의 이동 경로를 구성합니다.",
        "origin_description": "두루누비 코스 응답을 route asset과 RAG 검색 근거로 저장합니다.",
        "purpose_tags": ["walking"],
    },
    "kto_wellness": {
        "purpose": "웰니스/힐링 테마에 맞는 시설과 속성을 찾습니다.",
        "input_fields": ["지역", "키워드", "콘텐츠 ID"],
        "output_fields": ["시설명", "주소", "소개", "테마 속성", "운영 정보", "이미지 후보"],
        "example_use": "힐링, 휴식, 웰니스 중심 상품 후보를 보강합니다.",
        "origin_description": "웰니스 API 검색 결과를 테마 근거 문서로 저장합니다.",
        "purpose_tags": ["wellness"],
    },
    "kto_medical": {
        "purpose": "의료관광 관련 시설 정보를 별도 설정이 켜진 경우에만 확인합니다.",
        "input_fields": ["지역", "키워드", "콘텐츠 ID"],
        "output_fields": ["시설명", "주소", "진료/서비스 정보", "소개", "운영 정보"],
        "example_use": "의료관광 상품 검토 시 과장 표현을 피하고 사실 근거를 확인합니다.",
        "origin_description": "의료관광 API 응답은 고위험 테마 근거로 분리해 저장합니다.",
        "purpose_tags": ["wellness"],
    },
    "kto_audio": {
        "purpose": "관광지 해설, 스토리, 오디오 가이드 후보를 찾습니다.",
        "input_fields": ["테마", "지역", "스토리 키워드"],
        "output_fields": ["해설 제목", "스토리 요약", "오디오/해설 식별자", "관련 장소"],
        "example_use": "문화해설형 상품, 외국인 대상 스토리텔링 설명에 사용합니다.",
        "origin_description": "오디오 가이드 검색 결과를 스토리 근거 문서로 저장합니다.",
        "purpose_tags": ["culture"],
    },
    "kto_eco": {
        "purpose": "생태 관광 테마 후보와 지역 기반 생태 정보를 찾습니다.",
        "input_fields": ["지역 코드", "키워드"],
        "output_fields": ["생태 관광지명", "주소", "소개", "테마 속성"],
        "example_use": "생태/공정관광 성격의 상품 후보를 찾되 효과를 보장하지 않습니다.",
        "origin_description": "생태 관광 API 응답을 테마 근거 문서로 저장합니다.",
        "purpose_tags": ["culture", "base"],
    },
    "kto_tourism_bigdata": {
        "purpose": "광역/기초 지자체 방문자 수요 신호를 확인합니다.",
        "input_fields": ["지역 코드", "기간"],
        "output_fields": ["방문자 수", "기간", "지역", "증감 신호"],
        "example_use": "상품 우선순위나 시즌 수요 판단의 보조 신호로 사용합니다.",
        "origin_description": "관광빅데이터 응답을 signal record와 RAG 검색 근거로 저장합니다.",
        "purpose_tags": ["demand"],
    },
    "kto_crowding_forecast": {
        "purpose": "관광지 집중률과 혼잡 예측 신호를 확인합니다.",
        "input_fields": ["관광지", "지역", "기간"],
        "output_fields": ["집중률", "예측 기간", "혼잡 해석", "관련 관광지"],
        "example_use": "혼잡 회피 일정이나 운영 리스크 판단에 참고합니다.",
        "origin_description": "집중률 예측 응답을 signal record로 저장합니다.",
        "purpose_tags": ["demand"],
    },
    "kto_related_places": {
        "purpose": "특정 관광지와 함께 묶기 좋은 연관 장소를 찾습니다.",
        "input_fields": ["지역", "키워드", "관광지 식별자"],
        "output_fields": ["연관 관광지명", "주소", "관계 신호", "좌표"],
        "example_use": "반나절 코스나 주변 방문지 추천을 구성합니다.",
        "origin_description": "연관 관광지 API 응답을 route/signal 보조 근거로 저장합니다.",
        "purpose_tags": ["base", "walking"],
    },
    "kto_regional_tourism_demand": {
        "purpose": "지역별 관광서비스/문화자원 수요 예측을 확인합니다.",
        "input_fields": ["지역 코드", "기간", "서비스/문화자원 유형"],
        "output_fields": ["수요 예측값", "지역", "기간", "자원 유형"],
        "example_use": "지역별 상품 소재 우선순위와 시즌성을 판단합니다.",
        "origin_description": "지역 수요 예측 응답을 signal record로 저장합니다.",
        "purpose_tags": ["demand"],
    },
    "official_web": {
        "purpose": "공식 홈페이지, 예약 페이지, 공지에서 마지막 운영 근거를 확인합니다.",
        "input_fields": ["장소명", "주소", "확인할 필드", "공식 URL 후보"],
        "output_fields": ["공식 페이지 URL", "요약", "확신도", "검토 필요 여부"],
        "example_use": "API 데이터가 부족할 때 운영시간, 예약, 휴무 정보를 보완합니다.",
        "origin_description": "공식 웹 검색/추출 결과는 web evidence로 저장하고 사람 검토 대상으로 표시합니다.",
        "purpose_tags": ["base"],
    },
}


@router.get("/capabilities")
def get_data_source_capabilities() -> dict:
    sources = [
        KtoSourceCapability.model_validate(source)
        for source in list_kto_capabilities()
    ]
    response = DataSourceCapabilitiesResponse(
        sources=sources,
        enabled_count=sum(1 for source in sources if source.enabled),
        implemented_operation_count=sum(
            1
            for source in sources
            for operation in source.operations
            if operation.implemented
        ),
        workflow_operation_count=sum(
            1
            for source in sources
            for operation in source.operations
            if operation.workflow_enabled
        ),
    )
    return ok(response.model_dump(mode="json"), count=len(sources))


@router.get("/overview")
def get_data_source_overview(db: Session = Depends(get_db)) -> dict:
    capability_sources = [
        KtoSourceCapability.model_validate(source)
        for source in list_kto_capabilities()
    ]
    inventory_by_family = _collect_inventory_by_family(db)
    overview_sources = [
        _build_overview_item(source, inventory_by_family.get(source.source_family))
        for source in capability_sources
    ]
    documents = _document_status(db)
    tourism_inventory = _tourism_inventory(db)
    catalogs = _catalog_statuses(db)
    latest_activity_at = _latest_datetime(
        [source.inventory.latest_activity_at for source in overview_sources]
        + [documents.latest_updated_at, tourism_inventory.latest_synced_at]
        + [catalog.last_synced_at for catalog in catalogs]
    )
    summary = DataSourceOverviewSummary(
        total_sources=len(overview_sources),
        ready_sources=sum(1 for source in overview_sources if source.readiness_status in {"ready", "available"}),
        setup_required_sources=sum(1 for source in overview_sources if source.readiness_status == "setup_required"),
        disabled_sources=sum(1 for source in overview_sources if source.readiness_status == "off"),
        implemented_operation_count=sum(source.implemented_operation_count for source in overview_sources),
        workflow_operation_count=sum(source.workflow_operation_count for source in overview_sources),
        tourism_item_count=tourism_inventory.total_items,
        source_document_count=documents.total,
        indexed_document_count=documents.indexed,
        enrichment_run_count=db.query(models.EnrichmentRun).count(),
        latest_activity_at=latest_activity_at,
    )
    response = DataSourceOverviewResponse(
        purpose="운영자가 관광 데이터 API와 실제 저장 데이터를 확인하는 화면",
        purpose_detail=(
            "각 API가 어떤 입력을 받아 어떤 결과를 주는지, 실제로 DB에 어떤 관광 데이터와 "
            "RAG 검색 근거가 쌓였는지, 지역/관광 분류 기준표에는 무엇이 있는지 확인합니다."
        ),
        summary=summary,
        sources=overview_sources,
        catalogs=catalogs,
        documents=documents,
        tourism_inventory=tourism_inventory,
        purpose_profiles=list(PURPOSE_PROFILES),
    )
    return ok(response.model_dump(mode="json"), count=len(overview_sources))


@router.get("/documents")
def browse_data_source_documents(
    keyword: str | None = Query(default=None),
    source_family: str | None = Query(default=None),
    embedding_status: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    source_labels = _source_label_map()
    query = db.query(models.SourceDocument)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                models.SourceDocument.title.ilike(pattern),
                models.SourceDocument.content.ilike(pattern),
                models.SourceDocument.source.ilike(pattern),
            )
        )
    if source_family and source_family != "all":
        source_filters = _source_document_source_filters(source_family)
        query = query.filter(models.SourceDocument.source.in_(source_filters))
    if embedding_status and embedding_status != "all":
        query = query.filter(models.SourceDocument.embedding_status == embedding_status)
    total = query.count()
    documents = (
        query.order_by(models.SourceDocument.updated_at.desc())
        .limit(limit)
        .all()
    )
    source_item_ids = [document.source_item_id for document in documents]
    item_titles = {
        item.id: item.title
        for item in db.query(models.TourismItem)
        .filter(models.TourismItem.id.in_(source_item_ids))
        .all()
    }
    response = DataSourceDocumentBrowserResponse(
        items=[
            _document_preview(
                document,
                source_labels=source_labels,
                source_item_title=item_titles.get(document.source_item_id),
            )
            for document in documents
        ],
        total=total,
        limit=limit,
    )
    return ok(response.model_dump(mode="json"), count=len(response.items))


@router.get("/tourism-items")
def browse_collected_tourism_items(
    keyword: str | None = Query(default=None),
    source_family: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    region: str | None = Query(default=None),
    has_image: bool | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    source_labels = _source_label_map()
    query = db.query(models.TourismItem)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                models.TourismItem.title.ilike(pattern),
                models.TourismItem.address.ilike(pattern),
                models.TourismItem.overview.ilike(pattern),
                models.TourismItem.content_id.ilike(pattern),
            )
        )
    if source_family and source_family != "all":
        query = query.filter(models.TourismItem.source == _tourism_item_source_filter(source_family))
    if content_type and content_type != "all":
        query = query.filter(models.TourismItem.content_type == content_type)
    if region:
        pattern = f"%{region.strip()}%"
        query = query.filter(
            or_(
                models.TourismItem.address.ilike(pattern),
                models.TourismItem.ldong_regn_cd.ilike(pattern),
                models.TourismItem.ldong_signgu_cd.ilike(pattern),
            )
        )
    if has_image is not None:
        query = query.filter(models.TourismItem.image_url.isnot(None) if has_image else models.TourismItem.image_url.is_(None))
    total = query.count()
    items = (
        query.order_by(models.TourismItem.last_synced_at.desc())
        .limit(limit)
        .all()
    )
    item_ids = [item.id for item in items]
    evidence_ids = {
        source_item_id
        for (source_item_id,) in db.query(models.SourceDocument.source_item_id)
        .filter(models.SourceDocument.source_item_id.in_(item_ids))
        .distinct()
        .all()
    }
    ldong_labels = _ldong_labels_for_items(db, items)
    classification_labels = _classification_labels_for_items(db, items)
    response = DataSourceTourismItemBrowserResponse(
        items=[
            _tourism_item_preview(
                item,
                source_labels=source_labels,
                has_ai_evidence=item.id in evidence_ids,
                ldong_label=ldong_labels.get((item.ldong_regn_cd, item.ldong_signgu_cd)),
                classification_label=classification_labels.get(
                    (item.lcls_systm_1, item.lcls_systm_2, item.lcls_systm_3)
                ),
            )
            for item in items
        ],
        total=total,
        limit=limit,
    )
    return ok(response.model_dump(mode="json"), count=len(response.items))


@router.get("/catalogs/browser")
def browse_data_source_catalogs(
    region_keyword: str | None = Query(default=None),
    classification_keyword: str | None = Query(default=None),
    region_code: str | None = Query(default=None),
    lcls_systm_1: str | None = Query(default=None),
    lcls_systm_2: str | None = Query(default=None),
    region_offset: int = Query(default=0, ge=0),
    classification_offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    regions_query = db.query(models.TourApiLdongCode)
    classifications_query = db.query(models.TourApiLclsCode)
    if region_keyword:
        pattern = f"%{region_keyword.strip()}%"
        regions_query = regions_query.filter(
            or_(
                models.TourApiLdongCode.full_name.ilike(pattern),
                models.TourApiLdongCode.ldong_regn_nm.ilike(pattern),
                models.TourApiLdongCode.ldong_signgu_nm.ilike(pattern),
                models.TourApiLdongCode.ldong_regn_cd.ilike(pattern),
                models.TourApiLdongCode.ldong_signgu_cd.ilike(pattern),
            )
        )
    elif region_code:
        regions_query = regions_query.filter(
            models.TourApiLdongCode.ldong_regn_cd == region_code,
            models.TourApiLdongCode.ldong_signgu_cd.isnot(None),
        )
    else:
        regions_query = regions_query.filter(models.TourApiLdongCode.ldong_signgu_cd.is_(None))

    if classification_keyword:
        pattern = f"%{classification_keyword.strip()}%"
        classifications_query = classifications_query.filter(
            or_(
                models.TourApiLclsCode.full_name.ilike(pattern),
                models.TourApiLclsCode.lcls_systm_1_nm.ilike(pattern),
                models.TourApiLclsCode.lcls_systm_2_nm.ilike(pattern),
                models.TourApiLclsCode.lcls_systm_3_nm.ilike(pattern),
                models.TourApiLclsCode.content_type_name.ilike(pattern),
            )
        )
    elif lcls_systm_2:
        classifications_query = classifications_query.filter(
            models.TourApiLclsCode.lcls_systm_1 == lcls_systm_1,
            models.TourApiLclsCode.lcls_systm_2 == lcls_systm_2,
            models.TourApiLclsCode.lcls_systm_3.isnot(None),
        )
    elif lcls_systm_1:
        classifications_query = classifications_query.filter(
            models.TourApiLclsCode.lcls_systm_1 == lcls_systm_1,
            models.TourApiLclsCode.lcls_systm_2.isnot(None),
            models.TourApiLclsCode.lcls_systm_3.is_(None),
        )
    else:
        classifications_query = classifications_query.filter(
            models.TourApiLclsCode.lcls_systm_1.isnot(None),
            models.TourApiLclsCode.lcls_systm_2.is_(None),
            models.TourApiLclsCode.lcls_systm_3.is_(None),
        )
    region_total = regions_query.count()
    classification_total = classifications_query.count()
    regions = (
        regions_query.order_by(
            models.TourApiLdongCode.ldong_regn_nm.asc(),
            models.TourApiLdongCode.ldong_signgu_nm.asc(),
        )
        .offset(region_offset)
        .limit(limit)
        .all()
    )
    classifications = (
        classifications_query.order_by(
            models.TourApiLclsCode.lcls_systm_1_nm.asc(),
            models.TourApiLclsCode.lcls_systm_2_nm.asc(),
            models.TourApiLclsCode.lcls_systm_3_nm.asc(),
        )
        .offset(classification_offset)
        .limit(limit)
        .all()
    )
    region_counts = _tourism_counts_by_ldong(db)
    classification_counts = _tourism_counts_by_lcls(db)
    response = DataSourceCatalogBrowserResponse(
        regions=[
            _region_catalog_item(region, region_counts=region_counts)
            for region in regions
        ],
        classifications=[
            _classification_catalog_item(classification, classification_counts=classification_counts)
            for classification in classifications
        ],
        region_total=region_total,
        classification_total=classification_total,
        limit=limit,
        region_offset=region_offset,
        classification_offset=classification_offset,
    )
    return ok(response.model_dump(mode="json"), count=len(response.regions) + len(response.classifications))


def _build_overview_item(
    source: KtoSourceCapability,
    inventory: DataSourceInventoryStats | None,
) -> DataSourceOverviewItem:
    implemented_operation_count = sum(1 for operation in source.operations if operation.implemented)
    workflow_operation_count = sum(1 for operation in source.operations if operation.workflow_enabled)
    readiness_status, status_label, status_detail = _readiness_status(source)
    inventory = inventory or DataSourceInventoryStats()
    profile = _api_profile(source)
    payload = source.model_dump()
    payload["notes"] = _operator_notes(source.notes)
    return DataSourceOverviewItem(
        **payload,
        purpose=profile["purpose"],
        input_fields=profile["input_fields"],
        output_fields=profile["output_fields"],
        example_use=profile["example_use"],
        origin_description=profile["origin_description"],
        purpose_tags=profile["purpose_tags"],
        stored_count=_stored_count(inventory),
        evidence_count=inventory.source_documents,
        readiness_status=readiness_status,
        status_label=status_label,
        status_detail=status_detail,
        implemented_operation_count=implemented_operation_count,
        workflow_operation_count=workflow_operation_count,
        inventory=inventory,
    )


def _api_profile(source: KtoSourceCapability) -> dict[str, Any]:
    fallback_inputs = sorted(
        {
            "지역/키워드",
            *(
                "콘텐츠 ID"
                for operation in source.operations
                if "detail" in operation.operation.lower()
            ),
        }
    )
    profile = SOURCE_API_PROFILES.get(source.source_family)
    if profile:
        return profile
    return {
        "purpose": f"{source.display_name}에서 상품 기획에 필요한 보조 데이터를 확인합니다.",
        "input_fields": fallback_inputs or ["지역", "키워드"],
        "output_fields": ["제목", "주소", "소개", "상세 속성", "출처 정보"],
        "example_use": source.operations[0].purpose if source.operations else "상품 기획 보조 데이터로 사용합니다.",
        "origin_description": "외부 API 응답을 운영 DB에 저장하고 필요한 경우 RAG 검색 근거로 변환합니다.",
        "purpose_tags": [source.category],
    }


def _stored_count(inventory: DataSourceInventoryStats) -> int:
    return (
        inventory.tourism_items
        + inventory.visual_assets
        + inventory.route_assets
        + inventory.signal_records
    )


def _operator_notes(notes: list[str]) -> list[str]:
    replacements = {
        "workflow": "상품 생성 과정",
        "Phase 10.2에서": "현재 구현에서는",
        "Phase 9 이후": "추가 보강 단계에서",
        "provider method": "내부 수집 기능",
        "baseline": "기본",
    }
    result: list[str] = []
    for note in notes:
        value = note
        for target, replacement in replacements.items():
            value = value.replace(target, replacement)
        result.append(value)
    return result


def _readiness_status(source: KtoSourceCapability) -> tuple[str, str, str]:
    if source.source_setting_enabled is False:
        return "off", "꺼짐", "이 데이터 묶음은 현재 사용하지 않도록 설정되어 있습니다."
    if source.missing_env_vars:
        return "setup_required", "키 연결 필요", "공공데이터 호출에 필요한 인증 정보가 아직 연결되지 않았습니다."
    workflow_operation_count = sum(1 for operation in source.operations if operation.workflow_enabled)
    implemented_operation_count = sum(1 for operation in source.operations if operation.implemented)
    if source.enabled and workflow_operation_count > 0:
        return "ready", "연결됨", "조건이 맞는 상품 생성 과정에서 자동으로 보강 후보가 됩니다."
    if source.enabled and implemented_operation_count > 0:
        return "available", "수동 확인 가능", "기능은 구현되어 있지만 현재 자동 보강 경로에는 제한적으로만 쓰입니다."
    return "planned", "준비 중", "데이터 정의는 있지만 실제 호출 경로는 아직 제한적입니다."


def _collect_inventory_by_family(db: Session) -> dict[str, DataSourceInventoryStats]:
    stats: dict[str, DataSourceInventoryStats] = {}

    def ensure(source_family: str) -> DataSourceInventoryStats:
        if source_family not in stats:
            stats[source_family] = DataSourceInventoryStats()
        return stats[source_family]

    tourapi_stats = ensure("kto_tourapi_kor")
    tourapi_stats.tourism_items = db.query(models.TourismItem).count()
    latest_tourism_sync = db.query(func.max(models.TourismItem.last_synced_at)).scalar()
    tourapi_stats.latest_activity_at = _latest_datetime([tourapi_stats.latest_activity_at, latest_tourism_sync])

    documents = db.query(models.SourceDocument).all()
    for document in documents:
        source_family = _source_document_family(document)
        source_stats = ensure(source_family)
        source_stats.source_documents += 1
        if document.embedding_status == "indexed":
            source_stats.indexed_documents += 1
        source_stats.latest_activity_at = _latest_datetime([source_stats.latest_activity_at, document.updated_at])

    for source_family, count, latest in (
        db.query(
            models.TourismVisualAsset.source_family,
            func.count(models.TourismVisualAsset.id),
            func.max(models.TourismVisualAsset.created_at),
        )
        .group_by(models.TourismVisualAsset.source_family)
        .all()
    ):
        source_stats = ensure(str(source_family))
        source_stats.visual_assets = int(count or 0)
        source_stats.latest_activity_at = _latest_datetime([source_stats.latest_activity_at, latest])

    for source_family, count, latest in (
        db.query(
            models.TourismRouteAsset.source_family,
            func.count(models.TourismRouteAsset.id),
            func.max(models.TourismRouteAsset.created_at),
        )
        .group_by(models.TourismRouteAsset.source_family)
        .all()
    ):
        source_stats = ensure(str(source_family))
        source_stats.route_assets = int(count or 0)
        source_stats.latest_activity_at = _latest_datetime([source_stats.latest_activity_at, latest])

    for source_family, count, latest in (
        db.query(
            models.TourismSignalRecord.source_family,
            func.count(models.TourismSignalRecord.id),
            func.max(models.TourismSignalRecord.created_at),
        )
        .group_by(models.TourismSignalRecord.source_family)
        .all()
    ):
        source_stats = ensure(str(source_family))
        source_stats.signal_records = int(count or 0)
        source_stats.latest_activity_at = _latest_datetime([source_stats.latest_activity_at, latest])

    for source_family, status, count, latest in (
        db.query(
            models.EnrichmentToolCall.source_family,
            models.EnrichmentToolCall.status,
            func.count(models.EnrichmentToolCall.id),
            func.max(models.EnrichmentToolCall.created_at),
        )
        .group_by(models.EnrichmentToolCall.source_family, models.EnrichmentToolCall.status)
        .all()
    ):
        source_stats = ensure(str(source_family))
        count_int = int(count or 0)
        source_stats.enrichment_calls += count_int
        if status == "succeeded":
            source_stats.successful_enrichment_calls += count_int
        if status == "failed":
            source_stats.failed_enrichment_calls += count_int
        source_stats.latest_activity_at = _latest_datetime([source_stats.latest_activity_at, latest])

    return stats


def _source_document_family(document: models.SourceDocument) -> str:
    metadata = document.document_metadata if isinstance(document.document_metadata, dict) else {}
    source_family = metadata.get("source_family")
    if isinstance(source_family, str) and source_family:
        return source_family
    if document.source == "tourapi":
        return "kto_tourapi_kor"
    return document.source or "unknown"


def _document_status(db: Session) -> DataSourceDocumentStatus:
    rows = (
        db.query(models.SourceDocument.embedding_status, func.count(models.SourceDocument.id))
        .group_by(models.SourceDocument.embedding_status)
        .all()
    )
    counts = {str(status): int(count or 0) for status, count in rows}
    total = sum(counts.values())
    indexed = counts.get("indexed", 0)
    pending = counts.get("pending", 0)
    failed = counts.get("failed", 0)
    if total == 0:
        status, label = "empty", "아직 수집 없음"
    elif failed > 0:
        status, label = "attention", "색인 실패 확인 필요"
    elif pending > 0:
        status, label = "pending", "색인 대기 있음"
    else:
        status, label = "ready", "검색 근거 준비됨"
    return DataSourceDocumentStatus(
        total=total,
        indexed=indexed,
        pending=pending,
        failed=failed,
        status=status,
        status_label=label,
        latest_updated_at=db.query(func.max(models.SourceDocument.updated_at)).scalar(),
    )


def _tourism_inventory(db: Session) -> DataSourceTourismInventory:
    content_type_rows = (
        db.query(models.TourismItem.content_type, func.count(models.TourismItem.id))
        .group_by(models.TourismItem.content_type)
        .all()
    )
    content_type_counts = {
        str(content_type or "unknown"): int(count or 0)
        for content_type, count in content_type_rows
    }
    return DataSourceTourismInventory(
        total_items=sum(content_type_counts.values()),
        items_with_image=db.query(models.TourismItem).filter(models.TourismItem.image_url.isnot(None)).count(),
        content_type_counts=content_type_counts,
        latest_synced_at=db.query(func.max(models.TourismItem.last_synced_at)).scalar(),
    )


def _catalog_statuses(db: Session) -> list[DataSourceCatalogStatus]:
    return [
        _catalog_status(
            key="tourapi_ldong",
            label="지역 코드 목록",
            record_count=db.query(models.TourApiLdongCode).count(),
            last_synced_at=db.query(func.max(models.TourApiLdongCode.synced_at)).scalar(),
        ),
        _catalog_status(
            key="tourapi_lcls",
            label="관광 분류 목록",
            record_count=db.query(models.TourApiLclsCode).count(),
            last_synced_at=db.query(func.max(models.TourApiLclsCode.synced_at)).scalar(),
        ),
    ]


def _catalog_status(
    *,
    key: str,
    label: str,
    record_count: int,
    last_synced_at: datetime | None,
) -> DataSourceCatalogStatus:
    status = "ready" if record_count > 0 else "empty"
    return DataSourceCatalogStatus(
        key=key,
        label=label,
        record_count=record_count,
        status=status,
        status_label="동기화됨" if status == "ready" else "동기화 필요",
        last_synced_at=last_synced_at,
    )


def _source_label_map() -> dict[str, str]:
    labels = {
        source["source_family"]: str(source["display_name"]).replace("_GW", "")
        for source in list_kto_capabilities()
    }
    labels["tourapi"] = labels.get("kto_tourapi_kor", "TourAPI 국문 관광정보")
    return labels


def _document_preview(
    document: models.SourceDocument,
    *,
    source_labels: dict[str, str],
    source_item_title: str | None,
) -> DataSourceDocumentPreview:
    metadata = document.document_metadata if isinstance(document.document_metadata, dict) else {}
    source_family = _source_document_family(document)
    content_type = metadata.get("content_type") if isinstance(metadata.get("content_type"), str) else None
    address = metadata.get("address") if isinstance(metadata.get("address"), str) else None
    return DataSourceDocumentPreview(
        id=document.id,
        title=document.title,
        source=document.source,
        source_family=source_family,
        source_role=source_document_role(document),
        source_label=source_labels.get(source_family, source_family),
        source_item_id=document.source_item_id,
        source_item_title=source_item_title,
        content_excerpt=_excerpt(document.content),
        content=document.content,
        embedding_status=document.embedding_status,
        status_label=_embedding_status_label(document.embedding_status),
        content_type=content_type,
        address=address,
        origin_summary=_document_origin_summary(source_family),
        usage_summary=(
            "상품 설명, 추천 이유, 일정 구성에서 RAG가 사실 근거를 찾을 때 사용합니다. "
            "색인 상태가 대기/실패이면 RAG 검색 결과에 빠질 수 있습니다."
        ),
        lifecycle_summary=_document_lifecycle_summary(metadata),
        updated_at=document.updated_at,
    )


def _tourism_item_preview(
    item: models.TourismItem,
    *,
    source_labels: dict[str, str],
    has_ai_evidence: bool,
    ldong_label: str | None,
    classification_label: str | None,
) -> DataSourceTourismItemPreview:
    source_family = "kto_tourapi_kor" if item.source == "tourapi" else item.source
    detail_flags = []
    raw = item.raw if isinstance(item.raw, dict) else {}
    if raw.get("detail_common"):
        detail_flags.append("공통 상세")
    if raw.get("detail_intro"):
        detail_flags.append("소개 상세")
    if raw.get("detail_info"):
        detail_flags.append("반복 상세")
    if raw.get("detail_images"):
        detail_flags.append("상세 이미지")
    return DataSourceTourismItemPreview(
        id=item.id,
        title=item.title,
        source=item.source,
        source_family=source_family,
        source_label=source_labels.get(source_family, source_family),
        content_id=item.content_id,
        content_type=item.content_type,
        content_type_label=CONTENT_TYPE_LABELS.get(item.content_type, item.content_type),
        address=item.address,
        ldong_label=ldong_label,
        classification_label=classification_label,
        has_image=bool(item.image_url),
        has_ai_evidence=has_ai_evidence,
        origin_summary=source_labels.get(source_family, source_family),
        detail_summary=" · ".join(detail_flags) if detail_flags else "기본 목록 정보만 저장되어 있습니다.",
        last_synced_at=item.last_synced_at,
    )


def _region_catalog_item(
    row: models.TourApiLdongCode,
    *,
    region_counts: dict[tuple[str | None, str | None], int],
) -> DataSourceRegionCatalogItem:
    key = (row.ldong_regn_cd, row.ldong_signgu_cd)
    if row.ldong_signgu_cd:
        tourism_item_count = region_counts.get(key, 0)
    else:
        tourism_item_count = sum(
            count
            for (region_code, _signgu_code), count in region_counts.items()
            if region_code == row.ldong_regn_cd
        )
    return DataSourceRegionCatalogItem(
        id=row.id,
        region_code=row.ldong_regn_cd,
        region_name=row.ldong_regn_nm,
        signgu_code=row.ldong_signgu_cd,
        signgu_name=row.ldong_signgu_nm,
        full_name=row.full_name,
        tourism_item_count=tourism_item_count,
        synced_at=row.synced_at,
    )


def _classification_catalog_item(
    row: models.TourApiLclsCode,
    *,
    classification_counts: dict[tuple[str | None, str | None, str | None], int],
) -> DataSourceClassificationCatalogItem:
    code_path = [value for value in [row.lcls_systm_1, row.lcls_systm_2, row.lcls_systm_3] if value]
    name_path = [value for value in [row.lcls_systm_1_nm, row.lcls_systm_2_nm, row.lcls_systm_3_nm] if value]
    tourism_item_count = _classification_count_for_row(row, classification_counts)
    return DataSourceClassificationCatalogItem(
        id=row.id,
        code_path=code_path,
        name_path=name_path,
        content_type_id=row.content_type_id,
        content_type_name=row.content_type_name,
        full_name=row.full_name,
        tourism_item_count=tourism_item_count,
        synced_at=row.synced_at,
    )


def _classification_count_for_row(
    row: models.TourApiLclsCode,
    classification_counts: dict[tuple[str | None, str | None, str | None], int],
) -> int:
    if row.lcls_systm_3:
        return classification_counts.get((row.lcls_systm_1, row.lcls_systm_2, row.lcls_systm_3), 0)
    if row.lcls_systm_2:
        return sum(
            count
            for (level1, level2, _level3), count in classification_counts.items()
            if level1 == row.lcls_systm_1 and level2 == row.lcls_systm_2
        )
    if row.lcls_systm_1:
        return sum(
            count
            for (level1, _level2, _level3), count in classification_counts.items()
            if level1 == row.lcls_systm_1
        )
    return 0


def _ldong_labels_for_items(
    db: Session,
    items: list[models.TourismItem],
) -> dict[tuple[str | None, str | None], str]:
    keys = {
        (item.ldong_regn_cd, item.ldong_signgu_cd)
        for item in items
        if item.ldong_regn_cd
    }
    if not keys:
        return {}
    rows = db.query(models.TourApiLdongCode).all()
    labels: dict[tuple[str | None, str | None], str] = {}
    for row in rows:
        key = (row.ldong_regn_cd, row.ldong_signgu_cd)
        if key in keys or (row.ldong_regn_cd, None) in keys:
            labels[key] = row.full_name
    return labels


def _classification_labels_for_items(
    db: Session,
    items: list[models.TourismItem],
) -> dict[tuple[str | None, str | None, str | None], str]:
    keys = {
        (item.lcls_systm_1, item.lcls_systm_2, item.lcls_systm_3)
        for item in items
        if item.lcls_systm_1 or item.lcls_systm_2 or item.lcls_systm_3
    }
    if not keys:
        return {}
    rows = db.query(models.TourApiLclsCode).all()
    return {
        (row.lcls_systm_1, row.lcls_systm_2, row.lcls_systm_3): row.full_name
        for row in rows
        if (row.lcls_systm_1, row.lcls_systm_2, row.lcls_systm_3) in keys
    }


def _tourism_counts_by_ldong(db: Session) -> dict[tuple[str | None, str | None], int]:
    rows = (
        db.query(
            models.TourismItem.ldong_regn_cd,
            models.TourismItem.ldong_signgu_cd,
            func.count(models.TourismItem.id),
        )
        .group_by(models.TourismItem.ldong_regn_cd, models.TourismItem.ldong_signgu_cd)
        .all()
    )
    return {
        (region_code, signgu_code): int(count or 0)
        for region_code, signgu_code, count in rows
    }


def _tourism_counts_by_lcls(db: Session) -> dict[tuple[str | None, str | None, str | None], int]:
    rows = (
        db.query(
            models.TourismItem.lcls_systm_1,
            models.TourismItem.lcls_systm_2,
            models.TourismItem.lcls_systm_3,
            func.count(models.TourismItem.id),
        )
        .group_by(models.TourismItem.lcls_systm_1, models.TourismItem.lcls_systm_2, models.TourismItem.lcls_systm_3)
        .all()
    )
    return {
        (level1, level2, level3): int(count or 0)
        for level1, level2, level3, count in rows
    }


def _tourism_item_source_filter(source_family: str) -> str:
    return "tourapi" if source_family == "kto_tourapi_kor" else source_family


def _source_document_source_filters(source_family: str) -> list[str]:
    if source_family == "kto_tourapi_kor":
        return ["tourapi", "kto_tourapi_kor"]
    return [source_family]


def _document_origin_summary(source_family: str) -> str:
    profile = SOURCE_API_PROFILES.get(source_family)
    if profile:
        return str(profile["origin_description"])
    return "외부/내부 데이터 응답을 RAG 검색용 문서 형태로 변환해 저장했습니다."


def _document_lifecycle_summary(metadata: dict[str, Any]) -> str:
    role = _source_role_label(str(metadata.get("source_role") or "unknown"))
    method = _ingestion_method_label(str(metadata.get("ingestion_method") or "unknown"))
    first_seen = metadata.get("first_seen_run_id") or "없음"
    last_seen = metadata.get("last_seen_run_id") or "없음"
    return f"{role} / {method} / 최초 run {first_seen} / 최근 run {last_seen}"


def _source_role_label(role: str) -> str:
    return {
        "runtime_run_evidence": "workflow 실행 중 수집",
        "existing_catalog": "기존 catalog 근거",
        "seed_catalog": "사전 색인 catalog 근거",
        "manual_ingestion": "수동 수집 근거",
        "enrichment_result": "상세 보강 근거",
        "unknown": "분류되지 않은 기존 근거",
        "unclassified": "분류되지 않은 기존 근거",
    }.get(role, "분류되지 않은 기존 근거")


def _ingestion_method_label(method: str) -> str:
    return {
        "workflow_baseline_tourapi": "기본 TourAPI 수집",
        "workflow_detail_enrichment": "상세정보 보강",
        "visual_api_enrichment": "이미지 후보 보강",
        "route_signal_enrichment": "동선/수요 신호 보강",
        "theme_api_enrichment": "테마 근거 보강",
        "manual_data_search_api": "수동 검색",
        "manual_detail_enrichment_api": "수동 상세 보강",
        "rag_ingest_existing_tourism_items": "기존 관광 item 색인",
    }.get(method, method or "확인 필요")


def _embedding_status_label(status: str) -> str:
    if status == "indexed":
        return "RAG 검색 가능"
    if status == "pending":
        return "색인 대기"
    if status == "failed":
        return "색인 실패"
    return status


def _excerpt(value: str, limit: int = 260) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."


def _latest_datetime(values: list[Any]) -> datetime | None:
    datetimes = [value for value in values if isinstance(value, datetime)]
    if not datetimes:
        return None
    return max(datetimes)
