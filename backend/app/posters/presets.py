from __future__ import annotations

from dataclasses import dataclass


DEFAULT_INCLUDED_SECTIONS = [
    "product_summary",
    "itinerary",
    "marketing_copy",
    "claim_limits",
]


@dataclass(frozen=True)
class PosterStylePreset:
    id: str
    label: str
    description: str
    scene_fragment: str
    lighting_fragment: str
    color_fragment: str
    typography_fragment: str
    composition_fragment: str
    prompt_fragment: str


POSTER_STYLE_PRESETS: dict[str, PosterStylePreset] = {
    "editorial_travel": PosterStylePreset(
        id="editorial_travel",
        label="에디토리얼 여행 매거진",
        description="조용한 프리미엄 여행 매거진 스타일",
        scene_fragment=(
            "Frame the destination like a premium travel magazine feature: quiet, observational, "
            "place-led, with refined local texture and enough environmental context to understand the experience."
        ),
        lighting_fragment=(
            "Use natural daylight or gentle golden-hour light, soft shadows, and subtle depth-of-field; "
            "avoid dramatic neon or hard event-poster lighting."
        ),
        color_fragment=(
            "Use restrained, slightly desaturated destination colors with tactile paper warmth, "
            "muted contrast, and a calm editorial finish."
        ),
        typography_fragment=(
            "Use elegant editorial typography with generous margins, a strong but quiet headline, "
            "and sparse supporting text."
        ),
        composition_fragment=(
            "Use a refined magazine-cover composition with generous negative space, balanced image/text placement, "
            "and a premium print layout sensibility."
        ),
        prompt_fragment=(
            "Quiet premium travel magazine art direction, refined editorial layout, "
            "natural daylight, tactile paper texture, restrained color contrast, "
            "elegant typography with generous margins."
        ),
    ),
    "night_city": PosterStylePreset(
        id="night_city",
        label="시네마틱 나이트 시티",
        description="야간 도시와 로컬 경험을 강조하는 시네마틱 스타일",
        scene_fragment=(
            "Build a cinematic evening or night scene rooted in the product's local experience: streets, markets, "
            "cafes, waterfronts, cultural venues, or neighborhood details suggested by the product data."
        ),
        lighting_fragment=(
            "Use night-time practical lighting such as warm shop lights, street lamps, reflections, low-key shadows, "
            "and selective cinematic depth; avoid bright daylight or flat studio lighting."
        ),
        color_fragment=(
            "Use deep night tones, warm amber highlights, cool blue shadows, realistic reflections, "
            "and polished campaign contrast without becoming oversaturated."
        ),
        typography_fragment=(
            "Use clean cinematic campaign typography with high contrast against the dark scene, "
            "compact supporting text, and a confident headline."
        ),
        composition_fragment=(
            "Use a dramatic poster composition with clear foreground/background layering, a strong focal path, "
            "and enough local detail to feel specific rather than generic."
        ),
        prompt_fragment=(
            "Cinematic night city atmosphere, local street experience, deep shadows, "
            "warm practical lights, realistic urban details, polished travel campaign "
            "composition, dramatic but not exaggerated."
        ),
    ),
    "minimal_event": PosterStylePreset(
        id="minimal_event",
        label="미니멀 이벤트 포스터",
        description="정보가 명확한 미니멀 홍보 포스터 스타일",
        scene_fragment=(
            "Use a simplified destination or event-inspired visual metaphor tied to the product experience, "
            "not a detailed cinematic scene; keep the background clean and easy to read."
        ),
        lighting_fragment=(
            "Use even, clean, graphic lighting with minimal shadows and no cinematic blur; "
            "prioritize clarity over atmosphere."
        ),
        color_fragment=(
            "Use a limited palette with one or two accent colors drawn from the destination or product theme, "
            "crisp contrast, and ample neutral space."
        ),
        typography_fragment=(
            "Use accessible modern sans-serif typography, clear hierarchy, and event-poster spacing; "
            "the text should feel organized rather than decorative."
        ),
        composition_fragment=(
            "Use a clean grid, strong alignment, crisp negative space, and simple information hierarchy "
            "so the poster can be scanned quickly."
        ),
        prompt_fragment=(
            "Minimal event poster design, clear information hierarchy, clean grid, "
            "limited accent colors, crisp negative space, accessible typography, "
            "simple visual metaphor tied to the destination."
        ),
    ),
}
