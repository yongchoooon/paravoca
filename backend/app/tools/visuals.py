from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.timezone import now_kst_naive
from app.db import models
from app.rag.chroma_store import index_source_documents
from app.tools.tourism_enrichment import upsert_tourism_entity


KTO_TOURISM_PHOTO_BASE_URL = "https://apis.data.go.kr/B551011/PhotoGalleryService1"
KTO_PHOTO_CONTEST_BASE_URL = "https://apis.data.go.kr/B551011/PhokoAwrdService"


@dataclass
class VisualAssetCandidate:
    id: str
    source_family: str
    operation: str
    title: str | None
    image_url: str | None
    thumbnail_url: str | None = None
    source_item_id: str | None = None
    shooting_place: str | None = None
    shooting_date: str | None = None
    photographer: str | None = None
    keywords: list[str] = field(default_factory=list)
    license_type: str | None = None
    license_note: str | None = None
    usage_status: str = "needs_license_review"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class VisualDataProvider(Protocol):
    def search_tourism_photos(self, *, keyword: str, limit: int = 5) -> list[VisualAssetCandidate]:
        ...

    def search_photo_contest_awards(
        self,
        *,
        keyword: str,
        ldong_regn_cd: str | None = None,
        limit: int = 5,
    ) -> list[VisualAssetCandidate]:
        ...


class KtoVisualProvider:
    def __init__(self, settings: Settings | None = None, service_key: str | None = None) -> None:
        self.settings = settings or get_settings()
        self.service_key = service_key or self.settings.tourapi_service_key

    def search_tourism_photos(self, *, keyword: str, limit: int = 5) -> list[VisualAssetCandidate]:
        if not self.settings.kto_tourism_photo_enabled:
            raise RuntimeError("KTO_TOURISM_PHOTO_ENABLED is false")
        data = self._get(
            base_url=KTO_TOURISM_PHOTO_BASE_URL,
            operation="gallerySearchList1",
            params={"keyword": keyword, "numOfRows": limit, "pageNo": 1},
        )
        return [_tourism_photo_candidate(raw) for raw in _extract_response_items(data)]

    def search_photo_contest_awards(
        self,
        *,
        keyword: str,
        ldong_regn_cd: str | None = None,
        limit: int = 5,
    ) -> list[VisualAssetCandidate]:
        if not self.settings.kto_photo_contest_enabled:
            raise RuntimeError("KTO_PHOTO_CONTEST_ENABLED is false")
        data = self._get(
            base_url=KTO_PHOTO_CONTEST_BASE_URL,
            operation="phokoAwrdList",
            params={
                "keyword": keyword,
                "lDongRegnCd": ldong_regn_cd,
                "numOfRows": limit,
                "pageNo": 1,
            },
        )
        return [_photo_contest_candidate(raw) for raw in _extract_response_items(data)]

    def _get(self, *, base_url: str, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.service_key:
            raise RuntimeError("TOURAPI_SERVICE_KEY is required for visual KTO providers")
        clean_params = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": "PARAVOCAAX",
            "_type": "json",
            **{key: value for key, value in params.items() if value not in (None, "")},
        }
        response = httpx.get(f"{base_url.rstrip('/')}/{operation}", params=clean_params, timeout=10)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"KTO visual API {operation} HTTP {exc.response.status_code}"
            ) from exc
        data = response.json()
        top_level_code = str(data.get("resultCode", ""))
        if top_level_code and top_level_code != "0000":
            raise RuntimeError(
                f"KTO visual API {operation} failed with resultCode={top_level_code}: "
                f"{data.get('resultMsg') or 'Unknown error'}"
            )
        header = data.get("response", {}).get("header", {})
        result_code = str(header.get("resultCode", ""))
        if result_code and result_code != "0000":
            raise RuntimeError(
                f"KTO visual API {operation} failed with resultCode={result_code}: "
                f"{header.get('resultMsg') or 'Unknown error'}"
            )
        return data


def get_visual_provider() -> VisualDataProvider:
    return KtoVisualProvider()


