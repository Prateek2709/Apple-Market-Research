"""Time helpers: UTC fetch timestamps, IST dates, Sunday-Saturday weeks (plan, "Standardising")."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_ist_date(ts: datetime) -> date:
    """IST calendar date of an aware datetime."""
    if ts.tzinfo is None:
        raise ValueError("naive datetime; timestamps must be timezone-aware")
    return ts.astimezone(IST).date()


def iso_utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_stamp(ts: datetime) -> str:
    """Windows-safe timestamp for file names (no colons)."""
    return ts.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def week_start(d: date) -> date:
    """Sunday of the Sunday-Saturday week containing d: d - ((weekday + 1) mod 7) days, Monday = 0."""
    return d - timedelta(days=(d.weekday() + 1) % 7)
