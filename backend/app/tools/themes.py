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
from app.rag.source_documents import (
    SOURCE_ROLE_ENRICHMENT,
    merge_source_lifecycle_metadata,
    with_source_lifecycle_metadata,
)


KTO_WELLNESS_BASE_URL = "https://apis.data.go.kr/B551011/WellnessTursmService"
KTO_MEDICAL_BASE_URL = "https://apis.data.go.kr/B551011/MdclTursmService"
KTO_PET_BASE_URL = "https://apis.data.go.kr/B551011/KorPetTourService2"
KTO_AUDIO_BASE_URL = "https://apis.data.go.kr/B551011/Odii"


@dataclass
class ThemeDataCandidate:
    id: str
    source_family: str
    operation: str
    title: str | None = None
    content_id: str | None = None
    content_type_id: str | None = None
    address: str | None = None
    tel: str | None = None
    overview: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    license_type: str | None = None
    theme_attributes: dict[str, Any] = field(default_factory=dict)
    operating_info: dict[str, Any] = field(default_factory=dict)
    needs_review: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ThemeDataProvider(Protocol):
    def search_wellness(
        self,
        *,
        keyword: str,
        ldong_regn_cd: str | None = None,
        ldong_signgu_cd: str | None = None,
        limit: int = 5,
    ) -> list[ThemeDataCandidate]:
        ...

    def search_pet(
        self,
        *,
        keyword: str,
        ldong_regn_cd: str | None = None,
        ldong_signgu_cd: str | None = None,
        limit: int = 5,
    ) -> list[ThemeDataCandidate]:
        ...

    def search_audio(self, *, keyword: str, limit: int = 5) -> list[ThemeDataCandidate]:
        ...

    def search_medical(
        self,
        *,
        keyword: str,
        ldong_regn_cd: str | None = None,
        ldong_signgu_cd: str | None = None,
        limit: int = 5,
    ) -> list[ThemeDataCandidate]:
        ...


