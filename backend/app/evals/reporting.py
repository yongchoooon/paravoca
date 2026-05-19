from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings

EVAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def get_evaluation_report_dir() -> Path:
    path = Path(get_settings().evaluation_report_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_evaluation_report(report: dict[str, Any], report_dir: Path | None = None) -> Path:
    target_dir = report_dir or get_evaluation_report_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    report_path = target_dir / f"eval_{report['eval_id']}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (target_dir / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def write_markdown_report(report: dict[str, Any], report_dir: Path | None = None) -> Path:
    target_dir = report_dir or get_evaluation_report_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Evaluation {report.get('name') or report['eval_id']}",
        "",
        f"- Name: {report.get('name') or '-'}",
        f"- Dataset: `{report.get('dataset')}`",
        f"- Eval ID: `{report.get('eval_id')}`",
        f"- Started: {report.get('started_at')}",
        f"- Finished: {report.get('finished_at')}",
        f"- Summary: {report.get('summary')}",
        "",
        "| Case | Status | Score | Run | Failures |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for case in report.get("cases") or []:
        failures = "; ".join(str(failure.get("reason")) for failure in case.get("failures") or [])
        lines.append(
            "| {name} | {status} | {score} | `{run}` | {failures} |".format(
                name=str(case.get("name") or case.get("case_id")).replace("|", "\\|"),
                status=case.get("status"),
                score="" if case.get("score") is None else case.get("score"),
                run=case.get("workflow_run_id") or "-",
                failures=failures.replace("|", "\\|") or "-",
            )
        )
    path = target_dir / f"eval_{report['eval_id']}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def list_evaluation_reports(report_dir: Path | None = None) -> list[dict[str, Any]]:
    target_dir = report_dir or get_evaluation_report_dir()
    reports = []
    for path in sorted(target_dir.glob("eval_*.json"), reverse=True):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        report = _normalize_running_report(report, path)
        reports.append(summarize_report(report, path))
    return sorted(reports, key=lambda item: str(item.get("started_at") or ""), reverse=True)


def read_evaluation_report(eval_id: str, report_dir: Path | None = None) -> dict[str, Any] | None:
    target_dir = report_dir or get_evaluation_report_dir()
    candidates = [target_dir / f"eval_{eval_id}.json"]
    if eval_id == "latest":
        candidates.insert(0, target_dir / "latest.json")
    for path in candidates:
        if not path.exists():
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            return _normalize_running_report(report, path)
        except (OSError, json.JSONDecodeError):
            return None
    return None


def delete_evaluation_reports(eval_ids: list[str], report_dir: Path | None = None) -> dict[str, Any]:
    target_dir = report_dir or get_evaluation_report_dir()
    requested = [eval_id for eval_id in dict.fromkeys(eval_ids) if eval_id]
    invalid = [eval_id for eval_id in requested if not EVAL_ID_PATTERN.fullmatch(eval_id)]
    if invalid:
        return {"deleted_eval_ids": [], "deleted_count": 0, "missing_eval_ids": [], "invalid_eval_ids": invalid}

    missing: list[str] = []
    deleted: list[str] = []
    for eval_id in requested:
        json_path = target_dir / f"eval_{eval_id}.json"
        if not json_path.exists():
            missing.append(eval_id)

    if missing:
        return {
            "deleted_eval_ids": [],
            "deleted_count": 0,
            "missing_eval_ids": missing,
            "invalid_eval_ids": [],
        }

    for eval_id in requested:
        for suffix in ("json", "md"):
            path = target_dir / f"eval_{eval_id}.{suffix}"
            if path.exists():
                path.unlink()
        deleted.append(eval_id)

    _refresh_latest_report(target_dir)
    return {
        "deleted_eval_ids": deleted,
        "deleted_count": len(deleted),
        "missing_eval_ids": [],
        "invalid_eval_ids": [],
    }


def _refresh_latest_report(report_dir: Path) -> None:
    latest_path = report_dir / "latest.json"
    reports = list_evaluation_reports(report_dir)
    if not reports:
        if latest_path.exists():
            latest_path.unlink()
        return
    latest_report = read_evaluation_report(str(reports[0].get("eval_id") or ""), report_dir)
    if latest_report:
        latest_path.write_text(json.dumps(latest_report, ensure_ascii=False, indent=2), encoding="utf-8")


def summarize_report(report: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    status = report.get("status") or ("completed" if report.get("finished_at") else "running")
    return {
        "eval_id": report.get("eval_id"),
        "name": report.get("name"),
        "dataset": report.get("dataset"),
        "status": status,
        "started_at": report.get("started_at"),
        "finished_at": report.get("finished_at"),
        "summary": summary,
        "case_count": summary.get("case_count", len(report.get("cases") or [])),
        "total_case_count": report.get("total_case_count", summary.get("case_count", len(report.get("cases") or []))),
        "passed_count": summary.get("passed_count", 0),
        "failed_count": summary.get("failed_count", 0),
        "skipped_count": summary.get("skipped_count", 0),
        "average_score": summary.get("average_score"),
        "llm_cost_usd": summary.get("llm_cost_usd", 0),
        "llm_cost_krw": summary.get("llm_cost_krw", 0),
        "path": str(path) if path else None,
    }


def _normalize_running_report(report: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    if report.get("status") != "running":
        return report
    process = report.get("process") if isinstance(report.get("process"), dict) else {}
    pid = process.get("pid")
    if _process_is_alive(pid):
        return report
    next_report = dict(report)
    stopped_at = datetime.utcnow().isoformat() + "Z"
    next_report["status"] = "stopped"
    next_report["finished_at"] = next_report.get("finished_at") or stopped_at
    next_report["stopped_at"] = next_report.get("stopped_at") or stopped_at
    next_report["stop_reason"] = next_report.get("stop_reason") or (
        "process_not_running" if pid else "missing_process_metadata"
    )
    next_report["active_case"] = None
    if path:
        try:
            path.write_text(json.dumps(next_report, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    return next_report


def _process_is_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
