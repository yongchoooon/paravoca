from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from app.db import models


EXPLICIT_NATIONWIDE_TERMS = {
    "전국",
    "국내 전체",
    "국내전체",
    "대한민국 전체",
    "한국 전체",
    "전 지역",
    "전지역",
}

FOREIGN_DESTINATION_TERMS = {
    "해외",
    "일본",
    "도쿄",
    "동경",
    "오사카",
    "교토",
    "후쿠오카",
    "삿포로",
    "중국",
    "상하이",
    "상해",
    "베이징",
    "북경",
    "홍콩",
    "대만",
    "타이베이",
    "태국",
    "방콕",
    "베트남",
    "다낭",
    "하노이",
    "호치민",
    "싱가포르",
    "말레이시아",
    "쿠알라룸푸르",
    "필리핀",
    "세부",
    "보라카이",
    "인도네시아",
    "발리",
    "미국",
    "뉴욕",
    "로스앤젤레스",
    "LA",
    "하와이",
    "괌",
    "사이판",
    "프랑스",
    "파리",
    "영국",
    "런던",
    "이탈리아",
    "로마",
    "스페인",
    "바르셀로나",
    "독일",
    "베를린",
    "호주",
    "시드니",
    "캐나다",
    "밴쿠버",
}

FOREIGN_CONTEXT_EXCEPTIONS = {
    "해외 관광객",
    "해외 고객",
    "해외 방문객",
    "외국인",
    "인바운드",
}

ROUTE_ORIGIN_PATTERNS = ("에서 시작", "에서 출발", "출발", "부터")
ROUTE_DESTINATION_PATTERNS = ("에서 끝", "까지", "도착", "종료")
EXCLUSION_MARKERS = ("제외", "빼고", "빼줘", "제외하고")
SUB_AREA_PATTERN = re.compile(r"[가-힣A-Za-z0-9]{2,}(?:동|읍|면|리)")

REGION_SUFFIXES = (
    "특별자치시",
    "특별자치도",
    "특별시",
    "광역시",
    "자치도",
    "도",
    "시",
    "군",
    "구",
    "읍",
    "면",
    "동",
)

PROVINCE_ALIASES = {
    "서울": "서울특별시",
    "부산": "부산광역시",
    "대구": "대구광역시",
    "인천": "인천광역시",
    "광주": "광주광역시",
    "대전": "대전광역시",
    "울산": "울산광역시",
    "세종": "세종특별자치시",
    "경기": "경기도",
    "강원": "강원특별자치도",
    "충북": "충청북도",
    "충남": "충청남도",
    "전북": "전북특별자치도",
    "전남": "전라남도",
    "경북": "경상북도",
    "경남": "경상남도",
    "제주": "제주특별자치도",
}

@dataclass(frozen=True)
class LdongCandidate:
    ldong_regn_cd: str
    ldong_regn_nm: str
    ldong_signgu_cd: str | None
    ldong_signgu_nm: str | None
    full_name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    source: str = "catalog"

    @property
    def id(self) -> str:
        if self.ldong_signgu_cd:
            return f"{self.ldong_regn_cd}:{self.ldong_signgu_cd}"
        return self.ldong_regn_cd

    @property
    def display_name(self) -> str:
        return self.full_name

    @property
    def specificity(self) -> int:
        return 2 if self.ldong_signgu_cd else 1


@dataclass
class GeoMatch:
    candidate: LdongCandidate
    matched_text: str
    match_type: str
    confidence: float
    role: str = "primary"
    keyword: str | None = None


