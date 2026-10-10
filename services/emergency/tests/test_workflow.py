"""PostgreSQL-backed emergency workflow, authorization and concurrency tests."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from .conftest import auth_headers


def _synthetic_id() -> str:
    return str(1_000_000_000 + (uuid4().int % 8_000_000_000))


def _key(prefix: str) -> str:
    return prefix + "-" + uuid4().hex


def _submit(client, private_key, patient_id: str, *, description="Synthetic request", key=None):
    user_id = _synthetic_id()
    headers = auth_headers(private_key, user_id, ["patient"], patient_id)
    headers["Idempotency-Key"] = key or _key("emergency-submit")
    body = {
        "patient_id": patient_id,
        "description": description,
        "reported_urgency": "urgent",
        "synthetic_contact": "+91-0000000000",
    }
    response = client.post("/api/v1/emergencies", headers=headers, json=body)
    return response, headers, body


def _staff_headers(private_key, user_id: str | None = None):
    return auth_headers(private_key, user_id or _synthetic_id(), ["emergency_staff"])


def test_submit_tracking_history_and_persistence(workflow_client, emergency_test_url):
    client, private_key, patient_stub = workflow_client
    patient_id = _synthetic_id()
    created, headers, request_body = _submit(
        client,
        private_key,
        patient_id,
        description="Synthetic persistence marker",
        key=_key("emergency-submit-persist"),
    )

    assert created.status_code == 201
    initial = created.json()
    assert set(initial) == {
        "id",
        "state",
        "reported_urgency",
        "assigned_priority",
        "created_at",
        "updated_at",
        "version",
    }
    assert initial["state"] == "submitted"
    assert initial["reported_urgency"] == "urgent"
    assert initial["assigned_priority"] is None
    assert created.headers["etag"] == '"1"'
    assert patient_stub.calls[-1] == ("patient-status", patient_id)

    replay = client.post(
        "/api/v1/emergencies", headers=headers, json=request_body
    )
    assert replay.status_code == 201
    assert replay.json() == initial
    assert replay.headers["etag"] == created.headers["etag"]

    changed_payload = {**request_body, "description": "Different synthetic request"}
    key_reuse = client.post(
        "/api/v1/emergencies", headers=headers, json=changed_payload
    )
    assert key_reuse.status_code == 409
    assert key_reuse.json()["error"]["code"] == "idempotency_key_reused"

    tracked = client.get(
        f"/api/v1/emergencies/{initial['id']}",
        headers={"Authorization": headers["Authorization"]},
    )
    assert tracked.status_code == 200
    assert tracked.headers["etag"] == '"1"'
    assert "description" not in tracked.json()
    assert "synthetic_contact" not in tracked.json()

    history = client.get(
        f"/api/v1/emergencies/{initial['id']}/history",
        headers={"Authorization": headers["Authorization"]},
    )
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1
    assert "reason" not in history.json()["items"][0]
    assert "actor_user_id" not in history.json()["items"][0]

    engine = create_engine(emergency_test_url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT patient_id, description, reported_urgency, state, version "
                    "FROM emergency_requests WHERE id = :request_id"
                ),
                {"request_id": int(initial["id"])},
            ).mappings().one()
            history_count = connection.scalar(
                text(
                    "SELECT count(*) FROM emergency_status_history "
                    "WHERE request_id = :request_id"
                ),
                {"request_id": int(initial["id"])},
            )
            event = connection.execute(
                text(
                    "SELECT envelope::text FROM outbox_events "
                    "WHERE aggregate_id = :request_id ORDER BY aggregate_version LIMIT 1"
                ),
                {"request_id": int(initial["id"])},
            ).scalar_one()
            audit_rows = connection.execute(
                text(
                    "SELECT prev_hash, entry_hash, canonical_metadata::text "
                    "FROM audit_entries WHERE canonical_metadata->>'resource_id' = :id "
                    "ORDER BY sequence"
                ),
                {"id": initial["id"]},
            ).all()
        assert str(row["patient_id"]) == patient_id
        assert row["description"] == request_body["description"]
        assert (row["reported_urgency"], row["state"], row["version"]) == (
            "urgent",
            "submitted",
            1,
        )
        assert history_count == 1
        assert initial["id"] in event
        assert request_body["description"] not in event
        assert request_body["synthetic_contact"] not in event
        assert audit_rows
        for previous_hash, entry_hash, canonical_metadata in audit_rows:
            expected = hashlib.sha256(
                (previous_hash + canonical_metadata).encode("utf-8")
            ).hexdigest()
            assert entry_hash == expected
            assert request_body["description"] not in canonical_metadata
            assert request_body["synthetic_contact"] not in canonical_metadata
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE audit_entries SET entry_hash = repeat('0', 64) "
                        "WHERE canonical_metadata->>'resource_id' = :id"
                    ),
                    {"id": initial["id"]},
                )
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE emergency_status_history SET reason = 'rewritten' "
                        "WHERE request_id = :request_id"
                    ),
                    {"request_id": int(initial["id"])},
                )
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM emergency_requests WHERE id = :request_id"),
                    {"request_id": int(initial["id"])},
                )
    finally:
        engine.dispose()


def test_patient_cannot_choose_priority_or_another_patient_id(workflow_client):
    client, private_key, patient_stub = workflow_client
    patient_id = _synthetic_id()
    created, headers, body = _submit(client, private_key, patient_id)
    assert created.status_code == 201
    request_id = created.json()["id"]

    unauthorized = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers={
            "Authorization": headers["Authorization"],
            "If-Match": created.headers["etag"],
        },
        json={"assigned_priority": 1, "reason": "Patient cannot assign priority"},
    )
    assert unauthorized.status_code == 403

    statuses_before = sum(
        1 for method, _ in patient_stub.calls if method == "patient-status"
    )
    mismatch = client.post(
        "/api/v1/emergencies",
        headers={
            "Authorization": headers["Authorization"],
            "Idempotency-Key": _key("emergency-submit-mismatch"),
        },
        json={**body, "patient_id": _synthetic_id()},
    )
    assert mismatch.status_code == 403
    assert sum(1 for method, _ in patient_stub.calls if method == "patient-status") == statuses_before

    invalid_priority = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers=_staff_headers(private_key) | {"If-Match": created.headers["etag"]},
        json={"assigned_priority": 6, "reason": "Outside allowed range"},
    )
    assert invalid_priority.status_code == 422


def test_patient_status_and_current_authority_fail_closed(workflow_client):
    client, private_key, patient_stub = workflow_client
    patient_id = _synthetic_id()
    headers = auth_headers(private_key, _synthetic_id(), ["patient"], patient_id)
    headers["Idempotency-Key"] = _key("emergency-authority-denied")
    body = {
        "patient_id": patient_id,
        "description": "Synthetic authority check",
        "reported_urgency": "unspecified",
    }

    patient_stub.allow_authority = False
    denied = client.post("/api/v1/emergencies", headers=headers, json=body)
    assert denied.status_code == 403
    assert not any(method == "patient-status" for method, _ in patient_stub.calls)

    patient_stub.allow_authority = True
    patient_stub.patient_active = False
    invalid_reference = client.post(
        "/api/v1/emergencies",
        headers={**headers, "Idempotency-Key": _key("emergency-inactive-patient")},
        json=body,
    )
    assert invalid_reference.status_code == 422
    assert invalid_reference.json()["error"]["code"] == "invalid_reference"


def test_authorized_priority_claim_release_and_preconditions(workflow_client):
    client, private_key, patient_stub = workflow_client
    patient_id = _synthetic_id()
    created, patient_headers, _ = _submit(client, private_key, patient_id)
    request_id = created.json()["id"]
    staff = _staff_headers(private_key)

    patient_stub.allow_authority = False
    denied_current_staff = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers=staff | {"If-Match": created.headers["etag"]},
        json={"assigned_priority": 2, "reason": "Current staff authority is required"},
    )
    assert denied_current_staff.status_code == 403
    patient_stub.allow_authority = True

    missing = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers=staff,
        json={"assigned_priority": 2, "reason": "Staff reviewed synthetic request"},
    )
    assert missing.status_code == 428

    malformed = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers=staff | {"If-Match": "*"},
        json={"assigned_priority": 2, "reason": "Staff reviewed synthetic request"},
    )
    assert malformed.status_code == 400

    prioritized = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers=staff | {"If-Match": created.headers["etag"]},
        json={"assigned_priority": 2, "reason": "Staff reviewed synthetic request"},
    )
    assert prioritized.status_code == 200
    assert prioritized.json()["state"] == "triaged"
    assert prioritized.json()["assigned_priority"] == 2
    assert prioritized.headers["etag"] == '"2"'

    missing_claim_key = _key("emergency-claim-missing-etag")
    missing_claim_headers = staff | {"Idempotency-Key": missing_claim_key}
    missing_claim = client.post(
        f"/api/v1/emergencies/{request_id}/claim",
        headers=missing_claim_headers,
        json={},
    )
    assert missing_claim.status_code == 428
    missing_claim_replay = client.post(
        f"/api/v1/emergencies/{request_id}/claim",
        headers=missing_claim_headers,
        json={},
    )
    assert missing_claim_replay.status_code == 428
    assert missing_claim_replay.json() == missing_claim.json()

    stale = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers=staff | {"If-Match": created.headers["etag"]},
        json={"assigned_priority": 3, "reason": "Stale update"},
    )
    assert stale.status_code == 412

    claimed = client.post(
        f"/api/v1/emergencies/{request_id}/claim",
        headers=staff
        | {
            "If-Match": prioritized.headers["etag"],
            "Idempotency-Key": _key("emergency-claim"),
        },
        json={},
    )
    assert claimed.status_code == 200
    assert claimed.json()["claimed_by_user_id"] == jwt.decode(
        staff["Authorization"].split()[1], options={"verify_signature": False}
    )["sub"]
    assert claimed.json()["state"] == "claimed"
    assert claimed.json()["claim_expires_at"] is not None

    released = client.post(
        f"/api/v1/emergencies/{request_id}/release",
        headers=staff
        | {
            "If-Match": claimed.headers["etag"],
            "Idempotency-Key": _key("emergency-release"),
        },
        json={"reason": "Work returned to triage"},
    )
    assert released.status_code == 200
    assert released.json()["state"] == "triaged"
    assert released.json()["claimed_by_user_id"] is None
    assert released.json()["claim_expires_at"] is None

    cancelled = client.post(
        f"/api/v1/emergencies/{request_id}/transitions",
        headers={
            "Authorization": patient_headers["Authorization"],
            "If-Match": released.headers["etag"],
            "Idempotency-Key": _key("emergency-patient-cancel"),
        },
        json={"state": "cancelled", "reason": "Owner cancelled synthetic request"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"


def test_valid_resolution_invalid_edges_and_claim_ownership(workflow_client):
    client, private_key, _ = workflow_client
    patient_id = _synthetic_id()
    created, _, _ = _submit(client, private_key, patient_id)
    request_id = created.json()["id"]
    staff = _staff_headers(private_key)

    invalid = client.post(
        f"/api/v1/emergencies/{request_id}/transitions",
        headers=staff
        | {"If-Match": created.headers["etag"], "Idempotency-Key": _key("invalid-edge")},
        json={"state": "processing", "reason": "Cannot skip triage and claim"},
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "invalid_transition"

    prioritized = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers=staff | {"If-Match": created.headers["etag"]},
        json={"assigned_priority": 1, "reason": "Authorized staff priority"},
    )
    claimed = client.post(
        f"/api/v1/emergencies/{request_id}/claim",
        headers=staff
        | {
            "If-Match": prioritized.headers["etag"],
            "Idempotency-Key": _key("emergency-claim-resolution"),
        },
        json={},
    )
    other_staff = _staff_headers(private_key)
    wrong_owner = client.post(
        f"/api/v1/emergencies/{request_id}/transitions",
        headers=other_staff
        | {
            "If-Match": claimed.headers["etag"],
            "Idempotency-Key": _key("wrong-owner-processing"),
        },
        json={"state": "processing", "reason": "Another staff member cannot start"},
    )
    assert wrong_owner.status_code == 404

    processing_headers = staff | {
        "If-Match": claimed.headers["etag"],
        "Idempotency-Key": _key("emergency-processing"),
    }
    processing_body = {"state": "processing", "reason": "Assigned staff started work"}
    processing = client.post(
        f"/api/v1/emergencies/{request_id}/transitions",
        headers=processing_headers,
        json=processing_body,
    )
    assert processing.status_code == 200
    assert processing.json()["state"] == "processing"
    assert processing.json()["claim_expires_at"] is None
    processing_replay = client.post(
        f"/api/v1/emergencies/{request_id}/transitions",
        headers=processing_headers,
        json=processing_body,
    )
    assert processing_replay.status_code == 200
    assert processing_replay.json() == processing.json()
    assert processing_replay.headers["etag"] == processing.headers["etag"]

    resolved = client.post(
        f"/api/v1/emergencies/{request_id}/transitions",
        headers=staff
        | {
            "If-Match": processing.headers["etag"],
            "Idempotency-Key": _key("emergency-resolve"),
        },
        json={"state": "resolved", "reason": "Synthetic request resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["state"] == "resolved"
    assert resolved.json()["claimed_by_user_id"] is None

    terminal = client.post(
        f"/api/v1/emergencies/{request_id}/transitions",
        headers=staff
        | {
            "If-Match": resolved.headers["etag"],
            "Idempotency-Key": _key("emergency-terminal"),
        },
        json={"state": "cancelled", "reason": "Terminal requests cannot change"},
    )
    assert terminal.status_code == 409
    assert terminal.json()["error"]["code"] == "invalid_transition"

    history = client.get(
        f"/api/v1/emergencies/{request_id}/history", headers=staff
    )
    assert history.status_code == 200
    assert [item["new_state"] for item in history.json()["items"]] == [
        "submitted",
        "triaged",
        "claimed",
        "processing",
        "resolved",
    ]
    assert all("reason" in item and "actor_user_id" in item for item in history.json()["items"])


def test_claim_expiry_is_normalized_and_conflict_is_replayed(workflow_client, emergency_test_url):
    client, private_key, _ = workflow_client
    patient_id = _synthetic_id()
    created, _, _ = _submit(client, private_key, patient_id)
    request_id = created.json()["id"]
    staff = _staff_headers(private_key)
    prioritized = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers=staff | {"If-Match": created.headers["etag"]},
        json={"assigned_priority": 2, "reason": "Authorized priority"},
    )
    claimed = client.post(
        f"/api/v1/emergencies/{request_id}/claim",
        headers=staff
        | {
            "If-Match": prioritized.headers["etag"],
            "Idempotency-Key": _key("claim-expiry-claim"),
        },
        json={},
    )
    engine = create_engine(emergency_test_url, hide_parameters=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE emergency_requests SET claim_expires_at = "
                    "clock_timestamp() - interval '1 second' WHERE id = :request_id"
                ),
                {"request_id": int(request_id)},
            )
    finally:
        engine.dispose()

    key = _key("claim-expiry-transition")
    request_headers = staff | {
        "If-Match": claimed.headers["etag"],
        "Idempotency-Key": key,
    }
    expired = client.post(
        f"/api/v1/emergencies/{request_id}/transitions",
        headers=request_headers,
        json={"state": "processing", "reason": "Expired claim cannot process"},
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "claim_expired"
    replay = client.post(
        f"/api/v1/emergencies/{request_id}/transitions",
        headers=request_headers,
        json={"state": "processing", "reason": "Expired claim cannot process"},
    )
    assert replay.status_code == 409
    assert replay.json() == expired.json()

    refreshed = client.get(
        f"/api/v1/emergencies/{request_id}", headers=staff
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["state"] == "triaged"
    assert refreshed.json()["claimed_by_user_id"] is None


def test_listing_filters_paginates_and_binds_cursors(workflow_client):
    client, private_key, _ = workflow_client
    patient_id = _synthetic_id()
    created = [
        _submit(client, private_key, patient_id, description=f"Synthetic page {index}")[0]
        for index in range(3)
    ]
    assert all(response.status_code == 201 for response in created)
    headers = auth_headers(private_key, _synthetic_id(), ["patient"], patient_id)

    first = client.get(
        f"/api/v1/emergencies?state=submitted&limit=2&patient_id={patient_id}",
        headers=headers,
    )
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    cursor = first.json()["next_cursor"]
    assert cursor
    second = client.get(
        f"/api/v1/emergencies?state=submitted&limit=2&patient_id={patient_id}&cursor={cursor}",
        headers=headers,
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["next_cursor"] is None

    changed_filter = client.get(
        f"/api/v1/emergencies?state=triaged&limit=2&patient_id={patient_id}&cursor={cursor}",
        headers=headers,
    )
    assert changed_filter.status_code == 400
    unknown_filter = client.get(
        f"/api/v1/emergencies?patient_id={patient_id}&unknown=value", headers=headers
    )
    assert unknown_filter.status_code == 422


def test_concurrent_claims_serialize_on_the_request_row(workflow_client, emergency_test_url):
    client, private_key, _ = workflow_client
    patient_id = _synthetic_id()
    created, _, _ = _submit(client, private_key, patient_id)
    request_id = created.json()["id"]
    staff = [_staff_headers(private_key), _staff_headers(private_key)]
    prioritized = client.patch(
        f"/api/v1/emergencies/{request_id}/priority",
        headers=staff[0] | {"If-Match": created.headers["etag"]},
        json={"assigned_priority": 2, "reason": "Authorized priority"},
    )
    assert prioritized.status_code == 200

    def claim(headers):
        return client.post(
            f"/api/v1/emergencies/{request_id}/claim",
            headers=headers
            | {
                "If-Match": prioritized.headers["etag"],
                "Idempotency-Key": _key("concurrent-claim"),
            },
            json={},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, staff))
    assert sorted(result.status_code for result in results) == [200, 412]
    claimed = next(result for result in results if result.status_code == 200)

    already_claimed = client.post(
        f"/api/v1/emergencies/{request_id}/claim",
        headers=staff[0]
        | {
            "If-Match": claimed.headers["etag"],
            "Idempotency-Key": _key("fresh-already-claimed"),
        },
        json={},
    )
    assert already_claimed.status_code == 409
    conflict = already_claimed
    assert conflict.json()["error"]["code"] == "already_claimed"

    engine = create_engine(emergency_test_url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            state, owner, history_count = connection.execute(
                text(
                    "SELECT r.state, r.claimed_by_user_id, "
                    "(SELECT count(*) FROM emergency_status_history h "
                    "WHERE h.request_id = r.id AND h.new_state = 'claimed') "
                    "FROM emergency_requests r WHERE r.id = :request_id"
                ),
                {"request_id": int(request_id)},
            ).one()
        assert state == "claimed"
        assert owner in {
            int(jwt.decode(h["Authorization"].split()[1], options={"verify_signature": False})["sub"])
            for h in staff
        }
        assert history_count == 1
    finally:
        engine.dispose()
