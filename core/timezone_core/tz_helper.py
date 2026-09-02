"""Timezone helper for SQLite datetime modifiers.

Converts a timezone name (e.g. ``"Asia/Tokyo"``) into a SQLite datetime
modifier string (e.g. ``'+09:00'``).  When no timezone is configured the
modifier is ``'localtime'`` for backward compatibility.

Usage in SQL::

    datetime(f.mtime, 'unixepoch', tz_sqlite_modifier())
"""

import datetime as _dt
import logging
from zoneinfo import ZoneInfo

from core.configuration.api import load_config_json

logger = logging.getLogger(__name__)

COMMON_TIMEZONES = [
    "UTC",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Seoul",
    "Asia/Kolkata",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Moscow",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Sao_Paulo",
    "Australia/Sydney",
    "Pacific/Auckland",
]


def detect_system_timezone() -> str:
    """Return IANA timezone string from OS via tzlocal (bundled with apscheduler)."""
    try:
        from tzlocal import get_localzone_name  # noqa: PLC0415
        return get_localzone_name() or "UTC"
    except Exception:
        return "UTC"


def get_configured_tz() -> str | None:
    """Return the configured timezone name, or ``None`` for system default."""
    cfg = load_config_json(None)
    if isinstance(cfg, dict):
        tz = cfg.get("timezone")
        if tz and isinstance(tz, str) and tz.strip():
            return tz.strip()
    return None


def tz_sqlite_modifier(tz_name: str | None = None) -> str:
    """Convert a timezone name into a SQLite modifier string.

    - ``None`` / empty → ``'localtime'`` (backward compatible)
    - ``"UTC"`` → ``'+00:00'``
    - ``"Asia/Tokyo"`` → ``'+09:00'``

    The offset is calculated for the current instant, which means it
    accounts for DST transitions for the current moment.
    """
    if tz_name is None:
        tz_name = get_configured_tz()

    if not tz_name:
        return "localtime"

    if tz_name == "UTC":
        return "+00:00"

    try:
        zi = ZoneInfo(tz_name)
        now = _dt.datetime.now(_dt.UTC)
        offset = now.astimezone(zi).utcoffset()
        if offset is None:
            return "localtime"
        total_seconds = int(offset.total_seconds())
        sign = "+" if total_seconds >= 0 else "-"
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        return f"{sign}{hours:02d}:{minutes:02d}"
    except (KeyError, Exception):
        return "localtime"


def configured_now() -> _dt.datetime:
    """Return current time in the configured timezone, or local time."""
    tz_name = get_configured_tz()
    if not tz_name:
        return _dt.datetime.now().astimezone()
    try:
        return _dt.datetime.now(ZoneInfo(tz_name))
    except (KeyError, Exception):
        return _dt.datetime.now().astimezone()


def local_date_range_unix(day: _dt.date) -> tuple[int, int]:
    """Return inclusive Unix epoch bounds for a configured-timezone date."""
    tz_name = get_configured_tz()
    if tz_name:
        try:
            tz = ZoneInfo(tz_name)
            start = _dt.datetime.combine(day, _dt.time.min, tzinfo=tz)
            end = _dt.datetime.combine(day, _dt.time.max.replace(microsecond=0), tzinfo=tz)
            return int(start.timestamp()), int(end.timestamp())
        except (KeyError, Exception):
            logger.warning("step failed", exc_info=True)
    start = _dt.datetime.combine(day, _dt.time.min).astimezone()
    end = _dt.datetime.combine(day, _dt.time.max.replace(microsecond=0)).astimezone()
    return int(start.timestamp()), int(end.timestamp())


def month_range_unix(month_str: str) -> tuple[int, int]:
    """Return inclusive Unix epoch bounds for YYYY-MM in configured timezone."""
    import calendar

    parts = month_str.split("-")
    year, mon = int(parts[0]), int(parts[1])
    last_day = calendar.monthrange(year, mon)[1]
    return (
        local_date_range_unix(_dt.date(year, mon, 1))[0],
        local_date_range_unix(_dt.date(year, mon, last_day))[1],
    )
