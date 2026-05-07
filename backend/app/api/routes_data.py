from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.responses import ok
from app.db import models
from app.db.session import get_db
from app.schemas.tourism import (
    TourismDetailEnrichmentRequest,
    TourismDetailEnrichmentResult,
    TourismEntityRead,
    TourismItemRead,
    TourismVisualAssetRead,
)
from app.rag.chroma_store import index_source_documents
from app.rag.source_documents import upsert_source_documents_from_items
from app.tools.tourism import (
    TourismItem,
    get_tourism_provider,
    log_tool_call,
    upsert_tourism_items,
)
from app.tools.tourism_enrichment import enrich_items_with_tourapi_details

router = APIRouter(prefix="/data/tourism", tags=["tourism-data"])


@router.get("/search")
def search_tourism(
    region: str | None = Query(default=None),
    region_code: str | None = Query(default=None),
    ldong_regn_cd: str | None = Query(default=None),
    ldong_signgu_cd: str | None = Query(default=None),
    lcls_systm_1: str | None = Query(default=None),
    lcls_systm_2: str | None = Query(default=None),
    lcls_systm_3: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    run_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    enrich_details: bool = Query(default=False),
    detail_limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> dict:
    provider = get_tourism_provider()
    provider_name = "tourapi"
    resolved_region_code = region_code
    if not ldong_regn_cd:
        resolved_region_code = region_code or _resolve_region_code(
            provider=provider,
            db=db,
            run_id=run_id,
            region=region,
            source=provider_name,
        )
    geo_kwargs = {
        "ldong_regn_cd": ldong_regn_cd,
        "ldong_signgu_cd": ldong_signgu_cd,
        "lcls_systm_1": lcls_systm_1,
        "lcls_systm_2": lcls_systm_2,
        "lcls_systm_3": lcls_systm_3,
    }

    tool_name = _select_tool_name(content_type=content_type, keyword=keyword)
    arguments = {
        "region": region,
        "region_code": resolved_region_code,
        **geo_kwargs,
        "keyword": keyword,
        "content_type": content_type,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "limit": limit,
    }

    def call_provider():
        if content_type == "event":
            return provider.search_festival(
                region_code=resolved_region_code,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                **geo_kwargs,
            )
        if content_type == "accommodation":
            return provider.search_stay(
                region_code=resolved_region_code,
                limit=limit,
                **geo_kwargs,
            )
        if keyword:
            return provider.search_keyword(
                query=keyword,
                region_code=resolved_region_code,
                limit=limit,
                **geo_kwargs,
            )
        return provider.area_based_list(
            region_code=resolved_region_code,
            content_type=content_type,
            limit=limit,
            **geo_kwargs,
        )

    items = log_tool_call(
        db=db,
        run_id=run_id,
        tool_name=tool_name,
        arguments=arguments,
        source=provider_name,
        call=call_provider,
    )
    upsert_tourism_items(db, items)
    detail_enrichment = None
    if enrich_details and items:
        detail_enrichment = enrich_items_with_tourapi_details(
            db=db,
            provider=provider,
            items=items,
            run_id=run_id,
            limit=min(detail_limit, len(items)),
        )
        items = detail_enrichment["items"]
    source_documents = upsert_source_documents_from_items(db, items)
    indexed_count = index_source_documents(db, source_documents)
    data = [TourismItemRead.model_validate(item).model_dump(mode="json") for item in items]
    return ok(
        {
            "provider": provider_name,
            "region_code": resolved_region_code,
            "ldong_regn_cd": ldong_regn_cd,
            "ldong_signgu_cd": ldong_signgu_cd,
            "lcls_systm_1": lcls_systm_1,
            "lcls_systm_2": lcls_systm_2,
            "lcls_systm_3": lcls_systm_3,
            "items": data,
            "source_documents": len(source_documents),
            "indexed_documents": indexed_count,
            "detail_enrichment": _detail_enrichment_summary(detail_enrichment),
        },
        count=len(data),
    )


@router.post("/details/enrich")
def enrich_tourism_details(
    payload: TourismDetailEnrichmentRequest,
    db: Session = Depends(get_db),
) -> dict:
    items = _load_items_for_detail_enrichment(db, payload)
    if not items:
        raise HTTPException(status_code=404, detail="No tourism items found for detail enrichment")

    provider = get_tourism_provider()
    result = enrich_items_with_tourapi_details(
        db=db,
        provider=provider,
        items=items,
        run_id=payload.run_id,
        limit=payload.limit,
    )
    source_documents = upsert_source_documents_from_items(db, result["items"])
    indexed_count = index_source_documents(db, source_documents)
    response = TourismDetailEnrichmentResult(
        items=[TourismItemRead.model_validate(item) for item in result["items"]],
        entities=[TourismEntityRead.model_validate(entity) for entity in result["entities"]],
        visual_assets=[
            TourismVisualAssetRead.model_validate(asset)
            for asset in result["visual_assets"]
        ],
        source_documents=len(source_documents),
        indexed_documents=indexed_count,
        summary=result["summary"],
    )
    return ok(response.model_dump(mode="json"), count=len(response.items))


def _resolve_region_code(
    *,
    provider,
    db: Session,
    run_id: str | None,
    region: str | None,
    source: str,
) -> str | None:
    if not region:
        return None

    regions = log_tool_call(
        db=db,
        run_id=run_id,
        tool_name="tourapi_area_code",
        arguments={"region": region},
        source=source,
        call=lambda: provider.area_code(region),
    )
    if not regions:
        return None
    first = regions[0]
    return str(first.get("region_code") or first.get("code") or first.get("areaCode") or "")


def _select_tool_name(content_type: str | None, keyword: str | None) -> str:
    if content_type == "event":
        return "tourapi_search_festival"
    if content_type == "accommodation":
        return "tourapi_search_stay"
    if keyword:
        return "tourapi_search_keyword"
    return "tourapi_area_based_list"


def _load_items_for_detail_enrichment(
    db: Session,
    payload: TourismDetailEnrichmentRequest,
) -> list[models.TourismItem | TourismItem]:
    query = db.query(models.TourismItem)
    if payload.item_ids:
        return query.filter(models.TourismItem.id.in_(payload.item_ids)).limit(payload.limit).all()
    if payload.content_ids:
        existing = (
            query.filter(models.TourismItem.content_id.in_(payload.content_ids))
            .limit(payload.limit)
            .all()
        )
        existing_content_ids = {item.content_id for item in existing}
        placeholders = [
            TourismItem(
                id=f"tourapi:content:{content_id}",
                source="tourapi",
                content_id=content_id,
                content_type="attraction",
                title=content_id,
                region_code="",
            )
            for content_id in payload.content_ids[: payload.limit]
            if content_id not in existing_content_ids
        ]
        return [*existing, *placeholders][: payload.limit]
    return query.order_by(models.TourismItem.updated_at.desc()).limit(payload.limit).all()


def _detail_enrichment_summary(result: dict | None) -> dict:
    if not result:
        return {
            "enabled": False,
            "enriched_items": 0,
            "entities": 0,
            "visual_assets": 0,
        }
    return {
        "enabled": True,
        **result.get("summary", {}),
    }
