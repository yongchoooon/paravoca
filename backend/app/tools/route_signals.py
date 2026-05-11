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


KTO_DURUNUBI_BASE_URL = "https://apis.data.go.kr/B551011/Durunubi"
KTO_RELATED_PLACES_BASE_URL = "https://apis.data.go.kr/B551011/TarRlteTarService1"
KTO_TOURISM_BIGDATA_BASE_URL = "https://apis.data.go.kr/B551011/DataLabService"
KTO_CROWDING_FORECAST_BASE_URL = "https://apis.data.go.kr/B551011/TatsCnctrRateService"
KTO_REGIONAL_TOURISM_DEMAND_BASE_URL = "https://apis.data.go.kr/B551011/AreaTarResDemService"


@dataclass
class RouteAssetCandidate:
    id: str
    source_family: str
    operation: str
    course_name: str | None = None
    path_name: str | None = None
    gpx_url: str | None = None
    distance_km: float | None = None
    estimated_duration: str | None = None
    start_point: str | None = None
    end_point: str | None = None
    nearby_places: list[dict[str, Any]] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SignalRecordCandidate:
    id: str
    source_family: str
    operation: str
    signal_type: str
    region_code: str | None = None
    sigungu_code: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    value: dict[str, Any] = field(default_factory=dict)
    interpretation_note: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RouteSignalProvider(Protocol):
    def search_durunubi_courses(self, *, keyword: str, limit: int = 5) -> list[RouteAssetCandidate]:
        ...

    def search_related_places(
        self,
        *,
        keyword: str | None = None,
        area_cd: str | None = None,
        signgu_cd: str | None = None,
        base_ym: str | None = None,
        limit: int = 5,
    ) -> list[SignalRecordCandidate]:
        ...

    def search_tourism_bigdata_visitors(
        self,
        *,
        area_cd: str | None = None,
        signgu_cd: str | None = None,
        base_ymd: str | None = None,
        limit: int = 5,
    ) -> list[SignalRecordCandidate]:
        ...

    def search_crowding_forecast(
        self,
        *,
        keyword: str | None = None,
        area_cd: str | None = None,
        signgu_cd: str | None = None,
        limit: int = 5,
    ) -> list[SignalRecordCandidate]:
        ...

    def search_regional_tourism_demand(
        self,
        *,
        area_cd: str | None = None,
        signgu_cd: str | None = None,
        base_ym: str | None = None,
        limit: int = 5,
    ) -> list[SignalRecordCandidate]:
        ...


