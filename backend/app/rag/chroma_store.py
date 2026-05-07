from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import chromadb
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models
from app.rag.embeddings import get_embedding_provider

COLLECTION_NAME = "source_documents"

logger = logging.getLogger("uvicorn.error")


def get_chroma_client():
    settings = get_settings()
    path = Path(settings.chroma_path)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_collection():
    client = get_chroma_client()
    provider = get_embedding_provider()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
            "embedding_provider": provider.name,
            "embedding_model": provider.model,
            "embedding_dimension": provider.dimension,
        },
    )


def delete_source_documents_collection() -> bool:
    client = get_chroma_client()
    try:
        client.delete_collection(COLLECTION_NAME)
        return True
    except Exception as exc:
        if "does not exist" in str(exc).lower():
            return False
        raise


def index_source_documents(db: Session, documents: list[models.SourceDocument]) -> int:
    if not documents:
        return 0
    provider = get_embedding_provider()
    try:
        collection = get_collection()
        embeddings = provider.embed_documents([document.content for document in documents])
        collection.upsert(
            ids=[document.id for document in documents],
            documents=[document.content for document in documents],
            metadatas=[_clean_metadata(document.document_metadata) for document in documents],
            embeddings=embeddings,
        )
    except Exception:
        for document in documents:
            document.embedding_status = "failed"
            document.updated_at = models.utcnow()
        db.commit()
        logger.exception(
            "Source document indexing failed provider=%s model=%s document_ids=%s",
            provider.name,
            provider.model,
            [document.id for document in documents],
        )
        raise
    for document in documents:
        document.embedding_status = "indexed"
        document.updated_at = models.utcnow()
    db.commit()
    return len(documents)


def search_source_documents(
    *,
    query: str,
    top_k: int = 10,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    provider = get_embedding_provider()
    try:
        collection = get_collection()
        count = collection.count()
        if count == 0:
            return []

        requested = min(max(top_k * 3, top_k), count)
        result = collection.query(
            query_embeddings=[provider.embed_query(query)],
            n_results=requested,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        logger.exception(
            "Source document search failed provider=%s model=%s query=%r",
            provider.name,
            provider.model,
            query,
        )
        raise
    rows: list[dict[str, Any]] = []
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        if not _matches_filters(metadata or {}, filters or {}):
            continue
        rows.append(
            {
                "doc_id": doc_id,
                "title": (metadata or {}).get("title") or (metadata or {}).get("source_item_id"),
                "content": document,
                "snippet": document[:260],
                "score": round(1 - float(distance or 0), 4),
                "metadata": metadata or {},
            }
        )
        if len(rows) >= top_k:
            break
    return rows


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    cleaned = {}
    for key, value in metadata.items():
        if value is None:
            cleaned[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = json.dumps(value, ensure_ascii=False)
    if "title" not in cleaned:
        cleaned["title"] = cleaned.get("source_item_id", "")
    return cleaned


def _matches_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if expected in (None, "", []):
            continue
        actual = metadata.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True
