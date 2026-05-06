from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.responses import ok
from app.db import models
from app.db.session import get_db
from app.rag.chroma_store import index_source_documents, search_source_documents
from app.rag.source_documents import upsert_source_documents_from_items
from app.schemas.rag import RagSearchRequest

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/ingest/tourism")
def ingest_tourism_items(db: Session = Depends(get_db)) -> dict:
    items = db.query(models.TourismItem).all()
    source_documents = upsert_source_documents_from_items(db, items)
    indexed_count = index_source_documents(db, source_documents)
    return ok(
        {
            "source_documents": len(source_documents),
            "indexed_documents": indexed_count,
        }
    )


@router.post("/search")
def rag_search(payload: RagSearchRequest) -> dict:
    rows = search_source_documents(
        query=payload.query,
        top_k=payload.top_k,
        filters=payload.filters,
    )
    return ok({"results": rows}, count=len(rows))

