from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings


OUTPUT_IMAGE_TOKEN_ESTIMATES: dict[tuple[str, str], int] = {
    ("low", "1024x1024"): 272,
    ("low", "1024x1536"): 408,
    ("low", "1536x1024"): 400,
    ("medium", "1024x1024"): 1056,
    ("medium", "1024x1536"): 1584,
    ("medium", "1536x1024"): 1568,
    ("high", "1024x1024"): 4160,
    ("high", "1024x1536"): 6240,
    ("high", "1536x1024"): 6208,
}


@dataclass(frozen=True)
class PosterCostBreakdown:
    total_cost_usd: float
    total_cost_krw: float
    usd_krw_rate: float
    basis: str
    text_input_tokens: int
    text_cached_input_tokens: int
    image_input_tokens: int
    image_cached_input_tokens: int
    image_output_tokens: int
    text_input_cost_usd: float
    text_cached_input_cost_usd: float
    image_input_cost_usd: float
    image_cached_input_cost_usd: float
    image_output_cost_usd: float
    text_input_cost_krw: float
    text_cached_input_cost_krw: float
    image_input_cost_krw: float
    image_cached_input_cost_krw: float
    image_output_cost_krw: float
    pricing: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_cost_usd": self.total_cost_usd,
            "total_cost_krw": self.total_cost_krw,
            "usd_krw_rate": self.usd_krw_rate,
            "basis": self.basis,
            "tokens": {
                "text_input": self.text_input_tokens,
                "text_cached_input": self.text_cached_input_tokens,
                "image_input": self.image_input_tokens,
                "image_cached_input": self.image_cached_input_tokens,
                "image_output": self.image_output_tokens,
                "total": (
                    self.text_input_tokens
                    + self.text_cached_input_tokens
                    + self.image_input_tokens
                    + self.image_cached_input_tokens
                    + self.image_output_tokens
                ),
            },
            "costs_usd": {
                "text_input": self.text_input_cost_usd,
                "text_cached_input": self.text_cached_input_cost_usd,
                "image_input": self.image_input_cost_usd,
                "image_cached_input": self.image_cached_input_cost_usd,
                "image_output": self.image_output_cost_usd,
            },
            "costs_krw": {
                "text_input": self.text_input_cost_krw,
                "text_cached_input": self.text_cached_input_cost_krw,
                "image_input": self.image_input_cost_krw,
                "image_cached_input": self.image_cached_input_cost_krw,
                "image_output": self.image_output_cost_krw,
            },
            "pricing_per_million_tokens_usd": self.pricing,
        }


