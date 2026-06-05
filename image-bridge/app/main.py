from __future__ import annotations

import base64
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    image_bridge_token: str = ""
    image_bridge_model: str = "gpt-image-2"
    image_bridge_default_size: str = "1024x1536"
    image_bridge_default_quality: str = "low"
    image_bridge_public_base_url: str = ""
    image_bridge_storage_dir: str = "data/images"
    image_bridge_request_timeout_seconds: float = 120.0
    image_bridge_input_image_timeout_seconds: float = 20.0
    image_bridge_max_input_image_bytes: int = 20 * 1024 * 1024
    image_bridge_max_prompt_chars: int = 12000
    image_bridge_max_input_images: int = 3


settings = Settings()
app = FastAPI(title="PARAVOCA Ennoia Image Bridge", version="0.1.0")

storage_dir = Path(settings.image_bridge_storage_dir)
storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(storage_dir)), name="images")

_ALLOWED_SIZES = {"1024x1024", "1024x1536", "1536x1024", "auto"}
_ALLOWED_QUALITIES = {"low", "medium", "high", "auto"}
_ALLOWED_SCHEMES = {"http", "https"}


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    input_image_urls: list[str] = Field(default_factory=list)
    size: str | None = None
    quality: str | None = None
    model: str | None = None

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("prompt is required")
        if len(cleaned) > settings.image_bridge_max_prompt_chars:
            raise ValueError(f"prompt must be <= {settings.image_bridge_max_prompt_chars} characters")
        return cleaned

    @field_validator("input_image_urls")
    @classmethod
    def validate_input_image_urls(cls, value: list[str]) -> list[str]:
        if len(value) > settings.image_bridge_max_input_images:
            raise ValueError(f"input_image_urls must contain at most {settings.image_bridge_max_input_images} images")
        cleaned: list[str] = []
        for raw in value:
            url = raw.strip()
            if not url:
                continue
            parsed = urlparse(url)
            if parsed.scheme.lower() not in _ALLOWED_SCHEMES or not parsed.netloc:
                raise ValueError("input_image_urls must be http(s) URLs")
            cleaned.append(url)
        return cleaned

    @field_validator("size")
    @classmethod
    def validate_size(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in _ALLOWED_SIZES:
            raise ValueError(f"size must be one of {sorted(_ALLOWED_SIZES)}")
        return value

    @field_validator("quality")
    @classmethod
    def validate_quality(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in _ALLOWED_QUALITIES:
            raise ValueError(f"quality must be one of {sorted(_ALLOWED_QUALITIES)}")
        return value


class ImageGenerateResponse(BaseModel):
    image_url: str
    markdown: str
    image_id: str
    input_image_count: int
    model: str
    size: str
    quality: str
    provider_response_summary: dict[str, Any]
    latency_ms: int


def require_bearer_token(authorization: str | None = Header(default=None)) -> None:
    expected = settings.image_bridge_token.strip()
    if not expected:
        return
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization[len(prefix) :].strip()
    if token != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid bearer token")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model": settings.image_bridge_model,
        "storage_dir": str(storage_dir),
        "auth_configured": bool(settings.image_bridge_token.strip()),
    }


@app.post("/generate", response_model=ImageGenerateResponse, dependencies=[Depends(require_bearer_token)])
def generate_image(payload: ImageGenerateRequest, request: Request) -> ImageGenerateResponse:
    api_key = settings.openai_api_key.strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured")

    started = time.perf_counter()
    model = payload.model or settings.image_bridge_model
    size = payload.size or settings.image_bridge_default_size
    quality = payload.quality or settings.image_bridge_default_quality

    with httpx.Client(timeout=settings.image_bridge_request_timeout_seconds, follow_redirects=True) as client:
        if payload.input_image_urls:
            response = _call_image_edits(
                client=client,
                api_key=api_key,
                model=model,
                prompt=payload.prompt,
                size=size,
                quality=quality,
                input_image_urls=payload.input_image_urls,
            )
            endpoint = "images/edits"
        else:
            response = _call_image_generations(
                client=client,
                api_key=api_key,
                model=model,
                prompt=payload.prompt,
                size=size,
                quality=quality,
            )
            endpoint = "images/generations"

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "reason": "openai_image_request_failed",
                    "status_code": response.status_code,
                    "request_id": response.headers.get("x-request-id"),
                    "response": _safe_response_json(response),
                },
            )

        response_payload = response.json()
        image_bytes = _image_bytes_from_openai_response(client, response_payload)

    image_id, image_path = _new_timestamped_image_path()
    filename = image_path.name
    image_path.write_bytes(image_bytes)

    image_url = _public_image_url(request, filename)
    latency_ms = int((time.perf_counter() - started) * 1000)
    provider_summary = {
        "endpoint": endpoint,
        "request_id": response.headers.get("x-request-id"),
        "usage": response_payload.get("usage") if isinstance(response_payload, dict) else None,
        "output_format": response_payload.get("output_format") if isinstance(response_payload, dict) else "png",
    }
    return ImageGenerateResponse(
        image_url=image_url,
        markdown=f"![generated poster]({image_url})",
        image_id=image_id,
        input_image_count=len(payload.input_image_urls),
        model=model,
        size=size,
        quality=quality,
        provider_response_summary=provider_summary,
        latency_ms=latency_ms,
    )


