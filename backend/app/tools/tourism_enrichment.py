from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.core.timezone import now_kst_naive
from app.db import models
from app.tools.tourism import (
    TourismDataProvider,
    TourismItem,
    content_type_to_tourapi_id,
    tourapi_id_to_content_type,
    log_tool_call,
)


def enrich_items_with_tourapi_details(
    *,
    db: Session,
    provider: TourismDataProvider,
    items: list[TourismItem | models.TourismItem],
    run_id: str | None = None,
    step_id: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    selected_items = [item for item in items if item.content_id][:limit]
    enriched_items: list[models.TourismItem] = []
    entities: list[models.TourismEntity] = []
    visual_assets: list[models.TourismVisualAsset] = []

    for item in selected_items:
        content_id = item.content_id
        content_type_id = content_type_to_tourapi_id(item.content_type, getattr(item, "raw", {}))

        detail_common = log_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_tour_detail_common",
            arguments={"content_id": content_id},
            source="tourapi",
            call=lambda content_id=content_id: provider.detail_common(content_id=content_id),
        )
        content_type_id = str(detail_common.get("contenttypeid") or content_type_id)

        detail_intro = log_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_tour_detail_intro",
            arguments={"content_id": content_id, "content_type_id": content_type_id},
            source="tourapi",
            call=lambda content_id=content_id, content_type_id=content_type_id: provider.detail_intro(
                content_id=content_id,
                content_type_id=content_type_id,
            ),
        )
        detail_info = log_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_tour_detail_info",
            arguments={"content_id": content_id, "content_type_id": content_type_id},
            source="tourapi",
            call=lambda content_id=content_id, content_type_id=content_type_id: provider.detail_info(
                content_id=content_id,
                content_type_id=content_type_id,
            ),
        )
        detail_images = log_tool_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            tool_name="kto_tour_detail_image",
            arguments={"content_id": content_id},
            source="tourapi",
            call=lambda content_id=content_id: provider.detail_images(content_id=content_id),
        )

        enriched_item = upsert_enriched_tourism_item(
            db=db,
            item=item,
            detail_common=detail_common,
            detail_intro=detail_intro,
            detail_info=detail_info,
            detail_images=detail_images,
        )
        entity = upsert_tourism_entity(db, enriched_item)
        assets = upsert_detail_image_assets(
            db=db,
            entity=entity,
            item=enriched_item,
            detail_images=detail_images,
        )
        enriched_items.append(enriched_item)
        entities.append(entity)
        visual_assets.extend(assets)

    db.commit()
    return {
        "items": enriched_items,
        "entities": entities,
        "visual_assets": visual_assets,
        "summary": {
            "enriched_items": len(enriched_items),
            "entities": len(entities),
            "visual_assets": len(visual_assets),
        },
    }


def upsert_enriched_tourism_item(
    *,
    db: Session,
    item: TourismItem | models.TourismItem,
    detail_common: dict[str, Any],
    detail_intro: dict[str, Any],
    detail_info: list[dict[str, Any]],
    detail_images: list[dict[str, Any]],
) -> models.TourismItem:
    raw = dict(getattr(item, "raw", {}) or {})
    raw["detail_common"] = detail_common
    raw["detail_intro"] = detail_intro
    raw["detail_info"] = detail_info
    raw["detail_images"] = detail_images
    raw["detail_enriched_at"] = now_kst_naive().isoformat()

    payload = {
        "id": item.id,
        "source": item.source,
        "content_id": str(detail_common.get("contentid") or item.content_id),
        "content_type": tourapi_id_to_content_type(detail_common.get("contenttypeid"))
        if detail_common.get("contenttypeid")
        else item.content_type,
        "title": str(detail_common.get("title") or item.title),
        "region_code": str(detail_common.get("areacode") or item.region_code or ""),
        "sigungu_code": _string_or_none(detail_common.get("sigungucode") or item.sigungu_code),
        "address": _join_address(detail_common.get("addr1"), detail_common.get("addr2"))
        or item.address,
        "map_x": _float_or_none(detail_common.get("mapx")) or item.map_x,
        "map_y": _float_or_none(detail_common.get("mapy")) or item.map_y,
        "tel": detail_common.get("tel") or item.tel,
        "homepage": detail_common.get("homepage") or item.homepage,
        "overview": detail_common.get("overview") or item.overview,
        "image_url": detail_common.get("firstimage")
        or detail_common.get("firstimage2")
        or _first_detail_image_url(detail_images)
        or item.image_url,
        "license_type": item.license_type or "공공데이터포털/TourAPI 이용조건 확인 필요",
        "event_start_date": getattr(item, "event_start_date", None),
        "event_end_date": getattr(item, "event_end_date", None),
        "raw": raw,
    }

    existing = db.get(models.TourismItem, item.id)
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.last_synced_at = models.utcnow()
        existing.updated_at = models.utcnow()
        db.add(existing)
        db.flush()
        return existing

    model = models.TourismItem(**payload)
    db.add(model)
    db.flush()
    return model


