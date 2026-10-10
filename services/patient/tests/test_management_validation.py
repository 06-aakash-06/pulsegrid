"""Pure contract checks for Patient management request and cursor validation."""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from patient_service.errors import APIError
from patient_service.bootstrap_admin import normalize_synthetic_email
from patient_service.management import (
    AccountStatePatch,
    ProfilePatch,
    UserRolesPatch,
    _check_last_admin,
    _decode_cursor,
    _encode_cursor,
    _etag_version,
    _filter_hash,
    _limit,
    _like_prefix,
    _path_id,
    _prefix,
    _query_values,
)


def test_profile_patch_validates_only_allowed_fields_and_nonempty_patch():
    patch = ProfilePatch(display_name="  Synthetic Patient  ")

    assert patch.display_name == "Synthetic Patient"
    with pytest.raises(ValidationError):
        ProfilePatch()
    with pytest.raises(ValidationError):
        ProfilePatch(display_name="   ")
    with pytest.raises(ValidationError):
        ProfilePatch(display_name=None)
    with pytest.raises(ValidationError):
        ProfilePatch(roles=["hospital_admin"])
    with pytest.raises(ValidationError):
        ProfilePatch(synthetic_contact=17)
    with pytest.raises(ValidationError):
        ProfilePatch(date_of_birth=date.today() + timedelta(days=1))
    with pytest.raises(ValidationError):
        ProfilePatch(date_of_birth="2001-02-03T00:00:00Z")
    with pytest.raises(ValidationError):
        ProfilePatch(date_of_birth="2001-2-3")


def test_profile_patch_allows_nullable_stored_fields_to_be_cleared():
    assert ProfilePatch(date_of_birth=None).date_of_birth is None
    assert ProfilePatch(synthetic_contact=None).synthetic_contact is None


def test_admin_mutation_bodies_validate_roles_and_reason():
    assert UserRolesPatch(roles=["doctor", "patient"]).roles == ["doctor", "patient"]
    with pytest.raises(ValidationError):
        UserRolesPatch(roles=[])
    with pytest.raises(ValidationError):
        UserRolesPatch(roles=["doctor", "doctor"])
    with pytest.raises(ValidationError):
        UserRolesPatch(roles=["unknown"])
    assert AccountStatePatch(state="disabled", reason="  synthetic review  ").reason == (
        "synthetic review"
    )
    assert AccountStatePatch(state="disabled", reason="x" + " " * 500).reason == "x"
    with pytest.raises(ValidationError):
        AccountStatePatch(state="disabled", reason="  ")
    with pytest.raises(ValidationError):
        AccountStatePatch(state="disabled", reason="x", roles=["patient"])


def test_admin_bootstrap_accepts_only_normalized_synthetic_accounts():
    assert normalize_synthetic_email(" First.Admin@Example.Test ") == (
        "first.admin@example.test"
    )
    with pytest.raises(ValueError):
        normalize_synthetic_email("person@example.com")


def test_etag_and_id_validation_follow_the_wire_format():
    assert _etag_version('"12"') == 12
    assert _path_id("9223372036854775807") == 9223372036854775807
    for value in (None, "12", '"01"', 'W/"12"', '"9007199254740992"'):
        with pytest.raises(APIError):
            _etag_version(value)
    for value in ("0", "01", "9223372036854775808", "abc"):
        with pytest.raises(APIError):
            _path_id(value)


def test_list_query_validation_is_bounded_and_rejects_unknown_or_duplicate_keys():
    assert _prefix("  Li  ") == "li"
    assert _prefix(None) is None
    assert _limit(None) == 20
    assert _limit("100") == 100
    assert _like_prefix(r"A%_\B") == r"A\%\_\\B%"
    with pytest.raises(HTTPException) as failure:
        _prefix(" x ")
    assert failure.value.status_code == 422
    with pytest.raises(HTTPException):
        _limit("101")

    unknown = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"offset=10",
            "headers": [],
        }
    )
    with pytest.raises(HTTPException) as failure:
        _query_values(unknown, {"q", "cursor", "limit"})
    assert failure.value.status_code == 422

    duplicate = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"limit=10&limit=20",
            "headers": [],
        }
    )
    with pytest.raises(HTTPException) as failure:
        _query_values(duplicate, {"q", "cursor", "limit"})
    assert failure.value.status_code == 422


def test_cursor_is_opaque_and_bound_to_normalized_filter_scope():
    scope = {"route": "patients", "user_id": "123", "role": "receptionist"}
    filter_hash = _filter_hash(scope, {"q": "synthetic"})
    created_at = datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc)
    cursor = _encode_cursor(created_at, 456, filter_hash)

    assert _decode_cursor(cursor, filter_hash) == (created_at, 456)
    with pytest.raises(APIError) as failure:
        _decode_cursor(cursor, _filter_hash(scope, {"q": "other"}))
    assert failure.value.status_code == 400
    with pytest.raises(APIError):
        _decode_cursor("not-a-cursor", filter_hash)


def test_admin_cannot_disable_self_or_remove_own_admin_role():
    with pytest.raises(APIError) as failure:
        _check_last_admin(
            "123",
            123,
            "active",
            ["hospital_admin", "patient"],
            next_roles=["patient"],
        )
    assert failure.value.status_code == 409
    assert failure.value.error_code == "last_admin"

    with pytest.raises(APIError):
        _check_last_admin(
            "123",
            123,
            "active",
            ["patient"],
            next_state="disabled",
        )
