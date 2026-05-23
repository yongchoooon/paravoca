from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agents.run_cancellation import request_run_cancellation
from app.agents.workflow import run_product_planning_workflow
from app.core.config import get_settings
from app.db import models
from app.db.session import SessionLocal, init_db
from app.evals.metrics import (
    EvalOptions,
    collect_run_evaluation_context,
    evaluate_case,
    skipped_case_result,
    summarize_evaluation,
)
from app.evals.llm_judge import run_llm_judges
from app.evals.reporting import write_evaluation_report, write_markdown_report


DATASET_DIR = Path(__file__).parent / "datasets"
logger = logging.getLogger("eval.runner")


class EvaluationStopped(KeyboardInterrupt):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def load_dataset(name: str) -> list[dict[str, Any]]:
    path = DATASET_DIR / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found: {path}")
    cases: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            cases.append(json.loads(stripped))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return cases


def run_evaluation(
    *,
    dataset: str,
    name: str | None = None,
    limit: int | None = None,
    case_id: str | None = None,
    no_live_api: bool = False,
    reuse_run_id: str | None = None,
    output_md: bool = False,
    sleep_between_cases: float = 2.0,
    stop_on_first_failure: bool = False,
    enable_llm_judge: bool = False,
) -> tuple[dict[str, Any], Path]:
    init_db()
    settings = get_settings()
    cases = load_dataset(dataset)
    if case_id:
        cases = [case for case in cases if case.get("case_id") == case_id]
        if not cases:
            raise ValueError(f"case_id not found in dataset {dataset}: {case_id}")
    if limit is not None:
        cases = cases[: max(0, limit)]

    eval_id = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
    started_at = datetime.utcnow().isoformat() + "Z"
    results: list[dict[str, Any]] = []
    total_case_count = len(cases)
    process = {"pid": os.getpid(), "started_at": started_at}
    active_case: dict[str, Any] | None = None
    active_workflow_run_id: str | None = None
    options = {
        "limit": limit,
        "name": name,
        "case_id": case_id,
        "no_live_api": no_live_api,
        "reuse_run_id": reuse_run_id,
        "sleep_between_cases": sleep_between_cases,
        "stop_on_first_failure": stop_on_first_failure,
        "enable_llm_judge": enable_llm_judge,
        "usd_krw_rate": settings.usd_krw_rate,
    }

    report = _build_report(
        eval_id=eval_id,
        name=name,
        dataset=dataset,
        started_at=started_at,
        finished_at=None,
        status="running",
        results=results,
        options=options,
        total_case_count=total_case_count,
        process=process,
        active_case=active_case,
    )
    path = write_evaluation_report(report)
    logger.info("Evaluation started eval_id=%s dataset=%s cases=%s report=%s", eval_id, dataset, total_case_count, path)

    signal_handlers = _install_stop_signal_handlers()
    try:
        for index, case in enumerate(cases):
            case_id_value = case.get("case_id") or f"case_{index + 1}"
            active_case = {
                "case_id": case_id_value,
                "name": case.get("name"),
                "index": index + 1,
                "total": total_case_count,
                "workflow_run_id": None,
            }
            report = _build_report(
                eval_id=eval_id,
                name=name,
                dataset=dataset,
                started_at=started_at,
                finished_at=None,
                status="running",
                results=results,
                options=options,
                total_case_count=total_case_count,
                process=process,
                active_case=active_case,
            )
            write_evaluation_report(report)
            logger.info("Evaluation case started eval_id=%s case=%s index=%s/%s", eval_id, case_id_value, index + 1, total_case_count)
            if _should_skip_case(case, no_live_api=no_live_api, settings=settings, reuse_run_id=reuse_run_id):
                result = skipped_case_result(case, _skip_reason(case, no_live_api=no_live_api, settings=settings))
                results.append(result)
                active_case = None
                report = _build_report(
                    eval_id=eval_id,
                    name=name,
                    dataset=dataset,
                    started_at=started_at,
                    finished_at=None,
                    status="running",
                    results=results,
                    options=options,
                    total_case_count=total_case_count,
                    process=process,
                    active_case=active_case,
                )
                write_evaluation_report(report)
                logger.info("Evaluation case skipped eval_id=%s case=%s reason=%s", eval_id, case_id_value, result.get("skip_reason"))
                if stop_on_first_failure and result.get("status") == "failed":
                    break
                continue
            with SessionLocal() as db:
                try:
                    def on_run_created(run: models.WorkflowRun) -> None:
                        nonlocal active_case, active_workflow_run_id
                        active_workflow_run_id = run.id
                        if active_case is not None:
                            active_case = {**active_case, "workflow_run_id": run.id}
                        write_evaluation_report(
                            _build_report(
                                eval_id=eval_id,
                                name=name,
                                dataset=dataset,
                                started_at=started_at,
                                finished_at=None,
                                status="running",
                                results=results,
                                options=options,
                                total_case_count=total_case_count,
                                process=process,
                                active_case=active_case,
                            )
                        )

                    run = _load_or_execute_run(
                        db,
                        case,
                        reuse_run_id if index == 0 else None,
                        eval_id=eval_id,
                        dataset=dataset,
                        on_run_created=on_run_created,
                    )
                    active_workflow_run_id = run.id
                    context = collect_run_evaluation_context(db, run)
                    result = evaluate_case(
                        case,
                        context,
                        EvalOptions(usd_krw_rate=settings.usd_krw_rate),
                    )
                    if enable_llm_judge:
                        judge_metrics = run_llm_judges(db=db, case=case, context=context, settings=settings)
                        result = _append_llm_judge_metrics(result, judge_metrics)
                except Exception as exc:
                    result = _exception_case_result(case, exc)
            results.append(result)
            active_case = None
            active_workflow_run_id = None
            report = _build_report(
                eval_id=eval_id,
                name=name,
                dataset=dataset,
                started_at=started_at,
                finished_at=None,
                status="running",
                results=results,
                options=options,
                total_case_count=total_case_count,
                process=process,
                active_case=active_case,
            )
            write_evaluation_report(report)
            logger.info("Evaluation case finished eval_id=%s case=%s status=%s score=%s", eval_id, case_id_value, result.get("status"), result.get("score"))
            if stop_on_first_failure and result.get("status") == "failed":
                break
            _sleep_between_eval_cases(index, cases, sleep_between_cases)
    except EvaluationStopped as exc:
        if active_workflow_run_id:
            _mark_workflow_run_cancelled(active_workflow_run_id, "평가 실행이 중지되었습니다.")
        finished_at = datetime.utcnow().isoformat() + "Z"
        report = _build_report(
            eval_id=eval_id,
            name=name,
            dataset=dataset,
            started_at=started_at,
            finished_at=finished_at,
            status="stopped",
            results=results,
            options=options,
            total_case_count=total_case_count,
            process=process,
            active_case=None,
            stopped_at=finished_at,
            stop_reason=exc.reason,
        )
        path = write_evaluation_report(report)
        logger.info("Evaluation stopped eval_id=%s reason=%s report=%s", eval_id, exc.reason, path)
        return report, path
    except KeyboardInterrupt:
        if active_workflow_run_id:
            _mark_workflow_run_cancelled(active_workflow_run_id, "평가 실행이 중지되었습니다.")
        finished_at = datetime.utcnow().isoformat() + "Z"
        report = _build_report(
            eval_id=eval_id,
            name=name,
            dataset=dataset,
            started_at=started_at,
            finished_at=finished_at,
            status="stopped",
            results=results,
            options=options,
            total_case_count=total_case_count,
            process=process,
            active_case=None,
            stopped_at=finished_at,
            stop_reason="keyboard_interrupt",
        )
        path = write_evaluation_report(report)
        logger.info("Evaluation stopped eval_id=%s reason=keyboard_interrupt report=%s", eval_id, path)
        return report, path
    finally:
        _restore_signal_handlers(signal_handlers)

    finished_at = datetime.utcnow().isoformat() + "Z"
    report = _build_report(
        eval_id=eval_id,
        name=name,
        dataset=dataset,
        started_at=started_at,
        finished_at=finished_at,
        status="completed",
        results=results,
        options=options,
        total_case_count=total_case_count,
        process=process,
        active_case=None,
    )
    path = write_evaluation_report(report)
    if output_md:
        write_markdown_report(report)
    logger.info("Evaluation completed eval_id=%s passed=%s failed=%s skipped=%s report=%s", eval_id, report["summary"].get("passed_count"), report["summary"].get("failed_count"), report["summary"].get("skipped_count"), path)
    return report, path


