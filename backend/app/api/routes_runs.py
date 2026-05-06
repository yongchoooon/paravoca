import sys
import traceback
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.responses import ok
from app.agents.workflow import run_product_planning_workflow, run_revision_workflow
from app.db import models
from app.db.session import SessionLocal, get_db
from app.observability.workflow_error_log import safe_write_workflow_error_log
from app.schemas.workflow import (
    AgentStepRead,
    ApprovalActionRequest,
    ApprovalRead,
    LLMCallRead,
    QAIssueDeleteRequest,
    ToolCallRead,
    WorkflowRunCreate,
    WorkflowRunRead,
    WorkflowRevisionCreate,
)

router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])
logger = logging.getLogger("uvicorn.error")


def _log_workflow_exception(
    *,
    run_id: str,
    template_id: str,
    input_payload: dict,
    exc: Exception,
) -> None:
    logger.exception(
        "Workflow execution failed. run_id=%s template_id=%s input=%s",
        run_id,
        template_id,
        input_payload,
    )
    print(
        f"[workflow-run-failed] run_id={run_id} "
        f"type={exc.__class__.__name__} message={exc}",
        file=sys.stderr,
        flush=True,
    )
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
    safe_write_workflow_error_log(
        run_id=run_id,
        template_id=template_id,
        input_payload=input_payload,
        exc=exc,
    )


def _run_workflow_background(run_id: str, template_id: str, input_payload: dict) -> None:
    with SessionLocal() as db:
        try:
            run_product_planning_workflow(db, run_id)
        except Exception as exc:
            run = db.get(models.WorkflowRun, run_id)
            if run:
                run.status = "failed"
                run.error = {"type": exc.__class__.__name__, "message": str(exc)}
                run.finished_at = models.utcnow()
                db.commit()
            _log_workflow_exception(
                run_id=run_id,
                template_id=template_id,
                input_payload=input_payload,
                exc=exc,
            )


def _run_revision_background(run_id: str, template_id: str, input_payload: dict) -> None:
    with SessionLocal() as db:
        try:
            run_revision_workflow(db, run_id)
        except Exception as exc:
            run = db.get(models.WorkflowRun, run_id)
            if run:
                run.status = "failed"
                run.error = {"type": exc.__class__.__name__, "message": str(exc)}
                run.finished_at = models.utcnow()
                db.commit()
            _log_workflow_exception(
                run_id=run_id,
                template_id=template_id,
                input_payload=input_payload,
                exc=exc,
            )


