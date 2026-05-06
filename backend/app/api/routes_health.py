from fastapi import APIRouter

from app.api.responses import ok
from app.core.config import get_settings
from app.db.session import check_db

router = APIRouter()


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    db_status = "ok" if check_db() else "error"
    vector_db_status = "disabled" if settings.vector_db == "disabled" else "ok"
    return ok(
        {
            "status": "ok",
            "version": settings.app_version,
            "db": db_status,
            "vector_db": vector_db_status,
        }
    )