def _build_report(
    *,
    eval_id: str,
    name: str | None,
    dataset: str,
    started_at: str,
    finished_at: str | None,
    status: str,
    results: list[dict[str, Any]],
    options: dict[str, Any],
    total_case_count: int,
    process: dict[str, Any] | None = None,
    active_case: dict[str, Any] | None = None,
    stopped_at: str | None = None,
    stop_reason: str | None = None,
) -> dict[str, Any]:
    report = {
        "eval_id": eval_id,
        "name": name.strip() if isinstance(name, str) and name.strip() else None,
        "dataset": dataset,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "heartbeat_at": datetime.utcnow().isoformat() + "Z",
        "summary": summarize_evaluation(results),
        "total_case_count": total_case_count,
        "cases": results,
        "options": options,
    }
    if process:
        report["process"] = process
    if active_case:
        report["active_case"] = active_case
    if stopped_at:
        report["stopped_at"] = stopped_at
    if stop_reason:
        report["stop_reason"] = stop_reason
    return report


def _append_llm_judge_metrics(result: dict[str, Any], judge_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not judge_metrics:
        return result
    next_result = dict(result)
    metrics = [*list(next_result.get("metrics") or []), *judge_metrics]
    blocking = [metric for metric in metrics if metric.get("blocking") and not metric.get("passed")]
    score_metrics = [metric for metric in metrics if metric.get("score") is not None]
    next_result["metrics"] = metrics
    next_result["score"] = (
        round(sum(float(metric.get("score") or 0) for metric in score_metrics) / len(score_metrics), 4)
        if score_metrics
        else None
    )
    next_result["status"] = "failed" if blocking else result.get("status", "passed")
    next_result["failures"] = [
        {
            "metric": metric["name"],
            "reason": metric.get("reason") or "metric failed",
            "value": metric.get("value"),
        }
        for metric in blocking
    ]
    next_result["llm_judge_metrics"] = [
        {
            "name": metric.get("name"),
            "score": metric.get("score"),
            "passed": metric.get("passed"),
            "value": metric.get("value"),
        }
        for metric in judge_metrics
    ]
    return next_result


def _load_or_execute_run(
    db: Session,
    case: dict[str, Any],
    reuse_run_id: str | None,
    *,
    eval_id: str,
    dataset: str,
    on_run_created: Callable[[models.WorkflowRun], None] | None = None,
) -> models.WorkflowRun:
    if reuse_run_id:
        run = db.get(models.WorkflowRun, reuse_run_id)
        if not run:
            raise ValueError(f"Workflow run not found for reuse: {reuse_run_id}")
        if on_run_created:
            on_run_created(run)
        return run

    template = db.get(models.WorkflowTemplate, "default_product_planning")
    if not template:
        raise ValueError("Default workflow template is not initialized")
    input_payload = dict(case.get("input") or {})
    input_payload["_evaluation"] = {
        "eval_id": eval_id,
        "dataset": dataset,
        "case_id": case.get("case_id"),
        "case_name": case.get("name"),
    }
    run = models.WorkflowRun(
        template_id=template.id,
        status="pending",
        input=input_payload,
        normalized_input=None,
        final_output=None,
    )
    db.add(run)
    db.flush()
    db.add(
        models.AgentStep(
            run_id=run.id,
            agent_name="System",
            step_type="workflow_created",
            status="succeeded",
            input=input_payload,
            output={"message": "Evaluation runner created this workflow run."},
            latency_ms=0,
        )
    )
    db.commit()
    if on_run_created:
        on_run_created(run)

    started = time.perf_counter()
    try:
        run_product_planning_workflow(db, run.id)
    except Exception:
        db.rollback()
    finally:
        db.expire_all()
    refreshed = db.get(models.WorkflowRun, run.id)
    if not refreshed:
        raise ValueError(f"Workflow run disappeared during evaluation: {run.id}")
    if refreshed.latency_ms is None:
        refreshed.latency_ms = int((time.perf_counter() - started) * 1000)
        db.commit()
        db.refresh(refreshed)
    return refreshed


def _install_stop_signal_handlers() -> dict[int, Any]:
    handlers: dict[int, Any] = {}

    def handle_stop(signum: int, _frame: FrameType | None) -> None:
        if signum == signal.SIGINT:
            raise EvaluationStopped("keyboard_interrupt")
        raise EvaluationStopped("terminated")

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, handle_stop)
        except (ValueError, OSError):
            continue
    return handlers


