"""Helpers for interpreting and displaying times in the caregiver's own timezone.

Everything is *stored* as UTC. The user's timezone (IANA name, sent by the
browser) is only used to interpret what they typed ("Tuesday at 10") and to
work out what "today" means for them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc


def resolve_timezone(name: str | None) -> tzinfo:
    """IANA name -> tzinfo. Missing or unrecognised names fall back to UTC."""
    if not name:
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return UTC


def tz_label(tz: tzinfo) -> str:
    return getattr(tz, "key", None) or "UTC"


def parse_due_at(value: str, tz: tzinfo) -> datetime | None:
    """Parse an ISO8601 string from the LLM into an aware UTC datetime.

    A value with no offset is the user's local wall-clock time, so it's
    interpreted in `tz`. A value that carries its own offset/"Z" is respected.
    """
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(UTC)


def to_local(dt: datetime, tz: tzinfo) -> datetime:
    """A datetime read back from SQLite is naive-but-UTC; make it local."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(tz)


def day_bounds_utc(tz: tzinfo, now_utc: datetime) -> tuple[datetime, datetime]:
    """[start, end) of the user's current local day, expressed in UTC."""
    local_now = now_utc.astimezone(tz)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)  # wall-clock arithmetic, DST-safe
    return start_local.astimezone(UTC), end_local.astimezone(UTC)
