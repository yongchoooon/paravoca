from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.posters.presets import POSTER_STYLE_PRESETS


@dataclass(frozen=True)
class PosterPrompt:
    prompt: str
    visible_text: list[str]
    constraints: list[str]
    source_summary: dict[str, Any]


def build_poster_prompt(
    *,
    run_input: dict[str, Any],
    result: dict[str, Any],
    product: dict[str, Any],
    marketing: dict[str, Any] | None,
    included_sections: list[str],
    style_preset: str,
) -> PosterPrompt:
    if style_preset not in POSTER_STYLE_PRESETS:
        raise ValueError(f"Unknown poster style preset: {style_preset}")

    selected = set(included_sections)
    preset = POSTER_STYLE_PRESETS[style_preset]
    normalized_request = _dict(result.get("normalized_request"))
    geo_scope = _dict(result.get("geo_scope"))

    product_title = _clean_text(product.get("title"), 54) or "Travel product"
    one_liner = _clean_text(product.get("one_liner"), 86)
    target_customer = _clean_text(product.get("target_customer"), 72)
    location = _location_text(run_input, normalized_request, geo_scope)
    core_values = _string_list(product.get("core_value"), limit=4, item_limit=36)
    itinerary_items = _itinerary_texts(product.get("itinerary"), limit=3)
    evidence_summary = _clean_text(product.get("evidence_summary"), 150)
    marketing_copy = _marketing_texts(marketing)
    sns_copy = _string_list(_dict(marketing).get("sns_posts"), limit=1, item_limit=96)

    visible_text: list[str] = []
    if "product_summary" in selected:
        visible_text.extend([product_title])
        if one_liner:
            visible_text.append(one_liner)
    if "itinerary" in selected:
        visible_text.extend(itinerary_items[:2])
    if "marketing_copy" in selected:
        visible_text.extend(marketing_copy[:2])
    if "sns_copy" in selected:
        visible_text.extend(sns_copy[:1])
    if "evidence_summary" in selected and evidence_summary:
        visible_text.append(f"근거 기반 초안: {evidence_summary}")
    visible_text = _dedupe([_clean_text(item, 88) for item in visible_text if _clean_text(item, 88)])[:7]

    constraints = _constraints(product, marketing, result)
    key_details = _key_details(
        selected=selected,
        location=location,
        target_customer=target_customer,
        core_values=core_values,
        itinerary_items=itinerary_items,
        marketing_copy=marketing_copy,
        sns_copy=sns_copy,
        evidence_summary=evidence_summary,
    )

    prompt = "\n".join(
        [
            "Create one portrait travel promotion poster draft.",
            "",
            "Scene/background:",
            _bullet_sentence(
                [
                    f"Destination context: {location}" if location else "",
                    "Use a real-world Korean travel setting suggested by the product data.",
                    "Show atmosphere and place experience, not an abstract background.",
                ]
            ),
            "",
            "Subject:",
            _bullet_sentence(
                [
                    f"Travel product: {product_title}.",
                    f"Target customer: {target_customer}." if target_customer else "",
                    "The poster should promote one specific travel product, not a generic destination.",
                ]
            ),
            "",
            "Key details:",
            _bullet_sentence(key_details),
            "",
            "Included text:",
            _quoted_text_block(visible_text),
            "",
            "Style:",
            f"- {preset.prompt_fragment}",
            "",
            "Constraints:",
            _bullet_sentence(constraints),
        ]
    ).strip()

    return PosterPrompt(
        prompt=prompt,
        visible_text=visible_text,
        constraints=constraints,
        source_summary={
            "style_preset": style_preset,
            "included_sections": included_sections,
            "visible_text_count": len(visible_text),
            "constraint_count": len(constraints),
            "location": location,
            "target_customer": target_customer,
        },
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any, *, limit: int = 8, item_limit: int = 120) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _clean_text(item, item_limit)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _clean_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).replace("\n", " ").split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _location_text(
    run_input: dict[str, Any],
    normalized_request: dict[str, Any],
    geo_scope: dict[str, Any],
) -> str:
    candidates: list[str] = []
    for key in ("region", "location"):
        candidates.append(_clean_text(run_input.get(key), 60))
        candidates.append(_clean_text(normalized_request.get(key), 60))
    locations = geo_scope.get("locations")
    if isinstance(locations, list):
        for item in locations:
            if isinstance(item, dict):
                candidates.append(_clean_text(item.get("name"), 60))
                candidates.append(_clean_text(item.get("keyword"), 60))
            else:
                candidates.append(_clean_text(item, 60))
    return ", ".join(_dedupe([item for item in candidates if item])[:2])