def resolve_geo_scope(
    db: Session,
    *,
    message: str | None,
    region: str | None = None,
    llm_hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    input_text = _combined_input(message=message, region=region)
    hint_locations = _llm_location_hints(llm_hints, input_text)
    foreign_terms = _dedupe_strings([*_foreign_destination_terms(input_text), *_llm_foreign_terms(llm_hints)])
    if foreign_terms:
        return {
            "mode": "unsupported_region",
            "status": "unsupported",
            "needs_clarification": False,
            "clarification_question": None,
            "confidence": 1.0,
            "input_text": input_text,
            "locations": [],
            "excluded_locations": [],
            "unresolved_locations": [],
            "unsupported_locations": foreign_terms,
            "unsupported_reason": "PARAVOCA는 현재 국내 관광 데이터만 지원합니다.",
            "keywords": [],
            "allow_nationwide": False,
            "resolution_strategy": "foreign_destination_detected",
            "candidates": [],
            "llm_hints": llm_hints or {},
        }

    if _is_nationwide_request(input_text) or _llm_allows_nationwide_without_locations(llm_hints, hint_locations):
        return {
            "mode": "nationwide",
            "status": "resolved",
            "needs_clarification": False,
            "clarification_question": None,
            "confidence": 1.0,
            "input_text": input_text,
            "locations": [],
            "excluded_locations": [],
            "unresolved_locations": [],
            "keywords": [],
            "allow_nationwide": True,
            "resolution_strategy": "explicit_nationwide",
            "candidates": [],
            "llm_hints": llm_hints or {},
        }

    catalog = load_ldong_catalog(db)
    if not catalog:
        return _catalog_not_synced_scope(input_text)

    matches, ambiguous_groups, fuzzy_suggestions = _resolve_matches(input_text, catalog, hint_locations=hint_locations)
    excluded = _extract_excluded_locations(input_text, catalog)
    matches = [match for match in matches if match.candidate.id not in {item.candidate.id for item in excluded}]
    matches = _collapse_parent_matches(matches)
    matches = _apply_route_roles(input_text, matches)
    sub_area_terms = _extract_sub_area_terms(input_text, matches)
    unresolved_locality_terms = _unresolved_locality_terms(input_text, matches)

    if ambiguous_groups:
        return _clarification_scope(
            input_text=input_text,
            matches=matches,
            ambiguous_groups=ambiguous_groups,
            fuzzy_suggestions=fuzzy_suggestions,
            excluded=excluded,
            sub_area_terms=sub_area_terms,
            unresolved_terms=unresolved_locality_terms,
            reason="ambiguous_location",
            llm_hints=llm_hints,
        )

    if unresolved_locality_terms and not _has_specific_location_match(matches):
        return _clarification_scope(
            input_text=input_text,
            matches=matches,
            ambiguous_groups=[],
            fuzzy_suggestions=fuzzy_suggestions,
            excluded=excluded,
            sub_area_terms=sub_area_terms,
            unresolved_terms=unresolved_locality_terms,
            reason="unresolved_subregion",
            llm_hints=llm_hints,
        )

    if not matches:
        return _clarification_scope(
            input_text=input_text,
            matches=[],
            ambiguous_groups=[],
            fuzzy_suggestions=fuzzy_suggestions,
            excluded=excluded,
            sub_area_terms=sub_area_terms,
            unresolved_terms=unresolved_locality_terms,
            reason="unresolved_location",
            llm_hints=llm_hints,
        )

    mode = _mode_from_matches(matches)
    confidence = min(match.confidence for match in matches)
    return {
        "mode": mode,
        "status": "resolved",
        "needs_clarification": False,
        "clarification_question": None,
        "confidence": round(confidence, 4),
        "input_text": input_text,
        "locations": [_match_to_location(match, sub_area_terms=sub_area_terms) for match in matches],
        "excluded_locations": [_match_to_location(match) for match in excluded],
        "unresolved_locations": [],
        "keywords": _keywords_from_matches(matches, sub_area_terms=sub_area_terms),
        "sub_area_terms": sub_area_terms,
        "allow_nationwide": False,
        "resolution_strategy": _strategy_summary(matches),
        "candidates": [_match_to_candidate(match) for match in matches],
        "llm_hints": llm_hints or {},
    }


def save_geo_resolution(
    db: Session,
    *,
    run_id: str | None,
    geo_scope: dict[str, Any],
) -> models.GeoResolution:
    record = models.GeoResolution(
        run_id=run_id,
        input_text=str(geo_scope.get("input_text") or ""),
        mode=str(geo_scope.get("mode") or "unknown"),
        status=str(geo_scope.get("status") or "unknown"),
        locations=geo_scope.get("locations") or [],
        unresolved_locations=geo_scope.get("unresolved_locations") or [],
        excluded_locations=geo_scope.get("excluded_locations") or [],
        keywords=geo_scope.get("keywords") or [],
        needs_clarification=bool(geo_scope.get("needs_clarification")),
        clarification_question=geo_scope.get("clarification_question"),
        confidence=geo_scope.get("confidence"),
        raw=geo_scope,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def load_ldong_catalog(db: Session) -> list[LdongCandidate]:
    rows = db.query(models.TourApiLdongCode).all()
    candidates: list[LdongCandidate] = []
    for row in rows:
        aliases = row.aliases if isinstance(row.aliases, list) else []
        candidates.append(
            LdongCandidate(
                ldong_regn_cd=str(row.ldong_regn_cd),
                ldong_regn_nm=str(row.ldong_regn_nm),
                ldong_signgu_cd=str(row.ldong_signgu_cd) if row.ldong_signgu_cd else None,
                ldong_signgu_nm=str(row.ldong_signgu_nm) if row.ldong_signgu_nm else None,
                full_name=str(row.full_name),
                aliases=tuple(str(alias) for alias in aliases if str(alias or "").strip()),
                source="catalog",
            )
        )
    return sorted(candidates, key=lambda candidate: (candidate.specificity, len(candidate.full_name)), reverse=True)


def normalize_geo_name(value: str | None) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^0-9a-z가-힣]+", "", text)
    text = PROVINCE_ALIASES.get(text, text)
    for suffix in REGION_SUFFIXES:
        if len(text) > len(suffix) and text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text


def _resolve_matches(
    text: str,
    catalog: list[LdongCandidate],
    *,
    hint_locations: list[dict[str, str]] | None = None,
) -> tuple[list[GeoMatch], list[list[GeoMatch]], list[dict[str, Any]]]:
    hint_text = _hint_match_text(hint_locations or [])
    match_text = " ".join(part for part in [text, hint_text] if part.strip())
    normalized_text = normalize_geo_name(match_text)
    exact_matches = _exact_or_normalized_matches(match_text, normalized_text, catalog)
    alias_matches = _alias_matches(match_text, normalized_text, catalog, exact_matches)
    matches = _narrow_with_region_context([*exact_matches, *alias_matches])
    matches = _apply_llm_roles(matches, hint_locations or [])
    ambiguous_groups = _ambiguous_groups(matches)
    if matches:
        return matches, ambiguous_groups, []

    fuzzy_matches, fuzzy_suggestions = _fuzzy_matches(match_text, catalog)
    fuzzy_matches = _apply_llm_roles(fuzzy_matches, hint_locations or [])
    ambiguous_groups = _ambiguous_groups(fuzzy_matches)
    if fuzzy_matches and not ambiguous_groups:
        return fuzzy_matches, [], fuzzy_suggestions
    return [], ambiguous_groups, fuzzy_suggestions


def _narrow_with_region_context(matches: list[GeoMatch]) -> list[GeoMatch]:
    context_regns = {
        match.candidate.ldong_regn_cd
        for match in matches
        if not match.candidate.ldong_signgu_cd
    }
    if not context_regns:
        return matches
    narrowed: list[GeoMatch] = []
    for match in matches:
        if not match.candidate.ldong_signgu_cd:
            narrowed.append(match)
            continue
        same_name_matches = [
            other
            for other in matches
            if other.candidate.ldong_signgu_cd
            and normalize_geo_name(other.candidate.ldong_signgu_nm) == normalize_geo_name(match.candidate.ldong_signgu_nm)
        ]
        if len({other.candidate.id for other in same_name_matches}) <= 1:
            narrowed.append(match)
            continue
        if match.candidate.ldong_regn_cd in context_regns:
            narrowed.append(match)
    return _dedupe_matches(narrowed)


def _llm_location_hints(llm_hints: dict[str, Any] | None, input_text: str) -> list[dict[str, str]]:
    if not isinstance(llm_hints, dict):
        return []
    raw_locations = llm_hints.get("locations")
    if not isinstance(raw_locations, list):
        return []
    hints: list[dict[str, str]] = []
    for raw in raw_locations:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        normalized_text = str(raw.get("normalized_text") or text).strip()
        role = str(raw.get("role") or "primary").strip()
        if role not in {"primary", "origin", "destination", "stopover", "nearby_anchor", "comparison", "excluded"}:
            role = "primary"
        if not text and not normalized_text:
            continue
        # Gemini may normalize a typo, but the original span still needs to come from the prompt.
        if text and not _appears_in_input(text, input_text):
            continue
        hints.append({"text": text, "normalized_text": normalized_text, "role": role})
    return hints


def _llm_foreign_terms(llm_hints: dict[str, Any] | None) -> list[str]:
    if not isinstance(llm_hints, dict):
        return []
    terms: list[str] = []
    for key in ("unsupported_locations", "foreign_locations"):
        value = llm_hints.get(key)
        if isinstance(value, list):
            terms.extend(str(item).strip() for item in value if str(item or "").strip())
    raw_locations = llm_hints.get("locations")
    if isinstance(raw_locations, list):
        for raw in raw_locations:
            if isinstance(raw, dict) and raw.get("is_foreign") is True:
                term = str(raw.get("text") or raw.get("normalized_text") or "").strip()
                if term:
                    terms.append(term)
    return _dedupe_strings(terms)


def _llm_allows_nationwide_without_locations(
    llm_hints: dict[str, Any] | None,
    hint_locations: list[dict[str, str]],
) -> bool:
    if not isinstance(llm_hints, dict):
        return False
    return llm_hints.get("allow_nationwide") is True and not hint_locations


def _hint_match_text(hint_locations: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for hint in hint_locations:
        parts.extend([hint.get("text", ""), hint.get("normalized_text", "")])
    return " ".join(part for part in parts if part.strip())


def _appears_in_input(value: str, input_text: str) -> bool:
    compact_value = re.sub(r"\s+", "", value)
    compact_input = re.sub(r"\s+", "", input_text)
    return bool(compact_value and compact_value in compact_input)


def _apply_llm_roles(matches: list[GeoMatch], hint_locations: list[dict[str, str]]) -> list[GeoMatch]:
    if not hint_locations:
        return matches
    updated: list[GeoMatch] = []
    for match in matches:
        role = match.role
        for hint in hint_locations:
            if hint["role"] == "primary":
                continue
            hint_terms = [hint.get("text", ""), hint.get("normalized_text", "")]
            candidate_terms = [
                match.matched_text,
                match.candidate.full_name,
                match.candidate.ldong_regn_nm,
                match.candidate.ldong_signgu_nm or "",
            ]
            if _terms_overlap(hint_terms, candidate_terms):
                role = hint["role"]
                break
        updated.append(
            GeoMatch(
                candidate=match.candidate,
                matched_text=match.matched_text,
                match_type=match.match_type,
                confidence=match.confidence,
                role=role,
                keyword=match.keyword,
            )
        )
    return _dedupe_matches(updated)


def _terms_overlap(left_terms: list[str], right_terms: list[str]) -> bool:
    left = {normalize_geo_name(term) for term in left_terms if normalize_geo_name(term)}
    right = {normalize_geo_name(term) for term in right_terms if normalize_geo_name(term)}
    return any(left_term in right or any(left_term in right_term or right_term in left_term for right_term in right) for left_term in left)


def _exact_or_normalized_matches(
    text: str,
    normalized_text: str,
    catalog: list[LdongCandidate],
) -> list[GeoMatch]:
    exact: list[GeoMatch] = []
    normalized: list[GeoMatch] = []
    compact_text = re.sub(r"\s+", "", text)
    for candidate in catalog:
        names = [candidate.full_name]
        if candidate.ldong_signgu_nm:
            names.append(candidate.ldong_signgu_nm)
        else:
            names.append(candidate.ldong_regn_nm)
        for name in names:
            if not name:
                continue
            compact_name = re.sub(r"\s+", "", name)
            if compact_name and compact_name in compact_text:
                exact.append(
                    GeoMatch(
                        candidate=candidate,
                        matched_text=name,
                        match_type="exact",
                        confidence=1.0,
                    )
                )
                break
            normalized_name = normalize_geo_name(name)
            if len(normalized_name) >= 2 and normalized_name in normalized_text:
                normalized.append(
                    GeoMatch(
                        candidate=candidate,
                        matched_text=name,
                        match_type="normalized",
                        confidence=0.92,
                    )
                )
                break
    return _dedupe_matches([*exact, *normalized])


def _alias_matches(
    text: str,
    normalized_text: str,
    catalog: list[LdongCandidate],
    existing: list[GeoMatch],
) -> list[GeoMatch]:
    existing_ids = {match.candidate.id for match in existing}
    matches: list[GeoMatch] = []
    compact_text = re.sub(r"\s+", "", text)
    for candidate in catalog:
        if candidate.id in existing_ids:
            continue
        for alias in candidate.aliases:
            compact_alias = re.sub(r"\s+", "", alias)
            normalized_alias = normalize_geo_name(alias)
            if compact_alias and compact_alias in compact_text:
                matches.append(
                    GeoMatch(
                        candidate=candidate,
                        matched_text=alias,
                        match_type="alias",
                        confidence=0.9,
                        keyword=alias,
                    )
                )
                break
            if len(normalized_alias) >= 2 and normalized_alias in normalized_text:
                matches.append(
                    GeoMatch(
                        candidate=candidate,
                        matched_text=alias,
                        match_type="alias",
                        confidence=0.88,
                        keyword=alias,
                    )
                )
                break
    return _dedupe_matches(matches)


def _fuzzy_matches(
    text: str,
    catalog: list[LdongCandidate],
) -> tuple[list[GeoMatch], list[dict[str, Any]]]:
    tokens = _geo_like_tokens(text)
    suggestions: list[dict[str, Any]] = []
    matches: list[GeoMatch] = []
    for token in tokens:
        token_norm = normalize_geo_name(token)
        if len(token_norm) < 2:
            continue
        scored: list[GeoMatch] = []
        for candidate in catalog:
            candidate_terms = [candidate.full_name, candidate.ldong_signgu_nm or "", *candidate.aliases]
            if not candidate.ldong_signgu_nm:
                candidate_terms.append(candidate.ldong_regn_nm)
            best_score = 0.0
            best_term = ""
            for term in candidate_terms:
                term_norm = normalize_geo_name(term)
                if len(term_norm) < 2:
                    continue
                score = _fuzzy_score(token_norm, term_norm)
                if score > best_score:
                    best_score = score
                    best_term = term
            if best_score >= 0.78:
                scored.append(
                    GeoMatch(
                        candidate=candidate,
                        matched_text=best_term or token,
                        match_type="fuzzy",
                        confidence=best_score,
                    )
                )
        scored = sorted(scored, key=lambda match: match.confidence, reverse=True)
        if scored:
            suggestions.append(
                {
                    "input": token,
                    "candidates": [_match_to_candidate(match) for match in scored[:5]],
                }
            )
        high = [match for match in scored if match.confidence >= 0.84]
        if len(high) == 1:
            matches.append(high[0])
        elif len(high) > 1 and high[0].confidence - high[1].confidence >= 0.04:
            matches.append(high[0])
    return _dedupe_matches(matches), suggestions


def _fuzzy_score(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if left in right or right in left:
        short = min(len(left), len(right))
        long = max(len(left), len(right))
        return max(0.78, short / long)
    ratio = SequenceMatcher(None, left, right).ratio()
    distance = _levenshtein_distance(left, right)
    if distance == 1 and min(len(left), len(right)) >= 2:
        ratio = max(ratio, 0.84)
    return ratio


def _levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    previous = list(range(len(right) + 1))
    for index_left, char_left in enumerate(left, start=1):
        current = [index_left]
        for index_right, char_right in enumerate(right, start=1):
            insert_cost = current[index_right - 1] + 1
            delete_cost = previous[index_right] + 1
            replace_cost = previous[index_right - 1] + (char_left != char_right)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _ambiguous_groups(matches: list[GeoMatch]) -> list[list[GeoMatch]]:
    groups: dict[str, list[GeoMatch]] = {}
    for match in matches:
        key = normalize_geo_name(match.matched_text)
        if match.candidate.ldong_signgu_nm:
            key = normalize_geo_name(match.candidate.ldong_signgu_nm)
        groups.setdefault(key, []).append(match)
    ambiguous: list[list[GeoMatch]] = []
    for group in groups.values():
        unique_ids = {match.candidate.id for match in group}
        if len(unique_ids) <= 1:
            continue
        top_confidence = max(match.confidence for match in group)
        top = [match for match in group if abs(match.confidence - top_confidence) <= 0.02]
        if len({match.candidate.id for match in top}) > 1:
            ambiguous.append(top)
    return ambiguous


def _collapse_parent_matches(matches: list[GeoMatch]) -> list[GeoMatch]:
    specific_region_codes = {
        match.candidate.ldong_regn_cd
        for match in matches
        if match.candidate.ldong_signgu_cd
    }
    collapsed = [
        match
        for match in matches
        if match.candidate.ldong_signgu_cd or match.candidate.ldong_regn_cd not in specific_region_codes
    ]
    return _dedupe_matches(collapsed)


def _apply_route_roles(text: str, matches: list[GeoMatch]) -> list[GeoMatch]:
    if len(matches) < 2:
        return matches
    role_matches: list[GeoMatch] = []
    route_detected = any(pattern in text for pattern in ROUTE_ORIGIN_PATTERNS + ROUTE_DESTINATION_PATTERNS)
    for match in matches:
        role = "primary"
        if route_detected:
            role = _infer_route_role(text, match)
        role_matches.append(
            GeoMatch(
                candidate=match.candidate,
                matched_text=match.matched_text,
                match_type=match.match_type,
                confidence=match.confidence,
                role=role,
                keyword=match.keyword,
            )
        )
    if route_detected and all(match.role == "primary" for match in role_matches):
        role_matches[0].role = "origin"
        role_matches[-1].role = "destination"
    if route_detected:
        role_order = {"origin": 0, "primary": 1, "destination": 2}
        role_matches = sorted(role_matches, key=lambda match: role_order.get(match.role, 1))
    return role_matches


def _infer_route_role(text: str, match: GeoMatch) -> str:
    terms = [
        match.matched_text,
        match.candidate.full_name,
        match.candidate.ldong_regn_nm,
        match.candidate.ldong_signgu_nm or "",
        *match.candidate.aliases,
    ]
    index = -1
    matched_text = ""
    for term in terms:
        if not term:
            continue
        index = text.find(term)
        matched_text = term
        if index >= 0:
            break
    if index < 0:
        return "primary"
    window = text[index : index + len(matched_text) + 16]
    if any(pattern in window for pattern in ROUTE_ORIGIN_PATTERNS):
        return "origin"
    if any(pattern in window for pattern in ROUTE_DESTINATION_PATTERNS):
        return "destination"
    before = text[max(0, index - 8) : index + len(matched_text)]
    if "까지" in before or "도착" in before:
        return "destination"
    return "primary"


def _extract_excluded_locations(text: str, catalog: list[LdongCandidate]) -> list[GeoMatch]:
    if not any(marker in text for marker in EXCLUSION_MARKERS):
        return []
    excluded: list[GeoMatch] = []
    for candidate in catalog:
        names = [candidate.full_name, candidate.ldong_signgu_nm or "", *candidate.aliases]
        for name in names:
            if name and name in text:
                index = text.find(name)
                window = text[index : index + len(name) + 12]
                if any(marker in window for marker in EXCLUSION_MARKERS):
                    excluded.append(
                        GeoMatch(
                            candidate=candidate,
                            matched_text=name,
                            match_type="excluded",
                            confidence=1.0,
                            role="excluded",
                        )
                    )
                    break
    return _dedupe_matches(excluded)


def _mode_from_matches(matches: list[GeoMatch]) -> str:
    roles = {match.role for match in matches}
    if "origin" in roles or "destination" in roles:
        return "route"
    if len(matches) > 1:
        return "multi_region"
    return "single_region"


def _has_specific_location_match(matches: list[GeoMatch]) -> bool:
    return any(match.candidate.ldong_signgu_cd for match in matches)


def _extract_sub_area_terms(text: str, matches: list[GeoMatch]) -> list[str]:
    matched_region_terms: set[str] = set()
    for match in matches:
        candidate = match.candidate
        for value in [
            candidate.full_name,
            candidate.ldong_regn_nm,
            candidate.ldong_signgu_nm or "",
            match.matched_text,
        ]:
            if value:
                matched_region_terms.add(normalize_geo_name(value))
    terms: list[str] = []
    for raw_term in SUB_AREA_PATTERN.findall(text):
        term = raw_term.strip()
        normalized = normalize_geo_name(term)
        if not normalized or normalized in matched_region_terms:
            continue
        terms.append(term)
    return list(dict.fromkeys(terms))


def _unresolved_locality_terms(text: str, matches: list[GeoMatch]) -> list[str]:
    if not matches:
        return []
    matched_terms: set[str] = set()
    top_level_matches = [match for match in matches if not match.candidate.ldong_signgu_cd]
    if not top_level_matches:
        return []
    for match in matches:
        candidate = match.candidate
        for value in [match.matched_text, candidate.full_name, candidate.ldong_regn_nm, *candidate.aliases]:
            if value:
                matched_terms.add(normalize_geo_name(value))

    unresolved: list[str] = []
    for match in top_level_matches:
        search_terms = [match.matched_text, match.candidate.ldong_regn_nm, *match.candidate.aliases]
        for term in search_terms:
            if not term:
                continue
            index = text.find(term)
            if index < 0:
                continue
            window = text[index + len(term) : index + len(term) + 18]
            for found in re.findall(r"\s*([가-힣A-Za-z0-9]{2,})(?:에서|일대|근처|군|시|구|읍|면|동)", window):
                normalized = normalize_geo_name(found)
                if normalized and normalized not in matched_terms:
                    unresolved.append(found)
    return list(dict.fromkeys(unresolved))


def _strategy_summary(matches: list[GeoMatch]) -> str:
    ordered = []
    for match in matches:
        if match.match_type not in ordered:
            ordered.append(match.match_type)
    return "+".join(ordered)


def _keywords_from_matches(matches: list[GeoMatch], *, sub_area_terms: list[str] | None = None) -> list[str]:
    keywords: list[str] = []
    for match in matches:
        if match.keyword:
            keywords.append(match.keyword)
        for alias in match.candidate.aliases:
            if alias == match.matched_text:
                keywords.append(alias)
    keywords.extend(sub_area_terms or [])
    return list(dict.fromkeys(keywords))


def _match_to_location(match: GeoMatch, *, sub_area_terms: list[str] | None = None) -> dict[str, Any]:
    candidate = match.candidate
    local_terms = list(sub_area_terms or [])
    name = candidate.display_name
    if local_terms:
        name = f"{name} {' '.join(local_terms)} 일대"
    return {
        "role": match.role,
        "name": name,
        "base_name": candidate.display_name,
        "matched_text": match.matched_text,
        "match_type": match.match_type,
        "confidence": round(match.confidence, 4),
        "ldong_regn_cd": candidate.ldong_regn_cd,
        "ldong_regn_nm": candidate.ldong_regn_nm,
        "ldong_signgu_cd": candidate.ldong_signgu_cd,
        "ldong_signgu_nm": candidate.ldong_signgu_nm,
        "keyword": match.keyword,
        "sub_area_terms": local_terms,
    }


def _match_to_candidate(match: GeoMatch) -> dict[str, Any]:
    location = _match_to_location(match)
    return {
        "name": location["name"],
        "matched_text": location["matched_text"],
        "match_type": location["match_type"],
        "confidence": location["confidence"],
        "ldong_regn_cd": location["ldong_regn_cd"],
        "ldong_signgu_cd": location["ldong_signgu_cd"],
    }


def _clarification_scope(
    *,
    input_text: str,
    matches: list[GeoMatch],
    ambiguous_groups: list[list[GeoMatch]],
    fuzzy_suggestions: list[dict[str, Any]],
    excluded: list[GeoMatch],
    sub_area_terms: list[str],
    unresolved_terms: list[str],
    reason: str,
    llm_hints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = []
    for group in ambiguous_groups:
        candidates.extend(_match_to_candidate(match) for match in group)
    if not candidates:
        for suggestion in fuzzy_suggestions:
            candidates.extend(suggestion.get("candidates") or [])
    candidates = _dedupe_dicts(candidates)
    return {
        "mode": "clarification_required",
        "status": "needs_clarification",
        "needs_clarification": True,
        "clarification_question": "지역을 하나로 확정할 수 없습니다. 후보 중 원하는 지역을 선택해 주세요.",
        "confidence": min((candidate.get("confidence", 0.0) for candidate in candidates), default=0.0),
        "input_text": input_text,
        "locations": [_match_to_location(match, sub_area_terms=sub_area_terms) for match in matches],
        "excluded_locations": [_match_to_location(match) for match in excluded],
        "unresolved_locations": [
            {
                "input": input_text,
                "reason": reason,
                "terms": unresolved_terms,
                "candidates": candidates,
            }
        ],
        "keywords": _keywords_from_matches(matches, sub_area_terms=sub_area_terms),
        "sub_area_terms": sub_area_terms,
        "allow_nationwide": False,
        "resolution_strategy": reason,
        "candidates": candidates,
        "fuzzy_suggestions": fuzzy_suggestions,
        "llm_hints": llm_hints or {},
    }


def _dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _dedupe_matches(matches: list[GeoMatch]) -> list[GeoMatch]:
    best_by_id: dict[str, GeoMatch] = {}
    for match in matches:
        existing = best_by_id.get(match.candidate.id)
        if not existing or match.confidence > existing.confidence or (
            match.confidence == existing.confidence and match.candidate.specificity > existing.candidate.specificity
        ):
            best_by_id[match.candidate.id] = match
    return sorted(
        best_by_id.values(),
        key=lambda match: (match.candidate.specificity, match.confidence, len(match.candidate.full_name)),
        reverse=True,
    )


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (item.get("ldong_regn_cd"), item.get("ldong_signgu_cd"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _geo_like_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[가-힣A-Za-z]{2,}", text)
    blocked = {
        "이번",
        "외국인",
        "대상",
        "액티비티",
        "상품",
        "기획",
        "여행",
        "관광",
        "축제",
        "시작",
        "끝나는",
        "도착",
        "출발",
        "해주세요",
        "해줘",
    }
    cleaned: list[str] = []
    for token in tokens:
        token = re.sub(r"(에서|으로|부터|까지|에는|은|는|이|가|을|를|의)$", "", token)
        if len(token) >= 2 and token not in blocked:
            cleaned.append(token)
    return cleaned


def _foreign_destination_terms(text: str) -> list[str]:
    if not text:
        return []
    compact = re.sub(r"\s+", "", text)
    foreign_terms: list[str] = []
    domestic_context_exists = any(term in text for term in FOREIGN_CONTEXT_EXCEPTIONS)
    for term in FOREIGN_DESTINATION_TERMS:
        if term == "해외" and domestic_context_exists:
            continue
        if term in text or term in compact:
            foreign_terms.append(term)
    return sorted(set(foreign_terms), key=len, reverse=True)


def _combined_input(*, message: str | None, region: str | None) -> str:
    parts = [str(message or "").strip()]
    region_text = str(region or "").strip()
    if region_text and region_text not in parts[0]:
        parts.append(region_text)
    return " ".join(part for part in parts if part).strip()


def _is_nationwide_request(text: str) -> bool:
    normalized = normalize_geo_name(text)
    return any(term in text or normalize_geo_name(term) in normalized for term in EXPLICIT_NATIONWIDE_TERMS)


def _catalog_not_synced_scope(input_text: str) -> dict[str, Any]:
    return {
        "mode": "catalog_required",
        "status": "needs_clarification",
        "needs_clarification": True,
        "clarification_question": "TourAPI 법정동 지역 catalog가 동기화되지 않았습니다.",
        "confidence": 0.0,
        "input_text": input_text,
        "locations": [],
        "excluded_locations": [],
        "unresolved_locations": [
            {
                "input": input_text,
                "reason": "tourapi_ldong_catalog_not_synced",
                "candidates": [],
            }
        ],
        "keywords": [],
        "allow_nationwide": False,
        "resolution_strategy": "catalog_not_synced",
        "candidates": [],
    }
