from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.config import Settings, get_settings
from app.core.timezone import now_kst


logger = logging.getLogger("uvicorn.error")
_lock = Lock()


def write_poster_prompt_log(
    *,
    poster_id: str,
    run_id: str,
    product_id: str,
    product_title: str,
    style_preset: str,
    included_sections: list[str],
    prompt: str,
    prompt_language: str,
    image_model: str,
    image_size: str,
    image_quality: str,
    prompt_source: dict[str, Any] | None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    record = {
        "timestamp": now_kst().isoformat(),
        "poster_id": poster_id,
        "run_id": run_id,
        "product_id": product_id,
        "product_title": product_title,
        "style_preset": style_preset,
        "included_sections": included_sections,
        "prompt_language": prompt_language,
        "image_model": image_model,
        "image_size": image_size,
        "image_quality": image_quality,
        "prompt_source": prompt_source or {},
        "prompt": prompt,
    }

    log_dir = _resolve_log_dir(settings.poster_prompt_log_dir) / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    with _lock:
        (log_dir / f"{poster_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (log_dir / f"{poster_id}.md").write_text(_markdown(record), encoding="utf-8")


def safe_write_poster_prompt_log(**kwargs: Any) -> None:
    try:
        write_poster_prompt_log(**kwargs)
    except Exception:
        logger.exception("Poster prompt file logging failed")


def _resolve_log_dir(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / path


def _markdown(record: dict[str, Any]) -> str:
    metadata = {key: value for key, value in record.items() if key != "prompt"}
    return "\n".join(
        [
            f"# Poster Prompt / {record['poster_id']}",
            "",
            "## Metadata",
            "",
            "```json",
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
            "## Prompt",
            "",
            "```text",
            str(record["prompt"]),
            "```",
            "",
        ]
    )
