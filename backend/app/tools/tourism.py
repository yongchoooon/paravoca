from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Protocol

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models


@dataclass
class TourismItem:
    id: str
    source: str
    content_id: str
    content_type: str
    title: str
    region_code: str
    sigungu_code: str | None = None
    address: str | None = None
    map_x: float | None = None
    map_y: float | None = None
    tel: str | None = None
    homepage: str | None = None
    overview: str | None = None
    image_url: str | None = None
    license_type: str | None = None
    event_start_date: str | None = None
    event_end_date: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TourismDataProvider(Protocol):
    def area_code(self, region: str | None = None) -> list[dict[str, Any]]:
        ...

    def area_based_list(
        self,
        *,
        region_code: str | None = None,
        content_type: str | None = None,
        keyword: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        ...

    def search_keyword(
        self,
        *,
        query: str,
        region_code: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        ...

    def search_festival(
        self,
        *,
        region_code: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        ...

    def search_stay(
        self,
        *,
        region_code: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        ...


class TourApiProvider:
    def __init__(self, service_key: str | None = None) -> None:
        settings = get_settings()
        self.service_key = service_key or settings.tourapi_service_key
        self.base_url = settings.tourapi_base_url

    def area_code(self, region: str | None = None) -> list[dict[str, Any]]:
        data = self._get("areaCode2", {"numOfRows": 50})
        items = _extract_response_items(data)
        if not region:
            return items
        return [item for item in items if region in str(item.get("name", ""))]

    def area_based_list(
        self,
        *,
        region_code: str | None = None,
        content_type: str | None = None,
        keyword: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        params: dict[str, Any] = {"numOfRows": limit, "areaCode": region_code}
        if content_type:
            params["contentTypeId"] = content_type
        data = self._get("areaBasedList2", params)
        return [_tourapi_raw_to_item(item) for item in _extract_response_items(data)]

    def search_keyword(
        self,
        *,
        query: str,
        region_code: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        params: dict[str, Any] = {"numOfRows": limit, "keyword": query, "areaCode": region_code}
        data = self._get("searchKeyword2", params)
        return [_tourapi_raw_to_item(item) for item in _extract_response_items(data)]

    def search_festival(
        self,
        *,
        region_code: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        params: dict[str, Any] = {
            "numOfRows": limit,
            "areaCode": region_code,
            "eventStartDate": start_date.strftime("%Y%m%d") if start_date else None,
        }
        data = self._get("searchFestival2", params)
        return [_tourapi_raw_to_item(item, content_type="event") for item in _extract_response_items(data)]

    def search_stay(
        self,
        *,
        region_code: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        params: dict[str, Any] = {"numOfRows": limit, "areaCode": region_code}
        data = self._get("searchStay2", params)
        return [
            _tourapi_raw_to_item(item, content_type="accommodation")
            for item in _extract_response_items(data)
        ]

    def _get(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.service_key:
            raise RuntimeError("TOURAPI_SERVICE_KEY is required for TourApiProvider")
        clean_params = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": "TravelOpsAX",
            "_type": "json",
            **{key: value for key, value in params.items() if value is not None},
        }
        response = httpx.get(f"{self.base_url}/{operation}", params=clean_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        header = data.get("response", {}).get("header", {})
        result_code = str(header.get("resultCode", ""))
        if result_code and result_code != "0000":
            result_message = header.get("resultMsg") or "Unknown TourAPI error"
            raise RuntimeError(
                f"TourAPI {operation} failed with resultCode={result_code}: {result_message}"
            )
        return data


def get_tourism_provider() -> TourismDataProvider:
    return TourApiProvider()


def log_tool_call(
    *,
    db: Session,
    run_id: str | None,
    step_id: str | None = None,
    tool_name: str,
    arguments: dict[str, Any],
    source: str,
    call,
):
    started = time.perf_counter()
    tool_call = None
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
        latency_ms = int((time.perf_counter() - started) * 1000)
        response_summary = _summarize_tool_result(result)
        if tool_call:
            tool_call.status = "succeeded"
            tool_call.response_summary = response_summary
            tool_call.latency_ms = latency_ms
            db.commit()
        return result
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        if tool_call:
            tool_call.status = "failed"
            tool_call.error = {"type": exc.__class__.__name__, "message": str(exc)}
            tool_call.latency_ms = latency_ms
            db.commit()
        raise


def upsert_tourism_items(db: Session, items: list[TourismItem]) -> None:
    for item in items:
        existing = db.get(models.TourismItem, item.id)
        payload = item.to_dict()
        if existing:
            _apply_item_payload(existing, payload)
        else:
            db.add(models.TourismItem(**payload))
    db.commit()


def _apply_item_payload(model: models.TourismItem, payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        setattr(model, key, value)
    model.last_synced_at = models.utcnow()
    model.updated_at = models.utcnow()


def _summarize_tool_result(result: Any) -> dict[str, Any]:
    if isinstance(result, list):
        return {
            "count": len(result),
            "titles": [
                getattr(item, "title", None) or item.get("title")
                for item in result[:5]
                if item is not None
            ],
        }
    return {"type": type(result).__name__}


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


def _tourapi_raw_to_item(raw: dict[str, Any], content_type: str | None = None) -> TourismItem:
    content_id = str(raw.get("contentid", ""))
    content_type_id = str(raw.get("contenttypeid", ""))
    normalized_type = content_type or _content_type_from_id(content_type_id)
    return TourismItem(
        id=f"tourapi:content:{content_id}",
        source="tourapi",
        content_id=content_id,
        content_type=normalized_type,
        title=str(raw.get("title", "")),
        region_code=str(raw.get("areacode", "")),
        sigungu_code=str(raw.get("sigungucode")) if raw.get("sigungucode") is not None else None,
        address=raw.get("addr1"),
        map_x=_float_or_none(raw.get("mapx")),
        map_y=_float_or_none(raw.get("mapy")),
        tel=raw.get("tel"),
        homepage=raw.get("homepage"),
        overview=raw.get("overview"),
        image_url=raw.get("firstimage") or raw.get("firstimage2"),
        license_type="공공데이터포털/TourAPI 이용조건 확인 필요",
        event_start_date=_normalize_yyyymmdd(raw.get("eventstartdate")),
        event_end_date=_normalize_yyyymmdd(raw.get("eventenddate")),
        raw=raw,
    )


def _content_type_from_id(content_type_id: str) -> str:
    return {
        "12": "attraction",
        "14": "culture",
        "15": "event",
        "25": "course",
        "28": "leisure",
        "32": "accommodation",
        "38": "shopping",
        "39": "restaurant",
    }.get(content_type_id, "attraction")


def _normalize_yyyymmdd(value: Any) -> str | None:
    text = str(value or "")
    if len(text) != 8:
        return None
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
