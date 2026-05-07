from __future__ import annotations

import argparse
from typing import Any

from sqlalchemy.orm import Session

from app.agents.geo_resolver import PROVINCE_ALIASES, normalize_geo_name
from app.db import models
from app.db.session import SessionLocal, init_db
from app.tools.tourism import TourApiProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync TourAPI v4.4 ldong/lcls catalogs.")
    parser.add_argument("--skip-ldong", action="store_true", help="Skip ldongCode2 sync.")
    parser.add_argument("--skip-lcls", action="store_true", help="Skip lclsSystmCode2 sync.")
    parser.add_argument("--reset", action="store_true", help="Delete existing catalog rows before sync.")
    args = parser.parse_args()

    init_db()
    provider = TourApiProvider()
    with SessionLocal() as db:
        if args.reset:
            if not args.skip_ldong:
                db.query(models.TourApiLdongCode).delete()
            if not args.skip_lcls:
                db.query(models.TourApiLclsCode).delete()
            db.commit()
        ldong_count = 0 if args.skip_ldong else sync_ldong_catalog(db, provider)
        lcls_count = 0 if args.skip_lcls else sync_lcls_catalog(db, provider)
    print(f"TourAPI catalog sync complete: ldong={ldong_count}, lcls={lcls_count}")


def sync_ldong_catalog(db: Session, provider: TourApiProvider) -> int:
    rows = _paged_ldong_rows(provider, list_yn="Y", limit=1000)
    seen: set[tuple[str, str | None]] = set()
    upserted = 0
    for row in rows:
        payload = _ldong_payload_from_row(row)
        if not payload:
            continue
        regn_cd, regn_nm, signgu_cd, signgu_nm = payload
        if (regn_cd, None) not in seen:
            upserted += _upsert_ldong_payload(
                db,
                regn_cd=regn_cd,
                regn_nm=regn_nm,
                signgu_cd=None,
                signgu_nm=None,
                raw=row,
            )
            seen.add((regn_cd, None))
        if not signgu_cd or (regn_cd, signgu_cd) in seen:
            continue
        upserted += _upsert_ldong_payload(
            db,
            regn_cd=regn_cd,
            regn_nm=regn_nm,
            signgu_cd=signgu_cd,
            signgu_nm=signgu_nm,
            raw=row,
        )
        seen.add((regn_cd, signgu_cd))
    db.commit()
    return upserted


