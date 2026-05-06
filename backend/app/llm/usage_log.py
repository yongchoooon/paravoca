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


def write_llm_usage_log(
    *,
    run_id: str,
    step_id: str | None,
    call_id: str | None = None,
    provider: str,
    model: str,
    purpose: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost_usd: float,
    paid_tier_equivalent_cost_usd: float = 0.0,
    latency_ms: int | None,
    request_hash: str | None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    record = {
        "timestamp": now_kst().isoformat(),
        "run_id": run_id,
        "step_id": step_id,
        "call_id": call_id,
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "status": "failed" if purpose.endswith("_failed") else "succeeded",
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "cost_usd": round(float(cost_usd or 0.0), 8),
        "paid_tier_equivalent_cost_usd": round(float(paid_tier_equivalent_cost_usd or 0.0), 8),
        "latency_ms": int(latency_ms or 0),
        "request_hash": request_hash,
    }

    log_dir = _resolve_log_dir(settings.llm_usage_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    with _lock:
        _append_jsonl(log_dir / "llm_usage.jsonl", record)
        _append_csv(log_dir / "llm_usage.csv", record)
        _update_summary(log_dir / "llm_usage_summary.json", record)


def safe_write_llm_usage_log(**kwargs: Any) -> None:
    try:
        write_llm_usage_log(**kwargs)
    except Exception:
        logger.exception("LLM usage file logging failed")


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
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "paid_tier_equivalent_cost_usd": 0.0,
            "by_provider": {},
            "by_model": {},
            "by_purpose": {},
        }

    summary["updated_at"] = record["timestamp"]
    summary["total_calls"] += 1
    if record["status"] == "failed":
        summary["failed_calls"] += 1
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        summary[key] += int(record[key] or 0)
    for key in ("cost_usd", "paid_tier_equivalent_cost_usd"):
        summary[key] = round(float(summary[key] or 0.0) + float(record[key] or 0.0), 8)

    _increment_bucket(summary["by_provider"], record["provider"], record)
    _increment_bucket(summary["by_model"], record["model"], record)
    _increment_bucket(summary["by_purpose"], record["purpose"], record)

    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _increment_bucket(bucket: dict[str, Any], key: str, record: dict[str, Any]) -> None:
    item = bucket.setdefault(
        key,
        {
            "calls": 0,
            "failed_calls": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "paid_tier_equivalent_cost_usd": 0.0,
        },
    )
    item["calls"] += 1
    if record["status"] == "failed":
        item["failed_calls"] += 1
    item["total_tokens"] += int(record["total_tokens"] or 0)
    item["cost_usd"] = round(float(item["cost_usd"] or 0.0) + float(record["cost_usd"] or 0.0), 8)
    item["paid_tier_equivalent_cost_usd"] = round(
        float(item["paid_tier_equivalent_cost_usd"] or 0.0)
        + float(record["paid_tier_equivalent_cost_usd"] or 0.0),
        8,
    )