def upsert_tourism_entity(
    db: Session,
    item: models.TourismItem,
) -> models.TourismEntity:
    entity_id = f"entity:tourapi:content:{item.content_id}"
    metadata = {
        "source_family": "kto_tourapi_kor",
        "content_id": item.content_id,
        "content_type": item.content_type,
        "source_item_id": item.id,
        "detail_enriched": bool((item.raw or {}).get("detail_common")),
        "updated_from": "detailCommon2",
    }
    existing = db.get(models.TourismEntity, entity_id)
    payload = {
        "id": entity_id,
        "canonical_name": item.title,
        "entity_type": item.content_type,
        "region_code": item.region_code,
        "sigungu_code": item.sigungu_code,
        "address": item.address,
        "map_x": item.map_x,
        "map_y": item.map_y,
        "primary_source_item_id": item.id,
        "match_confidence": 1.0,
        "entity_metadata": metadata,
    }
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.updated_at = models.utcnow()
        db.add(existing)
        db.flush()
        return existing

    entity = models.TourismEntity(**payload)
    db.add(entity)
    db.flush()
    return entity


def upsert_detail_image_assets(
    *,
    db: Session,
    entity: models.TourismEntity,
    item: models.TourismItem,
    detail_images: list[dict[str, Any]],
) -> list[models.TourismVisualAsset]:
    assets: list[models.TourismVisualAsset] = []
    for index, raw in enumerate(detail_images):
        image_url = raw.get("originimgurl") or raw.get("smallimageurl") or raw.get("imageurl")
        if not image_url:
            continue
        serial = raw.get("serialnum") or raw.get("cpyrhtDivCd") or index
        asset_id = _stable_visual_asset_id(item.content_id, str(serial), str(image_url))
        payload = {
            "id": asset_id,
            "entity_id": entity.id,
            "source_family": "kto_tourapi_kor",
            "source_item_id": item.id,
            "title": raw.get("imgname") or item.title,
            "image_url": str(image_url),
            "thumbnail_url": raw.get("smallimageurl") or raw.get("originimgurl"),
            "shooting_place": item.address,
            "shooting_date": None,
            "photographer": None,
            "keywords": [item.title, item.content_type, item.region_code],
            "license_type": item.license_type,
            "license_note": "detailImage2 응답 기준입니다. 게시 전 공공데이터 이용 조건과 원 출처를 확인하세요.",
            "usage_status": "candidate",
            "raw": raw,
            "retrieved_at": models.utcnow(),
        }
        existing = db.get(models.TourismVisualAsset, asset_id)
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            db.add(existing)
            assets.append(existing)
        else:
            asset = models.TourismVisualAsset(**payload)
            db.add(asset)
            assets.append(asset)
    db.flush()
    return assets


