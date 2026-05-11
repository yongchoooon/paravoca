from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import models
from app.llm.usage_log import safe_write_llm_usage_log

logger = logging.getLogger("uvicorn.error")

GEMINI_PRICING_USD_PER_1M = {
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
}


class GeminiGatewayError(RuntimeError):
    pass


@dataclass
class GeminiJsonResult:
    data: dict[str, Any]
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    paid_tier_equivalent_cost_usd: float
    latency_ms: int
    raw_text: str


def call_gemini_json(
    *,
    db: Session,
    run_id: str,
    step_id: str,
    purpose: str,
    prompt: str,
    response_schema: dict[str, Any],
    max_output_tokens: int = 2048,
    temperature: float = 0.2,
    settings: Settings | None = None,
    _json_retry_attempt: int = 0,
    _original_prompt: str | None = None,
) -> GeminiJsonResult:
    settings = settings or get_settings()
    model = settings.gemini_generation_model
    started = time.perf_counter()
    original_prompt = _original_prompt or prompt
    full_prompt = _build_json_prompt(prompt=prompt, response_schema=response_schema)
    timeout_seconds = max(1.0, float(settings.gemini_timeout_seconds))
    debug_request_config = {
        "maxOutputTokens": max_output_tokens,
        "temperature": temperature,
        "timeoutSeconds": timeout_seconds,
    }

    if not settings.gemini_api_key:
        latency_ms = int((time.perf_counter() - started) * 1000)
        call_id = _record_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            provider="gemini",
            model=model,
            purpose=f"{purpose}_failed",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            paid_tier_equivalent_cost_usd=0.0,
            latency_ms=latency_ms,
            request_hash=_request_hash(full_prompt),
        )
        _write_prompt_debug_log(
            db=db,
            settings=settings,
            run_id=run_id,
            step_id=step_id,
            call_id=call_id,
            purpose=purpose,
            model=model,
            status="failed",
            prompt=prompt,
            full_prompt=full_prompt,
            original_prompt=original_prompt,
            response_schema=response_schema,
            request_config=debug_request_config,
            usage={},
            finish_reason=None,
            raw_text=None,
            parsed=None,
            error={"type": "GeminiGatewayError", "message": "GEMINI_API_KEY is not configured"},
            latency_ms=latency_ms,
            json_retry_attempt=_json_retry_attempt,
        )
        raise GeminiGatewayError("GEMINI_API_KEY is not configured")

    response: httpx.Response | None = None
    last_http_error: httpx.HTTPError | None = None
    request_payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": full_prompt}],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    max_retries = max(0, int(settings.gemini_max_retries))
    for attempt in range(max_retries + 1):
        try:
            response = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": settings.gemini_api_key},
                json=request_payload,
                timeout=timeout_seconds,
            )
            if response.is_error and _is_retryable_response(response) and attempt < max_retries:
                delay = _retry_delay_seconds(attempt=attempt, response=response, settings=settings)
                logger.warning(
                    "Gemini retryable response. run_id=%s step_id=%s purpose=%s model=%s "
                    "status_code=%s attempt=%s/%s retry_after_seconds=%.2f error=%s",
                    run_id,
                    step_id,
                    purpose,
                    model,
                    response.status_code,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                    _safe_error_message(response),
                )
                time.sleep(delay)
                continue
            last_http_error = None
            break
        except httpx.HTTPError as exc:
            last_http_error = exc
            if not _is_retryable_http_error(exc) or attempt >= max_retries:
                break
            delay = _retry_delay_seconds(attempt=attempt, response=None, settings=settings)
            logger.warning(
                "Gemini retryable transport error. run_id=%s step_id=%s purpose=%s model=%s "
                "attempt=%s/%s retry_after_seconds=%.2f error=%s",
                run_id,
                step_id,
                purpose,
                model,
                attempt + 1,
                max_retries + 1,
                delay,
                exc,
            )
            time.sleep(delay)

    if last_http_error is not None:
        latency_ms = int((time.perf_counter() - started) * 1000)
        call_id = _record_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            provider="gemini",
            model=model,
            purpose=f"{purpose}_failed",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            paid_tier_equivalent_cost_usd=0.0,
            latency_ms=latency_ms,
            request_hash=_request_hash(full_prompt),
        )
        _write_prompt_debug_log(
            db=db,
            settings=settings,
            run_id=run_id,
            step_id=step_id,
            call_id=call_id,
            purpose=purpose,
            model=model,
            status="failed",
            prompt=prompt,
            full_prompt=full_prompt,
            original_prompt=original_prompt,
            response_schema=response_schema,
            request_config=debug_request_config,
            usage={},
            finish_reason=None,
            raw_text=None,
            parsed=None,
            error={"type": last_http_error.__class__.__name__, "message": str(last_http_error)},
            latency_ms=latency_ms,
            json_retry_attempt=_json_retry_attempt,
        )
        raise GeminiGatewayError(str(last_http_error)) from last_http_error

    if response is None:
        raise GeminiGatewayError("Gemini request did not return a response")

    latency_ms = int((time.perf_counter() - started) * 1000)
    if response.is_error:
        error_message = _safe_error_message(response)
        call_id = _record_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            provider="gemini",
            model=model,
            purpose=f"{purpose}_failed",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            paid_tier_equivalent_cost_usd=0.0,
            latency_ms=latency_ms,
            request_hash=_request_hash(full_prompt),
        )
        _write_prompt_debug_log(
            db=db,
            settings=settings,
            run_id=run_id,
            step_id=step_id,
            call_id=call_id,
            purpose=purpose,
            model=model,
            status="failed",
            prompt=prompt,
            full_prompt=full_prompt,
            original_prompt=original_prompt,
            response_schema=response_schema,
            request_config=debug_request_config,
            usage={},
            finish_reason=None,
            raw_text=_response_debug_body(response),
            parsed=None,
            error={"type": "GeminiHTTPError", "message": error_message, "status_code": response.status_code},
            latency_ms=latency_ms,
            json_retry_attempt=_json_retry_attempt,
        )
        raise GeminiGatewayError(error_message)

    body = response.json()
    finish_reason = _finish_reason(body)
    usage = body.get("usageMetadata") or {}
    prompt_tokens = int(usage.get("promptTokenCount") or 0)
    completion_tokens = int(usage.get("candidatesTokenCount") or 0)
    total_tokens = int(usage.get("totalTokenCount") or prompt_tokens + completion_tokens)
    paid_equivalent_cost_usd = _estimate_cost(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    cost_usd = paid_equivalent_cost_usd
    try:
        raw_text = _extract_text(body)
        if finish_reason == "MAX_TOKENS":
            raise GeminiGatewayError(
                f"Gemini response was truncated by maxOutputTokens for {purpose}"
            )
        parsed = _parse_json(raw_text)
        _validate_json_schema(parsed, response_schema)
    except GeminiGatewayError as exc:
        raw_preview = ""
        if "raw_text" in locals():
            raw_preview = raw_text[-800:]
        logger.exception(
            "Gemini JSON handling failed. run_id=%s step_id=%s purpose=%s model=%s "
            "finish_reason=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s raw_tail=%r",
            run_id,
            step_id,
            purpose,
            model,
            finish_reason,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            raw_preview,
        )
        print(
            "[gemini-json-failed] "
            f"run_id={run_id} step_id={step_id} purpose={purpose} model={model} "
            f"finish_reason={finish_reason} prompt_tokens={prompt_tokens} "
            f"completion_tokens={completion_tokens} total_tokens={total_tokens} "
            f"error={exc} raw_tail={raw_preview!r}",
            file=sys.stderr,
            flush=True,
        )
        max_json_retries = max(0, int(settings.gemini_json_max_retries))
        will_retry_json = _json_retry_attempt < max_json_retries
        call_id = _record_call(
            db=db,
            run_id=run_id,
            step_id=step_id,
            provider="gemini",
            model=model,
            purpose=f"{purpose}_invalid_json_retry" if will_retry_json else f"{purpose}_failed",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            paid_tier_equivalent_cost_usd=paid_equivalent_cost_usd,
            latency_ms=latency_ms,
            request_hash=_request_hash(full_prompt),
        )
        _write_prompt_debug_log(
            db=db,
            settings=settings,
            run_id=run_id,
            step_id=step_id,
            call_id=call_id,
            purpose=purpose,
            model=model,
            status="retrying" if will_retry_json else "failed",
            prompt=prompt,
            full_prompt=full_prompt,
            original_prompt=original_prompt,
            response_schema=response_schema,
            request_config=debug_request_config,
            usage=usage,
            finish_reason=finish_reason,
            raw_text=raw_text if "raw_text" in locals() else None,
            parsed=None,
            error={"type": exc.__class__.__name__, "message": str(exc)},
            latency_ms=latency_ms,
            json_retry_attempt=_json_retry_attempt,
        )
        if will_retry_json:
            delay = min(0.5 * (_json_retry_attempt + 1), 2.0)
            logger.warning(
                "Retrying Gemini call after invalid JSON. run_id=%s step_id=%s purpose=%s "
                "model=%s json_attempt=%s/%s retry_after_seconds=%.2f error=%s",
                run_id,
                step_id,
                purpose,
                model,
                _json_retry_attempt + 1,
                max_json_retries,
                delay,
                exc,
            )
            time.sleep(delay)
            return call_gemini_json(
                db=db,
                run_id=run_id,
                step_id=step_id,
                purpose=purpose,
                prompt=_build_json_retry_prompt(
                    prompt=original_prompt,
                    error=str(exc),
                    attempt=_json_retry_attempt + 1,
                ),
                response_schema=response_schema,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                settings=settings,
                _json_retry_attempt=_json_retry_attempt + 1,
                _original_prompt=original_prompt,
            )
        raise

    call_id = _record_call(
        db=db,
        run_id=run_id,
        step_id=step_id,
        provider="gemini",
        model=model,
        purpose=purpose,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        paid_tier_equivalent_cost_usd=paid_equivalent_cost_usd,
        latency_ms=latency_ms,
        request_hash=_request_hash(full_prompt),
    )
    _write_prompt_debug_log(
        db=db,
        settings=settings,
        run_id=run_id,
        step_id=step_id,
        call_id=call_id,
        purpose=purpose,
        model=model,
        status="succeeded",
        prompt=prompt,
        full_prompt=full_prompt,
        original_prompt=original_prompt,
        response_schema=response_schema,
        request_config=debug_request_config,
        usage=usage,
        finish_reason=finish_reason,
        raw_text=raw_text,
        parsed=parsed,
        error=None,
        latency_ms=latency_ms,
        json_retry_attempt=_json_retry_attempt,
    )

    return GeminiJsonResult(
        data=parsed,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        paid_tier_equivalent_cost_usd=paid_equivalent_cost_usd,
        latency_ms=latency_ms,
        raw_text=raw_text,
    )


def _build_json_prompt(*, prompt: str, response_schema: dict[str, Any]) -> str:
    return (
        "당신은 PARAVOCA AX Agent Studio의 백엔드 에이전트입니다.\n"
        "반드시 유효한 JSON 객체 하나만 반환하세요. 첫 글자는 {, 마지막 글자는 } 여야 합니다.\n"
        "JSON을 markdown 코드블록으로 감싸지 말고, JSON 뒤에 두 번째 객체나 설명 문장을 붙이지 마세요.\n"
        "작업 입력에 없는 금지 기준을 새로 만들지 말고, 작업 입력의 규칙 안에서만 판단하세요.\n"
        "모든 상품과 주장은 제공된 근거 문서에 근거해야 합니다.\n"
        "사용자에게 보이는 모든 텍스트 값은 한국어로 작성하세요.\n\n"
        f"JSON 스키마:\n{json.dumps(response_schema, ensure_ascii=False)}\n\n"
        f"작업 입력:\n{prompt}"
    )


def _build_json_retry_prompt(*, prompt: str, error: str, attempt: int) -> str:
    return (
        f"이전 응답이 JSON 파싱 또는 스키마 검증에 실패했습니다. 재시도 {attempt}회차입니다.\n"
        f"이전 오류: {error}\n"
        "이번 응답은 반드시 단일 JSON 객체 하나만 반환하세요.\n"
        "JSON 앞뒤에 설명, markdown, 두 번째 JSON 객체, trailing comma, 주석을 절대 붙이지 마세요.\n\n"
        f"원래 작업 입력:\n{prompt}"
    )


def _extract_text(body: dict[str, Any]) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        raise GeminiGatewayError("Gemini response has no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise GeminiGatewayError("Gemini response text is empty")
    return text


def _finish_reason(body: dict[str, Any]) -> str | None:
    candidates = body.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        return None
    return candidates[0].get("finishReason")


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        if exc.msg == "Extra data":
            try:
                value, end = json.JSONDecoder().raw_decode(cleaned)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(value, dict) and cleaned[end:].strip():
                    logger.warning(
                        "Gemini JSON response had extra trailing data; using first JSON object. "
                        "trailing_chars=%s",
                        len(cleaned[end:].strip()),
                    )
                    return value
        raise GeminiGatewayError(f"Gemini returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise GeminiGatewayError("Gemini JSON response must be an object")
    return value


def _validate_json_schema(payload: dict[str, Any], schema: dict[str, Any], path: str = "$") -> None:
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(payload, dict):
        raise GeminiGatewayError(f"{path} must be an object")

    required = schema.get("required") or []
    for key in required:
        if key not in payload:
            raise GeminiGatewayError(f"{path}.{key} is required")

    properties = schema.get("properties") or {}
    required_set = set(required)
    for key, child_schema in properties.items():
        if key not in payload:
            continue
        if payload[key] is None and key not in required_set:
            continue
        _validate_json_value(payload[key], child_schema, f"{path}.{key}")


def _validate_json_value(value: Any, schema: dict[str, Any], path: str) -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            raise GeminiGatewayError(f"{path} must be an object")
        _validate_json_schema(value, schema, path)
    elif expected_type == "array":
        if not isinstance(value, list):
            raise GeminiGatewayError(f"{path} must be an array")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_json_value(item, item_schema, f"{path}[{index}]")
    elif expected_type == "string" and not isinstance(value, str):
        raise GeminiGatewayError(f"{path} must be a string")
    elif expected_type == "integer" and not isinstance(value, int):
        raise GeminiGatewayError(f"{path} must be an integer")
    elif expected_type == "number" and not isinstance(value, (int, float)):
        raise GeminiGatewayError(f"{path} must be a number")
    elif expected_type == "boolean" and not isinstance(value, bool):
        raise GeminiGatewayError(f"{path} must be a boolean")


def _record_call(
    *,
    db: Session,
    run_id: str,
    step_id: str,
    provider: str,
    model: str,
    purpose: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost_usd: float,
    paid_tier_equivalent_cost_usd: float,
    latency_ms: int,
    request_hash: str,
) -> str:
    call = models.LLMCall(
        run_id=run_id,
        step_id=step_id,
        provider=provider,
        model=model,
        purpose=purpose,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        cache_hit=False,
        request_hash=request_hash,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    safe_write_llm_usage_log(
        run_id=run_id,
        step_id=step_id,
        call_id=call.id,
        provider=provider,
        model=model,
        purpose=purpose,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        paid_tier_equivalent_cost_usd=paid_tier_equivalent_cost_usd,
        latency_ms=latency_ms,
        request_hash=request_hash,
    )
    return call.id


def _write_prompt_debug_log(
    *,
    db: Session,
    settings: Settings,
    run_id: str,
    step_id: str,
    call_id: str,
    purpose: str,
    model: str,
    status: str,
    prompt: str,
    full_prompt: str,
    original_prompt: str,
    response_schema: dict[str, Any],
    request_config: dict[str, Any],
    usage: dict[str, Any],
    finish_reason: str | None,
    raw_text: str | None,
    parsed: dict[str, Any] | None,
    error: dict[str, Any] | None,
    latency_ms: int,
    json_retry_attempt: int,
) -> None:
    if not settings.llm_prompt_debug_log_enabled:
        return
    try:
        agent_name = _agent_name_for_step(db, step_id)
        run_dir = Path(settings.llm_prompt_debug_log_dir) / _safe_filename(run_id or "no-run")
        run_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        filename = "__".join(
            [
                timestamp,
                _safe_filename(agent_name or "unknown-agent"),
                _safe_filename(purpose),
                _safe_filename(step_id or "no-step"),
                f"retry-{json_retry_attempt}",
                _safe_filename(status),
            ]
        )
        payload = {
            "timestamp": timestamp,
            "run_id": run_id,
            "step_id": step_id,
            "call_id": call_id,
            "agent_name": agent_name,
            "provider": "gemini",
            "model": model,
            "purpose": purpose,
            "status": status,
            "json_retry_attempt": json_retry_attempt,
            "request": {
                "config": request_config,
                "response_schema": response_schema,
                "input_prompt": prompt,
                "original_prompt": original_prompt,
                "full_prompt": full_prompt,
                "request_hash": _request_hash(full_prompt),
            },
            "response": {
                "finish_reason": finish_reason,
                "usage": usage,
                "raw_text": raw_text,
                "parsed_json": parsed,
                "error": error,
            },
            "latency_ms": latency_ms,
        }
        (run_dir / f"{filename}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / f"{filename}.md").write_text(
            _render_prompt_debug_markdown(payload),
            encoding="utf-8",
        )
    except Exception:
        logger.exception(
            "Failed to write Gemini prompt debug log. run_id=%s step_id=%s purpose=%s",
            run_id,
            step_id,
            purpose,
        )


def _render_prompt_debug_markdown(payload: dict[str, Any]) -> str:
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    lines = [
        f"# {payload.get('agent_name') or 'Unknown Agent'} / {payload.get('purpose') or 'unknown'}",
        "",
        "## Metadata",
        "",
        f"- run_id: `{payload.get('run_id')}`",
        f"- step_id: `{payload.get('step_id')}`",
        f"- call_id: `{payload.get('call_id')}`",
        f"- provider/model: `{payload.get('provider')}/{payload.get('model')}`",
        f"- status: `{payload.get('status')}`",
        f"- retry: `{payload.get('json_retry_attempt')}`",
        f"- finish_reason: `{response.get('finish_reason')}`",
        f"- latency_ms: `{payload.get('latency_ms')}`",
        "",
        "## Request Config",
        "",
        _fenced_json(request.get("config")),
        "",
        "## Usage",
        "",
        _fenced_json(response.get("usage")),
        "",
        "## Input Prompt",
        "",
        _fenced_text(str(request.get("input_prompt") or "")),
        "",
        "## Full Prompt Sent To Gemini",
        "",
        _fenced_text(str(request.get("full_prompt") or "")),
        "",
        "## Raw Output",
        "",
        _fenced_text(str(response.get("raw_text") or "")),
        "",
        "## Parsed JSON",
        "",
        _fenced_json(response.get("parsed_json")),
    ]
    if response.get("error"):
        lines.extend(["", "## Error", "", _fenced_json(response.get("error"))])
    return "\n".join(lines).rstrip() + "\n"


def _fenced_text(value: str) -> str:
    return f"```text\n{_escape_fence(value)}\n```"


def _fenced_json(value: Any) -> str:
    return f"```json\n{_escape_fence(json.dumps(value or {}, ensure_ascii=False, indent=2))}\n```"


def _escape_fence(value: str) -> str:
    return value.replace("```", "`` `")


def _estimate_cost(*, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = GEMINI_PRICING_USD_PER_1M.get(model)
    if not pricing:
        return 0.0
    return (
        prompt_tokens * pricing["input"] / 1_000_000
        + completion_tokens * pricing["output"] / 1_000_000
    )


def _safe_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    error = body.get("error", body) if isinstance(body, dict) else body
    if isinstance(error, dict):
        return str(error.get("message") or error.get("status") or error)[:500]
    return str(error)[:500]


def _response_debug_body(response: httpx.Response) -> str:
    try:
        return json.dumps(response.json(), ensure_ascii=False)
    except ValueError:
        return response.text


def _agent_name_for_step(db: Session, step_id: str) -> str | None:
    if not step_id:
        return None
    try:
        step = db.get(models.AgentStep, step_id)
    except Exception:
        return None
    if not step:
        return None
    return step.agent_name


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return cleaned.strip("._")[:120] or "unknown"


def _is_retryable_response(response: httpx.Response) -> bool:
    if response.status_code in {429, 500, 502, 503, 504}:
        return True
    message = _safe_error_message(response).lower()
    return any(
        keyword in message
        for keyword in (
            "high demand",
            "overloaded",
            "temporarily overloaded",
            "temporarily unavailable",
            "try again later",
            "resource exhausted",
            "rate limit",
            "quota exceeded",
        )
    )


def _is_retryable_http_error(exc: httpx.HTTPError) -> bool:
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError))


def _retry_delay_seconds(
    *,
    attempt: int,
    response: httpx.Response | None,
    settings: Settings,
) -> float:
    retry_after = _retry_after_seconds(response)
    if retry_after is not None:
        return min(retry_after, float(settings.gemini_retry_max_seconds))

    base = max(0.1, float(settings.gemini_retry_base_seconds))
    cap = max(base, float(settings.gemini_retry_max_seconds))
    delay = base * (2 ** attempt)
    jitter = random.uniform(0, base)
    return min(delay + jitter, cap)


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    raw_value = response.headers.get("retry-after")
    if not raw_value:
        return None
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        return None


def _request_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:32]