class KtoThemeProvider:
    def __init__(self, settings: Settings | None = None, service_key: str | None = None) -> None:
        self.settings = settings or get_settings()
        self.service_key = service_key or self.settings.tourapi_service_key

    def search_wellness(
        self,
        *,
        keyword: str,
        ldong_regn_cd: str | None = None,
        ldong_signgu_cd: str | None = None,
        limit: int = 5,
    ) -> list[ThemeDataCandidate]:
        if not self.settings.kto_wellness_enabled:
            raise RuntimeError("KTO_WELLNESS_ENABLED is false")
        data = self._get(
            base_url=KTO_WELLNESS_BASE_URL,
            operation="searchKeyword",
            params={
                "keyword": keyword,
                "langDivCd": "KOR",
                "lDongRegnCd": ldong_regn_cd,
                "lDongSignguCd": ldong_signgu_cd,
                "arrange": "C",
                "numOfRows": limit,
                "pageNo": 1,
            },
        )
        return [_wellness_candidate(raw, "searchKeyword") for raw in _extract_response_items(data)]

    def search_pet(
        self,
        *,
        keyword: str,
        ldong_regn_cd: str | None = None,
        ldong_signgu_cd: str | None = None,
        limit: int = 5,
    ) -> list[ThemeDataCandidate]:
        if not self.settings.kto_pet_enabled:
            raise RuntimeError("KTO_PET_ENABLED is false")
        data = self._get(
            base_url=KTO_PET_BASE_URL,
            operation="searchKeyword2",
            params={
                "keyword": keyword,
                "lDongRegnCd": ldong_regn_cd,
                "lDongSignguCd": ldong_signgu_cd,
                "arrange": "C",
                "numOfRows": limit,
                "pageNo": 1,
            },
        )
        candidates = [_pet_candidate(raw, "searchKeyword2") for raw in _extract_response_items(data)]
        for candidate in candidates:
            if not candidate.content_id:
                continue
            detail_data = self._get(
                base_url=KTO_PET_BASE_URL,
                operation="detailPetTour2",
                params={"contentId": candidate.content_id, "numOfRows": 1, "pageNo": 1},
            )
            detail_items = _extract_response_items(detail_data)
            if not detail_items:
                continue
            pet_detail = detail_items[0]
            candidate.raw["detail_pet_tour"] = pet_detail
            candidate.theme_attributes.update(_pet_policy_attributes(pet_detail))
            candidate.needs_review.extend(_pet_needs_review(candidate.theme_attributes))
        return candidates

    def search_audio(self, *, keyword: str, limit: int = 5) -> list[ThemeDataCandidate]:
        if not self.settings.kto_audio_enabled:
            raise RuntimeError("KTO_AUDIO_ENABLED is false")
        candidates: list[ThemeDataCandidate] = []
        for operation in ["storySearchList", "themeSearchList"]:
            data = self._get(
                base_url=KTO_AUDIO_BASE_URL,
                operation=operation,
                params={
                    "keyword": keyword,
                    "langCode": "ko",
                    "numOfRows": limit,
                    "pageNo": 1,
                },
            )
            candidates.extend(_audio_candidate(raw, operation) for raw in _extract_response_items(data))
            if len(candidates) >= limit:
                break
        return candidates[:limit]

    def search_medical(
        self,
        *,
        keyword: str,
        ldong_regn_cd: str | None = None,
        ldong_signgu_cd: str | None = None,
        limit: int = 5,
    ) -> list[ThemeDataCandidate]:
        if not self.settings.allow_medical_api:
            raise RuntimeError("ALLOW_MEDICAL_API is false")
        data = self._get(
            base_url=KTO_MEDICAL_BASE_URL,
            operation="searchKeyword",
            params={
                "keyword": keyword,
                "langDivCd": "ENG",
                "lDongRegnCd": ldong_regn_cd,
                "lDongSignguCd": ldong_signgu_cd,
                "arrange": "C",
                "numOfRows": limit,
                "pageNo": 1,
            },
        )
        return [_medical_candidate(raw, "searchKeyword") for raw in _extract_response_items(data)]

    def _get(self, *, base_url: str, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.service_key:
            raise RuntimeError("TOURAPI_SERVICE_KEY is required for theme KTO providers")
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
            raise RuntimeError(f"KTO theme API {operation} HTTP {exc.response.status_code}") from exc
        data = response.json()
        top_level_code = str(data.get("resultCode", ""))
        if top_level_code and top_level_code != "0000":
            raise RuntimeError(
                f"KTO theme API {operation} failed with resultCode={top_level_code}: "
                f"{data.get('resultMsg') or 'Unknown error'}"
            )
        header = _response_header(data)
        result_code = str(header.get("resultCode", ""))
        if result_code and result_code not in {"0000", "00"}:
            raise RuntimeError(
                f"KTO theme API {operation} failed with resultCode={result_code}: "
                f"{header.get('resultMsg') or 'Unknown error'}"
            )
        return data


def get_theme_provider() -> ThemeDataProvider:
    return KtoThemeProvider()


def execute_theme_search(
    *,
    db: Session,
    provider: ThemeDataProvider,
    plan_call: dict[str, Any],
    target_item: models.TourismItem | None,
    fallback_source_item_id: str | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
) -> dict[str, Any]:
    arguments = plan_call.get("arguments") if isinstance(plan_call.get("arguments"), dict) else {}
    source_family = str(plan_call.get("source_family") or "")
    keyword = _theme_query(plan_call, target_item, source_family=source_family)
    limit = int(arguments.get("limit") or arguments.get("numOfRows") or 5)
    ldong_regn_cd = _string_or_none(arguments.get("ldong_regn_cd") or _item_l_dong_regn_cd(target_item))
    ldong_signgu_cd = _string_or_none(arguments.get("ldong_signgu_cd") or _item_l_dong_signgu_cd(target_item))
    area_code = _string_or_none(arguments.get("area_code") or arguments.get("areaCode") or _item_area_cd(target_item))
    sigungu_code = _string_or_none(arguments.get("sigungu_code") or arguments.get("sigunguCode") or _item_signgu_cd(target_item))
    started = time.perf_counter()
    rejected_candidates: list[dict[str, Any]] = []

    if source_family == "kto_wellness":
        candidates = _log_theme_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_wellness_keyword_search",
            source=source_family,
            arguments={
                "keyword": keyword,
                "ldong_regn_cd": ldong_regn_cd,
                "ldong_signgu_cd": ldong_signgu_cd,
                "limit": limit,
            },
            call=lambda: provider.search_wellness(
                keyword=keyword,
                ldong_regn_cd=ldong_regn_cd,
                ldong_signgu_cd=ldong_signgu_cd,
                limit=limit,
            ),
        )
    elif source_family == "kto_pet":
        candidates = _log_theme_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_pet_keyword_search",
            source=source_family,
            arguments={
                "keyword": keyword,
                "ldong_regn_cd": ldong_regn_cd,
                "ldong_signgu_cd": ldong_signgu_cd,
                "limit": limit,
            },
            call=lambda: provider.search_pet(
                keyword=keyword,
                ldong_regn_cd=ldong_regn_cd,
                ldong_signgu_cd=ldong_signgu_cd,
                limit=limit,
            ),
        )
    elif source_family == "kto_audio":
        raw_candidates = _log_theme_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_audio_story_search",
            source=source_family,
            arguments={"keyword": keyword, "limit": limit},
            call=lambda: provider.search_audio(keyword=keyword, limit=limit),
        )
        candidates, rejected_candidates = _filter_theme_candidates_for_target(raw_candidates, target_item)
    elif source_family == "kto_medical":
        candidates = _log_theme_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_medical_keyword_search",
            source=source_family,
            arguments={
                "keyword": keyword,
                "ldong_regn_cd": ldong_regn_cd,
                "ldong_signgu_cd": ldong_signgu_cd,
                "limit": limit,
            },
            call=lambda: provider.search_medical(
                keyword=keyword,
                ldong_regn_cd=ldong_regn_cd,
                ldong_signgu_cd=ldong_signgu_cd,
                limit=limit,
            ),
        )
    else:
        raise ValueError(f"Unsupported theme source_family: {source_family}")

    entities = upsert_theme_entities(db=db, target_item=target_item, candidates=candidates)
    visual_assets = upsert_theme_visual_asset_candidates(db=db, target_item=target_item, candidates=candidates)
    documents = upsert_source_documents_from_theme_candidates(
        db=db,
        target_item=target_item,
        fallback_source_item_id=fallback_source_item_id or str(plan_call.get("id") or "theme_data"),
        candidates=candidates,
        entities=entities,
        visual_assets=visual_assets,
        run_id=run_id,
    )
    indexed = index_source_documents(db, documents) if documents else 0
    return {
        "source_family": source_family,
        "operation": plan_call.get("operation"),
        "query": keyword,
        "theme_candidates_found": len(candidates),
        "theme_candidates_rejected": len(rejected_candidates),
        "rejected_candidates": rejected_candidates,
        "theme_entities": len(entities),
        "visual_assets": len(visual_assets),
        "source_documents": len(documents),
        "indexed_documents": indexed,
        "usage_status": "theme_candidate" if candidates else "unavailable",
        "reason": plan_call.get("reason"),
        "expected_ui": plan_call.get("expected_ui"),
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def _filter_theme_candidates_for_target(
    candidates: list[ThemeDataCandidate],
    target_item: models.TourismItem | None,
) -> tuple[list[ThemeDataCandidate], list[dict[str, Any]]]:
    if not target_item:
        return candidates, []
    accepted: list[ThemeDataCandidate] = []
    rejected: list[dict[str, Any]] = []
    for candidate in candidates:
        signals, weak_signals = _theme_candidate_match_signals(candidate, target_item)
        if not signals:
            rejected.append(
                {
                    "candidate_id": candidate.id,
                    "title": candidate.title,
                    "source_family": candidate.source_family,
                    "theme_content_id": candidate.content_id,
                    "reason": (
                        "audio_candidate_does_not_reference_target_item"
                        if candidate.source_family == "kto_audio"
                        else "theme_candidate_does_not_reference_target_item"
                    ),
                    "target_item_id": target_item.id,
                    "target_title": target_item.title,
                    "weak_signals": weak_signals,
                }
            )
            continue
        candidate.raw["theme_match_signals"] = signals
        if weak_signals:
            candidate.raw["theme_match_weak_signals"] = weak_signals
        accepted.append(candidate)
    return accepted, rejected


def _theme_candidate_match_signals(
    candidate: ThemeDataCandidate,
    target_item: models.TourismItem,
) -> tuple[list[str], list[str]]:
    strong_signals: list[str] = []
    weak_signals: list[str] = []
    target_content_id = str(target_item.content_id or "").strip()
    raw_values = [str(value or "").strip() for value in (candidate.raw or {}).values()]
    raw_text = " ".join(raw_values)
    candidate_text = _normalize_match_text(
        " ".join(
            [
                candidate.title or "",
                candidate.address or "",
                candidate.overview or "",
                raw_text,
            ]
        )
    )
    if target_content_id and target_content_id in raw_values:
        weak_signals.append("cross_family_content_id_seen")
    target_title = _normalize_match_text(target_item.title)
    if target_title and target_title in candidate_text:
        strong_signals.append("target_title_text_match")
    matched_tokens = [token for token in _target_title_tokens(target_item.title) if token in candidate_text]
    if len(matched_tokens) >= 2:
        strong_signals.append("target_title_token_match")
    elif matched_tokens and len(matched_tokens[0]) >= 6:
        strong_signals.append(f"distinctive_target_title_token_match:{matched_tokens[0]}")
    for token in matched_tokens:
        weak_signals.append(f"target_title_token_seen:{token}")
    if (
        candidate.source_family != "kto_audio"
        and candidate.address
        and _same_exact_address(candidate.address, target_item.address)
    ):
        strong_signals.append("candidate_address_exact_match")
    if candidate.address and _same_region_text(candidate.address, target_item.address):
        weak_signals.append("candidate_address_region_match")
    return _dedupe_texts(strong_signals), _dedupe_texts(weak_signals)


_GENERIC_TITLE_TOKENS = {
    "관광",
    "여행",
    "투어",
    "체험",
    "축제",
    "행사",
    "문화",
    "역사",
    "코스",
    "안내",
    "소개",
    "오디오",
    "해설",
    "스토리",
    "테마",
    "후보",
    "프로그램",
}


def _target_title_tokens(title: str | None) -> list[str]:
    separators = str.maketrans({char: " " for char in "·/&,()[]{}<>「」『』‘’“”\"'"})
    raw_tokens = str(title or "").translate(separators).split()
    tokens = [_normalize_match_text(token) for token in raw_tokens]
    return [
        token
        for token in tokens
        if len(token) >= 2 and token not in _GENERIC_TITLE_TOKENS and not token.isdigit()
    ]


def _same_exact_address(candidate_address: str | None, target_address: str | None) -> bool:
    candidate = _normalize_match_text(candidate_address)
    target = _normalize_match_text(target_address)
    return bool(candidate and target and candidate == target)


def _same_region_text(candidate_address: str | None, target_address: str | None) -> bool:
    candidate = _normalize_match_text(candidate_address)
    target = _normalize_match_text(target_address)
    if not candidate or not target:
        return False
    target_parts = [part for part in str(target_address or "").split()[:2] if len(part) >= 2]
    return bool(target_parts) and all(_normalize_match_text(part) in candidate for part in target_parts)


def _normalize_match_text(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum() or "\uac00" <= ch <= "\ud7a3")


def upsert_theme_entities(
    *,
    db: Session,
    target_item: models.TourismItem | None,
    candidates: list[ThemeDataCandidate],
) -> list[models.TourismEntity]:
    entities: list[models.TourismEntity] = []
    for candidate in candidates:
        entity_id = _stable_theme_entity_id(candidate, target_item)
        payload = {
            "id": entity_id,
            "canonical_name": candidate.title or (target_item.title if target_item else "테마 후보"),
            "entity_type": "theme_candidate",
            "region_code": _item_area_cd(target_item),
            "sigungu_code": _item_signgu_cd(target_item),
            "address": candidate.address or (target_item.address if target_item else None),
            "map_x": _decimal_or_none(candidate.raw.get("mapX") or candidate.raw.get("mapx")),
            "map_y": _decimal_or_none(candidate.raw.get("mapY") or candidate.raw.get("mapy")),
            "primary_source_item_id": target_item.id if target_item else None,
            "match_confidence": 0.55,
            "entity_metadata": {
                "source_family": candidate.source_family,
                "operation": candidate.operation,
                "content_id": candidate.content_id,
                "content_type_id": candidate.content_type_id,
                "linked_content_id": target_item.content_id if target_item else None,
                "linked_source_item_id": target_item.id if target_item else None,
                "theme_attributes": candidate.theme_attributes,
                "operating_info": candidate.operating_info,
                "needs_review": candidate.needs_review or _default_theme_review_notes(candidate.source_family),
                "raw": candidate.raw,
                "retrieved_at": models.utcnow().isoformat(),
            },
        }
        existing = db.get(models.TourismEntity, entity_id)
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            db.add(existing)
            entities.append(existing)
            continue
        entity = models.TourismEntity(**payload)
        db.add(entity)
        entities.append(entity)
    db.commit()
    for entity in entities:
        db.refresh(entity)
    return entities


def upsert_theme_visual_asset_candidates(
    *,
    db: Session,
    target_item: models.TourismItem | None,
    candidates: list[ThemeDataCandidate],
) -> list[models.TourismVisualAsset]:
    assets: list[models.TourismVisualAsset] = []
    for candidate in candidates:
        if not candidate.image_url:
            continue
        entity_id = _stable_theme_entity_id(candidate, target_item)
        asset_id = _stable_theme_visual_asset_id(candidate, target_item)
        payload = {
            "id": asset_id,
            "entity_id": entity_id,
            "source_family": candidate.source_family,
            "source_item_id": target_item.id if target_item else None,
            "title": candidate.title,
            "image_url": str(candidate.image_url),
            "thumbnail_url": candidate.thumbnail_url or candidate.image_url,
            "shooting_place": candidate.address,
            "shooting_date": None,
            "photographer": None,
            "keywords": _dedupe_texts([candidate.title, candidate.source_family]),
            "license_type": candidate.license_type or "KTO theme API usage terms review required",
            "license_note": "테마 API 이미지 후보입니다. 게시 전 사용권, 저작권 유형, 출처 표시 조건을 확인하세요.",
            "usage_status": "needs_license_review",
            "raw": {
                "provider_operation": candidate.operation,
                "provider_content_id": candidate.content_id,
                "linked_content_id": target_item.content_id if target_item else None,
                "linked_source_item_id": target_item.id if target_item else None,
                "linked_target_address": target_item.address if target_item else None,
                "theme_source_family": candidate.source_family,
                "raw": candidate.raw,
            },
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


def upsert_source_documents_from_theme_candidates(
    *,
    db: Session,
    target_item: models.TourismItem | None,
    fallback_source_item_id: str,
    candidates: list[ThemeDataCandidate],
    entities: list[models.TourismEntity],
    visual_assets: list[models.TourismVisualAsset],
    run_id: str | None = None,
) -> list[models.SourceDocument]:
    documents: list[models.SourceDocument] = []
    entity_by_id = {entity.id: entity for entity in entities}
    visual_by_entity = {asset.entity_id: asset for asset in visual_assets}
    source_item_id = target_item.id if target_item else fallback_source_item_id
    for candidate in candidates:
        entity_id = _stable_theme_entity_id(candidate, target_item)
        entity = entity_by_id.get(entity_id)
        visual_asset = visual_by_entity.get(entity_id)
        metadata = _theme_source_metadata(
            target_item=target_item,
            candidate=candidate,
            source_item_id=source_item_id,
            entity=entity,
            visual_asset=visual_asset,
            run_id=run_id,
        )
        payload = {
            "id": f"doc:theme:{candidate.source_family}:{_stable_digest(entity_id, candidate.id)}",
            "source": candidate.source_family,
            "source_item_id": source_item_id,
            "title": candidate.title or (target_item.title if target_item else "테마 후보"),
            "content": _theme_source_content(target_item, candidate),
            "document_metadata": metadata,
            "embedding_status": "pending",
        }
        documents.append(_upsert_source_document(db, payload))
    db.commit()
    for document in documents:
        db.refresh(document)
    return documents


def _wellness_candidate(raw: dict[str, Any], operation: str) -> ThemeDataCandidate:
    content_id = _string_or_none(raw.get("contentId"))
    title = _string_or_none(raw.get("title"))
    theme_code = _string_or_none(raw.get("wellnessThemaCd"))
    return ThemeDataCandidate(
        id=_stable_candidate_id("kto_wellness", content_id or title or "", raw),
        source_family="kto_wellness",
        operation=operation,
        title=title,
        content_id=content_id,
        content_type_id=_string_or_none(raw.get("contentTypeId")),
        address=_join_address(raw.get("baseAddr"), raw.get("detailAddr")),
        tel=_string_or_none(raw.get("tel")),
        image_url=_string_or_none(raw.get("orgImage")),
        thumbnail_url=_string_or_none(raw.get("thumbImage")),
        license_type=_string_or_none(raw.get("cpyrhtDivCd")),
        theme_attributes={"wellness_theme_code": theme_code} if theme_code else {},
        needs_review=["웰니스 테마 정보는 건강 효능이나 치료 효과로 표현하지 마세요."],
        raw=raw,
    )


def _medical_candidate(raw: dict[str, Any], operation: str) -> ThemeDataCandidate:
    content_id = _string_or_none(raw.get("contentId"))
    title = _string_or_none(raw.get("title"))
    return ThemeDataCandidate(
        id=_stable_candidate_id("kto_medical", content_id or title or "", raw),
        source_family="kto_medical",
        operation=operation,
        title=title,
        content_id=content_id,
        content_type_id=_string_or_none(raw.get("contentTypeId")),
        address=_join_address(raw.get("baseAddr"), raw.get("detailAddr")),
        tel=_string_or_none(raw.get("tel")),
        image_url=_string_or_none(raw.get("orgImage")),
        thumbnail_url=_string_or_none(raw.get("thumbImage")),
        license_type=_string_or_none(raw.get("cpyrhtDivCd")),
        theme_attributes={"medical_context": True},
        needs_review=[
            "의료관광 정보는 고위험 근거입니다.",
            "치료, 효능, 안전성, 의료 결과를 단정하지 마세요.",
        ],
        raw=raw,
    )


def _pet_candidate(raw: dict[str, Any], operation: str) -> ThemeDataCandidate:
    content_id = _string_or_none(raw.get("contentid") or raw.get("contentId"))
    title = _string_or_none(raw.get("title"))
    return ThemeDataCandidate(
        id=_stable_candidate_id("kto_pet", content_id or title or "", raw),
        source_family="kto_pet",
        operation=operation,
        title=title,
        content_id=content_id,
        content_type_id=_string_or_none(raw.get("contenttypeid") or raw.get("contentTypeId")),
        address=_join_address(raw.get("addr1"), raw.get("addr2")),
        tel=_string_or_none(raw.get("tel")),
        image_url=_string_or_none(raw.get("firstimage")),
        thumbnail_url=_string_or_none(raw.get("firstimage2")),
        license_type=_string_or_none(raw.get("cpyrhtDivCd")),
        theme_attributes={"pet_tour_candidate": True},
        needs_review=["반려동물 동반 가능 여부와 제한 조건은 운영 전 재확인하세요."],
        raw=raw,
    )


def _audio_candidate(raw: dict[str, Any], operation: str) -> ThemeDataCandidate:
    title = _string_or_none(raw.get("audioTitle") or raw.get("title"))
    script = _string_or_none(raw.get("script"))
    content_id = _string_or_none(raw.get("stid") or raw.get("tid"))
    return ThemeDataCandidate(
        id=_stable_candidate_id("kto_audio", content_id or title or "", raw),
        source_family="kto_audio",
        operation=operation,
        title=title,
        content_id=content_id,
        address=_join_address(raw.get("addr1"), raw.get("addr2")),
        overview=script,
        image_url=_string_or_none(raw.get("imageUrl")),
        thumbnail_url=_string_or_none(raw.get("imageUrl")),
        theme_attributes={
            key: value
            for key, value in {
                "theme_category": _string_or_none(raw.get("themeCategory")),
                "language": _string_or_none(raw.get("langCode")),
                "language_check": _string_or_none(raw.get("langCheck")),
                "audio_title": _string_or_none(raw.get("audioTitle")),
                "audio_url_available": bool(raw.get("audioUrl")),
                "play_time": _string_or_none(raw.get("playTime")),
            }.items()
            if value not in (None, "", False)
        },
        needs_review=["오디오/스토리 소재는 해설 후보이며 실제 제공 언어와 사용 조건을 확인하세요."],
        raw=raw,
    )


def _pet_policy_attributes(raw: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "acmpyNeedMtr": "companion_requirements",
        "relaAcdntRiskMtr": "accident_risk_notes",
        "acmpyTypeCd": "companion_type_code",
        "relaPosesFclty": "related_facilities",
        "relaFrnshPrdlst": "provided_items",
        "etcAcmpyInfo": "other_companion_info",
        "relaPurcPrdlst": "purchase_items",
        "acmpyPsblCpam": "allowed_animals",
        "relaRntlPrdlst": "rental_items",
    }
    return {
        output_key: _string_or_none(raw.get(input_key))
        for input_key, output_key in keys.items()
        if _string_or_none(raw.get(input_key))
    }


def _pet_needs_review(attributes: dict[str, Any]) -> list[str]:
    notes = ["반려동물 동반 조건은 방문 전 운영자 확인이 필요합니다."]
    if not attributes.get("allowed_animals"):
        notes.append("동반 가능한 동물 종류가 명확하지 않습니다.")
    if attributes.get("accident_risk_notes"):
        notes.append("반려동물 관련 사고 대비사항을 운영 체크리스트로 검토하세요.")
    return notes


def _theme_source_metadata(
    *,
    target_item: models.TourismItem | None,
    candidate: ThemeDataCandidate,
    source_item_id: str,
    entity: models.TourismEntity | None,
    visual_asset: models.TourismVisualAsset | None,
    run_id: str | None = None,
) -> dict[str, Any]:
    return with_source_lifecycle_metadata(
        {
            "source": candidate.source_family,
            "source_family": candidate.source_family,
            "source_item_id": source_item_id,
            "title": candidate.title,
            "content_id": target_item.content_id if target_item else None,
            "theme_content_id": candidate.content_id,
            "content_type": "theme",
            "theme_source_family": candidate.source_family,
            "theme_operation": candidate.operation,
            "theme_entity_id": entity.id if entity else None,
            "theme_candidate_count": 1,
            "theme_attributes": candidate.theme_attributes,
            "operating_info": candidate.operating_info,
            "region_code": _item_area_cd(target_item),
            "sigungu_code": _item_signgu_cd(target_item),
            "legacy_area_code": target_item.legacy_area_code if target_item else None,
            "legacy_sigungu_code": target_item.legacy_sigungu_code if target_item else None,
            "ldong_regn_cd": _item_l_dong_regn_cd(target_item),
            "ldong_signgu_cd": _item_l_dong_signgu_cd(target_item),
            "address": candidate.address,
            "linked_target_title": target_item.title if target_item else None,
            "linked_target_address": target_item.address if target_item else None,
            "theme_match_signals": candidate.raw.get("theme_match_signals") if isinstance(candidate.raw, dict) else None,
            "image_url": candidate.image_url,
            "thumbnail_url": candidate.thumbnail_url,
            "visual_asset_id": visual_asset.id if visual_asset else None,
            "visual_asset_count": 1 if visual_asset else 0,
            "usage_status": "theme_candidate",
            "needs_review": True,
            "needs_review_notes": candidate.needs_review or _default_theme_review_notes(candidate.source_family),
            "data_quality_flags": _theme_data_quality_flags(candidate),
            "interpretation_notes": _theme_interpretation_notes(candidate.source_family),
            "retrieved_at": now_kst_naive().isoformat(),
            "trust_level": 0.55 if candidate.source_family != "kto_medical" else 0.35,
        },
        source_role=SOURCE_ROLE_ENRICHMENT,
        ingestion_method="theme_api_enrichment",
        run_id=run_id,
        detail_enriched=True,
    )


def _theme_source_content(target_item: models.TourismItem | None, candidate: ThemeDataCandidate) -> str:
    attributes = "; ".join(
        f"{key}: {value}"
        for key, value in (candidate.theme_attributes or {}).items()
        if value not in (None, "")
    )
    return "\n".join(
        part
        for part in [
            f"테마 후보: {candidate.title or ''}",
            f"연결 관광지: {target_item.title if target_item else ''}",
            f"출처 종류: {candidate.source_family}",
            f"작업: {candidate.operation}",
            f"후보 주소: {candidate.address or ''}",
            f"연결 관광지 주소: {target_item.address if target_item else ''}",
            f"문의: {candidate.tel or ''}",
            f"개요/스토리: {_truncate_text(candidate.overview, 800)}",
            f"테마 속성: {attributes}",
            f"이미지 후보: {candidate.image_url or ''}",
            f"사용권/확인: {'; '.join(candidate.needs_review or _default_theme_review_notes(candidate.source_family))}",
        ]
        if part.strip()
    )


def _log_theme_tool_call(
    *,
    db: Session,
    run_id: str | None,
    step_id: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    source: str,
    call,
) -> list[ThemeDataCandidate]:
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
    body = data.get("response", {}).get("body")
    if not isinstance(body, dict):
        body = data.get("body")
    if not isinstance(body, dict):
        return []
    items = body.get("items") or {}
    if not isinstance(items, dict):
        return []
    item = items.get("item", [])
    if isinstance(item, dict):
        return [item]
    if isinstance(item, list):
        return [entry for entry in item if isinstance(entry, dict)]
    return []


def _response_header(data: dict[str, Any]) -> dict[str, Any]:
    header = data.get("response", {}).get("header")
    if isinstance(header, dict):
        return header
    header = data.get("header")
    if isinstance(header, dict):
        return header
    return {}


def _upsert_source_document(db: Session, payload: dict[str, Any]) -> models.SourceDocument:
    existing = db.get(models.SourceDocument, payload["id"])
    if existing:
        payload["document_metadata"] = merge_source_lifecycle_metadata(
            existing.document_metadata if isinstance(existing.document_metadata, dict) else {},
            payload["document_metadata"],
            source_role=SOURCE_ROLE_ENRICHMENT,
            ingestion_method="theme_api_enrichment",
        )
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.updated_at = models.utcnow()
        document = existing
    else:
        document = models.SourceDocument(**payload)
        db.add(document)
    return document


def _theme_query(plan_call: dict[str, Any], target_item: models.TourismItem | None, *, source_family: str) -> str:
    arguments = plan_call.get("arguments") if isinstance(plan_call.get("arguments"), dict) else {}
    query = _string_or_none(arguments.get("query") or arguments.get("keyword"))
    if target_item and target_item.title and _should_use_target_title_for_theme_query(
        query,
        target_item.title,
        source_family,
    ):
        return target_item.title
    if query:
        return query
    if target_item and target_item.title:
        return target_item.title
    return _string_or_none(plan_call.get("target_content_id")) or "관광"


def _should_use_target_title_for_theme_query(query: str | None, target_title: str, source_family: str) -> bool:
    if not query:
        return False
    normalized_query = _normalize_match_text(query)
    normalized_title = _normalize_match_text(target_title)
    if normalized_title and normalized_title in normalized_query:
        return False
    if any(token in normalized_query for token in _target_title_tokens(target_title)):
        return False
    return _contains_family_generic_signal(query, source_family)


def _contains_family_generic_signal(query: str | None, source_family: str) -> bool:
    normalized = _normalize_match_text(query)
    if not normalized:
        return False
    generic_terms = {
        "kto_audio": {
            "audio",
            "audioguide",
            "story",
            "storytelling",
            "guide",
            "오디오",
            "오디오가이드",
            "오디오관광",
            "오디오해설",
            "스토리",
            "스토리소재",
            "스토리텔링",
            "해설",
            "음성",
            "음성가이드",
            "관광해설",
        },
        "kto_pet": {
            "pet",
            "pets",
            "dog",
            "반려동물",
            "반려견",
            "펫",
            "동반",
            "반려동물동반",
            "반려견동반",
            "펫동반",
        },
        "kto_wellness": {
            "wellness",
            "healing",
            "웰니스",
            "힐링",
            "휴식",
            "치유",
            "건강",
        },
        "kto_medical": {
            "medical",
            "meditour",
            "의료",
            "의료관광",
            "메디컬",
            "병원",
        },
    }
    family_terms = generic_terms.get(source_family, set())
    normalized_terms = {_normalize_match_text(term) for term in family_terms if term}
    return normalized in normalized_terms or any(term and term in normalized for term in normalized_terms)


def _theme_data_quality_flags(candidate: ThemeDataCandidate) -> list[str]:
    flags = ["theme_candidate", "needs_operational_review"]
    if candidate.image_url:
        flags.append("needs_license_review")
    if candidate.source_family == "kto_medical":
        flags.append("high_risk_medical_context")
    if candidate.source_family == "kto_wellness":
        flags.append("wellness_claims_restricted")
    return flags


def _theme_interpretation_notes(source_family: str) -> list[str]:
    return {
        "kto_wellness": ["웰니스 테마 후보입니다. 건강 효능이나 치료 효과를 확정 claim으로 쓰지 않습니다."],
        "kto_pet": ["반려동물 동반 조건 후보입니다. 실제 동반 가능 여부와 제한 조건은 운영 전 확인합니다."],
        "kto_audio": ["오디오/스토리 소재 후보입니다. 실제 제공 언어와 사용 조건은 확인 필요입니다."],
        "kto_medical": ["의료관광 고위험 근거입니다. 의료 효과, 안전, 치료 결과를 확정 표현하지 않습니다."],
    }.get(source_family, ["테마 보조 근거입니다. 운영자 확인이 필요합니다."])


def _default_theme_review_notes(source_family: str) -> list[str]:
    return _theme_interpretation_notes(source_family)


def _stable_candidate_id(source_family: str, source_id: str, raw: dict[str, Any]) -> str:
    return f"theme_candidate:{source_family}:{_stable_digest(source_id, raw)}"


def _stable_theme_entity_id(candidate: ThemeDataCandidate, target_item: models.TourismItem | None) -> str:
    linked = target_item.content_id if target_item else "regional"
    return f"entity:theme:{candidate.source_family}:{_stable_digest(linked, candidate.content_id, candidate.id)}"


def _stable_theme_visual_asset_id(candidate: ThemeDataCandidate, target_item: models.TourismItem | None) -> str:
    linked = target_item.content_id if target_item else "regional"
    return f"visual:theme:{candidate.source_family}:{_stable_digest(linked, candidate.content_id, candidate.image_url)}"


def _stable_digest(*values: Any) -> str:
    serialized = "|".join(str(value or "") for value in values)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()[:16]


def _item_area_cd(item: models.TourismItem | None) -> str | None:
    if not item:
        return None
    return _string_or_none(item.legacy_area_code or item.region_code)


def _item_signgu_cd(item: models.TourismItem | None) -> str | None:
    if not item:
        return None
    return _string_or_none(item.legacy_sigungu_code or item.sigungu_code)


def _item_l_dong_regn_cd(item: models.TourismItem | None) -> str | None:
    if not item:
        return None
    return _string_or_none(item.ldong_regn_cd)


def _item_l_dong_signgu_cd(item: models.TourismItem | None) -> str | None:
    if not item:
        return None
    return _string_or_none(item.ldong_signgu_cd)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _join_address(*values: Any) -> str | None:
    return " ".join(value for value in (_string_or_none(value) for value in values) if value) or None


def _decimal_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
