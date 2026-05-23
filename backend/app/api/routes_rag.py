from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.responses import ok
from app.db import models
from app.db.session import get_db
from app.rag.chroma_store import index_source_documents, search_source_documents_with_diagnostics
from app.rag.source_documents import SOURCE_ROLE_EXISTING, upsert_source_documents_from_items
from app.schemas.rag import RagSearchRequest

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/ingest/tourism")
def ingest_tourism_items(db: Session = Depends(get_db)) -> dict:
    items = db.query(models.TourismItem).all()
    source_documents = upsert_source_documents_from_items(
        db,
        items,
        source_role=SOURCE_ROLE_EXISTING,
        ingestion_method="rag_ingest_existing_tourism_items",
    )
    indexed_count = index_source_documents(db, source_documents)
    return ok(
        {
            "source_documents": len(source_documents),
            "indexed_documents": indexed_count,
        }
    )


@router.post("/search")
def rag_search(payload: RagSearchRequest) -> dict:
    result = search_source_documents_with_diagnostics(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
        search_context=payload.search_context,
    )
    rows = result["results"]
    return ok(
        {
            "results": rows,
            "retrieval_diagnostics": result["retrieval_diagnostics"],
        },
        count=len(rows),
    )