def _new_timestamped_image_path() -> tuple[str, Path]:
    """Return a timestamp-based image id and path with microsecond precision.

    The UTC timestamp keeps filenames sortable and avoids characters that are
    awkward in URLs. A numeric suffix is used only if two writes land on the
    same microsecond or an existing file is present.
    """

    base_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    image_id = base_id
    image_path = storage_dir / f"{image_id}.png"
    suffix = 2
    while image_path.exists():
        image_id = f"{base_id}-{suffix}"
        image_path = storage_dir / f"{image_id}.png"
        suffix += 1
    return image_id, image_path


def _call_image_generations(
    *,
    client: httpx.Client,
    api_key: str,
    model: str,
    prompt: str,
    size: str,
    quality: str,
) -> httpx.Response:
    return client.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "prompt": prompt, "n": 1, "size": size, "quality": quality},
    )


def _call_image_edits(
    *,
    client: httpx.Client,
    api_key: str,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    input_image_urls: list[str],
) -> httpx.Response:
    image_files = _download_input_images(input_image_urls)
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for index, image in enumerate(image_files):
        files.append(("image[]", (f"image_{index}.{image['extension']}", image["bytes"], image["content_type"])))
    return client.post(
        "https://api.openai.com/v1/images/edits",
        headers={"Authorization": f"Bearer {api_key}"},
        data={"model": model, "prompt": prompt, "n": "1", "size": size, "quality": quality},
        files=files,
    )


def _download_input_images(urls: list[str]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    with httpx.Client(timeout=settings.image_bridge_input_image_timeout_seconds, follow_redirects=True) as client:
        for url in urls:
            response = client.get(url)
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail={"reason": "input_image_download_failed", "url": url, "status_code": response.status_code},
                )
            content = response.content
            if len(content) > settings.image_bridge_max_input_image_bytes:
                raise HTTPException(
                    status_code=400,
                    detail={"reason": "input_image_too_large", "url": url, "max_bytes": settings.image_bridge_max_input_image_bytes},
                )
            detected = _detect_image_type(content)
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if not detected and not content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail={"reason": "input_url_is_not_image", "url": url})
            extension = _extension_from_image_type(detected, content_type)
            images.append({"bytes": content, "content_type": _content_type_from_extension(extension), "extension": extension})
    return images


def _image_bytes_from_openai_response(client: httpx.Client, payload: dict[str, Any]) -> bytes:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise HTTPException(status_code=502, detail={"reason": "openai_response_missing_data"})

    first = data[0]
    b64_json = first.get("b64_json")
    if isinstance(b64_json, str) and b64_json:
        try:
            return base64.b64decode(b64_json)
        except ValueError as exc:
            raise HTTPException(status_code=502, detail={"reason": "openai_response_invalid_base64"}) from exc

    url = first.get("url")
    if isinstance(url, str) and url:
        response = client.get(url)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail={"reason": "openai_image_url_download_failed", "status_code": response.status_code})
        return response.content

    raise HTTPException(status_code=502, detail={"reason": "openai_response_missing_image"})


def _public_image_url(request: Request, filename: str) -> str:
    base = settings.image_bridge_public_base_url.strip().rstrip("/")
    if not base:
        base = str(request.base_url).rstrip("/")
    return f"{base}/images/{filename}"


def _safe_response_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"text": response.text[:1000]}


def _detect_image_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return "gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


def _extension_from_image_type(detected: str | None, content_type: str) -> str:
    if detected in {"jpeg", "png", "gif", "webp"}:
        return "jpg" if detected == "jpeg" else detected
    match = re.match(r"image/(png|jpeg|jpg|webp|gif)$", content_type)
    if match:
        value = match.group(1)
        return "jpg" if value == "jpeg" else value
    return "png"


def _content_type_from_extension(extension: str) -> str:
    if extension == "jpg":
        return "image/jpeg"
    return f"image/{extension}"
