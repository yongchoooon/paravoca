from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.geo_resolver import normalize_geo_name
from app.db import models


TEST_LDONG_ROWS = [
    ("11", "서울특별시", None, None, ["서울"]),
    ("26", "부산광역시", None, None, ["부산"]),
    ("27", "대구광역시", None, None, ["대구"]),
    ("28", "인천광역시", None, None, ["인천"]),
    ("29", "광주광역시", None, None, ["광주"]),
    ("30", "대전광역시", None, None, ["대전"]),
    ("31", "울산광역시", None, None, ["울산"]),
    ("46", "전라남도", None, None, ["전남"]),
    ("47", "경상북도", None, None, ["경북"]),
    ("48", "경상남도", None, None, ["경남"]),
    ("51", "강원특별자치도", None, None, ["강원", "강원도"]),
    ("11", "서울특별시", "140", "중구", []),
    ("26", "부산광역시", "110", "중구", []),
    ("26", "부산광역시", "230", "부산진구", []),
    ("26", "부산광역시", "440", "강서구", []),
    ("27", "대구광역시", "110", "중구", []),
    ("28", "인천광역시", "110", "중구", []),
    ("29", "광주광역시", "110", "동구", []),
    ("30", "대전광역시", "140", "중구", []),
    ("30", "대전광역시", "200", "유성구", []),
    ("31", "울산광역시", "110", "중구", []),
    ("46", "전라남도", "800", "장흥군", []),
    ("47", "경상북도", "210", "영주시", []),
    ("47", "경상북도", "760", "영양군", []),
    ("47", "경상북도", "940", "울릉군", []),
    ("48", "경상남도", "330", "양산시", []),
    ("51", "강원특별자치도", "830", "양양군", []),
]


def seed_test_ldong_catalog(db: Session) -> None:
    for regn_cd, regn_nm, signgu_cd, signgu_nm, aliases in TEST_LDONG_ROWS:
        full_name = f"{regn_nm} {signgu_nm}".strip() if signgu_nm else regn_nm
        row_id = f"ldong:{regn_cd}:{signgu_cd or '*'}"
        row_aliases = list(aliases)
        if signgu_nm:
            short_signgu = normalize_geo_name(signgu_nm)
            if len(short_signgu) >= 2 and short_signgu != signgu_nm:
                row_aliases.append(short_signgu)
        else:
            short_regn = normalize_geo_name(regn_nm)
            if len(short_regn) >= 2 and short_regn != regn_nm:
                row_aliases.append(short_regn)
        payload = {
            "id": row_id,
            "ldong_regn_cd": regn_cd,
            "ldong_regn_nm": regn_nm,
            "ldong_signgu_cd": signgu_cd,
            "ldong_signgu_nm": signgu_nm,
            "full_name": full_name,
            "normalized_name": normalize_geo_name(full_name),
            "aliases": list(dict.fromkeys(row_aliases)),
            "raw": {"source": "test_catalog"},
            "synced_at": models.utcnow(),
        }
        existing = db.get(models.TourApiLdongCode, row_id)
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            existing.updated_at = models.utcnow()
        else:
            db.add(models.TourApiLdongCode(**payload))
    db.commit()
