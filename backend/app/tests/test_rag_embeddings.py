from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal
from app.rag import chroma_store
from app.rag.chroma_store import (
    delete_source_documents_collection,
    index_source_documents,
    search_source_documents,
)
from app.rag.embeddings import clear_embedding_provider_cache, get_embedding_provider


def reset_embedding_settings_cache() -> None:
    get_settings.cache_clear()
    clear_embedding_provider_cache()


def test_legacy_hash_embedding_provider_is_available():
    reset_embedding_settings_cache()

    provider = get_embedding_provider()
    vector = provider.embed_query("부산 야경 관광")

    assert provider.name == "legacy_hash"
    assert provider.model == "legacy_hash_128"
    assert provider.dimension == 128
    assert len(vector) == 128
    assert sum(value * value for value in vector) > 0


def test_local_embedding_provider_routes_to_sentence_transformer(monkeypatch):
    class FakeSentenceTransformer:
        def get_sentence_embedding_dimension(self):
            return 3

        def encode(
            self,
            texts,
            *,
            batch_size,
            normalize_embeddings,
            convert_to_numpy,
            show_progress_bar,
        ):
            assert batch_size == 7
            assert normalize_embeddings is True
            assert convert_to_numpy is True
            assert show_progress_bar is False
            return [[1.0, 0.0, 0.0] if "부산" in text else [0.0, 1.0, 0.0] for text in texts]

    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_MODEL", "fake-local-model")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "7")
    reset_embedding_settings_cache()
    monkeypatch.setattr(
        "app.rag.embeddings.LocalSentenceTransformerEmbeddingProvider._load_model",
        lambda self: FakeSentenceTransformer(),
    )

    try:
        provider = get_embedding_provider()

        assert provider.name == "local"
        assert provider.model == "fake-local-model"
        assert provider.dimension == 3
        assert provider.embed_documents(["부산 야경", "제주 해변"]) == [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]
    finally:
        reset_embedding_settings_cache()


def test_rag_retrieval_smoke_with_legacy_hash_provider():
    reset_embedding_settings_cache()
    delete_source_documents_collection()

    with SessionLocal() as db:
        docs = [
            models.SourceDocument(
                id="doc:test:phase95:drone",
                source="test",
                source_item_id="phase95:drone",
                title="광안리 드론 라이트쇼",
                content="부산 광안리 야경 드론 라이트쇼 외국인 관광 코스",
                document_metadata={
                    "source": "test",
                    "title": "광안리 드론 라이트쇼",
                    "region_code": "6",
                    "test_case": "phase95",
                },
            ),
            models.SourceDocument(
                id="doc:test:phase95:market",
                source="test",
                source_item_id="phase95:market",
                title="부산 전통시장 미식",
                content="부산 전통시장 먹거리 미식 투어 로컬 음식",
                document_metadata={
                    "source": "test",
                    "title": "부산 전통시장 미식",
                    "region_code": "6",
                    "test_case": "phase95",
                },
            ),
            models.SourceDocument(
                id="doc:test:phase95:beach",
                source="test",
                source_item_id="phase95:beach",
                title="제주 해변 산책",
                content="제주 해변 산책 자연 풍경 휴식 코스",
                document_metadata={
                    "source": "test",
                    "title": "제주 해변 산책",
                    "region_code": "39",
                    "test_case": "phase95",
                },
            ),
        ]
        docs = [db.merge(doc) for doc in docs]
        db.commit()
        for doc in docs:
            db.refresh(doc)

        assert index_source_documents(db, docs) == 3

    rows = search_source_documents(
        query="부산 광안리 야경 드론",
        top_k=3,
        filters={"test_case": "phase95"},
    )

    assert rows
    assert rows[0]["doc_id"] == "doc:test:phase95:drone"
    assert all(row["metadata"]["test_case"] == "phase95" for row in rows)


def test_index_source_documents_marks_failed_when_embedding_fails(monkeypatch):
    class FailingProvider:
        name = "failing"
        model = "failing-model"
        dimension = 3

        def embed_documents(self, texts):
            raise RuntimeError("embedding failed for test")

        def embed_query(self, text):
            return [0.0, 0.0, 0.0]

    monkeypatch.setattr(chroma_store, "get_embedding_provider", lambda: FailingProvider())

    with SessionLocal() as db:
        doc = models.SourceDocument(
            id="doc:test:phase95:failure",
            source="test",
            source_item_id="phase95:failure",
            title="Embedding failure",
            content="이 문서는 실패 상태 테스트용입니다.",
            document_metadata={"source": "test", "title": "Embedding failure"},
        )
        doc = db.merge(doc)
        db.commit()
        db.refresh(doc)

        with pytest.raises(RuntimeError, match="embedding failed for test"):
            index_source_documents(db, [doc])

        db.refresh(doc)
        assert doc.embedding_status == "failed"