def _itinerary_texts(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = (
                _clean_text(item.get("title") or item.get("name") or item.get("place"), 44)
                or _clean_text(item.get("activity") or item.get("description"), 62)
            )
        else:
            text = _clean_text(item, 62)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _marketing_texts(marketing: dict[str, Any] | None) -> list[str]:
    sales_copy = _dict(_dict(marketing).get("sales_copy"))
    texts = [
        _clean_text(sales_copy.get("headline"), 70),
        _clean_text(sales_copy.get("subheadline"), 88),
    ]
    return _dedupe([item for item in texts if item])


def _key_details(
    *,
    selected: set[str],
    location: str,
    target_customer: str,
    core_values: list[str],
    itinerary_items: list[str],
    marketing_copy: list[str],
    sns_copy: list[str],
    evidence_summary: str,
) -> list[str]:
    details: list[str] = []
    if location:
        details.append(f"Reflect the destination/location: {location}.")
    if target_customer:
        details.append(f"Speak to this audience: {target_customer}.")
    if "product_summary" in selected and core_values:
        details.append(f"Core values to evoke: {', '.join(core_values)}.")
    if "itinerary" in selected and itinerary_items:
        details.append(f"Experience cues: {', '.join(itinerary_items)}.")
    if "marketing_copy" in selected and marketing_copy:
        details.append(f"Marketing tone cues: {' / '.join(marketing_copy[:2])}.")
    if "sns_copy" in selected and sns_copy:
        details.append(f"Social copy tone cue: {sns_copy[0]}.")
    if "evidence_summary" in selected and evidence_summary:
        details.append(
            f"Use this as background evidence context, without overclaiming: {evidence_summary}."
        )
    return details or ["Use the product data as the primary source of visual and text choices."]


def _constraints(
    product: dict[str, Any],
    marketing: dict[str, Any] | None,
    result: dict[str, Any],
) -> list[str]:
    raw_constraints = [
        "No watermark, no logos, no trademarks, no QR code.",
        "Do not add unsupported claims or facts that are not present in the product data.",
        "Do not invent prices, discounts, opening hours, booking availability, safety guarantees, medical effects, or wellness efficacy.",
        "Keep poster text short and readable; avoid dense paragraphs.",
        "Make this look like a generated poster draft, not a final approved publication.",
    ]
    raw_constraints.extend(
        f"Avoid claiming: {item}."
        for item in _string_list(product.get("claim_limits"), limit=8, item_limit=110)
    )
    raw_constraints.extend(
        f"Do not imply: {item}."
        for item in _string_list(product.get("not_to_claim"), limit=8, item_limit=110)
    )
    raw_constraints.extend(
        f"Do not show as a verified fact: {item}."
        for item in _string_list(product.get("needs_review"), limit=6, item_limit=110)
    )
    raw_constraints.extend(
        f"Avoid claiming: {item}."
        for item in _string_list(_dict(marketing).get("claim_limits"), limit=6, item_limit=110)
    )
    raw_constraints.extend(
        f"Treat this as a limitation, not promotional copy: {item}."
        for item in _string_list(result.get("unresolved_gaps"), limit=5, item_limit=110)
    )
    return _dedupe(raw_constraints)[:24]


def _bullet_sentence(items: list[str]) -> str:
    cleaned = [_clean_text(item, 220) for item in items if _clean_text(item, 220)]
    if not cleaned:
        return "- No additional detail."
    return "\n".join(f"- {item}" for item in cleaned)


def _quoted_text_block(items: list[str]) -> str:
    if not items:
        return "- Use no visible marketing copy except a short product title if needed."
    return "\n".join(f'- "{item}"' for item in items)