def _paged_ldong_rows(provider: TourApiProvider, *, list_yn: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_no = 1
    while True:
        page = provider.ldong_code(list_yn=list_yn, page_no=page_no, limit=limit)
        if not page:
            break
        rows.extend(page)
        if len(page) < limit:
            break
        page_no += 1
        if page_no > 1000:
            raise RuntimeError("ldongCode2 paging exceeded 1000 pages")
    return rows


def sync_lcls_catalog(db: Session, provider: TourApiProvider) -> int:
    rows = provider.lcls_system_code(list_yn="N", limit=100)
    seen: set[tuple[str | None, str | None, str | None]] = set()
    upserted = 0
    for row in rows:
        payload = _lcls_payload_from_row(row)
        if not payload:
            continue
        l1, l1_nm, l2, l2_nm, l3, l3_nm = payload
        key = (l1, l2, l3)
        if key not in seen:
            upserted += _upsert_lcls_payload(
                db,
                l1=l1,
                l1_nm=l1_nm,
                l2=l2,
                l2_nm=l2_nm,
                l3=l3,
                l3_nm=l3_nm,
                raw=row,
            )
            seen.add(key)
        if not l1:
            continue
        for second in provider.lcls_system_code(lcls_systm_1=l1, list_yn="N", limit=500):
            second_payload = _lcls_payload_from_row(
                second,
                parent_l1=l1,
                parent_l1_nm=l1_nm,
            )
            if not second_payload:
                continue
            child_l1, child_l1_nm, child_l2, child_l2_nm, child_l3, child_l3_nm = second_payload
            child_key = (child_l1, child_l2, child_l3)
            if child_key not in seen:
                upserted += _upsert_lcls_payload(
                    db,
                    l1=child_l1,
                    l1_nm=child_l1_nm,
                    l2=child_l2,
                    l2_nm=child_l2_nm,
                    l3=child_l3,
                    l3_nm=child_l3_nm,
                    raw=second,
                )
                seen.add(child_key)
            if not child_l2:
                continue
            for third in provider.lcls_system_code(
                lcls_systm_1=child_l1,
                lcls_systm_2=child_l2,
                list_yn="N",
                limit=500,
            ):
                third_payload = _lcls_payload_from_row(
                    third,
                    parent_l1=child_l1,
                    parent_l1_nm=child_l1_nm,
                    parent_l2=child_l2,
                    parent_l2_nm=child_l2_nm,
                )
                if not third_payload:
                    continue
                grand_l1, grand_l1_nm, grand_l2, grand_l2_nm, grand_l3, grand_l3_nm = third_payload
                grand_key = (grand_l1, grand_l2, grand_l3)
                if grand_key in seen:
                    continue
                upserted += _upsert_lcls_payload(
                    db,
                    l1=grand_l1,
                    l1_nm=grand_l1_nm,
                    l2=grand_l2,
                    l2_nm=grand_l2_nm,
                    l3=grand_l3,
                    l3_nm=grand_l3_nm,
                    raw=third,
                )
                seen.add(grand_key)
    db.commit()
    return upserted


def _ldong_payload_from_row(
    row: dict[str, Any],
    *,
    parent_regn_cd: str | None = None,
    parent_regn_nm: str | None = None,
) -> tuple[str, str, str | None, str | None] | None:
    code = _string_value(row, "code", "Code")
    name = _string_value(row, "name", "Name")
    regn_cd = _string_value(row, "lDongRegnCd", "ldongRegnCd", "ldong_regn_cd")
    regn_nm = _string_value(row, "lDongRegnNm", "ldongRegnNm", "ldong_regn_nm")
    signgu_cd = _string_value(row, "lDongSignguCd", "ldongSignguCd", "ldong_signgu_cd")
    signgu_nm = _string_value(row, "lDongSignguNm", "ldongSignguNm", "ldong_signgu_nm")

    if parent_regn_cd:
        regn_cd = regn_cd or parent_regn_cd
        regn_nm = regn_nm or parent_regn_nm
        signgu_cd = signgu_cd or code
        signgu_nm = signgu_nm or name
    else:
        regn_cd = regn_cd or code
        regn_nm = regn_nm or name

    if not regn_cd or not regn_nm:
        return None
    return regn_cd, regn_nm, signgu_cd, signgu_nm


def _upsert_ldong_payload(
    db: Session,
    *,
    regn_cd: str,
    regn_nm: str,
    signgu_cd: str | None,
    signgu_nm: str | None,
    raw: dict[str, Any],
) -> int:
    full_name = f"{regn_nm} {signgu_nm}".strip() if signgu_nm else regn_nm
    row_id = f"ldong:{regn_cd}:{signgu_cd or '*'}"
    payload = {
        "id": row_id,
        "ldong_regn_cd": regn_cd,
        "ldong_regn_nm": regn_nm,
        "ldong_signgu_cd": signgu_cd,
        "ldong_signgu_nm": signgu_nm,
        "full_name": full_name,
        "normalized_name": normalize_geo_name(full_name),
        "aliases": _ldong_aliases(regn_nm=regn_nm, signgu_nm=signgu_nm),
        "raw": raw,
        "synced_at": models.utcnow(),
    }
    existing = db.get(models.TourApiLdongCode, row_id)
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.updated_at = models.utcnow()
    else:
        db.add(models.TourApiLdongCode(**payload))
    return 1


def _lcls_payload_from_row(
    row: dict[str, Any],
    *,
    parent_l1: str | None = None,
    parent_l1_nm: str | None = None,
    parent_l2: str | None = None,
    parent_l2_nm: str | None = None,
) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None] | None:
    code = _string_value(row, "code", "Code")
    name = _string_value(row, "name", "Name")
    l1 = _string_value(row, "lclsSystm1", "lclsSystm1Cd", "lcls_systm_1")
    l1_nm = _string_value(row, "lclsSystm1Nm", "lcls_systm_1_nm")
    l2 = _string_value(row, "lclsSystm2", "lclsSystm2Cd", "lcls_systm_2")
    l2_nm = _string_value(row, "lclsSystm2Nm", "lcls_systm_2_nm")
    l3 = _string_value(row, "lclsSystm3", "lclsSystm3Cd", "lcls_systm_3")
    l3_nm = _string_value(row, "lclsSystm3Nm", "lcls_systm_3_nm")

    if parent_l2:
        l1 = l1 or parent_l1
        l1_nm = l1_nm or parent_l1_nm
        l2 = l2 or parent_l2
        l2_nm = l2_nm or parent_l2_nm
        l3 = l3 or code
        l3_nm = l3_nm or name
    elif parent_l1:
        l1 = l1 or parent_l1
        l1_nm = l1_nm or parent_l1_nm
        l2 = l2 or code
        l2_nm = l2_nm or name
    else:
        l1 = l1 or code
        l1_nm = l1_nm or name

    if not any([l1, l2, l3]):
        return None
    return l1, l1_nm, l2, l2_nm, l3, l3_nm


