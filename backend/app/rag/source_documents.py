from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.timezone import now_kst
from app.db import models
from app.tools.tourism import TourismItem
from app.tools.tourism_enrichment import (
    detail_info_to_lines,
    detail_intro_to_lines,
    image_candidates_from_item,
)

SOURCE_ROLE_RUNTIME = "runtime_run_evidence"
SOURCE_ROLE_EXISTING = "existing_catalog"
SOURCE_ROLE_SEED = "seed_catalog"
SOURCE_ROLE_MANUAL = "manual_ingestion"
SOURCE_ROLE_ENRICHMENT = "enrichment_result"
SOURCE_ROLE_UNKNOWN = "unknown"

VALID_SOURCE_ROLES = {
    SOURCE_ROLE_RUNTIME,
    SOURCE_ROLE_EXISTING,
    SOURCE_ROLE_SEED,
    SOURCE_ROLE_MANUAL,
    SOURCE_ROLE_ENRICHMENT,
    SOURCE_ROLE_UNKNOWN,
    "unclassified",
}


def build_source_document(
    item: TourismItem | models.TourismItem,
    *,
    run_id: str | None = None,
    source_role: str = SOURCE_ROLE_MANUAL,
    ingestion_method: str = "manual_or_api_ingestion",
) -> dict[str, Any]:
    source_family = _source_family_for_item(item)
    retrieved_at = now_kst().isoformat()
    license_note = item.license_type or "공식 응답 기준, 상세 이용 조건 확인 필요"
    raw = dict(getattr(item, "raw", {}) or {})
    detail_intro = raw.get("detail_intro") if isinstance(raw.get("detail_intro"), dict) else {}
    detail_info = raw.get("detail_info") if isinstance(raw.get("detail_info"), list) else []
    image_candidates = image_candidates_from_item(item)
    detail_intro_lines = detail_intro_to_lines(detail_intro)
    detail_info_lines = detail_info_to_lines(detail_info)
    metadata = with_source_lifecycle_metadata(
        {
            "source": item.source,
            "source_family": source_family,
            "source_item_id": item.id,
            "title": item.title,
            "content_id": item.content_id,
            "content_type": item.content_type,
            "region_code": item.region_code,
            "sigungu_code": item.sigungu_code,
            "legacy_area_code": getattr(item, "legacy_area_code", None),
            "legacy_sigungu_code": getattr(item, "legacy_sigungu_code", None),
            "ldong_regn_cd": getattr(item, "ldong_regn_cd", None),
            "ldong_signgu_cd": getattr(item, "ldong_signgu_cd", None),
            "lcls_systm_1": getattr(item, "lcls_systm_1", None),
            "lcls_systm_2": getattr(item, "lcls_systm_2", None),
            "lcls_systm_3": getattr(item, "lcls_systm_3", None),
            "address": item.address,
            "homepage": item.homepage,
            "image_url": item.image_url,
            "license_type": item.license_type,
            "license_note": license_note,
            "event_start_date": item.event_start_date,
            "event_end_date": item.event_end_date,
            "detail_common_available": bool(raw.get("detail_common")),
            "detail_intro_available": bool(detail_intro),
            "detail_info_count": len(detail_info),
            "detail_image_count": len(raw.get("detail_images") or []),
            "visual_asset_count": len(image_candidates),
            "image_candidates": image_candidates[:5],
            "retrieved_at": retrieved_at,
            "valid_from": item.event_start_date,
            "valid_to": item.event_end_date,
            "trust_level": 0.9 if item.source == "tourapi" else 0.7,
            "data_quality_flags": _data_quality_flags(item),
            "interpretation_notes": _interpretation_notes(item),
        },
        source_role=source_role,
        ingestion_method=ingestion_method,
        run_id=run_id,
        detail_enriched=bool(raw.get("detail_common") or detail_intro or detail_info or raw.get("detail_images")),
    )
    content = "\n".join(
        part
        for part in [
            f"제목: {item.title}",
            f"유형: {item.content_type}",
            f"지역코드: {item.region_code}",
            f"법정동코드: {getattr(item, 'ldong_regn_cd', '') or ''}/{getattr(item, 'ldong_signgu_cd', '') or ''}",
            f"신분류체계: {getattr(item, 'lcls_systm_1', '') or ''}/{getattr(item, 'lcls_systm_2', '') or ''}/{getattr(item, 'lcls_systm_3', '') or ''}",
            f"주소: {item.address or ''}",
            f"기간: {item.event_start_date or ''}~{item.event_end_date or ''}",
            f"개요: {item.overview or ''}",
            f"홈페이지: {item.homepage or ''}",
            "상세 소개: " + " / ".join(detail_intro_lines[:8]) if detail_intro_lines else "",
            "이용정보: " + " / ".join(detail_info_lines[:12]) if detail_info_lines else "",
            f"이미지 후보 수: {len(image_candidates)}",
            f"이미지/라이선스: {item.license_type or '확인 필요'}",
        ]
        if part.strip()
    )
    return {
        "id": f"doc:{item.id}",
        "source": item.source,
        "source_item_id": item.id,
        "title": item.title,
        "content": content,
        "document_metadata": metadata,
        "embedding_status": "pending",
    }


