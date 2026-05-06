from typing import Any
from uuid import uuid4


def ok(data: Any, **meta: Any) -> dict[str, Any]:
    return {
        "data": data,
        "error": None,
        "meta": {"request_id": f"req_{uuid4().hex[:12]}", **meta},
    }


def error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "data": None,
        "error": {"code": code, "message": message, "details": details or {}},
        "meta": {"request_id": f"req_{uuid4().hex[:12]}"},
    }

