from __future__ import annotations

import hashlib
import time
from typing import Any, Literal

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import models
from app.llm.usage_log import safe_write_llm_usage_log

ProviderName = Literal["openai", "gemini"]

OPENAI_PRICING_USD_PER_1M = {
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
}

GEMINI_PRICING_USD_PER_1M = {
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
}

KEY_CHECK_PROMPT = "Reply with exactly: OK"


def run_provider_key_check(
    *,
    db: Session,
    run_id: str,
    provider: ProviderName,
    settings: Settings,
    max_output_tokens: int,
) -> dict[str, Any]:
    if provider == "openai":
        result = _check_openai(settings=settings, max_output_tokens=max_output_tokens)
    else:
        result = _check_gemini(settings=settings, max_output_tokens=max_output_tokens)

    _record_llm_call(db=db, run_id=run_id, result=result)
    return result


def _check_openai(*, settings: Settings, max_output_tokens: int) -> dict[str, Any]:
    model = settings.openai_check_model
    if not settings.openai_api_key:
        return _skipped_result("openai", model, "OPENAI_API_KEY is not configured")

    started = time.perf_counter()
    output_token_limit = max(max_output_tokens, 16)
    try:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": KEY_CHECK_PROMPT,
                "max_output_tokens": output_token_limit,
                "temperature": 0,
            },
            timeout=20,
        )
    except httpx.HTTPError as exc:
        return _failed_result("openai", model, started, {"message": str(exc)})

    if response.is_error:
        return _failed_result("openai", model, started, _safe_error(response))

    body = response.json()
    usage = body.get("usage") or {}
    prompt_tokens = int(usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    cost_usd = _estimate_cost(
        pricing=OPENAI_PRICING_USD_PER_1M,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return _success_result(
        provider="openai",
        model=model,
        started=started,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost_usd,
        billing_note=(
            "OpenAI 응답으로 API key 유효성과 token usage는 확인했지만, "
            "실제 청구/크레딧 차감 여부는 OpenAI billing dashboard에서만 확정할 수 있습니다."
        ),
    )


def _check_gemini(*, settings: Settings, max_output_tokens: int) -> dict[str, Any]:
    model = settings.gemini_check_model
    if not settings.gemini_api_key:
        return _skipped_result("gemini", model, "GEMINI_API_KEY is not configured")

    started = time.perf_counter()
    try:
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": settings.gemini_api_key},
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": KEY_CHECK_PROMPT}],
                    }
                ],
                "generationConfig": {
                    "maxOutputTokens": max_output_tokens,
                    "temperature": 0,
                },
            },
            timeout=20,
        )
    except httpx.HTTPError as exc:
        return _failed_result("gemini", model, started, {"message": str(exc)})

    if response.is_error:
        return _failed_result("gemini", model, started, _safe_error(response))

    body = response.json()
    usage = body.get("usageMetadata") or {}
    prompt_tokens = int(usage.get("promptTokenCount") or 0)
    completion_tokens = int(usage.get("candidatesTokenCount") or 0)
    total_tokens = int(usage.get("totalTokenCount") or prompt_tokens + completion_tokens)
    paid_equivalent_cost_usd = _estimate_cost(
        pricing=GEMINI_PRICING_USD_PER_1M,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    estimated_cost_usd = paid_equivalent_cost_usd
    return _success_result(
        provider="gemini",
        model=model,
        started=started,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
        paid_tier_equivalent_cost_usd=paid_equivalent_cost_usd,
        billing_note="Token usage와 pricing table 기반 Gemini 2.5 Flash-Lite paid tier 예상 비용을 cost_usd에 기록합니다.",
    )


def _record_llm_call(*, db: Session, run_id: str, result: dict[str, Any]) -> None:
    if result["status"] == "skipped":
        return

    purpose = "key_check" if result["status"] == "succeeded" else "key_check_failed"
    request_hash = _request_hash(result["provider"], result["model"])
    call = models.LLMCall(
        run_id=run_id,
        provider=result["provider"],
        model=result["model"],
        purpose=purpose,
        prompt_tokens=result.get("prompt_tokens", 0),
        completion_tokens=result.get("completion_tokens", 0),
        total_tokens=result.get("total_tokens", 0),
        cost_usd=result.get("estimated_cost_usd", 0),
        latency_ms=result.get("latency_ms"),
        cache_hit=False,
        request_hash=request_hash,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    safe_write_llm_usage_log(
        run_id=run_id,
        step_id=None,
        call_id=call.id,
        provider=result["provider"],
        model=result["model"],
        purpose=purpose,
        prompt_tokens=result.get("prompt_tokens", 0),
        completion_tokens=result.get("completion_tokens", 0),
        total_tokens=result.get("total_tokens", 0),
        cost_usd=result.get("estimated_cost_usd", 0),
        paid_tier_equivalent_cost_usd=result.get("paid_tier_equivalent_cost_usd", 0),
        latency_ms=result.get("latency_ms"),
        request_hash=request_hash,
    )


def _success_result(
    *,
    provider: ProviderName,
    model: str,
    started: float,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
    billing_note: str,
    paid_tier_equivalent_cost_usd: float | None = None,
) -> dict[str, Any]:
    result = {
        "provider": provider,
        "model": model,
        "status": "succeeded",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost_usd, 8),
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "billing_note": billing_note,
    }
    if paid_tier_equivalent_cost_usd is not None:
        result["paid_tier_equivalent_cost_usd"] = round(paid_tier_equivalent_cost_usd, 8)
    return result


def _failed_result(
    provider: ProviderName,
    model: str,
    started: float,
    error: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "status": "failed",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "error": error,
        "billing_note": "API 호출이 실패해 token usage와 과금 추정치가 없습니다.",
    }


def _skipped_result(provider: ProviderName, model: str, reason: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "status": "skipped",
        "reason": reason,
        "estimated_cost_usd": 0.0,
        "billing_note": "API key가 없어 외부 호출을 하지 않았습니다.",
    }


def _estimate_cost(
    *,
    pricing: dict[str, dict[str, float]],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    model_pricing = pricing.get(model)
    if not model_pricing:
        return 0.0
    return (
        prompt_tokens * model_pricing["input"] / 1_000_000
        + completion_tokens * model_pricing["output"] / 1_000_000
    )


def _safe_error(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        body = {"message": response.text[:500]}

    error = body.get("error", body) if isinstance(body, dict) else {"message": str(body)}
    return {
        "status_code": response.status_code,
        "type": error.get("type") or error.get("status") if isinstance(error, dict) else None,
        "message": (error.get("message") if isinstance(error, dict) else str(error))[:500],
    }


def _request_hash(provider: str, model: str) -> str:
    return hashlib.sha256(f"{provider}:{model}:{KEY_CHECK_PROMPT}".encode("utf-8")).hexdigest()[:32]
