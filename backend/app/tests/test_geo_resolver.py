import pytest

from app.agents.geo_resolver import resolve_geo_scope
from app.db.session import SessionLocal, init_db
from app.tests.geo_catalog_helpers import seed_test_ldong_catalog


@pytest.fixture(scope="module", autouse=True)
def initialize_db():
    init_db()
    with SessionLocal() as db:
        seed_test_ldong_catalog(db)


@pytest.mark.parametrize(
    ("message", "expected_regn", "expected_signgu"),
    [
        ("대전 외국인 액티비티 3개", "30", None),
        ("대전 유성구 외국인 액티비티", "30", "200"),
        ("울릉도 트레킹 상품", "47", "940"),
        ("영양 자연 체험", "47", "760"),
        ("양산에서 즐기는 가족 상품", "48", "330"),
        ("전남 장흥에서 외국인 대상 액티비티 상품", "46", "800"),
        ("장흥에서 외국인 대상 액티비티 상품", "46", "800"),
        ("청도에서 외국인 대상 액티비티 상품을 3개 기획해줘", "47", "820"),
    ],
)
def test_geo_resolver_resolves_catalog_and_alias_codes(message, expected_regn, expected_signgu):
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message=message)

    assert scope["needs_clarification"] is False
    assert scope["locations"][0]["ldong_regn_cd"] == expected_regn
    assert scope["locations"][0]["ldong_signgu_cd"] == expected_signgu


def test_geo_resolver_does_not_match_cheongdo_inside_daecheongdo():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="대청도 액티비티 상품을 만들어줘")

    assert scope["needs_clarification"] is True
    assert scope["locations"] == []
    assert not any(
        candidate.get("ldong_regn_cd") == "47" and candidate.get("ldong_signgu_cd") == "820"
        for suggestion in scope.get("fuzzy_suggestions", [])
        for candidate in suggestion.get("candidates", [])
    )


def test_geo_resolver_uses_gemini_catalog_selection_for_locality_not_in_ldong_catalog():
    llm_hints = {
        "locations": [
            {
                "text": "대청도",
                "normalized_text": "대청도",
                "role": "primary",
                "is_foreign": False,
            }
        ],
        "resolved_locations": [
            {
                "text": "대청도",
                "role": "primary",
                "name": "인천광역시 옹진군",
                "ldong_regn_cd": "28",
                "ldong_signgu_cd": "720",
                "confidence": 0.93,
                "reason": "대청도는 인천광역시 옹진군 관할 섬으로 판단됩니다.",
            }
        ],
        "excluded_locations": [],
        "allow_nationwide": False,
        "unsupported_locations": [],
    }
    with SessionLocal() as db:
        scope = resolve_geo_scope(
            db,
            message="이번 달 대청도에서 외국인 대상 액티비티 상품을 3개 기획해줘",
            llm_hints=llm_hints,
        )

    assert scope["needs_clarification"] is False
    assert scope["locations"][0]["name"] == "인천광역시 옹진군"
    assert scope["locations"][0]["matched_text"] == "대청도"
    assert scope["locations"][0]["match_type"] == "llm_catalog"
    assert scope["locations"][0]["ldong_regn_cd"] == "28"
    assert scope["locations"][0]["ldong_signgu_cd"] == "720"
    assert scope["keywords"] == ["대청도"]


def test_geo_resolver_does_not_treat_administrative_llm_match_as_keyword():
    llm_hints = {
        "locations": [
            {
                "text": "부산 부산진구",
                "normalized_text": "부산광역시 부산진구",
                "role": "primary",
                "is_foreign": False,
            }
        ],
        "resolved_locations": [
            {
                "text": "부산 부산진구",
                "role": "primary",
                "name": "부산광역시 부산진구",
                "ldong_regn_cd": "26",
                "ldong_signgu_cd": "230",
                "confidence": 0.99,
                "reason": "사용자가 부산 부산진구를 명확히 언급했습니다.",
            }
        ],
        "excluded_locations": [],
        "allow_nationwide": False,
        "unsupported_locations": [],
    }
    with SessionLocal() as db:
        scope = resolve_geo_scope(
            db,
            message="부산 부산진구에서 외국인 대상 감성 야간 관광 상품 3개 기획해줘",
            llm_hints=llm_hints,
        )

    assert scope["needs_clarification"] is False
    assert scope["locations"][0]["ldong_regn_cd"] == "26"
    assert scope["locations"][0]["ldong_signgu_cd"] == "230"
    assert scope["locations"][0]["keyword"] is None
    assert scope["keywords"] == []