def estimate_poster_image_cost(
    *,
    prompt: str,
    usage: dict[str, Any] | None,
    size: str,
    quality: str,
    settings: Settings,
    input_image_count: int = 0,
) -> PosterCostBreakdown:
    pricing = {
        "text_input": settings.poster_text_input_cost_per_million_tokens_usd,
        "text_cached_input": settings.poster_text_cached_input_cost_per_million_tokens_usd,
        "image_input": settings.poster_image_input_cost_per_million_tokens_usd,
        "image_cached_input": settings.poster_image_cached_input_cost_per_million_tokens_usd,
        "image_output": settings.poster_image_output_cost_per_million_tokens_usd,
    }
    parsed = _parse_usage(usage)
    if parsed:
        basis = "openai_usage"
        text_input_tokens = parsed["text_input_tokens"]
        text_cached_input_tokens = parsed["text_cached_input_tokens"]
        image_input_tokens = parsed["image_input_tokens"]
        image_cached_input_tokens = parsed["image_cached_input_tokens"]
        image_output_tokens = parsed["image_output_tokens"]
    else:
        basis = "local_estimate_from_prompt_chars_and_size_quality"
        text_input_tokens = _estimate_text_tokens(prompt)
        text_cached_input_tokens = 0
        image_input_tokens = _estimate_image_input_tokens(input_image_count)
        image_cached_input_tokens = 0
        image_output_tokens = output_image_token_estimate(size=size, quality=quality)

    text_input_cost = _token_cost(text_input_tokens, pricing["text_input"])
    text_cached_input_cost = _token_cost(text_cached_input_tokens, pricing["text_cached_input"])
    image_input_cost = _token_cost(image_input_tokens, pricing["image_input"])
    image_cached_input_cost = _token_cost(image_cached_input_tokens, pricing["image_cached_input"])
    image_output_cost = _token_cost(image_output_tokens, pricing["image_output"])
    total = round(
        text_input_cost
        + text_cached_input_cost
        + image_input_cost
        + image_cached_input_cost
        + image_output_cost,
        8,
    )
    usd_krw_rate = float(settings.usd_krw_rate or 0)
    return PosterCostBreakdown(
        total_cost_usd=total,
        total_cost_krw=_krw_cost(total, usd_krw_rate),
        usd_krw_rate=usd_krw_rate,
        basis=basis,
        text_input_tokens=text_input_tokens,
        text_cached_input_tokens=text_cached_input_tokens,
        image_input_tokens=image_input_tokens,
        image_cached_input_tokens=image_cached_input_tokens,
        image_output_tokens=image_output_tokens,
        text_input_cost_usd=text_input_cost,
        text_cached_input_cost_usd=text_cached_input_cost,
        image_input_cost_usd=image_input_cost,
        image_cached_input_cost_usd=image_cached_input_cost,
        image_output_cost_usd=image_output_cost,
        text_input_cost_krw=_krw_cost(text_input_cost, usd_krw_rate),
        text_cached_input_cost_krw=_krw_cost(text_cached_input_cost, usd_krw_rate),
        image_input_cost_krw=_krw_cost(image_input_cost, usd_krw_rate),
        image_cached_input_cost_krw=_krw_cost(image_cached_input_cost, usd_krw_rate),
        image_output_cost_krw=_krw_cost(image_output_cost, usd_krw_rate),
        pricing=pricing,
    )


def output_image_token_estimate(*, size: str, quality: str) -> int:
    key = (quality.lower(), size)
    if key in OUTPUT_IMAGE_TOKEN_ESTIMATES:
        return OUTPUT_IMAGE_TOKEN_ESTIMATES[key]
    return OUTPUT_IMAGE_TOKEN_ESTIMATES[("medium", "1024x1536")]


def _parse_usage(usage: dict[str, Any] | None) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None
    details = usage.get("input_tokens_details")
    details = details if isinstance(details, dict) else {}
    output_details = usage.get("output_tokens_details")
    output_details = output_details if isinstance(output_details, dict) else {}

    text_cached = _int_token(
        details.get("cached_text_tokens")
        or details.get("cached_tokens_text")
        or details.get("cached_tokens", 0)
    )
    image_cached = _int_token(
        details.get("cached_image_tokens") or details.get("cached_tokens_image") or 0
    )
    text_total = _int_token(details.get("text_tokens"))
    image_total = _int_token(details.get("image_tokens"))
    input_total = _int_token(usage.get("input_tokens"))

    if text_total == 0 and image_total == 0 and input_total > 0:
        text_total = input_total

    image_output = _int_token(
        output_details.get("image_tokens")
        or output_details.get("image_output_tokens")
        or usage.get("output_tokens")
    )

    if text_total == 0 and image_total == 0 and image_output == 0:
        return None

    return {
        "text_input_tokens": max(0, text_total - text_cached),
        "text_cached_input_tokens": text_cached,
        "image_input_tokens": max(0, image_total - image_cached),
        "image_cached_input_tokens": image_cached,
        "image_output_tokens": image_output,
    }


def _estimate_text_tokens(prompt: str) -> int:
    # A conservative local estimate for cases where the Image API response omits usage.
    return max(1, math.ceil(len(prompt) / 4))


def _estimate_image_input_tokens(image_count: int) -> int:
    # Conservative local estimate: ~1,000 tokens per input image.
    return max(0, int(image_count or 0)) * 1000


def _token_cost(tokens: int, per_million_usd: float) -> float:
    return round((int(tokens or 0) / 1_000_000) * float(per_million_usd or 0), 8)


def _krw_cost(cost_usd: float, usd_krw_rate: float) -> float:
    return round(float(cost_usd or 0) * float(usd_krw_rate or 0), 2)


def _int_token(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
