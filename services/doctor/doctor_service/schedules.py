"""Validation and slot-count bounds for immutable schedule proposals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import ApiError
from .schemas import ScheduleInput


def validate_schedule(value: ScheduleInput, *, now: datetime | None = None) -> None:
    try:
        ZoneInfo(value.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ApiError(422, "validation_error") from None

    current = now or datetime.now(timezone.utc)
    current = current.astimezone(timezone.utc)
    horizon = current + timedelta(days=366)
    prior_end: datetime | None = None
    total_slots = 0
    for interval in value.intervals:
        starts_at = interval.starts_at.astimezone(timezone.utc)
        ends_at = interval.ends_at.astimezone(timezone.utc)
        if starts_at <= current or ends_at > horizon:
            raise ApiError(422, "validation_error")
        if prior_end is not None and starts_at < prior_end:
            raise ApiError(422, "validation_error")
        duration = ends_at - starts_at
        slot_seconds = value.slot_minutes * 60
        duration_seconds = duration.total_seconds()
        if duration_seconds % slot_seconds:
            raise ApiError(422, "validation_error")
        total_slots += int(duration_seconds // slot_seconds)
        prior_end = ends_at
    if value.intervals:
        span = value.intervals[-1].ends_at - value.intervals[0].starts_at
        if span > timedelta(days=31):
            raise ApiError(422, "validation_error")
    if total_slots > 1000:
        raise ApiError(422, "validation_error")