def get_run_or_404(db: Session, run_id: str) -> models.WorkflowRun:
    run = db.get(models.WorkflowRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return run


def apply_approval_decision(
    *,
    db: Session,
    run: models.WorkflowRun,
    decision: str,
    next_status: str,
    payload: ApprovalActionRequest,
) -> models.Approval:
    if not run.final_output:
        raise HTTPException(status_code=409, detail="Workflow run has no generated result")
    if run.status not in {"awaiting_approval", "changes_requested"}:
        raise HTTPException(
            status_code=409,
            detail=f"Workflow run status {run.status} cannot be changed by approval action",
        )

    approval = models.Approval(
        run_id=run.id,
        decision=decision,
        reviewer=payload.reviewer,
        comment=payload.comment,
        approval_metadata={
            "high_risk_override": payload.high_risk_override,
            "requested_changes": payload.requested_changes,
            "previous_status": run.status,
        },
    )
    db.add(approval)

    run.status = next_status
    final_output = dict(run.final_output)
    approval_state = dict(final_output.get("approval") or {})
    approval_state.update(
        {
            "required": decision != "approve",
            "status": next_status,
            "decision": decision,
            "reviewer": payload.reviewer,
            "comment": payload.comment,
            "high_risk_override": payload.high_risk_override,
            "requested_changes": payload.requested_changes,
            "decided_at": models.utcnow().isoformat(),
        }
    )
    final_output["approval"] = approval_state
    run.final_output = final_output
    db.commit()
    db.refresh(approval)
    db.refresh(run)
    return approval


@router.post("")
def create_workflow_run(
    payload: WorkflowRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    template = db.get(models.WorkflowTemplate, payload.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Workflow template not found")

    run = models.WorkflowRun(
        template_id=payload.template_id,
        status="pending",
        input=payload.input.model_dump(),
        normalized_input=None,
        final_output=None,
    )
    db.add(run)
    db.flush()

    initial_step = models.AgentStep(
        run_id=run.id,
        agent_name="System",
        step_type="workflow_created",
        status="succeeded",
        input=payload.input.model_dump(),
        output={"message": "워크플로우 실행 요청이 생성되었습니다. 백그라운드 실행을 시작합니다."},
        latency_ms=0,
    )
    db.add(initial_step)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(
        _run_workflow_background,
        run.id,
        payload.template_id,
        payload.input.model_dump(),
    )
    return ok(WorkflowRunRead.model_validate(run).model_dump(mode="json"))


@router.get("")
def list_workflow_runs(db: Session = Depends(get_db)) -> dict:
    runs = db.query(models.WorkflowRun).order_by(models.WorkflowRun.created_at.desc()).all()
    data = [WorkflowRunRead.model_validate(run).model_dump(mode="json") for run in runs]
    return ok(data, count=len(data))


@router.get("/{run_id}")
def get_workflow_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = get_run_or_404(db, run_id)
    return ok(WorkflowRunRead.model_validate(run).model_dump(mode="json"))


@router.get("/{run_id}/steps")
def list_run_steps(run_id: str, db: Session = Depends(get_db)) -> dict:
    get_run_or_404(db, run_id)
    steps = (
        db.query(models.AgentStep)
        .filter(models.AgentStep.run_id == run_id)
        .order_by(models.AgentStep.started_at.asc().nulls_last(), models.AgentStep.id)
        .all()
    )
    data = [AgentStepRead.model_validate(step).model_dump(mode="json") for step in steps]
    return ok(data, count=len(data))


@router.get("/{run_id}/tool-calls")
def list_run_tool_calls(run_id: str, db: Session = Depends(get_db)) -> dict:
    get_run_or_404(db, run_id)
    tool_calls = (
        db.query(models.ToolCall)
        .filter(models.ToolCall.run_id == run_id)
        .order_by(models.ToolCall.created_at.asc())
        .all()
    )
    data = [ToolCallRead.model_validate(call).model_dump(mode="json") for call in tool_calls]
    return ok(data, count=len(data))


@router.get("/{run_id}/llm-calls")
def list_run_llm_calls(run_id: str, db: Session = Depends(get_db)) -> dict:
    get_run_or_404(db, run_id)
    llm_calls = (
        db.query(models.LLMCall)
        .filter(models.LLMCall.run_id == run_id)
        .order_by(models.LLMCall.created_at.asc())
        .all()
    )
    data = [LLMCallRead.model_validate(call).model_dump(mode="json") for call in llm_calls]
    return ok(data, count=len(data))


@router.get("/{run_id}/approvals")
def list_run_approvals(run_id: str, db: Session = Depends(get_db)) -> dict:
    get_run_or_404(db, run_id)
    approvals = (
        db.query(models.Approval)
        .filter(models.Approval.run_id == run_id)
        .order_by(models.Approval.created_at.asc())
        .all()
    )
    data = [ApprovalRead.model_validate(approval).model_dump(mode="json") for approval in approvals]
    return ok(data, count=len(data))


@router.post("/{run_id}/approve")
def approve_workflow_run(
    run_id: str,
    payload: ApprovalActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    run = get_run_or_404(db, run_id)
    approval = apply_approval_decision(
        db=db,
        run=run,
        decision="approve",
        next_status="approved",
        payload=payload,
    )
    return ok(
        {
            "run": WorkflowRunRead.model_validate(run).model_dump(mode="json"),
            "approval": ApprovalRead.model_validate(approval).model_dump(mode="json"),
        }
    )


@router.post("/{run_id}/reject")
def reject_workflow_run(
    run_id: str,
    payload: ApprovalActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    run = get_run_or_404(db, run_id)
    approval = apply_approval_decision(
        db=db,
        run=run,
        decision="reject",
        next_status="rejected",
        payload=payload,
    )
    return ok(
        {
            "run": WorkflowRunRead.model_validate(run).model_dump(mode="json"),
            "approval": ApprovalRead.model_validate(approval).model_dump(mode="json"),
        }
    )


@router.post("/{run_id}/request-changes")
def request_workflow_run_changes(
    run_id: str,
    payload: ApprovalActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    run = get_run_or_404(db, run_id)
    approval = apply_approval_decision(
        db=db,
        run=run,
        decision="request_changes",
        next_status="changes_requested",
        payload=payload,
    )
    return ok(
        {
            "run": WorkflowRunRead.model_validate(run).model_dump(mode="json"),
            "approval": ApprovalRead.model_validate(approval).model_dump(mode="json"),
        }
    )


@router.post("/{run_id}/revisions")
def create_workflow_revision(
    run_id: str,
    payload: WorkflowRevisionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    source_run = get_run_or_404(db, run_id)
    if not source_run.final_output:
        raise HTTPException(status_code=409, detail="Source workflow run has no generated result")

    if payload.revision_mode in {"manual_save", "manual_edit"} and (
        not payload.products or not payload.marketing_assets
    ):
        raise HTTPException(
            status_code=422,
            detail="manual_save/manual_edit revision requires products and marketing_assets",
        )

    root_run = _root_run(db, source_run)
    next_revision_number = _next_revision_number(db, root_run.id)
    requested_changes = payload.requested_changes or _request_changes_from_approvals(source_run.approvals)
    approval_history = [
        ApprovalRead.model_validate(approval).model_dump(mode="json")
        for approval in _lineage_approvals(db, root_run.id)
    ]
    revision_context = {
        "root_run_id": root_run.id,
        "source_run_id": source_run.id,
        "revision_mode": payload.revision_mode,
        "revision_number": next_revision_number,
        "requested_changes": requested_changes,
        "qa_issues": payload.qa_issues,
        "qa_settings": payload.qa_settings,
        "comment": payload.comment,
        "approval_history": approval_history,
        "source_final_output": source_run.final_output,
        "manual_products": payload.products,
        "manual_marketing_assets": payload.marketing_assets,
    }
    revision_input = {
        **source_run.input,
        "revision_context": revision_context,
    }
    revision_run = models.WorkflowRun(
        template_id=source_run.template_id,
        parent_run_id=root_run.id,
        revision_number=next_revision_number,
        revision_mode=payload.revision_mode,
        status="pending",
        input=revision_input,
        normalized_input=None,
        final_output=None,
    )
    db.add(revision_run)
    db.flush()

    initial_step = models.AgentStep(
        run_id=revision_run.id,
        agent_name="System",
        step_type="revision_created",
        status="succeeded",
        input={
            "root_run_id": root_run.id,
            "source_run_id": source_run.id,
            "revision_mode": payload.revision_mode,
            "revision_number": next_revision_number,
        },
        output={"message": "Revision run이 생성되었습니다. 백그라운드 실행을 시작합니다."},
        latency_ms=0,
    )
    db.add(initial_step)
    db.commit()
    db.refresh(revision_run)

    background_tasks.add_task(
        _run_revision_background,
        revision_run.id,
        revision_run.template_id,
        revision_input,
    )
    return ok(WorkflowRunRead.model_validate(revision_run).model_dump(mode="json"))


@router.post("/{run_id}/qa-issues/delete")
def delete_run_qa_issues(
    run_id: str,
    payload: QAIssueDeleteRequest,
    db: Session = Depends(get_db),
) -> dict:
    run = get_run_or_404(db, run_id)
    if not run.final_output:
        raise HTTPException(status_code=409, detail="Workflow run has no generated result")
    if not payload.issue_indices:
        raise HTTPException(status_code=422, detail="issue_indices must not be empty")

    final_output = dict(run.final_output)
    qa_report = dict(final_output.get("qa_report") or {})
    issues = list(qa_report.get("issues") or [])
    unique_indices = sorted(set(payload.issue_indices), reverse=True)
    invalid_indices = [index for index in unique_indices if index < 0 or index >= len(issues)]
    if invalid_indices:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid QA issue indices: {invalid_indices}",
        )

    removed_issues = []
    for index in unique_indices:
        removed_issues.append(issues.pop(index))

    dismissed_issues = list(qa_report.get("dismissed_issues") or [])
    dismissed_issues.extend(
        {
            "issue": issue,
            "dismissed_at": models.utcnow().isoformat(),
            "reason": "operator_deleted",
        }
        for issue in reversed(removed_issues)
    )

    qa_report["issues"] = issues
    qa_report["dismissed_issues"] = dismissed_issues
    qa_report["needs_review_count"] = len(issues)
    qa_report["fail_count"] = sum(
        1
        for issue in issues
        if str(issue.get("severity") or "").lower() in {"critical", "high"}
    )
    if issues:
        qa_report["overall_status"] = "needs_review"
        qa_report["summary"] = f"선택한 QA 리뷰 {len(removed_issues)}건을 삭제했습니다. 현재 {len(issues)}건이 남아 있습니다."
        qa_report["pass_count"] = int(qa_report.get("pass_count") or 0)
    else:
        products = list(final_output.get("products") or [])
        qa_report["overall_status"] = "pass"
        qa_report["summary"] = "선택한 QA 리뷰가 삭제되어 현재 표시할 QA 이슈가 없습니다."
        qa_report["pass_count"] = len(products)

    final_output["qa_report"] = qa_report
    run.final_output = final_output
    db.commit()
    db.refresh(run)

    return ok(
        {
            "run": WorkflowRunRead.model_validate(run).model_dump(mode="json"),
            "qa_report": qa_report,
            "removed_count": len(removed_issues),
        }
    )


@router.get("/{run_id}/result")
def get_run_result(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = get_run_or_404(db, run_id)
    return ok(
        run.final_output
        or {
            "status": run.status,
            "message": "생성된 결과가 없습니다.",
            "error": run.error,
        }
    )


def _next_revision_number(db: Session, source_run_id: str) -> int:
    existing_revisions = (
        db.query(models.WorkflowRun)
        .filter(models.WorkflowRun.parent_run_id == source_run_id)
        .all()
    )
    if not existing_revisions:
        return 1
    return max(run.revision_number or 0 for run in existing_revisions) + 1


def _root_run(db: Session, run: models.WorkflowRun) -> models.WorkflowRun:
    if not run.parent_run_id:
        return run
    root = db.get(models.WorkflowRun, run.parent_run_id)
    if not root:
        raise HTTPException(status_code=409, detail="Root workflow run not found")
    return root


def _lineage_approvals(db: Session, root_run_id: str) -> list[models.Approval]:
    lineage_run_ids = [
        run.id
        for run in db.query(models.WorkflowRun)
        .filter(
            (models.WorkflowRun.id == root_run_id)
            | (models.WorkflowRun.parent_run_id == root_run_id)
        )
        .all()
    ]
    return (
        db.query(models.Approval)
        .filter(models.Approval.run_id.in_(lineage_run_ids))
        .order_by(models.Approval.created_at.asc())
        .all()
    )


def _request_changes_from_approvals(approvals: list[models.Approval]) -> list[str]:
    changes: list[str] = []
    for approval in sorted(approvals, key=lambda item: item.created_at):
        if approval.decision != "request_changes":
            continue
        metadata = approval.approval_metadata or {}
        requested = metadata.get("requested_changes") or []
        if isinstance(requested, list):
            changes.extend(str(item) for item in requested if str(item).strip())
        if approval.comment:
            changes.append(approval.comment)
    return changes
