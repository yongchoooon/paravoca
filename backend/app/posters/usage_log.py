from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.config import Settings, get_settings
from app.core.timezone import now_kst


logger = logging.getLogger("uvicorn.error")
_lock = Lock()


def write_poster_usage_log(
    *,
    poster_id: str,
    run_id: str,
    product_id: str,
    status: str,
    provider: str,
    model: str,
    style_preset: str,
    image_size: str,
    image_quality: str,
    latency_ms: int | None,
    cost_usd: float,
    provider_response_summary: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    summary = provider_response_summary if isinstance(provider_response_summary, dict) else {}
    cost_breakdown = summary.get("cost_breakdown")
    cost_breakdown = cost_breakdown if isinstance(cost_breakdown, dict) else {}
    tokens = cost_breakdown.get("tokens")
    tokens = tokens if isinstance(tokens, dict) else {}
    usage = summary.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    record = {
        "timestamp": now_kst().isoformat(),
        "poster_id": poster_id,
        "run_id": run_id,
        "product_id": product_id,
        "status": status,
        "provider": provider,
        "model": model,
        "style_preset": style_preset,
        "image_size": image_size,
        "image_quality": image_quality,
        "latency_ms": int(latency_ms or 0),
        "cost_usd": round(float(cost_usd or 0), 8),
        "cost_krw": float(cost_breakdown.get("total_cost_krw") or 0),
        "usd_krw_rate": float(cost_breakdown.get("usd_krw_rate") or settings.usd_krw_rate or 0),
        "cost_basis": cost_breakdown.get("basis") or "unknown",
        "text_input_tokens": int(tokens.get("text_input") or 0),
        "text_cached_input_tokens": int(tokens.get("text_cached_input") or 0),
        "image_input_tokens": int(tokens.get("image_input") or 0),
        "image_cached_input_tokens": int(tokens.get("image_cached_input") or 0),
        "image_output_tokens": int(tokens.get("image_output") or 0),
        "total_tokens": int(tokens.get("total") or usage.get("total_tokens") or 0),
        "request_id": summary.get("request_id"),
        "error_code": _error_code(error),
    }

    log_dir = _resolve_log_dir(settings.poster_usage_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    with _lock:
        _append_jsonl(log_dir / "poster_usage.jsonl", record)
        _append_csv(log_dir / "poster_usage.csv", record)
        _update_summary(log_dir / "poster_usage_summary.json", record)


def safe_write_poster_usage_log(**kwargs: Any) -> None:
    try:
        write_poster_usage_log(**kwargs)
    except Exception:
        logger.exception("Poster usage file logging failed")


def _resolve_log_dir(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / path


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _append_csv(path: Path, record: dict[str, Any]) -> None:
    fieldnames = list(record.keys())
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(record)


def _update_summary(path: Path, record: dict[str, Any]) -> None:
    if path.exists():
        summary = json.loads(path.read_text(encoding="utf-8"))
    else:
        summary = {
            "updated_at": None,
            "total_calls": 0,
            "failed_calls": 0,
            "cost_usd": 0.0,
            "cost_krw": 0.0,
            "total_tokens": 0,
            "image_output_tokens": 0,
            "by_model": {},
            "by_status": {},
            "by_style_preset": {},
        }

    summary["updated_at"] = record["timestamp"]
    summary["total_calls"] += 1
    if record["status"] == "failed":
        summary["failed_calls"] += 1
    summary["cost_usd"] = round(float(summary["cost_usd"] or 0) + float(record["cost_usd"] or 0), 8)
    summary["cost_krw"] = round(float(summary["cost_krw"] or 0) + float(record["cost_krw"] or 0), 2)
    summary["total_tokens"] += int(record["total_tokens"] or 0)
    summary["image_output_tokens"] += int(record["image_output_tokens"] or 0)
    _increment_bucket(summary["by_model"], record["model"], record)
    _increment_bucket(summary["by_status"], record["status"], record)
    _increment_bucket(summary["by_style_preset"], record["style_preset"], record)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _increment_bucket(bucket: dict[str, Any], key: str, record: dict[str, Any]) -> None:
    item = bucket.setdefault(
        key,
        {
            "calls": 0,
            "failed_calls": 0,
            "cost_usd": 0.0,
            "cost_krw": 0.0,
            "total_tokens": 0,
            "image_output_tokens": 0,
        },
    )
    item["calls"] += 1
    if record["status"] == "failed":
        item["failed_calls"] += 1
    item["cost_usd"] = round(float(item["cost_usd"] or 0) + float(record["cost_usd"] or 0), 8)
    item["cost_krw"] = round(float(item["cost_krw"] or 0) + float(record["cost_krw"] or 0), 2)
    item["total_tokens"] += int(record["total_tokens"] or 0)
    item["image_output_tokens"] += int(record["image_output_tokens"] or 0)


def _error_code(error: dict[str, Any] | None) -> str | None:
    if not isinstance(error, dict):
        return None
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    response = details.get("response") if isinstance(details.get("response"), dict) else {}
    response_error = response.get("error") if isinstance(response.get("error"), dict) else {}
    code = response_error.get("code") or details.get("reason")
    return str(code) if code else None