def execute_visual_search(
    *,
    db: Session,
    provider: VisualDataProvider,
    plan_call: dict[str, Any],
    target_item: models.TourismItem,
    run_id: str | None = None,
    step_id: str | None = None,
) -> dict[str, Any]:
    arguments = plan_call.get("arguments") if isinstance(plan_call.get("arguments"), dict) else {}
    keyword = _visual_query(plan_call, target_item)
    limit = int(arguments.get("limit") or arguments.get("numOfRows") or 5)
    source_family = str(plan_call.get("source_family") or "")
    started = time.perf_counter()
    if source_family == "kto_tourism_photo":
        raw_candidates = _log_visual_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_tourism_photo_search",
            source=source_family,
            arguments={"keyword": keyword, "limit": limit},
            call=lambda: provider.search_tourism_photos(keyword=keyword, limit=limit),
        )
    elif source_family == "kto_photo_contest":
        raw_candidates = _log_visual_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_photo_contest_award_list",
            source=source_family,
            arguments={
                "keyword": keyword,
                "ldong_regn_cd": target_item.ldong_regn_cd,
                "limit": limit,
            },
            call=lambda: provider.search_photo_contest_awards(
                keyword=keyword,
                ldong_regn_cd=target_item.ldong_regn_cd,
                limit=limit,
            ),
        )
    else:
        raise ValueError(f"Unsupported visual source_family: {source_family}")

    candidates = [candidate for candidate in raw_candidates if candidate.image_url]
    assets = upsert_visual_asset_candidates(
        db=db,
        target_item=target_item,
        candidates=candidates,
    )
    documents = upsert_source_documents_from_visual_assets(
        db=db,
        target_item=target_item,
        assets=assets,
    )
    indexed = index_source_documents(db, documents) if documents else 0
    return {
        "source_family": source_family,
        "operation": plan_call.get("operation"),
        "query": keyword,
        "visual_candidates_found": len(raw_candidates),
        "visual_assets": len(assets),
        "source_documents": len(documents),
        "indexed_documents": indexed,
        "usage_status": "needs_license_review" if assets else "unavailable",
        "reason": plan_call.get("reason"),
        "expected_ui": plan_call.get("expected_ui"),
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def upsert_visual_asset_candidates(
    *,
    db: Session,
    target_item: models.TourismItem,
    candidates: list[VisualAssetCandidate],
) -> list[models.TourismVisualAsset]:
    entity = upsert_tourism_entity(db, target_item)
    assets: list[models.TourismVisualAsset] = []
    for candidate in candidates:
        if not candidate.image_url:
            continue
        asset_id = _stable_visual_asset_id(
            candidate.source_family,
            target_item.content_id,
            candidate.source_item_id or candidate.title or "",
            candidate.image_url,
        )
        raw = dict(candidate.raw or {})
        raw.update(
            {
                "provider_operation": candidate.operation,
                "provider_source_item_id": candidate.source_item_id,
                "linked_content_id": target_item.content_id,
                "linked_source_item_id": target_item.id,
                "usage_status": candidate.usage_status,
            }
        )
        payload = {
            "id": asset_id,
            "entity_id": entity.id,
            "source_family": candidate.source_family,
            "source_item_id": target_item.id,
            "title": candidate.title or target_item.title,
            "image_url": str(candidate.image_url),
            "thumbnail_url": candidate.thumbnail_url or candidate.image_url,
            "shooting_place": candidate.shooting_place or target_item.address,
            "shooting_date": candidate.shooting_date,
            "photographer": candidate.photographer,
            "keywords": _dedupe_texts([*candidate.keywords, target_item.title]),
            "license_type": candidate.license_type or "KTO visual API usage terms review required",
            "license_note": candidate.license_note
            or "이미지 후보입니다. 게시 전 공공데이터 이용 조건, 저작권 유형, 원 출처 표시 조건을 확인하세요.",
            "usage_status": candidate.usage_status or "needs_license_review",
            "raw": raw,
            "retrieved_at": models.utcnow(),
        }
        existing = db.get(models.TourismVisualAsset, asset_id)
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            db.add(existing)
            assets.append(existing)
            continue
        asset = models.TourismVisualAsset(**payload)
        db.add(asset)
        assets.append(asset)
    db.commit()
    for asset in assets:
        db.refresh(asset)
    return assets


def upsert_source_documents_from_visual_assets(
    *,
    db: Session,
    target_item: models.TourismItem,
    assets: list[models.TourismVisualAsset],
) -> list[models.SourceDocument]:
    documents: list[models.SourceDocument] = []
    for asset in assets:
        metadata = _visual_source_metadata(target_item, asset)
        payload = {
            "id": f"doc:{asset.id}",
            "source": asset.source_family,
            "source_item_id": target_item.id,
            "title": asset.title or target_item.title,
            "content": _visual_source_content(target_item, asset),
            "document_metadata": metadata,
            "embedding_status": "pending",
        }
        existing = db.get(models.SourceDocument, payload["id"])
        if existing:
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


def _tourism_photo_candidate(raw: dict[str, Any]) -> VisualAssetCandidate:
    image_url = _string_or_none(raw.get("galWebImageUrl"))
    content_id = _string_or_none(raw.get("galContentId"))
    title = _string_or_none(raw.get("galTitle"))
    return VisualAssetCandidate(
        id=_stable_candidate_id("kto_tourism_photo", content_id or title or "", image_url or ""),
        source_family="kto_tourism_photo",
        operation="gallerySearchList1",
        source_item_id=content_id,
        title=title,
        image_url=image_url,
        thumbnail_url=image_url,
        shooting_place=_string_or_none(raw.get("galPhotographyLocation")),
        shooting_date=_string_or_none(raw.get("galPhotographyMonth")),
        photographer=_string_or_none(raw.get("galPhotographer")),
        keywords=_split_keywords(raw.get("galSearchKeyword")),
        license_type="관광사진 정보_GW 이용 조건 확인 필요",
        license_note="관광사진 API 이미지 후보입니다. 게시 전 공공누리/출처 표시/상업적 사용 가능 범위를 확인하세요.",
        usage_status="needs_license_review" if image_url else "unavailable",
        raw=raw,
    )


def _photo_contest_candidate(raw: dict[str, Any]) -> VisualAssetCandidate:
    image_url = _string_or_none(raw.get("orgImage") or raw.get("thumbImage"))
    content_id = _string_or_none(raw.get("contentId"))
    title = _string_or_none(raw.get("koTitle") or raw.get("enTitle"))
    copyright_code = _string_or_none(raw.get("cpyrhtDivCd"))
    return VisualAssetCandidate(
        id=_stable_candidate_id("kto_photo_contest", content_id or title or "", image_url or ""),
        source_family="kto_photo_contest",
        operation="phokoAwrdList",
        source_item_id=content_id,
        title=title,
        image_url=image_url,
        thumbnail_url=_string_or_none(raw.get("thumbImage")) or image_url,
        shooting_place=_string_or_none(raw.get("koFilmst") or raw.get("enFilmst")),
        shooting_date=_string_or_none(raw.get("filmDay")),
        photographer=_string_or_none(raw.get("koCmanNm") or raw.get("enCmanNm")),
        keywords=_split_keywords(raw.get("koKeyWord") or raw.get("enKeyWord")),
        license_type=copyright_code or "관광공모전 사진 이용 조건 확인 필요",
        license_note=(
            f"관광공모전 사진 후보입니다. 저작권 유형 {copyright_code or '미확인'} 기준으로 "
            "게시 가능 여부와 출처 표시 조건을 확인하세요."
        ),
        usage_status="needs_license_review" if image_url else "unavailable",
        raw=raw,
    )


def _visual_source_metadata(target_item: models.TourismItem, asset: models.TourismVisualAsset) -> dict[str, Any]:
    return {
        "source": asset.source_family,
        "source_family": asset.source_family,
        "source_item_id": target_item.id,
        "title": asset.title or target_item.title,
        "content_id": target_item.content_id,
        "content_type": target_item.content_type,
        "region_code": target_item.region_code,
        "sigungu_code": target_item.sigungu_code,
        "legacy_area_code": target_item.legacy_area_code,
        "legacy_sigungu_code": target_item.legacy_sigungu_code,
        "ldong_regn_cd": target_item.ldong_regn_cd,
        "ldong_signgu_cd": target_item.ldong_signgu_cd,
        "lcls_systm_1": target_item.lcls_systm_1,
        "lcls_systm_2": target_item.lcls_systm_2,
        "lcls_systm_3": target_item.lcls_systm_3,
        "address": target_item.address,
        "visual_asset_id": asset.id,
        "image_url": asset.image_url,
        "thumbnail_url": asset.thumbnail_url,
        "visual_asset_count": 1,
        "image_candidates": [
            {
                "image_url": asset.image_url,
                "thumbnail_url": asset.thumbnail_url or asset.image_url,
                "title": asset.title or target_item.title,
                "usage_status": asset.usage_status,
                "source": asset.source_family,
                "license_type": asset.license_type,
            }
        ],
        "shooting_place": asset.shooting_place,
        "shooting_date": asset.shooting_date,
        "photographer": asset.photographer,
        "keywords": asset.keywords,
        "license_type": asset.license_type,
        "license_note": asset.license_note,
        "usage_status": asset.usage_status,
        "needs_review": True,
        "data_quality_flags": ["needs_license_review"],
        "interpretation_notes": ["이미지 후보이며 게시 전 사용권과 출처 표시 조건 확인이 필요합니다."],
        "retrieved_at": (asset.retrieved_at or now_kst_naive()).isoformat(),
        "trust_level": 0.65,
    }


def _visual_source_content(target_item: models.TourismItem, asset: models.TourismVisualAsset) -> str:
    return "\n".join(
        part
        for part in [
            f"이미지 후보: {asset.title or target_item.title}",
            f"연결 관광지: {target_item.title}",
            f"출처 종류: {asset.source_family}",
            f"촬영 장소: {asset.shooting_place or ''}",
            f"촬영 시기: {asset.shooting_date or ''}",
            f"촬영자: {asset.photographer or ''}",
            f"키워드: {', '.join(asset.keywords or [])}",
            f"사용 상태: {asset.usage_status}",
            f"라이선스: {asset.license_type or '확인 필요'}",
            f"사용권 메모: {asset.license_note or '게시 전 확인 필요'}",
        ]
        if part.strip()
    )


def _visual_query(plan_call: dict[str, Any], target_item: models.TourismItem) -> str:
    arguments = plan_call.get("arguments") if isinstance(plan_call.get("arguments"), dict) else {}
    query = _string_or_none(arguments.get("query") or arguments.get("keyword"))
    if query:
        return query
    title = str(target_item.title or "").strip()
    address = str(target_item.address or "").strip()
    if title:
        return title
    return address or str(target_item.content_id)


def _log_visual_tool_call(
    *,
    db: Session,
    run_id: str | None,
    step_id: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    source: str,
    call,
) -> list[VisualAssetCandidate]:
    tool_call = None
    started = time.perf_counter()
    if run_id:
        tool_call = models.ToolCall(
            run_id=run_id,
            step_id=step_id,
            tool_name=tool_name,
            status="started",
            arguments=arguments,
            source=source,
        )
        db.add(tool_call)
        db.commit()
        db.refresh(tool_call)
    try:
        result = call()
        if tool_call:
            tool_call.status = "succeeded"
            tool_call.response_summary = {
                "count": len(result),
                "titles": [candidate.title for candidate in result[:5]],
            }
            tool_call.latency_ms = int((time.perf_counter() - started) * 1000)
            db.commit()
        return result
    except Exception as exc:
        if tool_call:
            tool_call.status = "failed"
            tool_call.error = {"type": exc.__class__.__name__, "message": str(exc)}
            tool_call.latency_ms = int((time.perf_counter() - started) * 1000)
            db.commit()
        raise


def _extract_response_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    body = data.get("response", {}).get("body", {})
    items = body.get("items") or {}
    if not isinstance(items, dict):
        return []
    item = items.get("item", [])
    if isinstance(item, dict):
        return [item]
    if isinstance(item, list):
        return item
    return []


def _split_keywords(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    for delimiter in [",", "|", "#", ";"]:
        text = text.replace(delimiter, " ")
    return _dedupe_texts(part.strip() for part in text.split() if part.strip())


def _dedupe_texts(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _stable_candidate_id(source_family: str, source_id: str, image_url: str) -> str:
    digest = hashlib.sha1(f"{source_family}:{source_id}:{image_url}".encode("utf-8")).hexdigest()[:16]
    return f"visual_candidate:{source_family}:{digest}"


def _stable_visual_asset_id(source_family: str, content_id: str, source_id: str, image_url: str) -> str:
    digest = hashlib.sha1(f"{source_family}:{content_id}:{source_id}:{image_url}".encode("utf-8")).hexdigest()[:16]
    return f"visual:{source_family}:{content_id}:{digest}"


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
