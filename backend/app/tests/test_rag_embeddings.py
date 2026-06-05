from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.agents import workflow
from app.db import models
from app.db.session import SessionLocal, init_db
from app.rag import chroma_store
from app.rag.chroma_store import (
    delete_source_documents_collection,
    index_source_documents,
    search_source_documents,
    search_source_documents_with_diagnostics,
)
from app.rag.embeddings import clear_embedding_provider_cache, get_embedding_provider
from app.rag.source_documents import (
    SOURCE_ROLE_RUNTIME,
    SOURCE_ROLE_UNKNOWN,
    build_source_document,
    source_document_role,
    upsert_source_documents_from_items,
)
from app.tools.tourism import TourismItem


def reset_embedding_settings_cache() -> None:
    get_settings.cache_clear()
    clear_embedding_provider_cache()


@pytest.fixture(autouse=True)
def ensure_db_initialized():
    init_db()
    delete_source_documents_collection()
    yield
    delete_source_documents_collection()
    reset_embedding_settings_cache()


def test_embedding_provider_uses_sentence_transformer(monkeypatch):
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


def test_rag_retrieval_smoke_with_semantic_provider(monkeypatch):
    class DirectionalProvider:
        name = "local"
        model = "test-directional"
        dimension = 3

        def _embed(self, text: str):
            if "드론" in text:
                return [1.0, 0.0, 0.0]
            if "시장" in text:
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0]

        def embed_documents(self, texts):
            return [self._embed(text) for text in texts]

        def embed_query(self, text):
            return self._embed(text)

    monkeypatch.setattr(chroma_store, "get_embedding_provider", lambda: DirectionalProvider())
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


def test_chroma_search_applies_metadata_filter_before_semantic_top_k(monkeypatch):
    class DirectionalProvider:
        name = "directional"
        model = "directional-2d"
        dimension = 2

        def _embed(self, text: str):
            return [1.0, 0.0] if "부산" in text else [0.0, 1.0]

        def embed_documents(self, texts):
            return [self._embed(text) for text in texts]

        def embed_query(self, text):
            return self._embed(text)

    monkeypatch.setattr(chroma_store, "get_embedding_provider", lambda: DirectionalProvider())
    delete_source_documents_collection()

    with SessionLocal() as db:
        docs = [
            models.SourceDocument(
                id=f"doc:test:phase95:jeju:{index}",
                source="tourapi",
                source_item_id=f"jeju:{index}",
                title=f"제주 해변 {index}",
                content=f"제주 해변 산책 자연 풍경 {index}",
                document_metadata={
                    "source": "tourapi",
                    "title": f"제주 해변 {index}",
                    "ldong_regn_cd": "50",
                    "ldong_signgu_cd": "110",
                    "test_case": "phase95-filter",
                },
            )
            for index in range(4)
        ]
        docs.append(
            models.SourceDocument(
                id="doc:test:phase95:busanjin",
                source="tourapi",
                source_item_id="busanjin",
                title="부산진구 야간 산책",
                content="부산 부산진구 야간 관광 대중교통 산책",
                document_metadata={
                    "source": "tourapi",
                    "title": "부산진구 야간 산책",
                    "ldong_regn_cd": "26",
                    "ldong_signgu_cd": "230",
                    "test_case": "phase95-filter",
                },
            )
        )
        docs = [db.merge(doc) for doc in docs]
        db.commit()
        for doc in docs:
            db.refresh(doc)

        assert index_source_documents(db, docs) == 5

    rows = search_source_documents(
        query="제주 해변",
        top_k=1,
        filters={
            "source": "tourapi",
            "ldong_regn_cd": "26",
            "ldong_signgu_cd": "230",
            "test_case": "phase95-filter",
        },
    )

    assert [row["doc_id"] for row in rows] == ["doc:test:phase95:busanjin"]

    rows = search_source_documents(
        query="제주 해변",
        top_k=1,
        filters={
            "source": "tourapi",
            "ldong_regn_cd": ["26", "51"],
            "ldong_signgu_cd": "230",
            "test_case": "phase95-filter",
        },
    )

    assert [row["doc_id"] for row in rows] == ["doc:test:phase95:busanjin"]


def test_source_document_lifecycle_metadata_and_runtime_upsert():
    item = TourismItem(
        id="tourapi:content:phase171",
        source="tourapi",
        content_id="phase171",
        content_type="event",
        title="포항 해변 자연 체험",
        region_code="35",
        ldong_regn_cd="47",
        ldong_signgu_cd="111",
        lcls_systm_1="A",
        lcls_systm_2="A02",
        lcls_systm_3="A0207",
        address="경상북도 포항시 북구",
        overview="해변과 자연 관찰을 함께 다루는 체험 행사입니다.",
    )

    payload = build_source_document(
        item,
        run_id="run_phase171",
        source_role=SOURCE_ROLE_RUNTIME,
        ingestion_method="workflow_baseline_tourapi",
    )

    metadata = payload["document_metadata"]
    assert metadata["source_role"] == SOURCE_ROLE_RUNTIME
    assert metadata["source_family"] == "kto_tourapi_kor"
    assert metadata["content_id"] == "phase171"
    assert metadata["source_item_id"] == "tourapi:content:phase171"
    assert metadata["first_seen_run_id"] == "run_phase171"
    assert metadata["last_seen_run_id"] == "run_phase171"
    assert metadata["ingestion_method"] == "workflow_baseline_tourapi"
    assert metadata["dedupe_key"] == "kto_tourapi_kor:phase171"


