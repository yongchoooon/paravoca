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
from app.rag.source_documents import SOURCE_ROLE_UNKNOWN, normalize_source_role

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
    return search_source_documents_with_diagnostics(
        query=query,
        top_k=top_k,
        filters=filters,
    )["results"]


def search_source_documents_with_diagnostics(
    *,
    query: str,
    top_k: int = 10,
    filters: dict[str, Any] | None = None,
    search_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider = get_embedding_provider()
    filters = filters or {}
    search_context = search_context or {}
    diagnostics: dict[str, Any] = {
        "query": query,
        "filters": filters,
        "top_k": top_k,
        "result_count": 0,
        "fallback_applied": False,
        "scope_expansion_applied": False,
        "reason": None,
    }
    try:
        collection = get_collection()
        count = collection.count()
        if count == 0:
            diagnostics["reason"] = "source_documents_collection_empty"
            return {"results": [], "retrieval_diagnostics": diagnostics}

        requested = min(max(top_k * 3, top_k), count)
        where = _filters_to_chroma_where(filters)
        diagnostics["candidate_count_before_filter"] = count
        diagnostics["requested_chroma_results"] = requested
        result = collection.query(
            query_embeddings=[provider.embed_query(query)],
            n_results=requested,
            where=where,
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
        metadata = metadata or {}
        if not _matches_filters(metadata, filters):
            continue
        score = round(1 - float(distance or 0), 4)
        signals = _matching_signals(
            metadata=metadata,
            document=document,
            query=query,
            filters=filters,
            search_context=search_context,
        )
        role = normalize_source_role(metadata.get("source_role"))
        rows.append(
            {
                "doc_id": doc_id,
                "title": metadata.get("title") or metadata.get("source_item_id"),
                "content": document,
                "snippet": document[:260],
                "score": score,
                "relevance_score": _relevance_score(score, signals, role),
                "matching_signals": signals,
                "source_role": role,
                "metadata": metadata,
            }
        )
    rows.sort(key=lambda row: float(row.get("relevance_score") or 0), reverse=True)
    rows = rows[:top_k]
    diagnostics["result_count"] = len(rows)
    diagnostics["unknown_role_result_count"] = sum(1 for row in rows if row.get("source_role") == SOURCE_ROLE_UNKNOWN)
    diagnostics["matching_signal_summary"] = _matching_signal_summary(rows)
    if not rows:
        diagnostics["reason"] = "no_documents_matched_query_and_filters"
    return {"results": rows, "retrieval_diagnostics": diagnostics}


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


def _matching_signals(
    *,
    metadata: dict[str, Any],
    document: str,
    query: str,
    filters: dict[str, Any],
    search_context: dict[str, Any],
) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    for key, label in [
        ("ldong_regn_cd", "같은 시도 코드와 일치"),
        ("ldong_signgu_cd", "같은 시군구 코드와 일치"),
        ("content_type", "요청한 콘텐츠 유형과 일치"),
        ("source_family", "요청한 데이터 출처와 일치"),
        ("lcls_systm_1", "관광 대분류와 일치"),
        ("lcls_systm_2", "관광 중분류와 일치"),
        ("lcls_systm_3", "관광 소분류와 일치"),
    ]:
        expected = filters.get(key)
        if expected in (None, "", []):
            continue
        actual = metadata.get(key)
        if isinstance(expected, list):
            matched = actual in expected
        else:
            matched = actual == expected
        if matched:
            signals.append({"type": key, "label": label, "value": str(actual)})

    searchable_text = " ".join(
        str(value or "")
        for value in [
            metadata.get("title"),
            metadata.get("address"),
            metadata.get("content_type"),
            metadata.get("source_family"),
            document,
        ]
    )
    for theme in _context_terms(search_context, "preferred_themes"):
        if theme and theme in searchable_text:
            signals.append({"type": "theme_text_match", "label": "요청 theme와 문서 내용이 일치", "value": theme})
    for keyword in _context_terms(search_context, "narrow_keywords"):
        if keyword and keyword in searchable_text:
            signals.append({"type": "narrow_keyword_match", "label": "좁은 지역/관심 keyword가 문서에 포함", "value": keyword})
    target_customer = str(search_context.get("target_customer") or "").strip()
    if target_customer and target_customer in f"{query} {searchable_text}":
        signals.append({"type": "target_customer_query_match", "label": "대상 고객 조건이 검색 문맥에 포함", "value": target_customer})
    role = normalize_source_role(metadata.get("source_role"))
    if role != SOURCE_ROLE_UNKNOWN:
        signals.append({"type": "source_role_known", "label": "근거 문서 역할이 분류됨", "value": role})
    return signals


def _context_terms(search_context: dict[str, Any], key: str) -> list[str]:
    value = search_context.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _relevance_score(score: float, signals: list[dict[str, str]], source_role: str) -> float:
    role_penalty = 0.12 if source_role == SOURCE_ROLE_UNKNOWN else 0.0
    signal_bonus = min(len(signals) * 0.025, 0.2)
    return round(max(0.0, min(1.0, score + signal_bonus - role_penalty)), 4)


def _matching_signal_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for row in rows:
        for signal in row.get("matching_signals") or []:
            signal_type = str(signal.get("type") or "unknown")
            summary[signal_type] = summary.get(signal_type, 0) + 1
    return summary


def _filters_to_chroma_where(filters: dict[str, Any]) -> dict[str, Any] | None:
    clauses: list[dict[str, Any]] = []
    for key, expected in filters.items():
        if expected in (None, "", []):
            continue
        if isinstance(expected, list):
            values = [value for value in expected if value not in (None, "")]
            if not values:
                continue
            clauses.append({key: values[0] if len(values) == 1 else {"$in": values}})
        elif isinstance(expected, (str, int, float, bool)):
            clauses.append({key: expected})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
