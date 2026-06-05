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
    marketing_copy = _marketing_texts(marketing)
    sns_copy = _sns_texts(marketing)
    target_segment_texts = _target_segment_texts(marketing)
    key_selling_point_texts = _key_selling_point_texts(marketing)
    landing_outline_texts = _landing_outline_texts(marketing)
    faq_strategy_texts = _faq_strategy_texts(marketing)
    usable_claim_texts = _usable_claim_texts(marketing)
    evidence_context_texts = _evidence_context_texts(product=product, result=result)
    specific_place_hints = _specific_place_hints(
        product_title=product_title,
        one_liner=one_liner,
        itinerary_items=itinerary_items,
        marketing_copy=marketing_copy,
        sns_copy=sns_copy,
        target_segment_texts=target_segment_texts,
        key_selling_point_texts=key_selling_point_texts,
        landing_outline_texts=landing_outline_texts,
        evidence_context_texts=evidence_context_texts,
    )

    visible_text: list[str] = []
    if "product_summary" in selected:
        visible_text.extend([product_title])
        if one_liner:
            visible_text.append(one_liner)
    if "itinerary" in selected:
        visible_text.extend(itinerary_items[:2])
    if "marketing_copy" in selected:
        visible_text.extend(marketing_copy[:2])
    if "key_selling_points" in selected:
        visible_text.extend(key_selling_point_texts[:2])
    if "landing_outline" in selected:
        visible_text.extend(landing_outline_texts[:2])
    if "sns_copy" in selected:
        visible_text.extend(sns_copy[:1])
    if "usable_claims" in selected:
        visible_text.extend(usable_claim_texts[:1])
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
        target_segment_texts=target_segment_texts,
        key_selling_point_texts=key_selling_point_texts,
        landing_outline_texts=landing_outline_texts,
        faq_strategy_texts=faq_strategy_texts,
        usable_claim_texts=usable_claim_texts,
        evidence_context_texts=evidence_context_texts,
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
                (
                    f"Most specific place and experience cues from the product data: {', '.join(specific_place_hints)}."
                    if specific_place_hints
                    else ""
                ),
                "Before choosing the background, infer the most specific district, venue type, event type, local culture, or neighborhood implied by the product title, itinerary, marketing copy, and evidence summary.",
                "Use a real-world Korean travel setting suggested by the product data.",
                "Do not substitute a generic famous landmark just because the broader city or province is known for it.",
                "Show atmosphere and place experience, not an abstract background.",
                preset.scene_fragment,
                preset.lighting_fragment,
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
                f"Apply this selected style preset: {preset.label}.",
                preset.color_fragment,
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
    else:
        sections.extend(
            [
                "",
                "=== NO REFERENCE IMAGE GUIDANCE ===",
                _bullet_sentence(
                    [
                        "No reference image is provided. Create the visual background from the product data instead of defaulting to a broad-city landmark.",
                        "If the broad location is a city or province but the product text implies a more specific district, festival, street, market, cafe culture, waterfront, forest, temple, or local venue, prioritize that specific cue.",
                        "For example, a coffee festival or cafe-culture product should look like a local coffee festival, roastery street, cafe interior/exterior, or neighborhood waterfront cafe atmosphere, not an unrelated bridge, skyline, or tourist landmark.",
                        "If the precise venue is uncertain, choose a plausible non-specific local scene that matches the product's experience type and avoid recognizable landmarks that are not supported by the product data.",
                    ]
                ),
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
                    preset.typography_fragment,
                    "Ensure all text is legible against the background — use subtle text shadows, semi-transparent overlays, or contrasting placement as needed.",
                    "Keep text areas sparse and well-spaced; avoid dense paragraphs or cluttered layouts.",
                    "Secondary text lines should be smaller and positioned below or beside the headline with clear visual hierarchy.",
                ]
            ),
            "",
            "Composition:",
            _bullet_sentence([preset.composition_fragment]),
            "",
            "Style summary:",
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
            "specific_place_hints": specific_place_hints,
            "evidence_context_count": len(evidence_context_texts),
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
    marketing_dict = _dict(marketing)
    sales_copy = _dict(marketing_dict.get("sales_copy"))
    outline = _dict(marketing_dict.get("landing_page_outline"))
    hero = _dict(outline.get("hero"))
    strategy = _dict(marketing_dict.get("marketing_strategy"))
    key_points = []
    for item in _records(strategy.get("key_selling_points"), limit=3):
        key_points.extend([_clean_text(item.get("point")), _clean_text(item.get("usage_note"))])
    texts = [
        _clean_text(hero.get("headline")),
        *key_points,
        _clean_text(hero.get("subheadline")),
        _clean_text(hero.get("hook")),
        _clean_text(sales_copy.get("headline")),
        _clean_text(sales_copy.get("subheadline")),
    ]
    return _dedupe([item for item in texts if item])