@pytest.mark.parametrize("message", ["영종도 액티비티", "가덕도 해양 액티비티"])
def test_geo_resolver_does_not_force_non_catalog_place_aliases(message):
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message=message)

    assert scope["needs_clarification"] is True
    assert scope["allow_nationwide"] is False
    assert scope["locations"] == []


def test_geo_resolver_blocks_route_origin_and_destination():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="부산에서 시작해서 양산에서 끝나는 상품을 기획해줘")

    assert scope["mode"] == "unsupported_multi_region"
    assert scope["needs_clarification"] is True
    assert scope["allow_nationwide"] is False
    assert "하나의 지역" in scope["clarification_question"] or "하나만" in scope["clarification_question"]
    assert {candidate["ldong_regn_cd"] for candidate in scope["candidates"]} >= {"26", "48"}


def test_geo_resolver_blocks_multiple_regions_without_route_expression():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="부산과 양산에서 외국인 대상 관광 상품을 기획해줘")

    assert scope["mode"] == "unsupported_multi_region"
    assert scope["status"] == "needs_clarification"
    assert scope["needs_clarification"] is True
    assert {candidate["ldong_regn_cd"] for candidate in scope["candidates"]} >= {"26", "48"}


def test_geo_resolver_marks_ambiguous_signgu_for_clarification():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="중구 야간 관광 상품을 만들어줘")

    assert scope["needs_clarification"] is True
    assert scope["status"] == "needs_clarification"
    assert len(scope["candidates"]) >= 2
    assert {candidate["ldong_signgu_cd"] for candidate in scope["candidates"]} >= {"110", "140"}


def test_geo_resolver_uses_parent_region_context_for_ambiguous_signgu():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="대전 중구 야간 관광 상품을 만들어줘")

    assert scope["needs_clarification"] is False
    assert scope["locations"][0]["ldong_regn_cd"] == "30"
    assert scope["locations"][0]["ldong_signgu_cd"] == "140"


@pytest.mark.parametrize(
    ("message", "expected_signgu", "expected_sub_area"),
    [
        ("부산 중구 남포동 일대 외국인 상품을 기획해줘", "110", "남포동"),
        ("부산 부산진구 전포동 일대 카페 투어를 기획해줘", "230", "전포동"),
    ],
)
def test_geo_resolver_preserves_fine_grained_locality_terms(
    message,
    expected_signgu,
    expected_sub_area,
):
    resolved_text = message.split(" 일대")[0].replace(" 외국인 상품을 기획해줘", "").replace(" 카페 투어를 기획해줘", "")
    signgu_name = "부산광역시 중구" if expected_signgu == "110" else "부산광역시 부산진구"
    llm_hints = {
        "locations": [
            {
                "text": resolved_text,
                "normalized_text": f"{signgu_name} {expected_sub_area}",
                "role": "primary",
                "is_foreign": False,
            }
        ],
        "resolved_locations": [
            {
                "text": resolved_text,
                "role": "primary",
                "name": signgu_name,
                "ldong_regn_cd": "26",
                "ldong_signgu_cd": expected_signgu,
                "confidence": 0.95,
                "reason": f"{expected_sub_area}은 {signgu_name} 관할로 판단됩니다.",
                "sub_area_terms": [expected_sub_area],
                "keywords": [expected_sub_area],
            }
        ],
        "excluded_locations": [],
        "allow_nationwide": False,
        "unsupported_locations": [],
    }
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message=message, llm_hints=llm_hints)

    assert scope["needs_clarification"] is False
    assert scope["mode"] == "single_region"
    assert len(scope["locations"]) == 1
    assert scope["locations"][0]["ldong_regn_cd"] == "26"
    assert scope["locations"][0]["ldong_signgu_cd"] == expected_signgu
    assert expected_sub_area in scope["locations"][0]["sub_area_terms"]
    assert expected_sub_area in scope["keywords"]
    assert all(location["ldong_regn_cd"] == "26" for location in scope["locations"])