def _restore_signal_handlers(handlers: dict[int, Any]) -> None:
    for signum, handler in handlers.items():
        try:
            signal.signal(signum, handler)
        except (ValueError, OSError):
            continue


def _mark_workflow_run_cancelled(run_id: str, message: str) -> None:
    request_run_cancellation(run_id)
    with SessionLocal() as db:
        run = db.get(models.WorkflowRun, run_id)
        if not run or run.status in {"cancelled", "completed", "failed", "awaiting_approval"}:
            return
        run.status = "cancelled"
        run.error = {"type": "EvaluationStopped", "message": message}
        run.finished_at = models.utcnow()
        if run.started_at:
            run.latency_ms = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
        run.final_output = run.final_output or {
            "status": "cancelled",
            "run_status": "cancelled",
            "reason": "evaluation_stopped",
            "user_message": {
                "title": "평가 실행이 중지되었습니다",
                "message": message,
            },
            "retrieved_documents": [],
            "products": [],
            "marketing_assets": [],
            "qa_report": {"overall_status": "not_run", "issues": []},
        }
        db.commit()


def _sleep_between_eval_cases(index: int, cases: list[dict[str, Any]], seconds: float) -> None:
    if seconds <= 0 or index >= len(cases) - 1:
        return
    time.sleep(seconds)


