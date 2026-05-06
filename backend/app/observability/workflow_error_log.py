from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.config import Settings, get_settings
from app.core.timezone import now_kst

logger = logging.getLogger("uvicorn.error")
_lock = Lock()


def write_workflow_error_log(
    *,
    run_id: str,
    template_id: str,
    input_payload: dict[str, Any],
    exc: Exception,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    log_dir = _resolve_log_dir(settings.app_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": now_kst().isoformat(),
        "run_id": run_id,
        "template_id": template_id,
        "input": input_payload,
        "error": {
            "type": exc.__class__.__name__,
            "message": str(exc),
        },
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }

    with _lock:
        _append_jsonl(log_dir / "workflow_errors.jsonl", record)
        _append_text(log_dir / "workflow_errors.log", record)


def safe_write_workflow_error_log(**kwargs: Any) -> None:
    try:
        write_workflow_error_log(**kwargs)
    except Exception:
        logger.exception("Workflow error file logging failed")


def _resolve_log_dir(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / path


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _append_text(path: Path, record: dict[str, Any]) -> None:
    lines = [
        f"[{record['timestamp']}] run_id={record['run_id']} template_id={record['template_id']}",
        f"{record['error']['type']}: {record['error']['message']}",
        record["traceback"].rstrip(),
        "",
    ]
    with path.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