class KtoRouteSignalProvider:
    def __init__(self, settings: Settings | None = None, service_key: str | None = None) -> None:
        self.settings = settings or get_settings()
        self.service_key = service_key or self.settings.tourapi_service_key

    def search_durunubi_courses(self, *, keyword: str, limit: int = 5) -> list[RouteAssetCandidate]:
        if not self.settings.kto_durunubi_enabled:
            raise RuntimeError("KTO_DURUNUBI_ENABLED is false")
        data = self._get(
            base_url=KTO_DURUNUBI_BASE_URL,
            operation="courseList",
            params={"crsKorNm": keyword, "numOfRows": limit, "pageNo": 1},
        )
        return [_durunubi_course_candidate(raw) for raw in _extract_response_items(data)]

    def search_related_places(
        self,
        *,
        keyword: str | None = None,
        area_cd: str | None = None,
        signgu_cd: str | None = None,
        base_ym: str | None = None,
        limit: int = 5,
    ) -> list[SignalRecordCandidate]:
        if not self.settings.kto_related_places_enabled:
            raise RuntimeError("KTO_RELATED_PLACES_ENABLED is false")
        operation = "searchKeyword1" if keyword else "areaBasedList1"
        data = self._get(
            base_url=KTO_RELATED_PLACES_BASE_URL,
            operation=operation,
            params={
                "keyword": keyword,
                "baseYm": base_ym or "202503",
                "areaCd": area_cd,
                "signguCd": signgu_cd,
                "numOfRows": limit,
                "pageNo": 1,
            },
        )
        return [_related_place_candidate(raw, operation=operation) for raw in _extract_response_items(data)]

    def search_tourism_bigdata_visitors(
        self,
        *,
        area_cd: str | None = None,
        signgu_cd: str | None = None,
        base_ymd: str | None = None,
        limit: int = 5,
    ) -> list[SignalRecordCandidate]:
        if not self.settings.kto_bigdata_enabled:
            raise RuntimeError("KTO_BIGDATA_ENABLED is false")
        operation = "locgoRegnVisitrDDList" if signgu_cd else "metcoRegnVisitrDDList"
        data = self._get(
            base_url=KTO_TOURISM_BIGDATA_BASE_URL,
            operation=operation,
            params={
                "areaCode": area_cd,
                "signguCode": signgu_cd,
                "startYmd": base_ymd or "20210513",
                "endYmd": base_ymd or "20210513",
                "numOfRows": limit,
                "pageNo": 1,
            },
        )
        return [_bigdata_signal_candidate(raw, operation=operation) for raw in _extract_response_items(data)]

    def search_crowding_forecast(
        self,
        *,
        keyword: str | None = None,
        area_cd: str | None = None,
        signgu_cd: str | None = None,
        limit: int = 5,
    ) -> list[SignalRecordCandidate]:
        if not self.settings.kto_crowding_enabled:
            raise RuntimeError("KTO_CROWDING_ENABLED is false")
        data = self._get(
            base_url=KTO_CROWDING_FORECAST_BASE_URL,
            operation="tatsCnctrRatedList",
            params={
                "keyword": keyword,
                "areaCd": area_cd,
                "signguCd": signgu_cd,
                "numOfRows": limit,
                "pageNo": 1,
            },
        )
        return [_crowding_signal_candidate(raw) for raw in _extract_response_items(data)]

    def search_regional_tourism_demand(
        self,
        *,
        area_cd: str | None = None,
        signgu_cd: str | None = None,
        base_ym: str | None = None,
        limit: int = 5,
    ) -> list[SignalRecordCandidate]:
        if not self.settings.kto_regional_tourism_demand_enabled:
            raise RuntimeError("KTO_REGIONAL_TOURISM_DEMAND_ENABLED is false")
        candidates: list[SignalRecordCandidate] = []
        for operation in ["areaTarSvcDemList", "areaCulResDemList"]:
            data = self._get(
                base_url=KTO_REGIONAL_TOURISM_DEMAND_BASE_URL,
                operation=operation,
                params={
                    "areaCd": area_cd,
                    "signguCd": signgu_cd,
                    "baseYm": base_ym or "202509",
                    "numOfRows": limit,
                    "pageNo": 1,
                },
            )
            candidates.extend(
                _regional_demand_candidate(raw, operation=operation)
                for raw in _extract_response_items(data)
            )
        return candidates[:limit]

    def _get(self, *, base_url: str, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.service_key:
            raise RuntimeError("TOURAPI_SERVICE_KEY is required for route/signal KTO providers")
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
                f"KTO route/signal API {operation} HTTP {exc.response.status_code}"
            ) from exc
        data = response.json()
        top_level_code = str(data.get("resultCode", ""))
        if top_level_code and top_level_code != "0000":
            raise RuntimeError(
                f"KTO route/signal API {operation} failed with resultCode={top_level_code}: "
                f"{data.get('resultMsg') or 'Unknown error'}"
            )
        header = data.get("response", {}).get("header", {})
        result_code = str(header.get("resultCode", ""))
        if result_code and result_code != "0000":
            raise RuntimeError(
                f"KTO route/signal API {operation} failed with resultCode={result_code}: "
                f"{header.get('resultMsg') or 'Unknown error'}"
            )
        return data


def get_route_signal_provider() -> RouteSignalProvider:
    return KtoRouteSignalProvider()


