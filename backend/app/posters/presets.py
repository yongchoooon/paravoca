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
    prompt_fragment: str


POSTER_STYLE_PRESETS: dict[str, PosterStylePreset] = {
    "editorial_travel": PosterStylePreset(
        id="editorial_travel",
        label="에디토리얼 여행 매거진",
        description="조용한 프리미엄 여행 매거진 스타일",
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
        prompt_fragment=(
            "Minimal event poster design, clear information hierarchy, clean grid, "
            "limited accent colors, crisp negative space, accessible typography, "
            "simple visual metaphor tied to the destination."
        ),
    ),
}
