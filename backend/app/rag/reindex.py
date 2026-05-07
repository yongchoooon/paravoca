from __future__ import annotations

import argparse
import logging

from app.db import models
from app.db.session import SessionLocal, init_db
from app.rag.chroma_store import delete_source_documents_collection, index_source_documents
from app.rag.embeddings import get_embedding_provider

logger = logging.getLogger("uvicorn.error")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reindex PARAVOCA RAG collections.")
    parser.add_argument(
        "--collection",
        default="source_documents",
        choices=["source_documents"],
        help="Collection to reindex.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the Chroma collection before indexing.",
    )
    args = parser.parse_args()

    init_db()
    provider = get_embedding_provider()
    print(
        "Reindexing collection=source_documents "
        f"provider={provider.name} model={provider.model} dimension={provider.dimension}"
    )

    if args.reset:
        deleted = delete_source_documents_collection()
        print("Reset Chroma source_documents collection" if deleted else "No existing collection to reset")

    succeeded = 0
    failed = 0
    with SessionLocal() as db:
        documents = db.query(models.SourceDocument).order_by(models.SourceDocument.id).all()
        for document in documents:
            document.embedding_status = "pending"
            document.updated_at = models.utcnow()
        db.commit()

        for document in documents:
            try:
                index_source_documents(db, [document])
                succeeded += 1
            except Exception as exc:
                failed += 1
                logger.exception("Reindex failed for source_document_id=%s", document.id)
                print(f"failed {document.id}: {exc}")

    print(
        "Reindex complete "
        f"collection=source_documents total={succeeded + failed} succeeded={succeeded} failed={failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
