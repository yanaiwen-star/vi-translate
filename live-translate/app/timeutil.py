"""China Standard Time (Asia/Shanghai, UTC+8) helpers.

The database stores timestamps in UTC (SQLAlchemy column defaults use
``datetime.utcnow``). For display and for day/month bucket keys we must use
China time so that:

  * order / usage times shown to the user match Beijing wall-clock, and
  * per-day usage buckets (anti-abuse safety caps, camera frame caps) roll over
    at China-local midnight rather than UTC midnight (08:00 Beijing).

Note: the free translation allowance is a one-off lifetime grant
(``FREE_TOTAL_MINUTES``) and never resets — no daily quota exists anymore.

All "current time" access in business logic should go through ``now_cst()``,
and any UTC ``datetime`` loaded from the DB should be converted with
``to_cst()`` before formatting for the user.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")


def now_cst() -> datetime:
    """Current time in China Standard Time (offset-aware)."""
    return datetime.now(CST)


def to_cst(dt: datetime | None) -> datetime | None:
    """Convert a (naive or aware) UTC datetime to China Standard Time.

    SQLAlchemy ``DateTime`` columns are stored naive in UTC, so we assume the
    input is UTC when it has no tzinfo. Aware datetimes are converted directly.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CST)


def cst_key(fmt: str) -> str:
    """Format the current China-time as a bucket key, e.g. ``%Y-%m-%d``."""
    return now_cst().strftime(fmt)
