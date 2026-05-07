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

    def detail_common(self, *, content_id: str) -> dict[str, Any]:
        ...

    def detail_intro(
        self,
        *,
        content_id: str,
        content_type_id: str,
    ) -> dict[str, Any]:
        ...

    def detail_info(
        self,
        *,
        content_id: str,
        content_type_id: str,
    ) -> list[dict[str, Any]]:
        ...

    def detail_images(self, *, content_id: str) -> list[dict[str, Any]]:
        ...

    def category_code(
        self,
        *,
        cat1: str | None = None,
        cat2: str | None = None,
        cat3: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        ...

    def location_based_list(
        self,
        *,
        map_x: float,
        map_y: float,
        radius: int = 1000,
        content_type: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        ...


class TourApiProvider:
    source_family = "kto_tourapi_kor"
    operation_names = {
        "area_code": "areaCode2",
        "area_based_list": "areaBasedList2",
        "search_keyword": "searchKeyword2",
        "search_festival": "searchFestival2",
        "search_stay": "searchStay2",
        "detail_common": "detailCommon2",
        "detail_intro": "detailIntro2",
        "detail_info": "detailInfo2",
        "detail_images": "detailImage2",
        "category_code": "categoryCode2",
        "location_based_list": "locationBasedList2",
    }

    def __init__(self, service_key: str | None = None) -> None:
        settings = get_settings()
        self.enabled = settings.tourapi_enabled
        self.service_key = service_key or settings.tourapi_service_key
        self.base_url = settings.tourapi_base_url

    def area_code(self, region: str | None = None) -> list[dict[str, Any]]:
        data = self.request_operation(self.operation_names["area_code"], {"numOfRows": 50})
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
        data = self.request_operation(self.operation_names["area_based_list"], params)
        return [_tourapi_raw_to_item(item) for item in _extract_response_items(data)]

    def search_keyword(
        self,
        *,
        query: str,
        region_code: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        params: dict[str, Any] = {"numOfRows": limit, "keyword": query, "areaCode": region_code}
        data = self.request_operation(self.operation_names["search_keyword"], params)
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
        data = self.request_operation(self.operation_names["search_festival"], params)
        return [_tourapi_raw_to_item(item, content_type="event") for item in _extract_response_items(data)]

    def search_stay(
        self,
        *,
        region_code: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        params: dict[str, Any] = {"numOfRows": limit, "areaCode": region_code}
        data = self.request_operation(self.operation_names["search_stay"], params)
        return [
            _tourapi_raw_to_item(item, content_type="accommodation")
            for item in _extract_response_items(data)
        ]

    def detail_common(self, *, content_id: str) -> dict[str, Any]:
        data = self.request_operation(
            self.operation_names["detail_common"],
            {"contentId": content_id},
        )
        items = _extract_response_items(data)
        return items[0] if items else {}

    def detail_intro(
        self,
        *,
        content_id: str,
        content_type_id: str,
    ) -> dict[str, Any]:
        data = self.request_operation(
            self.operation_names["detail_intro"],
            {
                "contentId": content_id,
                "contentTypeId": content_type_id,
                "numOfRows": 10,
            },
        )
        items = _extract_response_items(data)
        return items[0] if items else {}

    def detail_info(
        self,
        *,
        content_id: str,
        content_type_id: str,
    ) -> list[dict[str, Any]]:
        data = self.request_operation(
            self.operation_names["detail_info"],
            {
                "contentId": content_id,
                "contentTypeId": content_type_id,
                "numOfRows": 100,
            },
        )
        return _extract_response_items(data)

    def detail_images(self, *, content_id: str) -> list[dict[str, Any]]:
        data = self.request_operation(
            self.operation_names["detail_images"],
            {
                "contentId": content_id,
                "imageYN": "Y",
                "numOfRows": 50,
            },
        )
        return _extract_response_items(data)

    def category_code(
        self,
        *,
        cat1: str | None = None,
        cat2: str | None = None,
        cat3: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        data = self.request_operation(
            self.operation_names["category_code"],
            {"cat1": cat1, "cat2": cat2, "cat3": cat3, "numOfRows": limit},
        )
        return _extract_response_items(data)

    def location_based_list(
        self,
        *,
        map_x: float,
        map_y: float,
        radius: int = 1000,
        content_type: str | None = None,
        limit: int = 20,
    ) -> list[TourismItem]:
        params: dict[str, Any] = {
            "mapX": map_x,
            "mapY": map_y,
            "radius": radius,
            "contentTypeId": content_type,
            "numOfRows": limit,
        }
        data = self.request_operation(self.operation_names["location_based_list"], params)
        return [_tourapi_raw_to_item(item) for item in _extract_response_items(data)]

    def request_operation(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._get(operation, params)

    def operation_url(self, operation: str) -> str:
        return f"{self.base_url}/{operation}"

    def _get(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("TOURAPI_ENABLED is false")
        if not self.service_key:
            raise RuntimeError("TOURAPI_SERVICE_KEY is required for TourApiProvider")
        clean_params = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": "PARAVOCAAX",
            "_type": "json",
            **{key: value for key, value in params.items() if value is not None},
        }
        response = httpx.get(self.operation_url(operation), params=clean_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        top_level_code = str(data.get("resultCode", ""))
        if top_level_code and top_level_code != "0000":
            result_message = data.get("resultMsg") or "Unknown TourAPI error"
            raise RuntimeError(
                f"TourAPI {operation} failed with resultCode={top_level_code}: {result_message}"
            )
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
        address=_join_address(raw.get("addr1"), raw.get("addr2")),
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


def content_type_to_tourapi_id(content_type: str | None, raw: dict[str, Any] | None = None) -> str:
    raw_content_type = str((raw or {}).get("contenttypeid") or "")
    if raw_content_type:
        return raw_content_type
    return {
        "attraction": "12",
        "culture": "14",
        "event": "15",
        "course": "25",
        "leisure": "28",
        "accommodation": "32",
        "shopping": "38",
        "restaurant": "39",
    }.get(str(content_type or ""), "12")


def tourapi_id_to_content_type(content_type_id: str | None) -> str:
    return _content_type_from_id(str(content_type_id or ""))


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


def _join_address(addr1: Any, addr2: Any) -> str | None:
    parts = [str(part).strip() for part in [addr1, addr2] if str(part or "").strip()]
    return " ".join(parts) if parts else None