def _sns_texts(marketing: dict[str, Any] | None) -> list[str]:
    marketing_dict = _dict(marketing)
    campaign = _dict(marketing_dict.get("sns_campaign"))
    posts = _records(campaign.get("posts"), limit=2)
    texts: list[str] = []
    for post in posts:
        texts.extend([_clean_text(post.get("hook")), _clean_text(post.get("body"))])
    return _dedupe([item for item in texts if item])[:2]


def _target_segment_texts(marketing: dict[str, Any] | None) -> list[str]:
    strategy = _dict(_dict(marketing).get("marketing_strategy"))
    target = _dict(strategy.get("target_segment"))
    secondary = _string_list(target.get("secondary"), limit=3)
    texts = [
        _clean_text(target.get("primary")),
        ", ".join(secondary),
        _clean_text(target.get("foreigner_context")),
    ]
    return _dedupe([item for item in texts if item])[:4]


def _key_selling_point_texts(marketing: dict[str, Any] | None) -> list[str]:
    strategy = _dict(_dict(marketing).get("marketing_strategy"))
    texts: list[str] = []
    for item in _records(strategy.get("key_selling_points"), limit=4):
        point = _clean_text(item.get("point"))
        usage_note = _clean_text(item.get("usage_note"))
        evidence_basis = _clean_text(item.get("evidence_basis"))
        if point:
            texts.append(point)
        if usage_note:
            texts.append(usage_note)
        if evidence_basis:
            texts.append(f"Evidence cue: {evidence_basis}")
    return _dedupe(texts)[:8]


def _landing_outline_texts(marketing: dict[str, Any] | None) -> list[str]:
    outline = _dict(_dict(marketing).get("landing_page_outline"))
    hero = _dict(outline.get("hero"))
    texts = [
        _clean_text(hero.get("headline")),
        _clean_text(hero.get("subheadline")),
        _clean_text(hero.get("hook")),
        *_string_list(outline.get("why_this_product"), limit=3),
        *_string_list(outline.get("practical_info"), limit=2),
    ]
    for item in _records(outline.get("evidence_backed_points"), limit=3):
        point = _clean_text(item.get("point"))
        if point:
            texts.append(point)
    return _dedupe([item for item in texts if item])[:8]


def _faq_strategy_texts(marketing: dict[str, Any] | None) -> list[str]:
    faq_strategy = _dict(_dict(marketing).get("faq_strategy"))
    texts: list[str] = []
    for key, label in (("buyer_faq", "Buyer FAQ"), ("operation_faq", "Operation FAQ")):
        for item in _records(faq_strategy.get(key), limit=2):
            question = _clean_text(item.get("question"))
            answer = _clean_text(item.get("answer"))
            if question or answer:
                texts.append(f"{label}: {' / '.join([part for part in [question, answer] if part])}")
    return _dedupe(texts)[:4]


def _usable_claim_texts(marketing: dict[str, Any] | None) -> list[str]:
    claim_strategy = _dict(_dict(marketing).get("claim_strategy"))
    texts: list[str] = []
    for item in _records(claim_strategy.get("usable_claims"), limit=4):
        claim = _clean_text(item.get("claim"))
        evidence_basis = _clean_text(item.get("evidence_basis"))
        if claim:
            texts.append(claim)
        if evidence_basis:
            texts.append(f"Evidence cue: {evidence_basis}")
    return _dedupe(texts)[:6]


