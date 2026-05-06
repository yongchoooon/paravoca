from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(APP_TIMEZONE)


def now_kst_naive() -> datetime:
    return now_kst().replace(tzinfo=None)