def test_source_document_upsert_preserves_first_seen_and_updates_last_seen():
    first_item = TourismItem(
        id="tourapi:content:phase171-upsert",
        source="tourapi",
        content_id="phase171-upsert",
        content_type="event",
        title="포항 해변 체험",
        region_code="35",
        overview="첫 번째 관측 내용입니다.",
    )
    second_item = TourismItem(
        id="tourapi:content:phase171-upsert",
        source="tourapi",
        content_id="phase171-upsert",
        content_type="event",
        title="포항 해변 체험",
        region_code="35",
        overview="두 번째 관측 내용입니다.",
    )

    with SessionLocal() as db:
        first_docs = upsert_source_documents_from_items(
            db,
            [first_item],
            run_id="run_first",
            source_role=SOURCE_ROLE_RUNTIME,
            ingestion_method="workflow_baseline_tourapi",
        )
        second_docs = upsert_source_documents_from_items(
            db,
            [second_item],
            run_id="run_second",
            source_role=SOURCE_ROLE_RUNTIME,
            ingestion_method="workflow_baseline_tourapi",
        )

        assert first_docs[0].id == second_docs[0].id
        stored = db.get(models.SourceDocument, "doc:tourapi:content:phase171-upsert")
        assert stored is not None
        assert stored.content.count("두 번째 관측 내용") == 1
        assert stored.document_metadata["first_seen_run_id"] == "run_first"
        assert stored.document_metadata["last_seen_run_id"] == "run_second"
        assert stored.document_metadata["source_role"] == SOURCE_ROLE_RUNTIME


def test_legacy_source_document_without_role_is_unknown():
    doc = models.SourceDocument(
        id="doc:test:legacy-role",
        source="tourapi",
        source_item_id="legacy-role",
        title="기존 문서",
        content="역할 메타데이터가 없는 기존 문서입니다.",
        document_metadata={"source": "tourapi", "title": "기존 문서"},
    )

    assert source_document_role(doc) == SOURCE_ROLE_UNKNOWN


def test_chroma_search_returns_retrieval_diagnostics_without_fallback(monkeypatch):
    class DirectionalProvider:
        name = "directional"
        model = "directional-2d"
        dimension = 2

        def embed_documents(self, texts):
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text):
            return [1.0, 0.0]

    monkeypatch.setattr(chroma_store, "get_embedding_provider", lambda: DirectionalProvider())
    delete_source_documents_collection()

    with SessionLocal() as db:
        docs = [
            models.SourceDocument(
                id="doc:test:phase171:match",
                source="tourapi",
                source_item_id="phase171:match",
                title="포항 자연 해변 산책",
                content="포항 자연 해변 외국인 산책 프로그램",
                document_metadata={
                    "source": "tourapi",
                    "source_family": "kto_tourapi_kor",
                    "source_role": SOURCE_ROLE_RUNTIME,
                    "title": "포항 자연 해변 산책",
                    "ldong_regn_cd": "47",
                    "ldong_signgu_cd": "111",
                    "content_type": "event",
                    "test_case": "phase171-diagnostics",
                },
            )
        ]
        docs = [db.merge(doc) for doc in docs]
        db.commit()
        for doc in docs:
            db.refresh(doc)
        assert index_source_documents(db, docs) == 1

    result = search_source_documents_with_diagnostics(
        query="경상북도 포항시 외국인 자연 해변",
        top_k=5,
        filters={
            "source": "tourapi",
            "source_family": "kto_tourapi_kor",
            "ldong_regn_cd": "47",
            "ldong_signgu_cd": "111",
            "content_type": "event",
            "test_case": "phase171-diagnostics",
        },
        search_context={
            "preferred_themes": ["자연", "해변"],
            "target_customer": "외국인",
            "narrow_keywords": ["포항", "해변"],
        },
    )

    assert [row["doc_id"] for row in result["results"]] == ["doc:test:phase171:match"]
    diagnostics = result["retrieval_diagnostics"]
    assert diagnostics["query"] == "경상북도 포항시 외국인 자연 해변"
    assert diagnostics["filters"]["ldong_signgu_cd"] == "111"
    assert diagnostics["result_count"] == 1
    assert diagnostics["fallback_applied"] is False
    assert diagnostics["scope_expansion_applied"] is False
    assert result["results"][0]["matching_signals"]