def detail_info_to_lines(detail_info: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in detail_info:
        name = str(row.get("infoname") or row.get("name") or "").strip()
        text = _clean_htmlish_text(row.get("infotext") or row.get("text") or "")
        if name and text:
            lines.append(f"{name}: {text}")
        elif text:
            lines.append(text)
    return lines


def detail_intro_to_lines(detail_intro: dict[str, Any]) -> list[str]:
    excluded = {"contentid", "contenttypeid", "serialnum", "createdtime", "modifiedtime"}
    lines: list[str] = []
    for key, value in detail_intro.items():
        if key in excluded or value in (None, ""):
            continue
        text = _clean_htmlish_text(value)
        if text:
            lines.append(f"{_detail_intro_label(key)}: {text}")
    return lines


def image_candidates_from_item(item: TourismItem | models.TourismItem) -> list[dict[str, Any]]:
    raw = dict(getattr(item, "raw", {}) or {})
    candidates: list[dict[str, Any]] = []
    if getattr(item, "image_url", None):
        candidates.append(
            {
                "image_url": item.image_url,
                "thumbnail_url": item.image_url,
                "title": item.title,
                "usage_status": "candidate",
                "source": "detail_common",
            }
        )
    for image in raw.get("detail_images") or []:
        image_url = image.get("originimgurl") or image.get("smallimageurl") or image.get("imageurl")
        if not image_url:
            continue
        candidates.append(
            {
                "image_url": image_url,
                "thumbnail_url": image.get("smallimageurl") or image_url,
                "title": image.get("imgname") or item.title,
                "usage_status": "candidate",
                "source": "detailImage2",
            }
        )
    return _dedupe_image_candidates(candidates)


def _stable_visual_asset_id(content_id: str, serial: str, image_url: str) -> str:
    digest = hashlib.sha1(f"{content_id}:{serial}:{image_url}".encode("utf-8")).hexdigest()[:16]
    return f"visual:tourapi:{content_id}:{digest}"


def _first_detail_image_url(detail_images: list[dict[str, Any]]) -> str | None:
    for raw in detail_images:
        image_url = raw.get("originimgurl") or raw.get("smallimageurl") or raw.get("imageurl")
        if image_url:
            return str(image_url)
    return None


def _dedupe_image_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for candidate in candidates:
        image_url = str(candidate.get("image_url") or "")
        if not image_url or image_url in seen:
            continue
        seen.add(image_url)
        deduped.append(candidate)
    return deduped


def _string_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _join_address(addr1: Any, addr2: Any) -> str | None:
    parts = [str(part).strip() for part in [addr1, addr2] if str(part or "").strip()]
    return " ".join(parts) if parts else None


def _clean_htmlish_text(value: Any) -> str:
    text = str(value or "")
    return (
        text.replace("<br>", " ")
        .replace("<br/>", " ")
        .replace("<br />", " ")
        .replace("&nbsp;", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _detail_intro_label(key: str) -> str:
    return {
        "sponsor1": "주최",
        "sponsor1tel": "주최 문의",
        "sponsor2": "주관",
        "sponsor2tel": "주관 문의",
        "eventstartdate": "행사 시작일",
        "eventenddate": "행사 종료일",
        "playtime": "공연/운영 시간",
        "eventplace": "행사 장소",
        "eventhomepage": "행사 홈페이지",
        "agelimit": "연령 제한",
        "bookingplace": "예약 안내",
        "placeinfo": "장소 안내",
        "subevent": "부대 행사",
        "program": "프로그램",
        "usetime": "이용 시간",
        "infocenter": "문의처",
        "restdate": "쉬는 날",
        "parking": "주차",
        "chkbabycarriage": "유모차 대여",
        "chkpet": "반려동물 동반",
        "chkcreditcard": "신용카드",
        "expagerange": "체험 가능 연령",
        "expguide": "체험 안내",
        "heritage1": "세계문화유산",
        "heritage2": "세계자연유산",
        "heritage3": "세계기록유산",
        "accomcount": "수용 인원",
        "checkintime": "체크인",
        "checkouttime": "체크아웃",
        "roomtype": "객실 유형",
        "foodplace": "식음 시설",
        "pickup": "픽업",
        "reservationlodging": "숙박 예약",
        "reservationurl": "예약 URL",
        "scalelodging": "숙박 규모",
        "subfacility": "부대 시설",
        "barbecue": "바비큐",
        "beauty": "뷰티 시설",
        "beverage": "식음료",
        "bicycle": "자전거 대여",
        "campfire": "캠프파이어",
        "fitness": "피트니스",
        "karaoke": "노래방",
        "publicbath": "공용 목욕",
        "publicpc": "공용 PC",
        "sauna": "사우나",
        "seminar": "세미나실",
        "sports": "스포츠 시설",
        "refundregulation": "환불 규정",
    }.get(key, key)
