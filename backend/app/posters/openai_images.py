from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.posters.costs import estimate_poster_image_cost


class PosterImageGenerationError(RuntimeError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class GeneratedPosterImage:
    image_bytes: bytes
    provider_response_summary: dict[str, Any]
    latency_ms: int
    cost_usd: float


def generate_poster_image(*, prompt: str, settings: Settings) -> GeneratedPosterImage:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise PosterImageGenerationError(
            "OPENAI_API_KEY is not configured. 실제 포스터 이미지는 생성되지 않았습니다.",
            {"reason": "missing_openai_api_key"},
        )

    request_payload = {
        "model": settings.poster_image_model,
        "prompt": prompt,
        "n": 1,
        "size": settings.poster_image_size,
        "quality": settings.poster_image_quality,
    }
    started = time.perf_counter()

    try:
        with httpx.Client(timeout=settings.poster_image_timeout_seconds) as client:
            response = client.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if response.status_code >= 400:
                raise PosterImageGenerationError(
                    _openai_error_message(response),
                    {
                        "reason": "openai_image_generation_failed",
                        "status_code": response.status_code,
                        "response": _safe_response_json(response),
                        "request_id": response.headers.get("x-request-id"),
                    },
                )
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list) or not data:
                raise PosterImageGenerationError(
                    "OpenAI image response did not contain image data.",
                    {
                        "reason": "openai_image_response_missing_data",
                        "request_id": response.headers.get("x-request-id"),
                    },
                )
            first = data[0] if isinstance(data[0], dict) else {}
            image_bytes = _image_bytes_from_response(client, first)
            if not image_bytes:
                raise PosterImageGenerationError(
                    "OpenAI image response did not contain b64_json or a downloadable URL.",
                    {
                        "reason": "openai_image_response_missing_image",
                        "request_id": response.headers.get("x-request-id"),
                    },
                )
            usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
            cost = estimate_poster_image_cost(
                prompt=prompt,
                usage=usage,
                size=str(payload.get("size") or request_payload["size"]),
                quality=str(payload.get("quality") or request_payload["quality"]),
                settings=settings,
            )
            return GeneratedPosterImage(
                image_bytes=image_bytes,
                provider_response_summary={
                    "request_id": response.headers.get("x-request-id"),
                    "model": request_payload["model"],
                    "size": payload.get("size") or request_payload["size"],
                    "quality": payload.get("quality") or request_payload["quality"],
                    "output_format": payload.get("output_format") or "png",
                    "usage": usage,
                    "cost_breakdown": cost.as_dict(),
                },
                latency_ms=latency_ms,
                cost_usd=cost.total_cost_usd,
            )
    except PosterImageGenerationError:
        raise
    except httpx.TimeoutException as exc:
        raise PosterImageGenerationError(
            "OpenAI image generation timed out.",
            {"reason": "openai_image_generation_timeout", "error": str(exc)},
        ) from exc
    except httpx.HTTPError as exc:
        raise PosterImageGenerationError(
            "OpenAI image generation request failed.",
            {"reason": "openai_image_generation_request_error", "error": str(exc)},
        ) from exc


def _image_bytes_from_response(client: httpx.Client, image_data: dict[str, Any]) -> bytes:
    b64_json = image_data.get("b64_json")
    if isinstance(b64_json, str) and b64_json:
        try:
            return base64.b64decode(b64_json)
        except ValueError as exc:
            raise PosterImageGenerationError(
                "OpenAI image response contained invalid base64 data.",
                {"reason": "invalid_openai_image_base64"},
            ) from exc

    image_url = image_data.get("url")
    if isinstance(image_url, str) and image_url:
        response = client.get(image_url)
        if response.status_code >= 400:
            raise PosterImageGenerationError(
                "OpenAI image URL could not be downloaded.",
                {
                    "reason": "openai_image_url_download_failed",
                    "status_code": response.status_code,
                },
            )
        return response.content
    return b""


def _openai_error_message(response: httpx.Response) -> str:
    payload = _safe_response_json(response)
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return f"OpenAI image generation failed with HTTP {response.status_code}."


def _safe_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {"text": response.text[:1000]}
    return payload if isinstance(payload, dict) else {"payload": payload}