def test_chroma_search_empty_result_does_not_widen_scope_or_create_fallback(monkeypatch):
    class DirectionalProvider:
        name = "directional"
        model = "directional-2d"
        dimension = 2

        def embed_documents(self, texts):
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text):
            return [1.0, 0.0]

    monkeypatch.setattr(chroma_store, "get_embedding_provider", lambda: DirectionalProvider())
    delete_source_documents_collection()

    with SessionLocal() as db:
        doc = db.merge(
            models.SourceDocument(
                id="doc:test:phase171:other-region",
                source="tourapi",
                source_item_id="phase171:other-region",
                title="부산 해변 산책",
                content="부산 해변 산책 프로그램",
                document_metadata={
                    "source": "tourapi",
                    "source_family": "kto_tourapi_kor",
                    "source_role": SOURCE_ROLE_RUNTIME,
                    "title": "부산 해변 산책",
                    "ldong_regn_cd": "26",
                    "ldong_signgu_cd": "110",
                    "test_case": "phase171-empty",
                },
            )
        )
        db.commit()
        db.refresh(doc)
        assert index_source_documents(db, [doc]) == 1

    result = search_source_documents_with_diagnostics(
        query="포항 자연 해변",
        top_k=5,
        filters={
            "source": "tourapi",
            "ldong_regn_cd": "47",
            "ldong_signgu_cd": "111",
            "test_case": "phase171-empty",
        },
    )

    assert result["results"] == []
    diagnostics = result["retrieval_diagnostics"]
    assert diagnostics["result_count"] == 0
    assert diagnostics["reason"] == "no_documents_matched_query_and_filters"
    assert diagnostics["fallback_applied"] is False
    assert diagnostics["scope_expansion_applied"] is False


def test_unknown_source_role_receives_lower_relevance_than_classified_role(monkeypatch):
    class DirectionalProvider:
        name = "directional"
        model = "directional-2d"
        dimension = 2

        def embed_documents(self, texts):
            return [[1.0, 0.0] for _ in texts]

        def embed_query(self, text):
            return [1.0, 0.0]

    monkeypatch.setattr(chroma_store, "get_embedding_provider", lambda: DirectionalProvider())
    delete_source_documents_collection()

    with SessionLocal() as db:
        docs = [
            models.SourceDocument(
                id="doc:test:phase171:known-role",
                source="tourapi",
                source_item_id="known-role",
                title="포항 해변 자연",
                content="포항 해변 자연 체험",
                document_metadata={
                    "source": "tourapi",
                    "source_family": "kto_tourapi_kor",
                    "source_role": SOURCE_ROLE_RUNTIME,
                    "title": "포항 해변 자연",
                    "test_case": "phase171-role-rank",
                },
            ),
            models.SourceDocument(
                id="doc:test:phase171:unknown-role",
                source="tourapi",
                source_item_id="unknown-role",
                title="포항 해변 자연",
                content="포항 해변 자연 체험",
                document_metadata={
                    "source": "tourapi",
                    "source_family": "kto_tourapi_kor",
                    "title": "포항 해변 자연",
                    "test_case": "phase171-role-rank",
                },
            ),
        ]
        docs = [db.merge(doc) for doc in docs]
        db.commit()
        for doc in docs:
            db.refresh(doc)
        assert index_source_documents(db, docs) == 2

    rows = search_source_documents(
        query="포항 해변 자연",
        top_k=2,
        filters={"test_case": "phase171-role-rank"},
    )

    assert rows[0]["doc_id"] == "doc:test:phase171:known-role"
    assert rows[0]["source_role"] == SOURCE_ROLE_RUNTIME
    assert rows[1]["source_role"] == SOURCE_ROLE_UNKNOWN
    assert rows[0]["relevance_score"] > rows[1]["relevance_score"]


def test_workflow_rag_query_and_filters_include_request_scope():
    normalized = {
        "question": "이번 달 포항에서 외국인 대상 해변 여행 상품을 기획해줘",
        "target_customer": "외국인",
        "preferred_themes": ["자연", "해변"],
    }
    geo_scope = {
        "allow_nationwide": False,
        "locations": [
            {
                "location_name": "경상북도 포항시",
                "ldong_regn_cd": "47",
                "ldong_signgu_cd": "111",
                "lcls_systm_1": "A",
                "lcls_systm_2": "A02",
            }
        ],
        "retained_keywords": ["포항", "해변"],
    }

    query = workflow._rag_query_for_request(normalized, geo_scope)
    context = workflow._rag_search_context(normalized, geo_scope)
    filters = workflow._vector_filters_for_geo_scope(geo_scope, source="tourapi", normalized=normalized)

    assert "경상북도 포항시" in query
    assert "외국인" in query
    assert "자연" in query
    assert "해변" in query
    assert "포항" in context["narrow_keywords"]
    assert context["target_customer"] == "외국인"
    assert filters["source"] == "tourapi"
    assert filters["source_family"] == "kto_tourapi_kor"
    assert filters["ldong_regn_cd"] == "47"
    assert filters["ldong_signgu_cd"] == "111"
    assert filters["lcls_systm_1"] == "A"
    assert filters["lcls_systm_2"] == "A02"


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