def upsert_source_documents_from_items(
    db: Session,
    items: list[TourismItem | models.TourismItem],
    *,
    run_id: str | None = None,
    source_role: str = SOURCE_ROLE_MANUAL,
    ingestion_method: str = "manual_or_api_ingestion",
) -> list[models.SourceDocument]:
    documents: list[models.SourceDocument] = []
    for item in items:
        payload = build_source_document(
            item,
            run_id=run_id,
            source_role=source_role,
            ingestion_method=ingestion_method,
        )
        existing = db.get(models.SourceDocument, payload["id"])
        if existing:
            payload["document_metadata"] = merge_source_lifecycle_metadata(
                existing.document_metadata if isinstance(existing.document_metadata, dict) else {},
                payload["document_metadata"],
                run_id=run_id,
                source_role=source_role,
                ingestion_method=ingestion_method,
            )
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.updated_at = models.utcnow()
            document = existing
        else:
            document = models.SourceDocument(**payload)
            db.add(document)
        documents.append(document)
    db.commit()
    for document in documents:
        db.refresh(document)
    return documents


def with_source_lifecycle_metadata(
    metadata: dict[str, Any],
    *,
    source_role: str,
    ingestion_method: str,
    run_id: str | None = None,
    detail_enriched: bool | None = None,
) -> dict[str, Any]:
    observed_at = now_kst().isoformat()
    role = normalize_source_role(source_role)
    lifecycle = {
        "source_role": role,
        "ingestion_method": ingestion_method,
        "first_seen_run_id": run_id,
        "last_seen_run_id": run_id,
        "observed_at": observed_at,
        "last_observed_at": observed_at,
        "detail_enriched": bool(detail_enriched),
        "dedupe_key": source_document_dedupe_key(metadata),
        "stale_status": "not_evaluated",
        "stale_reasons": [],
    }
    return {**metadata, **lifecycle}


def merge_source_lifecycle_metadata(
    existing_metadata: dict[str, Any],
    new_metadata: dict[str, Any],
    *,
    run_id: str | None = None,
    source_role: str | None = None,
    ingestion_method: str | None = None,
) -> dict[str, Any]:
    observed_at = now_kst().isoformat()
    role = normalize_source_role(source_role or new_metadata.get("source_role") or existing_metadata.get("source_role"))
    merged = {**existing_metadata, **new_metadata}
    merged["source_role"] = role
    if ingestion_method:
        merged["ingestion_method"] = ingestion_method
    else:
        merged["ingestion_method"] = merged.get("ingestion_method") or "unknown"
    merged["first_seen_run_id"] = existing_metadata.get("first_seen_run_id") or new_metadata.get("first_seen_run_id") or run_id
    merged["last_seen_run_id"] = run_id or new_metadata.get("last_seen_run_id") or existing_metadata.get("last_seen_run_id")
    merged["observed_at"] = existing_metadata.get("observed_at") or new_metadata.get("observed_at") or observed_at
    merged["last_observed_at"] = observed_at
    merged["detail_enriched"] = bool(new_metadata.get("detail_enriched") or existing_metadata.get("detail_enriched"))
    merged["dedupe_key"] = source_document_dedupe_key(merged)
    merged.setdefault("stale_status", "not_evaluated")
    merged.setdefault("stale_reasons", [])
    return merged


def normalize_source_role(value: Any) -> str:
    role = str(value or "").strip()
    return role if role in VALID_SOURCE_ROLES else SOURCE_ROLE_UNKNOWN


def source_document_dedupe_key(metadata: dict[str, Any]) -> str:
    source_family = str(metadata.get("source_family") or metadata.get("source") or "unknown").strip()
    content_id = str(metadata.get("content_id") or "").strip()
    source_item_id = str(metadata.get("source_item_id") or "").strip()
    stable_id = content_id or source_item_id or str(metadata.get("title") or "").strip()
    return f"{source_family}:{stable_id or 'unknown'}"


def source_document_role(document_or_metadata: models.SourceDocument | dict[str, Any]) -> str:
    metadata = (
        document_or_metadata.document_metadata
        if isinstance(document_or_metadata, models.SourceDocument)
        else document_or_metadata
    )
    if not isinstance(metadata, dict):
        return SOURCE_ROLE_UNKNOWN
    return normalize_source_role(metadata.get("source_role"))


def _source_family_for_item(item: TourismItem | models.TourismItem) -> str:
    if item.source == "tourapi":
        return "kto_tourapi_kor"
    return item.source


def _data_quality_flags(item: TourismItem | models.TourismItem) -> list[str]:
    flags: list[str] = []
    if not item.overview:
        flags.append("missing_overview")
    if not item.image_url:
        flags.append("missing_image_asset")
    raw = dict(getattr(item, "raw", {}) or {})
    if not raw.get("detail_common"):
        flags.append("missing_detail_common")
    if not raw.get("detail_info"):
        flags.append("missing_detail_info")
    if item.content_type == "event" and not item.event_start_date:
        flags.append("missing_event_start_date")
    if item.content_type == "event" and not item.event_end_date:
        flags.append("missing_event_end_date")
    return flags


def _interpretation_notes(item: TourismItem | models.TourismItem) -> list[str]:
    notes = ["공공데이터 응답 기준이며 실제 운영 조건은 게시 전 확인이 필요합니다."]
    if item.content_type == "event":
        notes.append("행사 일정은 변경될 수 있으므로 공식 공지 확인이 필요합니다.")
    if not item.image_url:
        notes.append("대표 이미지가 없어 Phase 9 이후 detailImage 또는 관광사진 보강 대상입니다.")
    raw = dict(getattr(item, "raw", {}) or {})
    if raw.get("detail_common"):
        notes.append("detailCommon2로 상세 공통 정보가 보강되었습니다.")
    if raw.get("detail_info"):
        notes.append("detailInfo2 반복 정보가 보강되었지만 게시 전 운영 조건 확인이 필요합니다.")
    return notes
