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


def generate_poster_image(
    *,
    prompt: str,
    settings: Settings,
    input_images: list[str] | None = None,
) -> GeneratedPosterImage:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise PosterImageGenerationError(
            "OPENAI_API_KEY is not configured. 실제 포스터 이미지는 생성되지 않았습니다.",
            {"reason": "missing_openai_api_key"},
        )

    resolved_images = input_images or []
    input_image_count = len(resolved_images)
    use_edits_endpoint = input_image_count > 0

    started = time.perf_counter()

    try:
        with httpx.Client(timeout=settings.poster_image_timeout_seconds) as client:
            if use_edits_endpoint:
                response = _post_images_edits(
                    client=client,
                    api_key=api_key,
                    prompt=prompt,
                    image_urls=resolved_images,
                    settings=settings,
                )
            else:
                response = _post_images_generations(
                    client=client,
                    api_key=api_key,
                    prompt=prompt,
                    settings=settings,
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
                size=str(payload.get("size") or settings.poster_image_size),
                quality=str(payload.get("quality") or settings.poster_image_quality),
                settings=settings,
                input_image_count=input_image_count,
            )
            return GeneratedPosterImage(
                image_bytes=image_bytes,
                provider_response_summary={
                    "request_id": response.headers.get("x-request-id"),
                    "model": settings.poster_image_model,
                    "size": payload.get("size") or settings.poster_image_size,
                    "quality": payload.get("quality") or settings.poster_image_quality,
                    "output_format": payload.get("output_format") or "png",
                    "usage": usage,
                    "cost_breakdown": cost.as_dict(),
                    "input_image_count": input_image_count,
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


def _post_images_generations(
    *,
    client: httpx.Client,
    api_key: str,
    prompt: str,
    settings: Settings,
) -> httpx.Response:
    request_payload = {
        "model": settings.poster_image_model,
        "prompt": prompt,
        "n": 1,
        "size": settings.poster_image_size,
        "quality": settings.poster_image_quality,
    }
    return client.post(
        "https://api.openai.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=request_payload,
    )


def _post_images_edits(
    *,
    client: httpx.Client,
    api_key: str,
    prompt: str,
    image_urls: list[str],
    settings: Settings,
) -> httpx.Response:
    image_binaries = _resolve_image_binaries(client, api_key, image_urls)
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for idx, img_bytes in enumerate(image_binaries):
        files.append(("image[]", (f"image_{idx}.png", img_bytes, "image/png")))

    form_data = {
        "model": settings.poster_image_model,
        "prompt": prompt,
        "n": "1",
        "size": settings.poster_image_size,
        "quality": settings.poster_image_quality,
    }
    return client.post(
        "https://api.openai.com/v1/images/edits",
        headers={"Authorization": f"Bearer {api_key}"},
        data=form_data,
        files=files,
    )


def _resolve_image_binaries(
    client: httpx.Client,
    api_key: str,
    image_urls: list[str],
) -> list[bytes]:
    result: list[bytes] = []
    for url in image_urls:
        url = url.strip()
        if not url:
            continue
        if url.startswith("data:"):
            # data URI: data:image/png;base64,<encoded>
            _, _, encoded = url.partition(",")
            try:
                result.append(base64.b64decode(encoded))
            except ValueError as exc:
                raise PosterImageGenerationError(
                    "Input image data URI contains invalid base64.",
                    {"reason": "invalid_input_image_base64"},
                ) from exc
        elif url.startswith("http://") or url.startswith("https://"):
            response = client.get(url)
            if response.status_code >= 400:
                raise PosterImageGenerationError(
                    f"Input image could not be downloaded: {url}",
                    {
                        "reason": "input_image_download_failed",
                        "status_code": response.status_code,
                        "url": url,
                    },
                )
            result.append(response.content)
        else:
            # Treat as raw base64 string
            try:
                result.append(base64.b64decode(url))
            except ValueError as exc:
                raise PosterImageGenerationError(
                    "Input image string is not a valid URL or base64.",
                    {"reason": "invalid_input_image_format"},
                ) from exc
    return result


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
