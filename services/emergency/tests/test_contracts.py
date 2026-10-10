"""Pure contract validation checks that do not require PostgreSQL."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from emergency_service.commands import _decode_cursor, _encode_cursor, _check_if_match
from emergency_service.exceptions import DomainHTTPException
from emergency_service.schemas import (
    ClaimCommand,
    EmergencyRequestCreate,
    PriorityUpdate,
    TransitionCommand,
)


def test_request_models_reject_extra_fields_and_noncanonical_ids():
    with pytest.raises(ValidationError):
        EmergencyRequestCreate.model_validate(
            {
                "patient_id": "12",
                "description": "Synthetic event",
                "reported_urgency": "urgent",
                "assigned_priority": 1,
            }
        )
    with pytest.raises(ValidationError):
        EmergencyRequestCreate.model_validate(
            {
                "patient_id": "9223372036854775808",
                "description": "Synthetic event",
                "reported_urgency": "urgent",
            }
        )
    with pytest.raises(ValidationError):
        EmergencyRequestCreate.model_validate(
            {
                "patient_id": 12,
                "description": "Synthetic event",
                "reported_urgency": "urgent",
            }
        )


def test_priority_and_transition_inputs_are_strict():
    with pytest.raises(ValidationError):
        PriorityUpdate.model_validate({"assigned_priority": True, "reason": "Not valid"})
    with pytest.raises(ValidationError):
        PriorityUpdate.model_validate({"assigned_priority": 6, "reason": "Too low"})
    with pytest.raises(ValidationError):
        TransitionCommand.model_validate({"state": "submitted", "reason": "No edge"})
    with pytest.raises(ValidationError):
        ClaimCommand.model_validate({"claimed_by_user_id": "123"})


def test_cursor_is_bound_to_filters_and_rejects_malformed_values():
    timestamp = datetime(2026, 10, 11, 10, 30, tzinfo=timezone.utc)
    encoded = _encode_cursor(timestamp, 123, "a" * 64)
    decoded_timestamp, decoded_id = _decode_cursor(encoded, "a" * 64)
    assert decoded_timestamp == timestamp
    assert decoded_id == 123

    with pytest.raises(DomainHTTPException) as changed_filters:
        _decode_cursor(encoded, "b" * 64)
    assert changed_filters.value.status_code == 400
    with pytest.raises(DomainHTTPException):
        _decode_cursor("not a cursor", "a" * 64)


@pytest.mark.parametrize(
    "value,status",
    [(None, 428), ("*", 400), ('"2"', 412)],
)
def test_if_match_requires_an_exact_current_version(value, status):
    with pytest.raises(DomainHTTPException) as error:
        _check_if_match(value, 3)
    assert error.value.status_code == status


def test_if_match_accepts_the_exact_version():
    _check_if_match('"3"', 3)
