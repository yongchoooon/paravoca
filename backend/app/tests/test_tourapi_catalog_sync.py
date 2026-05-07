from app.db import models
from app.db.session import SessionLocal, init_db
from app.tools.sync_tourapi_catalogs import sync_lcls_catalog, sync_ldong_catalog


class OfficialShapeLdongProvider:
    def __init__(self) -> None:
        self.calls = []

    def ldong_code(
        self,
        *,
        ldong_regn_cd=None,
        ldong_signgu_cd=None,
        list_yn="N",
        page_no=1,
        limit=100,
    ):
        self.calls.append(
            {
                "ldong_regn_cd": ldong_regn_cd,
                "ldong_signgu_cd": ldong_signgu_cd,
                "list_yn": list_yn,
                "page_no": page_no,
                "limit": limit,
            }
        )
        if list_yn == "Y" and page_no == 1:
            return [
                {
                    "lDongRegnCd": "46",
                    "lDongRegnNm": "전라남도",
                    "lDongSignguCd": "800",
                    "lDongSignguNm": "장흥군",
                }
            ]
        return []


class OfficialShapeLclsProvider:
    def __init__(self) -> None:
        self.calls = []

    def lcls_system_code(
        self,
        *,
        lcls_systm_1=None,
        lcls_systm_2=None,
        lcls_systm_3=None,
        list_yn="N",
        page_no=1,
        limit=1000,
    ):
        self.calls.append(
            {
                "lcls_systm_1": lcls_systm_1,
                "lcls_systm_2": lcls_systm_2,
                "lcls_systm_3": lcls_systm_3,
                "list_yn": list_yn,
                "page_no": page_no,
                "limit": limit,
            }
        )
        if lcls_systm_1 == "EV" and lcls_systm_2 == "EV01":
            return [{"code": "EV010100", "name": "문화관광축제"}]
        if lcls_systm_1 == "EV":
            return [{"code": "EV01", "name": "축제"}]
        return [{"code": "EV", "name": "축제/공연/행사"}]


def test_sync_ldong_catalog_uses_official_code_name_shape():
    init_db()
    provider = OfficialShapeLdongProvider()

    with SessionLocal() as db:
        count = sync_ldong_catalog(db, provider)  # type: ignore[arg-type]
        jangheung = db.get(models.TourApiLdongCode, "ldong:46:800")

    assert count == 2
    assert [call["list_yn"] for call in provider.calls] == ["Y"]
    assert [call["page_no"] for call in provider.calls] == [1]
    assert jangheung is not None
    assert jangheung.ldong_regn_cd == "46"
    assert jangheung.ldong_regn_nm == "전라남도"
    assert jangheung.ldong_signgu_cd == "800"
    assert jangheung.ldong_signgu_nm == "장흥군"
    assert jangheung.full_name == "전라남도 장흥군"


def test_sync_lcls_catalog_uses_official_code_name_shape():
    init_db()
    provider = OfficialShapeLclsProvider()

    with SessionLocal() as db:
        count = sync_lcls_catalog(db, provider)  # type: ignore[arg-type]
        festival = db.get(models.TourApiLclsCode, "lcls:EV:EV01:EV010100")

    assert count == 3
    assert [call["list_yn"] for call in provider.calls] == ["N", "N", "N"]
    assert festival is not None
    assert festival.lcls_systm_1 == "EV"
    assert festival.lcls_systm_1_nm == "축제/공연/행사"
    assert festival.lcls_systm_2 == "EV01"
    assert festival.lcls_systm_2_nm == "축제"
    assert festival.lcls_systm_3 == "EV010100"
    assert festival.lcls_systm_3_nm == "문화관광축제"
    assert festival.content_type_id == "15"