def _upsert_lcls_payload(
    db: Session,
    *,
    l1: str | None,
    l1_nm: str | None,
    l2: str | None,
    l2_nm: str | None,
    l3: str | None,
    l3_nm: str | None,
    raw: dict[str, Any],
) -> int:
    if not any([l1, l2, l3]):
        return 0
    row_id = f"lcls:{l1 or '*'}:{l2 or '*'}:{l3 or '*'}"
    full_name = " > ".join(part for part in [l1_nm, l2_nm, l3_nm] if part)
    payload = {
        "id": row_id,
        "lcls_systm_1": l1,
        "lcls_systm_1_nm": l1_nm,
        "lcls_systm_2": l2,
        "lcls_systm_2_nm": l2_nm,
        "lcls_systm_3": l3,
        "lcls_systm_3_nm": l3_nm,
        "content_type_id": _content_type_id_for_lcls(l1),
        "content_type_name": _content_type_name_for_lcls(l1),
        "full_name": full_name or row_id,
        "aliases": [value for value in [l1_nm, l2_nm, l3_nm] if value],
        "raw": raw,
        "synced_at": models.utcnow(),
    }
    existing = db.get(models.TourApiLclsCode, row_id)
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.updated_at = models.utcnow()
    else:
        db.add(models.TourApiLclsCode(**payload))
    return 1


def _ldong_aliases(*, regn_nm: str, signgu_nm: str | None) -> list[str]:
    aliases: list[str] = []
    if signgu_nm:
        short_signgu = normalize_geo_name(signgu_nm)
        if len(short_signgu) >= 2 and short_signgu != signgu_nm:
            aliases.append(short_signgu)
    else:
        for alias, canonical in PROVINCE_ALIASES.items():
            if canonical == regn_nm:
                aliases.append(alias)
        short_regn = normalize_geo_name(regn_nm)
        if len(short_regn) >= 2 and short_regn != regn_nm:
            aliases.append(short_regn)
    return list(dict.fromkeys(aliases))


def _content_type_id_for_lcls(lcls_systm_1: str | None) -> str | None:
    prefix = str(lcls_systm_1 or "")[:2]
    return {
        "AC": "32",
        "EV": "15",
        "LS": "28",
        "FD": "39",
        "SH": "38",
    }.get(prefix)


def _content_type_name_for_lcls(lcls_systm_1: str | None) -> str | None:
    content_type_id = _content_type_id_for_lcls(lcls_systm_1)
    return {
        "15": "event",
        "28": "leisure",
        "32": "accommodation",
        "38": "shopping",
        "39": "restaurant",
    }.get(str(content_type_id or ""))


def _string_value(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


if __name__ == "__main__":
    main()