def test_geo_resolver_does_not_add_unmentioned_regions_from_locality_suffix():
    llm_hints = {
        "locations": [
            {
                "text": "부산 부산진구 전포동",
                "normalized_text": "부산광역시 부산진구 전포동",
                "role": "primary",
                "is_foreign": False,
            }
        ],
        "resolved_locations": [
            {
                "text": "부산 부산진구 전포동",
                "role": "primary",
                "name": "부산광역시 부산진구",
                "ldong_regn_cd": "26",
                "ldong_signgu_cd": "230",
                "confidence": 0.95,
                "reason": "전포동은 부산광역시 부산진구 관할로 판단됩니다.",
                "sub_area_terms": ["전포동"],
                "keywords": ["전포동"],
            }
        ],
        "excluded_locations": [],
        "allow_nationwide": False,
        "unsupported_locations": [],
    }
    with SessionLocal() as db:
        scope = resolve_geo_scope(
            db,
            message="부산 부산진구 전포동 일대 카페 투어 상품 3개 기획해줘",
            llm_hints=llm_hints,
        )

    assert scope["needs_clarification"] is False
    assert scope["mode"] == "single_region"
    assert len(scope["locations"]) == 1
    assert scope["locations"][0]["name"] == "부산광역시 부산진구 전포동 일대"
    assert scope["locations"][0]["ldong_regn_cd"] == "26"
    assert scope["locations"][0]["ldong_signgu_cd"] == "230"
    assert scope["keywords"] == ["전포동"]


def test_geo_resolver_does_not_treat_pet_theme_as_dong_sub_area():
    llm_hints = {
        "locations": [
            {
                "text": "부산",
                "normalized_text": "부산광역시",
                "role": "primary",
                "is_foreign": False,
            }
        ],
        "resolved_locations": [
            {
                "text": "부산",
                "role": "primary",
                "name": "부산광역시",
                "ldong_regn_cd": "26",
                "ldong_signgu_cd": "",
                "confidence": 0.9,
                "reason": "사용자 요청에 명시된 부산은 부산광역시 전체입니다.",
            }
        ],
        "excluded_locations": [],
        "allow_nationwide": False,
        "unsupported_locations": [],
    }
    with SessionLocal() as db:
        scope = resolve_geo_scope(
            db,
            message="부산에서 반려동물 동반 외국인 대상 관광 상품 3개 기획해줘. 반려동물 동반 조건은 근거가 있는 경우에만 써줘.",
            llm_hints=llm_hints,
        )

    assert scope["needs_clarification"] is False
    assert scope["locations"][0]["name"] == "부산광역시"
    assert scope["locations"][0]["sub_area_terms"] == []
    assert "반려동" not in scope["keywords"]
    assert scope["keywords"] == []


def test_geo_resolver_does_not_treat_pet_theme_as_unknown_subregion_without_llm_hints():
    with SessionLocal() as db:
        scope = resolve_geo_scope(
            db,
            message="부산에서 반려동물 동반 외국인 대상 관광 상품 3개 기획해줘",
        )

    assert scope["needs_clarification"] is False
    assert scope["locations"][0]["name"] == "부산광역시"
    assert scope["locations"][0]["sub_area_terms"] == []
    assert scope["unresolved_locations"] == []


def test_geo_resolver_blocks_foreign_destination():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="도쿄에서 외국인 대상 액티비티 상품을 만들어줘")

    assert scope["status"] == "unsupported"
    assert scope["mode"] == "unsupported_region"
    assert scope["allow_nationwide"] is False
    assert "도쿄" in scope["unsupported_locations"]


def test_geo_resolver_keeps_fuzzy_candidates_for_typo_without_forced_selection():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="대젼 액티비티 상품을 만들어줘")

    assert scope["needs_clarification"] is True
    assert scope["locations"] == []
    assert scope["fuzzy_suggestions"]
    assert any(
        candidate["ldong_regn_cd"] == "30"
        for suggestion in scope["fuzzy_suggestions"]
        for candidate in suggestion["candidates"]
    )


def test_geo_resolver_does_not_allow_nationwide_fallback_for_unresolved_region():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="없는지역 액티비티를 찾아줘")

    assert scope["needs_clarification"] is True
    assert scope["allow_nationwide"] is False
    assert scope["locations"] == []


def test_geo_resolver_does_not_silently_broaden_when_subregion_is_unknown():
    llm_hints = {
        "locations": [
            {
                "text": "전남 없는지역",
                "normalized_text": "전라남도 없는지역",
                "role": "primary",
                "is_foreign": False,
            }
        ],
        "resolved_locations": [],
        "clarification_candidates": [],
        "excluded_locations": [],
        "allow_nationwide": False,
        "unsupported_locations": [],
    }
    with SessionLocal() as db:
        scope = resolve_geo_scope(
            db,
            message="전남 없는지역에서 액티비티를 찾아줘",
            llm_hints=llm_hints,
        )

    assert scope["needs_clarification"] is True
    assert scope["allow_nationwide"] is False
    assert scope["unresolved_locations"][0]["reason"] == "unresolved_location"


def test_geo_resolver_allows_nationwide_only_when_explicit():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="전국 축제 중 외국인 대상 상품을 기획해줘")

    assert scope["mode"] == "nationwide"
    assert scope["allow_nationwide"] is True
    assert scope["needs_clarification"] is False