def _should_skip_case(
    case: dict[str, Any],
    *,
    no_live_api: bool,
    settings: Any,
    reuse_run_id: str | None,
) -> bool:
    if reuse_run_id:
        return False
    if no_live_api and case.get("requires_live_api", True):
        return True
    if case.get("requires_live_api", True) and not settings.tourapi_service_key:
        return True
    if case.get("requires_llm", True) and not settings.gemini_api_key:
        return True
    return False


def _skip_reason(case: dict[str, Any], *, no_live_api: bool, settings: Any) -> str:
    if no_live_api and case.get("requires_live_api", True):
        return "--no-live-api is set and this case requires live KTO/TourAPI data."
    if case.get("requires_live_api", True) and not settings.tourapi_service_key:
        return "TOURAPI_SERVICE_KEY is not configured."
    if case.get("requires_llm", True) and not settings.gemini_api_key:
        return "GEMINI_API_KEY is required."
    return "Case skipped by evaluation runner."


def _exception_case_result(case: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "case_id": case.get("case_id"),
        "name": case.get("name"),
        "status": "failed",
        "score": 0,
        "workflow_run_id": None,
        "input": case.get("input"),
        "tags": case.get("tags") or [],
        "metrics": [
            _workflow_exception_metric(exc)
        ],
        "failures": [{"metric": "workflow_success", "reason": str(exc), "value": exc.__class__.__name__}],
        "source_family_coverage": [],
        "latency_ms": None,
        "llm_cost_usd": 0,
        "llm_cost_krw": 0,
    }


def _workflow_exception_metric(exc: Exception) -> dict[str, Any]:
    return {
        "name": "workflow_success",
        "passed": False,
        "score": 0,
        "value": exc.__class__.__name__,
        "reason": str(exc),
        "blocking": True,
        "evaluator_type": "code",
        "principle": "워크플로우가 검토 가능한 결과나 통제된 안내 종료로 끝났는지 확인합니다.",
        "expected": "평가 실행 중에도 workflow는 결과 또는 진단 가능한 종료 상태를 남겨야 합니다.",
        "actual": f"평가 runner에서 {exc.__class__.__name__} 예외가 발생했습니다.",
        "penalty_reason": str(exc),
        "next_check": "해당 run의 server log, 마지막 agent step, provider timeout/retry 로그를 확인하세요.",
        "not_applicable_reason": None,
    }