def _evidence_context_texts(
    *,
    product: dict[str, Any],
    result: dict[str, Any],
    limit: int = 3,
) -> list[str]:
    """Return meaningful evidence context, not a low-information "N sources used" summary."""

    source_ids = set(_string_list(product.get("source_ids"), limit=12))
    docs = result.get("retrieved_documents")
    texts: list[str] = []
    if isinstance(docs, list):
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            doc_id = _clean_text(doc.get("doc_id") or doc.get("source_id") or doc.get("id"))
            if source_ids and doc_id and doc_id not in source_ids:
                continue
            title = _clean_text(doc.get("title"))
            snippet = _clean_text(doc.get("snippet") or doc.get("summary"))
            content = _clean_text(doc.get("content"))
            body = snippet or _short_meaningful_content(content)
            if title and body:
                texts.append(f"{title}: {body}")
            elif title:
                texts.append(title)
            elif body:
                texts.append(body)
            if len(texts) >= limit:
                break

    # Use product evidence_summary only when it contains actual context, not just a count/title shell.
    summary = _clean_text(product.get("evidence_summary"))
    if summary and not _is_low_information_evidence_summary(summary):
        texts.append(summary)

    return _dedupe([_trim_for_context(item, max_chars=420) for item in texts if item])[:limit]


def _short_meaningful_content(content: str) -> str:
    if not content:
        return ""
    # Do not dump long raw evidence into poster prompts. Use the first sentence-like chunk only.
    for separator in (". ", "。", "\n"):
        if separator in content:
            candidate = content.split(separator)[0]
            return _trim_for_context(candidate, max_chars=260)
    return _trim_for_context(content, max_chars=260)


def _trim_for_context(text: str, *, max_chars: int) -> str:
    cleaned = _clean_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _is_low_information_evidence_summary(text: str) -> bool:
    normalized = text.strip()
    return (
        "근거를 사용했습니다" in normalized
        and len(normalized) < 90
        and ":" not in normalized
        and " - " not in normalized
    )


def _records(value: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:limit]


def _specific_place_hints(
    *,
    product_title: str,
    one_liner: str,
    itinerary_items: list[str],
    marketing_copy: list[str],
    sns_copy: list[str],
    target_segment_texts: list[str],
    key_selling_point_texts: list[str],
    landing_outline_texts: list[str],
    evidence_context_texts: list[str],
) -> list[str]:
    candidates = [
        product_title,
        one_liner,
        *itinerary_items,
        *marketing_copy,
        *sns_copy,
        *target_segment_texts,
        *key_selling_point_texts,
        *landing_outline_texts,
        *evidence_context_texts,
    ]
    return _dedupe([item for item in (_clean_text(candidate) for candidate in candidates) if item])[:8]


def _key_details(
    *,
    selected: set[str],
    location: str,
    target_customer: str,
    core_values: list[str],
    itinerary_items: list[str],
    marketing_copy: list[str],
    sns_copy: list[str],
    target_segment_texts: list[str],
    key_selling_point_texts: list[str],
    landing_outline_texts: list[str],
    faq_strategy_texts: list[str],
    usable_claim_texts: list[str],
    evidence_context_texts: list[str],
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
        details.append(f"Marketing tone cues: {' / '.join(marketing_copy[:4])}.")
    if "target_segment" in selected and target_segment_texts:
        details.append(f"Audience and sales target cues: {' / '.join(target_segment_texts[:4])}.")
    if "key_selling_points" in selected and key_selling_point_texts:
        details.append(f"Core selling point cues: {' / '.join(key_selling_point_texts[:5])}.")
    if "landing_outline" in selected and landing_outline_texts:
        details.append(f"Landing-page story cues: {' / '.join(landing_outline_texts[:5])}.")
    if "faq_strategy" in selected and faq_strategy_texts:
        details.append(f"Buyer/operator concern cues to reflect subtly: {' / '.join(faq_strategy_texts[:3])}.")
    if "sns_copy" in selected and sns_copy:
        details.append(f"Social copy tone cue: {sns_copy[0]}.")
    if "usable_claims" in selected and usable_claim_texts:
        details.append(f"Claims that may be used safely when supported: {' / '.join(usable_claim_texts[:4])}.")
    if "evidence_summary" in selected and evidence_context_texts:
        details.append(
            f"Use these evidence-backed context cues, without printing long evidence text: {' / '.join(evidence_context_texts)}."
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
    claim_strategy = _dict(_dict(marketing).get("claim_strategy"))
    raw_constraints.extend(
        f"Avoid claiming: {_clean_text(item.get('phrase'))} — {_clean_text(item.get('reason'))}."
        for item in _records(claim_strategy.get("caution_phrasing"), limit=6)
        if _clean_text(item.get("phrase")) or _clean_text(item.get("reason"))
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
