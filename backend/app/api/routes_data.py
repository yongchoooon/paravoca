from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.responses import ok
from app.db.session import get_db
from app.schemas.tourism import TourismItemRead
from app.rag.chroma_store import index_source_documents
from app.rag.source_documents import upsert_source_documents_from_items
from app.tools.tourism import (
    get_tourism_provider,
    log_tool_call,
    upsert_tourism_items,
)

router = APIRouter(prefix="/data/tourism", tags=["tourism-data"])


@router.get("/search")
def search_tourism(
    region: str | None = Query(default=None),
    region_code: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    run_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    provider = get_tourism_provider()
    provider_name = "tourapi"
    resolved_region_code = region_code or _resolve_region_code(
        provider=provider,
        db=db,
        run_id=run_id,
        region=region,
        source=provider_name,
    )

    tool_name = _select_tool_name(content_type=content_type, keyword=keyword)
    arguments = {
        "region": region,
        "region_code": resolved_region_code,
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
            )
        if content_type == "accommodation":
            return provider.search_stay(region_code=resolved_region_code, limit=limit)
        if keyword:
            return provider.search_keyword(
                query=keyword,
                region_code=resolved_region_code,
                limit=limit,
            )
        return provider.area_based_list(
            region_code=resolved_region_code,
            content_type=content_type,
            limit=limit,
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
    source_documents = upsert_source_documents_from_items(db, items)
    indexed_count = index_source_documents(db, source_documents)
    data = [TourismItemRead.model_validate(item).model_dump(mode="json") for item in items]
    return ok(
        {
            "provider": provider_name,
            "region_code": resolved_region_code,
            "items": data,
            "source_documents": len(source_documents),
            "indexed_documents": indexed_count,
        },
        count=len(data),
    )


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
