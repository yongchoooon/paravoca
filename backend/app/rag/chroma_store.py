from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import chromadb
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import models

VECTOR_DIM = 128


def embed_text(text: str) -> list[float]:
    vector = [0.0] * VECTOR_DIM
    tokens = [token for token in text.lower().replace("\n", " ").split(" ") if token]
    if not tokens:
        tokens = ["empty"]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % VECTOR_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def get_collection():
    settings = get_settings()
    path = Path(settings.chroma_path)
    path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(path))
    return client.get_or_create_collection(
        name="source_documents",
        metadata={"hnsw:space": "cosine"},
    )


def index_source_documents(db: Session, documents: list[models.SourceDocument]) -> int:
    if not documents:
        return 0
    collection = get_collection()
    collection.upsert(
        ids=[document.id for document in documents],
        documents=[document.content for document in documents],
        metadatas=[_clean_metadata(document.document_metadata) for document in documents],
        embeddings=[embed_text(document.content) for document in documents],
    )
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
    collection = get_collection()
    count = collection.count()
    if count == 0:
        return []

    requested = min(max(top_k * 3, top_k), count)
    result = collection.query(
        query_embeddings=[embed_text(query)],
        n_results=requested,
        include=["documents", "metadatas", "distances"],
    )
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
            cleaned[key] = str(value)
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

