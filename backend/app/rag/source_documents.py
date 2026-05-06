from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.tools.tourism import TourismItem


def build_source_document(item: TourismItem | models.TourismItem) -> dict[str, Any]:
    metadata = {
        "source": item.source,
        "source_item_id": item.id,
        "title": item.title,
        "content_id": item.content_id,
        "content_type": item.content_type,
        "region_code": item.region_code,
        "sigungu_code": item.sigungu_code,
        "license_type": item.license_type,
        "event_start_date": item.event_start_date,
        "event_end_date": item.event_end_date,
    }
    content = "\n".join(
        part
        for part in [
            f"제목: {item.title}",
            f"유형: {item.content_type}",
            f"지역코드: {item.region_code}",
            f"주소: {item.address or ''}",
            f"기간: {item.event_start_date or ''}~{item.event_end_date or ''}",
            f"개요: {item.overview or ''}",
            f"이미지/라이선스: {item.license_type or '확인 필요'}",
        ]
        if part.strip()
    )
    return {
        "id": f"doc:{item.id}",
        "source": item.source,
        "source_item_id": item.id,
        "title": item.title,
        "content": content,
        "document_metadata": metadata,
        "embedding_status": "pending",
    }


def upsert_source_documents_from_items(
    db: Session, items: list[TourismItem | models.TourismItem]
) -> list[models.SourceDocument]:
    documents: list[models.SourceDocument] = []
    for item in items:
        payload = build_source_document(item)
        existing = db.get(models.SourceDocument, payload["id"])
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.updated_at = models.utcnow()
            document = existing
        else:
            document = models.SourceDocument(**payload)
            db.add(document)
        documents.append(document)
    db.commit()
    for document in documents:
        db.refresh(document)
    return documents
