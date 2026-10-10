"""Contract parsing and proposal-bound validation without external services."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from doctor_service.errors import ApiError
from doctor_service.schedules import validate_schedule
from doctor_service.schemas import DoctorCreate, DoctorPatch, ScheduleInput
from doctor_service.wire import (
    decode_cursor,
    encode_cursor,
    filter_digest,
    idempotency_key,
    parse_id,
    parse_if_match,
)


def _time(days: int = 3, *, minute: int = 0) -> str:
    value = (
        (datetime.now(timezone.utc) + timedelta(days=days)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        + timedelta(minutes=minute)
    )
    return value.isoformat().replace("+00:00", "Z")


def _schedule(intervals, **overrides):
    value = {
        "timezone": "Asia/Kolkata",
        "slot_minutes": 15,
        "intervals": intervals,
        "expected_revision": 0,
        **overrides,
    }
    return ScheduleInput.model_validate(value)


def test_id_and_precondition_wire_formats_are_strict():
    assert parse_id("9223372036854775807") == "9223372036854775807"
    for value in ("0", "01", "9223372036854775808", 123):
        with pytest.raises(ApiError):
            parse_id(value)
    assert parse_if_match('"123"') == 123
    for value in (None, "123", 'W/"1"', '"0"', '"1", "2"'):
        with pytest.raises(ApiError):
            parse_if_match(value)
    assert idempotency_key("request-key-0001") == "request-key-0001"
    for value in (None, "short", "contains a space", "line\nbreak"):
        with pytest.raises(ApiError):
            idempotency_key(value)


def test_schedule_accepts_bounded_ordered_utc_working_intervals():
    start = _time()
    next_start = _time(minute=30)
    value = _schedule(
        [
            {"starts_at": start, "ends_at": _time(minute=30)},
            {"starts_at": next_start, "ends_at": _time(minute=60)},
        ]
    )
    validate_schedule(value)


def test_schedule_allows_empty_closure_and_rejects_overlap_or_bad_bounds():
    validate_schedule(_schedule([]))
    first_start = _time()
    with pytest.raises(ApiError):
        validate_schedule(
            _schedule(
                [
                    {"starts_at": first_start, "ends_at": _time(minute=30)},
                    {"starts_at": _time(minute=15), "ends_at": _time(minute=45)},
                ]
            )
        )
    with pytest.raises(ApiError):
        validate_schedule(
            _schedule([{"starts_at": first_start, "ends_at": _time(minute=20)}])
        )
    with pytest.raises(ApiError):
        validate_schedule(_schedule([], timezone="Not/A_Zone"))


def test_schedule_rejects_non_utc_or_extra_wire_fields():
    with pytest.raises(ValidationError):
        _schedule(
            [
                {
                    "starts_at": "2030-01-01T10:00:00+05:30",
                    "ends_at": "2030-01-01T10:15:00+05:30",
                }
            ]
        )
    with pytest.raises(ValidationError):
        DoctorCreate.model_validate(
            {
                "staff_user_id": "12",
                "display_name": "Doctor",
                "specialty_ids": ["1"],
                "doctor_id": "44",
            }
        )
    with pytest.raises(ValidationError):
        DoctorPatch.model_validate({})
    with pytest.raises(ValidationError):
        DoctorPatch.model_validate({"display_name": None})


def test_cursor_is_opaque_and_bound_to_normalized_filters():
    created_at = datetime(2026, 10, 11, tzinfo=timezone.utc)
    digest = filter_digest({"active": True, "q": "doctor"})
    value = encode_cursor(created_at, "55", digest)
    assert decode_cursor(value, digest) == (created_at, "55")
    with pytest.raises(ApiError):
        decode_cursor(value, filter_digest({"active": False, "q": "doctor"}))
    with pytest.raises(ApiError):
        decode_cursor("not a cursor", digest)
