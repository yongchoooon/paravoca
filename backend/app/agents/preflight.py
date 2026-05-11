from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


MAX_PRODUCT_COUNT = 20


KOREAN_NUMBER_WORDS = {
    "한": 1,
    "하나": 1,
    "두": 2,
    "둘": 2,
    "세": 3,
    "셋": 3,
    "네": 4,
    "넷": 4,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "여덟": 8,
    "아홉": 9,
    "열": 10,
    "열하나": 11,
    "열한": 11,
    "열둘": 12,
    "열두": 12,
    "열셋": 13,
    "열세": 13,
    "열넷": 14,
    "열네": 14,
    "열다섯": 15,
    "열여섯": 16,
    "열일곱": 17,
    "열여덟": 18,
    "열아홉": 19,
    "스무": 20,
    "스물": 20,
    "스물하나": 21,
    "스물한": 21,
    "스물둘": 22,
    "스물두": 22,
    "스물셋": 23,
    "스물세": 23,
    "스물넷": 24,
    "스물네": 24,
    "스물다섯": 25,
    "스물여섯": 26,
    "스물일곱": 27,
    "스물여덟": 28,
    "스물아홉": 29,
    "서른": 30,
}

TRAVEL_SCOPE_TERMS = {
    "관광",
    "여행",
    "투어",
    "코스",
    "일정",
    "상품",
    "축제",
    "행사",
    "체험",
    "액티비티",
    "숙박",
    "호텔",
    "카페",
    "맛집",
    "미식",
    "야간",
    "외국인",
    "관광객",
    "방문객",
    "트레킹",
    "걷기",
    "요트",
    "레저",
}

STRONG_TRAVEL_SCOPE_TERMS = {
    "관광",
    "여행",
    "투어",
    "코스",
    "일정",
    "상품",
    "축제",
    "행사",
    "체험",
    "액티비티",
    "관광객",
    "방문객",
    "트레킹",
    "요트",
    "레저",
}

REGION_SCOPE_TERMS = {
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
}

UNSUPPORTED_TOPIC_TERMS = {
    "레시피",
    "요리법",
    "된장찌개",
    "김치찌개",
    "코딩",
    "파이썬",
    "자바스크립트",
    "수학",
    "번역",
    "소설",
    "시 써",
    "주식",
    "투자",
    "부동산",
    "연애",
    "상담",
}


@dataclass(frozen=True)
class PreflightValidationResult:
    supported: bool
    reason_code: str
    user_message: str
    requested_product_count: int | None = None
    max_product_count: int = MAX_PRODUCT_COUNT

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": "PreflightValidationAgent",
            "supported": self.supported,
            "reason_code": self.reason_code,
            "user_message": self.user_message,
            "requested_product_count": self.requested_product_count,
            "max_product_count": self.max_product_count,
        }


def validate_preflight_request(payload: dict[str, Any]) -> PreflightValidationResult:
    message = str(payload.get("message") or "").strip()
    requested_count = _requested_product_count(payload, message)
    if not message:
        return PreflightValidationResult(
            supported=False,
            reason_code="empty_request",
            user_message="요청 내용을 입력해 주세요. PARAVOCA는 국내 관광 상품 기획 요청만 지원합니다.",
            requested_product_count=requested_count,
        )
    if requested_count and requested_count > MAX_PRODUCT_COUNT:
        return PreflightValidationResult(
            supported=False,
            reason_code="product_count_exceeds_limit",
            user_message=f"한 번에 만들 수 있는 상품은 최대 {MAX_PRODUCT_COUNT}개입니다. {MAX_PRODUCT_COUNT}개 이하로 다시 요청해 주세요.",
            requested_product_count=requested_count,
        )
    if not _is_supported_tourism_request(message, payload):
        return PreflightValidationResult(
            supported=False,
            reason_code="unsupported_scope",
            user_message="PARAVOCA는 국내 관광 상품 기획 요청만 지원합니다. 지역, 대상, 여행/관광 상품 의도를 포함해 다시 입력해 주세요.",
            requested_product_count=requested_count,
        )
    return PreflightValidationResult(
        supported=True,
        reason_code="supported",
        user_message="지원 범위 안의 요청입니다.",
        requested_product_count=requested_count,
    )


def _requested_product_count(payload: dict[str, Any], message: str) -> int | None:
    explicit_count = _int_or_none(payload.get("product_count"))
    message_count = _count_from_message(message)
    if message_count is not None:
        return message_count
    return explicit_count


def _count_from_message(message: str) -> int | None:
    normalized = re.sub(r"\s+", "", message)
    digit_matches = [
        int(match.group("count"))
        for match in re.finditer(r"(?P<count>\d{1,2})(?:개|가지|종|개정도|개쯤|개의)", normalized)
    ]
    if digit_matches:
        return max(digit_matches)
    for word, value in sorted(KOREAN_NUMBER_WORDS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"{word}(?:개|가지|종|개정도|개쯤|개의)", normalized):
            return value
    return None


def _is_supported_tourism_request(message: str, payload: dict[str, Any]) -> bool:
    compact = re.sub(r"\s+", "", message.lower())
    has_travel_signal = any(term.lower() in compact for term in TRAVEL_SCOPE_TERMS)
    has_strong_travel_signal = any(term.lower() in compact for term in STRONG_TRAVEL_SCOPE_TERMS)
    has_region_signal = any(term.lower() in compact for term in REGION_SCOPE_TERMS)
    preferences = " ".join(str(item or "") for item in payload.get("preferences") or [])
    has_preference_signal = any(term in preferences for term in TRAVEL_SCOPE_TERMS)
    if any(term.lower().replace(" ", "") in compact for term in UNSUPPORTED_TOPIC_TERMS) and not has_strong_travel_signal:
        return False
    if has_travel_signal or (has_region_signal and has_preference_signal):
        return True
    return has_region_signal and any(term in compact for term in {"기획", "추천", "만들", "짜줘", "작성"})


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
