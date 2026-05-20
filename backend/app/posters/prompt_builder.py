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
    input_images: list[str] | None = None,
) -> PosterPrompt:
    if style_preset not in POSTER_STYLE_PRESETS:
        raise ValueError(f"Unknown poster style preset: {style_preset}")

    selected = set(included_sections)
    preset = POSTER_STYLE_PRESETS[style_preset]
    normalized_request = _dict(result.get("normalized_request"))
    geo_scope = _dict(result.get("geo_scope"))

    product_title = _clean_text(product.get("title")) or "Travel product"
    one_liner = _clean_text(product.get("one_liner"))
    target_customer = _clean_text(product.get("target_customer"))
    location = _location_text(run_input, normalized_request, geo_scope)
    core_values = _string_list(product.get("core_value"), limit=4)
    itinerary_items = _itinerary_texts(product.get("itinerary"), limit=3)
    evidence_summary = _clean_text(product.get("evidence_summary"))
    marketing_copy = _marketing_texts(marketing)
    sns_copy = _string_list(_dict(marketing).get("sns_posts"), limit=1)

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
    visible_text = _dedupe([_clean_text(item) for item in visible_text if _clean_text(item)])[:7]

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

    resolved_input_images = input_images or []

    # --- Build the gpt-image-2 optimised prompt ---
    sections: list[str] = [
        "Create one portrait travel promotion poster draft.",
        "",
        "=== VISUAL DIRECTION ===",
        "",
        "Scene/background:",
        _bullet_sentence(
            [
                f"Destination context: {location}" if location else "",
                "Use a real-world Korean travel setting suggested by the product data.",
                "Show atmosphere and place experience, not an abstract background.",
                "Render the scene with cinematic depth-of-field, letting the background gently blur to draw the viewer's eye to the subject.",
                "Use soft, diffuse natural lighting that evokes the time of day suggested by the product's theme (golden hour warmth for sunset tours, cool blue-tinted twilight for night walks).",
            ]
        ),
        "",
        "Subject:",
        _bullet_sentence(
            [
                f"Travel product: {product_title}.",
                f"Target customer: {target_customer}." if target_customer else "",
                "The poster should promote one specific travel product, not a generic destination.",
                "Convey a sense of invitation — the viewer should feel drawn into the scene as if they are about to step into the experience.",
            ]
        ),
        "",
        "Key details:",
        _bullet_sentence(key_details),
        "",
        "Color palette & mood:",
        _bullet_sentence(
            [
                f"Draw the color palette from the destination's natural environment and the style preset: {preset.label}.",
                "Prefer harmonious, slightly desaturated tones that feel premium and editorial rather than oversaturated stock-photo colors.",
                "Maintain a cohesive mood throughout — every visual element should reinforce the same emotional tone.",
            ]
        ),
    ]

    # Input images reference block
    if resolved_input_images:
        sections.extend(
            [
                "",
                "=== REFERENCE IMAGES ===",
                f"The following {len(resolved_input_images)} reference image(s) are provided as visual context.",
                "Integrate their visual composition, scenic characteristics, textures, and color tones into the poster artwork.",
                "Do not reproduce the reference images verbatim; instead, use them as stylistic and compositional inspiration to create an original poster.",
            ]
        )

    sections.extend(
        [
            "",
            "=== TYPOGRAPHY & TEXT LAYOUT ===",
            "",
            "Included text:",
            _quoted_text_block(visible_text),
            "",
            "Typography rules:",
            _bullet_sentence(
                [
                    f"Render the primary headline \"{product_title}\" in bold, artistic typography positioned prominently near the top third of the poster.",
                    "Use a clean, modern sans-serif or editorial serif typeface that complements the visual style.",
                    "Ensure all text is legible against the background — use subtle text shadows, semi-transparent overlays, or contrasting placement as needed.",
                    "Keep text areas sparse and well-spaced; avoid dense paragraphs or cluttered layouts.",
                    "Secondary text lines should be smaller and positioned below or beside the headline with clear visual hierarchy.",
                ]
            ),
            "",
            "Style:",
            f"- {preset.prompt_fragment}",
            "",
            "=== CONSTRAINTS ===",
            "",
            _bullet_sentence(constraints),
        ]
    )

    prompt = "\n".join(sections).strip()

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
            "input_image_count": len(resolved_input_images),
        },
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any, *, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _clean_text(value: Any) -> str:
    """Normalize whitespace and return the full text without truncation."""
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split()).strip()


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
        candidates.append(_clean_text(run_input.get(key)))
        candidates.append(_clean_text(normalized_request.get(key)))
    locations = geo_scope.get("locations")
    if isinstance(locations, list):
        for item in locations:
            if isinstance(item, dict):
                candidates.append(_clean_text(item.get("name")))
                candidates.append(_clean_text(item.get("keyword")))
            else:
                candidates.append(_clean_text(item))
    return ", ".join(_dedupe([item for item in candidates if item])[:2])


def _itinerary_texts(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = (
                _clean_text(item.get("title") or item.get("name") or item.get("place"))
                or _clean_text(item.get("activity") or item.get("description"))
            )
        else:
            text = _clean_text(item)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _marketing_texts(marketing: dict[str, Any] | None) -> list[str]:
    sales_copy = _dict(_dict(marketing).get("sales_copy"))
    texts = [
        _clean_text(sales_copy.get("headline")),
        _clean_text(sales_copy.get("subheadline")),
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
        for item in _string_list(product.get("claim_limits"), limit=8)
    )
    raw_constraints.extend(
        f"Do not imply: {item}."
        for item in _string_list(product.get("not_to_claim"), limit=8)
    )
    raw_constraints.extend(
        f"Do not show as a verified fact: {item}."
        for item in _string_list(product.get("needs_review"), limit=6)
    )
    raw_constraints.extend(
        f"Avoid claiming: {item}."
        for item in _string_list(_dict(marketing).get("claim_limits"), limit=6)
    )
    raw_constraints.extend(
        f"Treat this as a limitation, not promotional copy: {item}."
        for item in _string_list(result.get("unresolved_gaps"), limit=5)
    )
    return _dedupe(raw_constraints)[:24]


def _bullet_sentence(items: list[str]) -> str:
    cleaned = [_clean_text(item) for item in items if _clean_text(item)]
    if not cleaned:
        return "- No additional detail."
    return "\n".join(f"- {item}" for item in cleaned)


def _quoted_text_block(items: list[str]) -> str:
    if not items:
        return "- Use no visible marketing copy except a short product title if needed."
    return "\n".join(f'- "{item}"' for item in items)