def execute_route_signal_search(
    *,
    db: Session,
    provider: RouteSignalProvider,
    plan_call: dict[str, Any],
    target_item: models.TourismItem | None,
    fallback_source_item_id: str | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
) -> dict[str, Any]:
    arguments = plan_call.get("arguments") if isinstance(plan_call.get("arguments"), dict) else {}
    source_family = str(plan_call.get("source_family") or "")
    query = _route_signal_query(plan_call, target_item)
    limit = int(arguments.get("limit") or arguments.get("numOfRows") or 5)
    area_cd = _string_or_none(arguments.get("area_cd") or arguments.get("areaCode") or _item_area_cd(target_item))
    signgu_cd = _string_or_none(arguments.get("signgu_cd") or arguments.get("signguCode") or _item_signgu_cd(target_item))
    started = time.perf_counter()
    route_candidates: list[RouteAssetCandidate] = []
    signal_candidates: list[SignalRecordCandidate] = []

    if source_family == "kto_durunubi":
        route_candidates = _log_route_signal_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_durunubi_course_list",
            source=source_family,
            arguments={"keyword": query, "limit": limit},
            call=lambda: provider.search_durunubi_courses(keyword=query, limit=limit),
        )
    elif source_family == "kto_related_places":
        signal_candidates = _log_route_signal_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name=str(plan_call.get("tool_name") or "kto_related_places_keyword"),
            source=source_family,
            arguments={"keyword": query, "area_cd": area_cd, "signgu_cd": signgu_cd, "limit": limit},
            call=lambda: provider.search_related_places(
                keyword=query,
                area_cd=area_cd,
                signgu_cd=signgu_cd,
                base_ym=_string_or_none(arguments.get("base_ym")),
                limit=limit,
            ),
        )
    elif source_family == "kto_tourism_bigdata":
        signal_candidates = _log_route_signal_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_tourism_bigdata_locgo_visitors" if signgu_cd else "kto_tourism_bigdata_metco_visitors",
            source=source_family,
            arguments={
                "area_cd": area_cd,
                "signgu_cd": signgu_cd,
                "base_ymd": arguments.get("base_ymd"),
                "limit": limit,
            },
            call=lambda: provider.search_tourism_bigdata_visitors(
                area_cd=area_cd,
                signgu_cd=signgu_cd,
                base_ymd=_string_or_none(arguments.get("base_ymd")),
                limit=limit,
            ),
        )
    elif source_family == "kto_crowding_forecast":
        signal_candidates = _log_route_signal_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_attraction_crowding_forecast",
            source=source_family,
            arguments={"keyword": query, "area_cd": area_cd, "signgu_cd": signgu_cd, "limit": limit},
            call=lambda: provider.search_crowding_forecast(
                keyword=query,
                area_cd=area_cd,
                signgu_cd=signgu_cd,
                limit=limit,
            ),
        )
    elif source_family == "kto_regional_tourism_demand":
        signal_candidates = _log_route_signal_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_regional_tourism_demand_area",
            source=source_family,
            arguments={
                "area_cd": area_cd,
                "signgu_cd": signgu_cd,
                "base_ym": arguments.get("base_ym"),
                "limit": limit,
            },
            call=lambda: provider.search_regional_tourism_demand(
                area_cd=area_cd,
                signgu_cd=signgu_cd,
                base_ym=_string_or_none(arguments.get("base_ym")),
                limit=limit,
            ),
        )
    else:
        raise ValueError(f"Unsupported route/signal source_family: {source_family}")

    route_assets = upsert_route_asset_candidates(
        db=db,
        target_item=target_item,
        candidates=route_candidates,
    )
    signal_records = upsert_signal_record_candidates(
        db=db,
        target_item=target_item,
        fallback_region_code=area_cd,
        fallback_sigungu_code=signgu_cd,
        candidates=signal_candidates,
    )
    documents = [
        *upsert_source_documents_from_route_assets(
            db=db,
            target_item=target_item,
            fallback_source_item_id=fallback_source_item_id or str(plan_call.get("id") or "route_signal"),
            assets=route_assets,
        ),
        *upsert_source_documents_from_signal_records(
            db=db,
            target_item=target_item,
            fallback_source_item_id=fallback_source_item_id or str(plan_call.get("id") or "route_signal"),
            records=signal_records,
        ),
    ]
    indexed = index_source_documents(db, documents) if documents else 0
    return {
        "source_family": source_family,
        "operation": plan_call.get("operation"),
        "query": query,
        "route_candidates_found": len(route_candidates),
        "signal_candidates_found": len(signal_candidates),
        "route_assets": len(route_assets),
        "signal_records": len(signal_records),
        "source_documents": len(documents),
        "indexed_documents": indexed,
        "usage_status": "supporting_signal" if route_assets or signal_records else "unavailable",
        "reason": plan_call.get("reason"),
        "expected_ui": plan_call.get("expected_ui"),
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def upsert_route_asset_candidates(
    *,
    db: Session,
    target_item: models.TourismItem | None,
    candidates: list[RouteAssetCandidate],
) -> list[models.TourismRouteAsset]:
    entity = upsert_tourism_entity(db, target_item) if target_item else None
    assets: list[models.TourismRouteAsset] = []
    for candidate in candidates:
        asset_id = _stable_route_asset_id(
            candidate.source_family,
            target_item.content_id if target_item else "regional",
            candidate.id,
        )
        raw = dict(candidate.raw or {})
        raw.update(
            {
                "provider_operation": candidate.operation,
                "linked_content_id": target_item.content_id if target_item else None,
                "linked_source_item_id": target_item.id if target_item else None,
                "usage_status": "supporting_route_candidate",
            }
        )
        payload = {
            "id": asset_id,
            "entity_id": entity.id if entity else None,
            "source_family": candidate.source_family,
            "course_name": candidate.course_name,
            "path_name": candidate.path_name,
            "gpx_url": candidate.gpx_url,
            "distance_km": candidate.distance_km,
            "estimated_duration": candidate.estimated_duration,
            "start_point": candidate.start_point,
            "end_point": candidate.end_point,
            "nearby_places": candidate.nearby_places,
            "safety_notes": candidate.safety_notes
            or ["코스/동선 정보는 보조 근거입니다. 실제 운영 전 안전, 날씨, 집결/해산 지점 확인이 필요합니다."],
            "raw": raw,
            "retrieved_at": models.utcnow(),
        }
        existing = db.get(models.TourismRouteAsset, asset_id)
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            db.add(existing)
            assets.append(existing)
            continue
        asset = models.TourismRouteAsset(**payload)
        db.add(asset)
        assets.append(asset)
    db.commit()
    for asset in assets:
        db.refresh(asset)
    return assets


def upsert_signal_record_candidates(
    *,
    db: Session,
    target_item: models.TourismItem | None,
    fallback_region_code: str | None,
    fallback_sigungu_code: str | None,
    candidates: list[SignalRecordCandidate],
) -> list[models.TourismSignalRecord]:
    entity = upsert_tourism_entity(db, target_item) if target_item else None
    records: list[models.TourismSignalRecord] = []
    for candidate in candidates:
        record_id = _stable_signal_record_id(
            candidate.source_family,
            target_item.content_id if target_item else "regional",
            candidate.id,
        )
        raw = dict(candidate.raw or {})
        raw.update(
            {
                "provider_operation": candidate.operation,
                "linked_content_id": target_item.content_id if target_item else None,
                "linked_source_item_id": target_item.id if target_item else None,
                "usage_status": "supporting_signal",
            }
        )
        payload = {
            "id": record_id,
            "entity_id": entity.id if entity else None,
            "region_code": candidate.region_code or _item_area_cd(target_item) or fallback_region_code,
            "sigungu_code": candidate.sigungu_code or _item_signgu_cd(target_item) or fallback_sigungu_code,
            "source_family": candidate.source_family,
            "signal_type": candidate.signal_type,
            "period_start": candidate.period_start,
            "period_end": candidate.period_end,
            "value": candidate.value,
            "interpretation_note": candidate.interpretation_note
            or "수요/혼잡/연관성은 상품화 판단 보조 신호이며 예약, 판매량, 안전을 보장하지 않습니다.",
            "raw": raw,
            "retrieved_at": models.utcnow(),
        }
        existing = db.get(models.TourismSignalRecord, record_id)
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            db.add(existing)
            records.append(existing)
            continue
        record = models.TourismSignalRecord(**payload)
        db.add(record)
        records.append(record)
    db.commit()
    for record in records:
        db.refresh(record)
    return records


def upsert_source_documents_from_route_assets(
    *,
    db: Session,
    target_item: models.TourismItem | None,
    fallback_source_item_id: str,
    assets: list[models.TourismRouteAsset],
) -> list[models.SourceDocument]:
    documents: list[models.SourceDocument] = []
    source_item_id = target_item.id if target_item else fallback_source_item_id
    for asset in assets:
        metadata = _route_source_metadata(target_item, asset, source_item_id)
        payload = {
            "id": f"doc:{asset.id}",
            "source": asset.source_family,
            "source_item_id": source_item_id,
            "title": asset.course_name or asset.path_name or (target_item.title if target_item else "동선 후보"),
            "content": _route_source_content(target_item, asset),
            "document_metadata": metadata,
            "embedding_status": "pending",
        }
        documents.append(_upsert_source_document(db, payload))
    db.commit()
    for document in documents:
        db.refresh(document)
    return documents


def upsert_source_documents_from_signal_records(
    *,
    db: Session,
    target_item: models.TourismItem | None,
    fallback_source_item_id: str,
    records: list[models.TourismSignalRecord],
) -> list[models.SourceDocument]:
    documents: list[models.SourceDocument] = []
    source_item_id = target_item.id if target_item else fallback_source_item_id
    for record in records:
        metadata = _signal_source_metadata(target_item, record, source_item_id)
        payload = {
            "id": f"doc:{record.id}",
            "source": record.source_family,
            "source_item_id": source_item_id,
            "title": _signal_title(target_item, record),
            "content": _signal_source_content(target_item, record),
            "document_metadata": metadata,
            "embedding_status": "pending",
        }
        documents.append(_upsert_source_document(db, payload))
    db.commit()
    for document in documents:
        db.refresh(document)
    return documents


def _upsert_source_document(db: Session, payload: dict[str, Any]) -> models.SourceDocument:
    existing = db.get(models.SourceDocument, payload["id"])
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.updated_at = models.utcnow()
        document = existing
    else:
        document = models.SourceDocument(**payload)
        db.add(document)
    return document


def _durunubi_course_candidate(raw: dict[str, Any]) -> RouteAssetCandidate:
    course_name = _string_or_none(raw.get("crsKorNm") or raw.get("themeNm"))
    route_idx = _string_or_none(raw.get("routeIdx") or raw.get("crsIdx"))
    return RouteAssetCandidate(
        id=_stable_candidate_id("kto_durunubi", route_idx or course_name or "", raw),
        source_family="kto_durunubi",
        operation="courseList",
        course_name=course_name,
        path_name=_string_or_none(raw.get("themeNm") or raw.get("linemsg")),
        gpx_url=_string_or_none(raw.get("gpxpath")),
        distance_km=_distance_to_km(raw.get("crsDstnc")),
        estimated_duration=_string_or_none(raw.get("crsTotlRqrmHour")),
        nearby_places=[
            {"name": value}
            for value in _dedupe_texts([raw.get("sigun"), raw.get("crsTourInfo")])
            if value
        ],
        safety_notes=[
            note
            for note in [
                _string_or_none(raw.get("crsLevel")) and f"난이도: {raw.get('crsLevel')}",
                _string_or_none(raw.get("travelerinfo")),
            ]
            if note
        ],
        raw=raw,
    )


def _related_place_candidate(raw: dict[str, Any], *, operation: str) -> SignalRecordCandidate:
    target = _string_or_none(raw.get("tAtsNm"))
    related = _string_or_none(raw.get("rlteTatsNm"))
    rank = _string_or_none(raw.get("rlteRank"))
    value = {
        "target_place": target,
        "related_place": related,
        "related_rank": rank,
        "category": " > ".join(
            part
            for part in [
                _string_or_none(raw.get("rlteCtgryLclsNm")),
                _string_or_none(raw.get("rlteCtgryMclsNm")),
                _string_or_none(raw.get("rlteCtgrySclsNm")),
            ]
            if part
        ),
        "related_region": " ".join(
            part
            for part in [_string_or_none(raw.get("rlteRegnNm")), _string_or_none(raw.get("rlteSignguNm"))]
            if part
        ),
    }
    return SignalRecordCandidate(
        id=_stable_candidate_id("kto_related_places", f"{target}:{related}:{rank}", raw),
        source_family="kto_related_places",
        operation=operation,
        signal_type="related_places",
        region_code=_string_or_none(raw.get("areaCd")),
        sigungu_code=_string_or_none(raw.get("signguCd")),
        period_start=_string_or_none(raw.get("baseYm")),
        period_end=_string_or_none(raw.get("baseYm")),
        value=value,
        interpretation_note="연관 관광지 순위는 코스 확장 후보를 찾는 보조 신호이며 실제 이동 가능성을 보장하지 않습니다.",
        raw=raw,
    )


def _bigdata_signal_candidate(raw: dict[str, Any], *, operation: str) -> SignalRecordCandidate:
    return SignalRecordCandidate(
        id=_stable_candidate_id("kto_tourism_bigdata", f"{raw.get('baseYmd')}:{raw.get('areaCode')}:{raw.get('signguCode')}:{raw.get('touDivCd')}", raw),
        source_family="kto_tourism_bigdata",
        operation=operation,
        signal_type="visitor_demand",
        region_code=_string_or_none(raw.get("areaCode")),
        sigungu_code=_string_or_none(raw.get("signguCode")),
        period_start=_string_or_none(raw.get("baseYmd")),
        period_end=_string_or_none(raw.get("baseYmd")),
        value={
            "visitor_count": _string_or_none(raw.get("touNum")),
            "visitor_type": _string_or_none(raw.get("touDivNm")),
            "weekday": _string_or_none(raw.get("daywkDivNm")),
            "area_name": _string_or_none(raw.get("areaNm") or raw.get("signguNm")),
        },
        interpretation_note="방문자 수는 지역 수요 보조 신호이며 판매량, 예약 가능성, 실제 방문객 구성을 보장하지 않습니다.",
        raw=raw,
    )


def _crowding_signal_candidate(raw: dict[str, Any]) -> SignalRecordCandidate:
    return SignalRecordCandidate(
        id=_stable_candidate_id("kto_crowding_forecast", f"{raw.get('baseYmd')}:{raw.get('tAtsNm')}", raw),
        source_family="kto_crowding_forecast",
        operation="tatsCnctrRatedList",
        signal_type="crowding_forecast",
        region_code=_string_or_none(raw.get("areaCd")),
        sigungu_code=_string_or_none(raw.get("signguCd")),
        period_start=_string_or_none(raw.get("baseYmd")),
        period_end=_string_or_none(raw.get("baseYmd")),
        value={
            "attraction_name": _string_or_none(raw.get("tAtsNm")),
            "crowding_rate": _string_or_none(raw.get("cnctrRate")),
            "area_name": " ".join(
                part
                for part in [_string_or_none(raw.get("areaNm")), _string_or_none(raw.get("signguNm"))]
                if part
            ),
        },
        interpretation_note="집중률은 예측 기반 보조 지표이며 실제 현장 혼잡이나 안전을 보장하지 않습니다.",
        raw=raw,
    )


def _regional_demand_candidate(raw: dict[str, Any], *, operation: str) -> SignalRecordCandidate:
    if operation == "areaTarSvcDemList":
        signal_type = "regional_service_demand"
        value = {
            "index_code": _string_or_none(raw.get("tarSvcDemIxCd")),
            "index_name": _string_or_none(raw.get("tarSvcDemIxNm")),
            "index_value": _string_or_none(raw.get("tarSvcDemIxVal")),
        }
    else:
        signal_type = "regional_culture_resource_demand"
        value = {
            "index_code": _string_or_none(raw.get("culResDemIxCd")),
            "index_name": _string_or_none(raw.get("culResDemIxNm")),
            "index_value": _string_or_none(raw.get("culResDemIxVal")),
        }
    value["area_name"] = " ".join(
        part
        for part in [_string_or_none(raw.get("areaNm")), _string_or_none(raw.get("signguNm"))]
        if part
    )
    return SignalRecordCandidate(
        id=_stable_candidate_id("kto_regional_tourism_demand", f"{operation}:{raw.get('baseYm')}:{value}", raw),
        source_family="kto_regional_tourism_demand",
        operation=operation,
        signal_type=signal_type,
        region_code=_string_or_none(raw.get("areaCd")),
        sigungu_code=_string_or_none(raw.get("signguCd")),
        period_start=_string_or_none(raw.get("baseYm")),
        period_end=_string_or_none(raw.get("baseYm")),
        value=value,
        interpretation_note="지역 관광수요 지수는 상품 ranking 보조 신호이며 예약/판매 가능성을 보장하지 않습니다.",
        raw=raw,
    )


def _route_source_metadata(
    target_item: models.TourismItem | None,
    asset: models.TourismRouteAsset,
    source_item_id: str,
) -> dict[str, Any]:
    return {
        "source": asset.source_family,
        "source_family": asset.source_family,
        "source_item_id": source_item_id,
        "title": asset.course_name or asset.path_name,
        "content_id": target_item.content_id if target_item else None,
        "content_type": "route",
        "region_code": _item_area_cd(target_item),
        "sigungu_code": _item_signgu_cd(target_item),
        "legacy_area_code": target_item.legacy_area_code if target_item else None,
        "legacy_sigungu_code": target_item.legacy_sigungu_code if target_item else None,
        "ldong_regn_cd": target_item.ldong_regn_cd if target_item else None,
        "ldong_signgu_cd": target_item.ldong_signgu_cd if target_item else None,
        "address": target_item.address if target_item else None,
        "route_asset_id": asset.id,
        "route_asset_count": 1,
        "course_name": asset.course_name,
        "distance_km": float(asset.distance_km) if asset.distance_km is not None else None,
        "estimated_duration": asset.estimated_duration,
        "gpx_url": asset.gpx_url,
        "safety_notes": asset.safety_notes,
        "needs_review": True,
        "data_quality_flags": ["route_candidate", "needs_operational_review"],
        "interpretation_notes": ["동선 후보이며 실제 운영 전 안전, 날씨, 이동 조건 확인이 필요합니다."],
        "retrieved_at": (asset.retrieved_at or now_kst_naive()).isoformat(),
        "trust_level": 0.62,
    }


def _signal_source_metadata(
    target_item: models.TourismItem | None,
    record: models.TourismSignalRecord,
    source_item_id: str,
) -> dict[str, Any]:
    return {
        "source": record.source_family,
        "source_family": record.source_family,
        "source_item_id": source_item_id,
        "title": _signal_title(target_item, record),
        "content_id": target_item.content_id if target_item else None,
        "content_type": "signal",
        "region_code": record.region_code,
        "sigungu_code": record.sigungu_code,
        "legacy_area_code": target_item.legacy_area_code if target_item else None,
        "legacy_sigungu_code": target_item.legacy_sigungu_code if target_item else None,
        "ldong_regn_cd": target_item.ldong_regn_cd if target_item else None,
        "ldong_signgu_cd": target_item.ldong_signgu_cd if target_item else None,
        "signal_record_id": record.id,
        "signal_record_count": 1,
        "signal_type": record.signal_type,
        "period_start": record.period_start,
        "period_end": record.period_end,
        "signal_value": record.value,
        "interpretation_note": record.interpretation_note,
        "needs_review": True,
        "data_quality_flags": ["supporting_signal", "no_sales_or_safety_guarantee"],
        "interpretation_notes": [record.interpretation_note or "보조 신호입니다."],
        "retrieved_at": (record.retrieved_at or now_kst_naive()).isoformat(),
        "trust_level": 0.58,
    }


def _route_source_content(target_item: models.TourismItem | None, asset: models.TourismRouteAsset) -> str:
    return "\n".join(
        part
        for part in [
            f"동선 후보: {asset.course_name or asset.path_name or ''}",
            f"연결 관광지: {target_item.title if target_item else '지역 단위 신호'}",
            f"출처 종류: {asset.source_family}",
            f"거리: {asset.distance_km or ''}",
            f"예상 소요: {asset.estimated_duration or ''}",
            f"GPX: {asset.gpx_url or ''}",
            f"안전/검토 메모: {' / '.join(asset.safety_notes or [])}",
        ]
        if part.strip()
    )


def _signal_source_content(target_item: models.TourismItem | None, record: models.TourismSignalRecord) -> str:
    value_lines = [
        f"{key}: {value}"
        for key, value in (record.value or {}).items()
        if value not in (None, "", [])
    ]
    return "\n".join(
        part
        for part in [
            f"보조 신호: {record.signal_type}",
            f"연결 관광지: {target_item.title if target_item else '지역 단위 신호'}",
            f"출처 종류: {record.source_family}",
            f"기간: {record.period_start or ''}~{record.period_end or ''}",
            *value_lines,
            f"해석 메모: {record.interpretation_note or ''}",
        ]
        if str(part).strip()
    )


def _route_signal_query(plan_call: dict[str, Any], target_item: models.TourismItem | None) -> str:
    arguments = plan_call.get("arguments") if isinstance(plan_call.get("arguments"), dict) else {}
    query = _string_or_none(arguments.get("query") or arguments.get("keyword"))
    if query:
        return query
    if target_item and target_item.title:
        return str(target_item.title)
    if target_item and target_item.address:
        return str(target_item.address)
    return _string_or_none(plan_call.get("reason")) or "관광"


def _log_route_signal_tool_call(
    *,
    db: Session,
    run_id: str | None,
    step_id: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    source: str,
    call,
) -> list[Any]:
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
                "items": [
                    getattr(candidate, "course_name", None)
                    or getattr(candidate, "signal_type", None)
                    for candidate in result[:5]
                ],
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


def _signal_title(target_item: models.TourismItem | None, record: models.TourismSignalRecord) -> str:
    base = target_item.title if target_item else "지역 관광 신호"
    return f"{base} - {record.signal_type}"


def _item_area_cd(target_item: models.TourismItem | None) -> str | None:
    if not target_item:
        return None
    return target_item.ldong_regn_cd or target_item.region_code or target_item.legacy_area_code


def _item_signgu_cd(target_item: models.TourismItem | None) -> str | None:
    if not target_item:
        return None
    if target_item.ldong_regn_cd and target_item.ldong_signgu_cd:
        signgu = str(target_item.ldong_signgu_cd)
        return signgu if signgu.startswith(str(target_item.ldong_regn_cd)) else f"{target_item.ldong_regn_cd}{signgu}"
    return target_item.sigungu_code or target_item.legacy_sigungu_code


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


def _distance_to_km(value: Any) -> float | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    cleaned = text.replace(",", "").replace("km", "").replace("㎞", "").strip()
    try:
        return float(cleaned)
    except ValueError:
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


def _stable_candidate_id(source_family: str, source_id: str, raw: dict[str, Any]) -> str:
    basis = source_id or str(sorted(raw.items()))
    digest = hashlib.sha1(f"{source_family}:{basis}".encode("utf-8")).hexdigest()[:16]
    return f"route_signal_candidate:{source_family}:{digest}"


def _stable_route_asset_id(source_family: str, content_id: str, source_id: str) -> str:
    digest = hashlib.sha1(f"{source_family}:{content_id}:{source_id}".encode("utf-8")).hexdigest()[:16]
    return f"route:{source_family}:{content_id}:{digest}"


def _stable_signal_record_id(source_family: str, content_id: str, source_id: str) -> str:
    digest = hashlib.sha1(f"{source_family}:{content_id}:{source_id}".encode("utf-8")).hexdigest()[:16]
    return f"signal:{source_family}:{content_id}:{digest}"


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
