from __future__ import annotations

import os
import signal
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.run_cancellation import request_run_cancellation
from app.api.responses import ok
from app.db import models
from app.db.session import get_db
from app.evals.reporting import delete_evaluation_reports, list_evaluation_reports, read_evaluation_report


router = APIRouter(prefix="/evaluations", tags=["evaluations"])


class EvaluationDeleteRequest(BaseModel):
    eval_ids: list[str] = Field(default_factory=list, min_length=1)


@router.get("")
def list_evaluations() -> dict:
    reports = list_evaluation_reports()
    return ok(reports, count=len(reports))


@router.post("/delete")
def delete_evaluations(payload: EvaluationDeleteRequest, db: Session = Depends(get_db)) -> dict:
    reports_by_id = {eval_id: read_evaluation_report(eval_id) for eval_id in payload.eval_ids}
    missing_before_delete = [eval_id for eval_id, report in reports_by_id.items() if not report]
    if missing_before_delete:
        raise HTTPException(status_code=404, detail=f"Evaluation report not found: {missing_before_delete[0]}")
    workflow_run_ids = _owned_workflow_run_ids_for_reports(db, reports_by_id)
    _request_workflow_run_cancellation(db, workflow_run_ids)
    terminated_processes = [
        result
        for report in reports_by_id.values()
        if report
        for result in [_terminate_evaluation_process(report)]
        if result
    ]

    result = delete_evaluation_reports(payload.eval_ids)
    invalid = result.get("invalid_eval_ids") or []
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid evaluation id: {invalid[0]}")
    missing = result.get("missing_eval_ids") or []
    if missing:
        raise HTTPException(status_code=404, detail=f"Evaluation report not found: {missing[0]}")
    deleted_workflow_run_ids: list[str] = []
    if workflow_run_ids:
        runs = db.query(models.WorkflowRun).filter(models.WorkflowRun.id.in_(workflow_run_ids)).all()
        for run in runs:
            deleted_workflow_run_ids.append(run.id)
            db.delete(run)
        db.commit()
    result["deleted_workflow_run_ids"] = sorted(deleted_workflow_run_ids)
    result["deleted_workflow_run_count"] = len(deleted_workflow_run_ids)
    result["terminated_eval_processes"] = terminated_processes
    return ok(result)


def _owned_workflow_run_ids_for_reports(db: Session, reports_by_id: dict[str, dict | None]) -> list[str]:
    run_ids: set[str] = set()
    for eval_id, report in reports_by_id.items():
        if not report:
            continue
        options = report.get("options") if isinstance(report.get("options"), dict) else {}
        if options.get("reuse_run_id"):
            continue
        active_case = report.get("active_case") if isinstance(report.get("active_case"), dict) else {}
        active_run_id = active_case.get("workflow_run_id")
        if active_run_id:
            _add_owned_workflow_run_id(db, run_ids, eval_id, str(active_run_id))
        for case in report.get("cases") or []:
            if not isinstance(case, dict) or not case.get("workflow_run_id"):
                continue
            _add_owned_workflow_run_id(db, run_ids, eval_id, str(case["workflow_run_id"]))
    return sorted(run_ids)


def _add_owned_workflow_run_id(db: Session, run_ids: set[str], eval_id: str, run_id: str) -> None:
    run = db.get(models.WorkflowRun, run_id)
    if not run:
        return
    run_input = run.input if isinstance(run.input, dict) else {}
    metadata = run_input.get("_evaluation") if isinstance(run_input.get("_evaluation"), dict) else {}
    if not metadata or metadata.get("eval_id") == eval_id:
        run_ids.add(run_id)


def _request_workflow_run_cancellation(db: Session, workflow_run_ids: list[str]) -> None:
    if not workflow_run_ids:
        return
    runs = db.query(models.WorkflowRun).filter(models.WorkflowRun.id.in_(workflow_run_ids)).all()
    changed = False
    for run in runs:
        if run.status not in {"pending", "running", "cancelling"}:
            continue
        request_run_cancellation(run.id)
        run.status = "cancelled"
        run.error = {
            "type": "EvaluationDeleted",
            "message": "평가 리포트 삭제로 workflow 실행을 중지했습니다.",
        }
        run.finished_at = models.utcnow()
        if run.started_at:
            run.latency_ms = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
        run.final_output = run.final_output or {
            "status": "cancelled",
            "run_status": "cancelled",
            "reason": "evaluation_deleted",
            "user_message": {
                "title": "평가 실행이 삭제되었습니다",
                "message": "평가 리포트 삭제로 workflow 실행을 중지했습니다.",
            },
            "retrieved_documents": [],
            "products": [],
            "marketing_assets": [],
            "qa_report": {"overall_status": "not_run", "issues": []},
        }
        changed = True
    if changed:
        db.commit()


def _terminate_evaluation_process(report: dict[str, Any]) -> dict[str, Any] | None:
    if report.get("status") != "running":
        return None
    process = report.get("process") if isinstance(report.get("process"), dict) else {}
    pid = process.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return {"eval_id": report.get("eval_id"), "pid": None, "status": "missing_pid"}
    if pid == os.getpid():
        return {"eval_id": report.get("eval_id"), "pid": pid, "status": "skipped_current_process"}
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return {"eval_id": report.get("eval_id"), "pid": pid, "status": "already_stopped"}
    except PermissionError as exc:
        return {"eval_id": report.get("eval_id"), "pid": pid, "status": "permission_denied", "error": str(exc)}

    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if not _process_is_alive(pid):
            return {"eval_id": report.get("eval_id"), "pid": pid, "status": "terminated"}
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return {"eval_id": report.get("eval_id"), "pid": pid, "status": "terminated"}
    except PermissionError as exc:
        return {"eval_id": report.get("eval_id"), "pid": pid, "status": "permission_denied", "error": str(exc)}
    return {"eval_id": report.get("eval_id"), "pid": pid, "status": "force_killed"}


def _process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@router.get("/{eval_id}")
def get_evaluation(eval_id: str) -> dict:
    report = read_evaluation_report(eval_id)
    if not report:
        raise HTTPException(status_code=404, detail="Evaluation report not found")
    return ok(report)


@router.get("/{eval_id}/cases")
def list_evaluation_cases(eval_id: str) -> dict:
    report = read_evaluation_report(eval_id)
    if not report:
        raise HTTPException(status_code=404, detail="Evaluation report not found")
    cases = report.get("cases") or []
    return ok(cases, count=len(cases))
