from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.responses import ok
from app.core.config import get_settings
from app.db import models
from app.db.session import get_db
from app.llm.key_check import run_provider_key_check
from app.schemas.llm import LLMKeyCheckRequest

router = APIRouter(prefix="/llm", tags=["llm"])


@router.post("/key-check")
def check_llm_keys(payload: LLMKeyCheckRequest, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    run = models.WorkflowRun(
        template_id="default_product_planning",
        status="running",
        input={
            "message": "LLM key check",
            "providers": payload.providers,
            "max_output_tokens": payload.max_output_tokens,
        },
        started_at=models.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    results = [
        run_provider_key_check(
            db=db,
            run_id=run.id,
            provider=provider,
            settings=settings,
            max_output_tokens=payload.max_output_tokens,
        )
        for provider in payload.providers
    ]
    total_estimated_cost_usd = round(
        sum(result.get("estimated_cost_usd", 0.0) for result in results), 8
    )
    total_estimated_cost_krw = round(total_estimated_cost_usd * settings.usd_krw_rate, 4)
    run.status = "succeeded" if any(result["status"] == "succeeded" for result in results) else "failed"
    run.final_output = {
        "purpose": "llm_key_check",
        "results": results,
        "total_estimated_cost_usd": total_estimated_cost_usd,
        "total_estimated_cost_krw": total_estimated_cost_krw,
        "billing_note": (
            "이 엔드포인트는 실제 provider invoice를 조회하지 않습니다. "
            "API 응답의 token usage와 설정된 pricing table 기준 예상 비용만 llm_calls에 기록합니다."
        ),
    }
    run.cost_total_usd = total_estimated_cost_usd
    run.finished_at = models.utcnow()
    db.commit()

    return ok(
        {
            "run_id": run.id,
            **run.final_output,
        }
    )
