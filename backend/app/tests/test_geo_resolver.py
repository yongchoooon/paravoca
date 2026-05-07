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
    ],
)
def test_geo_resolver_resolves_catalog_and_alias_codes(message, expected_regn, expected_signgu):
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message=message)

    assert scope["needs_clarification"] is False
    assert scope["locations"][0]["ldong_regn_cd"] == expected_regn
    assert scope["locations"][0]["ldong_signgu_cd"] == expected_signgu


@pytest.mark.parametrize("message", ["영종도 액티비티", "가덕도 해양 액티비티"])
def test_geo_resolver_does_not_force_non_catalog_place_aliases(message):
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message=message)

    assert scope["needs_clarification"] is True
    assert scope["allow_nationwide"] is False
    assert scope["locations"] == []


def test_geo_resolver_detects_route_origin_and_destination():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="부산에서 시작해서 양산에서 끝나는 상품을 기획해줘")

    assert scope["mode"] == "route"
    roles = {location["role"]: location for location in scope["locations"]}
    assert roles["origin"]["ldong_regn_cd"] == "26"
    assert roles["destination"]["ldong_regn_cd"] == "48"
    assert roles["destination"]["ldong_signgu_cd"] == "330"


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
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message=message)

    assert scope["needs_clarification"] is False
    assert scope["mode"] == "single_region"
    assert len(scope["locations"]) == 1
    assert scope["locations"][0]["ldong_regn_cd"] == "26"
    assert scope["locations"][0]["ldong_signgu_cd"] == expected_signgu
    assert expected_sub_area in scope["locations"][0]["sub_area_terms"]
    assert expected_sub_area in scope["keywords"]
    assert all(location["ldong_regn_cd"] == "26" for location in scope["locations"])


def test_geo_resolver_does_not_add_unmentioned_regions_from_locality_suffix():
    with SessionLocal() as db:
        scope = resolve_geo_scope(
            db,
            message="부산 부산진구 전포동 일대 카페 투어 상품 3개 기획해줘",
        )

    assert scope["needs_clarification"] is False
    assert scope["mode"] == "single_region"
    assert len(scope["locations"]) == 1
    assert scope["locations"][0]["name"] == "부산광역시 부산진구 전포동 일대"
    assert scope["locations"][0]["ldong_regn_cd"] == "26"
    assert scope["locations"][0]["ldong_signgu_cd"] == "230"
    assert scope["keywords"] == ["전포동"]


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
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="전남 없는지역에서 액티비티를 찾아줘")

    assert scope["needs_clarification"] is True
    assert scope["allow_nationwide"] is False
    assert scope["unresolved_locations"][0]["reason"] == "unresolved_subregion"


def test_geo_resolver_allows_nationwide_only_when_explicit():
    with SessionLocal() as db:
        scope = resolve_geo_scope(db, message="전국 축제 중 외국인 대상 상품을 기획해줘")

    assert scope["mode"] == "nationwide"
    assert scope["allow_nationwide"] is True
    assert scope["needs_clarification"] is False
