"""Doctor HTTP workflow, security, pagination, and PostgreSQL constraint tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from secrets import randbelow

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


API = "/api/v1/doctors"
ADMIN_ID = "900001"
DOCTOR_ID = "900002"
DOCTOR_2_ID = "900003"
PATIENT_ID = "900004"


def _headers(client, user_id=ADMIN_ID, roles=None, **extra):
    roles = roles or ["hospital_admin"]
    token = client.app.state._test_tokens.user(
        user_id,
        roles,
        patient_id="500" if "patient" in roles else None,
    )
    return {"Authorization": "Bearer " + token, **extra}


def _key(value: str) -> str:
    return "test-command-key-" + value


def _create_specialty(client, slug="cardiology", name="Cardiology", *, key=None):
    return client.post(
        API + "/specialties",
        headers=_headers(client, **{"Idempotency-Key": key or _key(slug)}),
        json={"slug": slug, "name": name},
    )


def _create_doctor(
    client,
    specialty_id: str,
    *,
    staff_user_id: str = DOCTOR_ID,
    display_name: str = "Dr. Alice",
    key: str | None = None,
):
    return client.post(
        API,
        headers=_headers(
            client,
            **{"Idempotency-Key": key or _key("doctor-" + staff_user_id)},
        ),
        json={
            "staff_user_id": staff_user_id,
            "display_name": display_name,
            "specialty_ids": [specialty_id],
        },
    )


def _time_at(day_offset: int, minute_offset: int = 0) -> str:
    now = datetime.now(timezone.utc)
    start = (now + timedelta(days=day_offset)).replace(
        hour=10, minute=0, second=0, microsecond=0
    ) + timedelta(minutes=minute_offset)
    return start.isoformat().replace("+00:00", "Z")


def _schedule_body(*, expected_revision=0, intervals=None):
    if intervals is None:
        intervals = [
            {"starts_at": _time_at(4), "ends_at": _time_at(4, 30)}
        ]
    return {
        "timezone": "Asia/Kolkata",
        "slot_minutes": 15,
        "intervals": intervals,
        "expected_revision": expected_revision,
    }


def _propose(client, doctor, payload, *, key="proposal-1", etag_value=None):
    return client.post(
        f"{API}/{doctor}/schedules",
        headers=_headers(
            client,
            DOCTOR_ID,
            ["doctor"],
            **{
                "If-Match": etag_value or '"1"',
                "Idempotency-Key": _key(key),
            },
        ),
        json=payload,
    )


def test_authenticated_profile_specialty_crud_and_idempotency(doctor_client):
    client = doctor_client
    created_specialty = _create_specialty(client)
    assert created_specialty.status_code == 201
    assert created_specialty.headers["etag"] == '"1"'
    assert set(created_specialty.json()) == {"id", "slug", "name", "version"}

    replay = _create_specialty(client)
    assert replay.status_code == 201
    assert replay.json() == created_specialty.json()
    assert replay.headers["etag"] == created_specialty.headers["etag"]

    changed = _create_specialty(
        client,
        slug="neurology",
        name="Neurology",
        key=_key("cardiology"),
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "idempotency_key_reused"

    specialty_id = created_specialty.json()["id"]
    created_doctor = _create_doctor(client, specialty_id)
    assert created_doctor.status_code == 201
    doctor = created_doctor.json()
    assert set(doctor) == {"id", "display_name", "specialties", "active", "version"}
    assert doctor["specialties"] == [{"id": specialty_id, "name": "Cardiology"}]
    doctor_id = doctor["id"]

    fetched = client.get(f"{API}/{doctor_id}", headers=_headers(client, PATIENT_ID, ["patient"]))
    assert fetched.status_code == 200
    assert fetched.headers["etag"] == '"1"'
    assert fetched.json() == doctor
    self_view = client.get(
        API + "/me", headers=_headers(client, DOCTOR_ID, ["doctor"])
    )
    assert self_view.status_code == 200
    assert self_view.headers["cache-control"] == "no-store"
    assert self_view.json() == {"doctor": doctor, "staff_user_id": DOCTOR_ID}

    updated = client.patch(
        f"{API}/{doctor_id}",
        headers=_headers(
            client,
            DOCTOR_ID,
            ["doctor"],
            **{"If-Match": '"1"'},
        ),
        json={"display_name": "Dr. Alice Smith"},
    )
    assert updated.status_code == 200
    assert updated.headers["etag"] == '"2"'
    assert updated.json()["display_name"] == "Dr. Alice Smith"

    second_specialty = _create_specialty(
        client,
        slug="neurology",
        name="Neurology",
        key=_key("neurology-create"),
    ).json()
    specialties_updated = client.patch(
        f"{API}/{doctor_id}",
        headers=_headers(client, **{"If-Match": '"2"'}),
        json={"specialty_ids": [second_specialty["id"]]},
    )
    assert specialties_updated.status_code == 200
    assert specialties_updated.headers["etag"] == '"3"'
    assert specialties_updated.json()["specialties"] == [
        {"id": second_specialty["id"], "name": "Neurology"}
    ]

    forbidden_field = client.patch(
        f"{API}/{doctor_id}",
        headers=_headers(
            client,
            DOCTOR_ID,
            ["doctor"],
            **{"If-Match": '"3"'},
        ),
        json={"active": False},
    )
    assert forbidden_field.status_code == 403

    wrong_owner = client.patch(
        f"{API}/{doctor_id}",
        headers=_headers(
            client,
            DOCTOR_2_ID,
            ["doctor"],
            **{"If-Match": '"3"'},
        ),
        json={"display_name": "Other"},
    )
    assert wrong_owner.status_code == 404

    duplicate_mapping = _create_doctor(
        client,
        specialty_id,
        staff_user_id=DOCTOR_ID,
        display_name="Another Name",
        key=_key("duplicate-mapping"),
    )
    assert duplicate_mapping.status_code == 409
    assert duplicate_mapping.json()["error"]["code"] == "duplicate_mapping"


def test_directory_filtering_pagination_and_query_validation(doctor_client):
    client = doctor_client
    specialty = _create_specialty(client).json()
    one = _create_doctor(
        client,
        specialty["id"],
        staff_user_id=DOCTOR_ID,
        display_name="Dr. Alice",
    ).json()
    two = _create_doctor(
        client,
        specialty["id"],
        staff_user_id=DOCTOR_2_ID,
        display_name="Dr. Alan",
    ).json()

    first_page = client.get(
        API + "?active=true&specialty_id=" + specialty["id"] + "&q=DR&limit=1",
        headers=_headers(client, PATIENT_ID, ["patient"]),
    )
    assert first_page.status_code == 200
    assert len(first_page.json()["items"]) == 1
    assert first_page.json()["next_cursor"]
    assert first_page.json()["items"][0]["id"] == one["id"]

    next_page = client.get(
        API + "?active=true&specialty_id=" + specialty["id"] + "&q=dr&limit=1&cursor="
        + first_page.json()["next_cursor"],
        headers=_headers(client, PATIENT_ID, ["patient"]),
    )
    assert next_page.status_code == 200
    assert next_page.json()["items"][0]["id"] == two["id"]
    assert next_page.json()["next_cursor"] is None

    changed_filter = client.get(
        API + "?active=false&limit=1&cursor=" + first_page.json()["next_cursor"],
        headers=_headers(client, PATIENT_ID, ["patient"]),
    )
    assert changed_filter.status_code == 400
    assert client.get(API + "?q=d", headers=_headers(client, PATIENT_ID, ["patient"])).status_code == 422
    assert client.get(API + "?unexpected=x", headers=_headers(client, PATIENT_ID, ["patient"])).status_code == 422
    assert client.get(API, headers={}).status_code == 401


def test_authentication_authority_and_role_permissions(doctor_client):
    client = doctor_client
    state = client.app.state._test_dependency_state
    assert client.get(API).status_code == 401
    wrong_audience = client.app.state._test_tokens.user(
        ADMIN_ID, ["hospital_admin"], audience="wrong-audience"
    )
    assert client.post(
        API + "/specialties",
        headers={"Authorization": "Bearer " + wrong_audience, "Idempotency-Key": _key("auth")},
        json={"slug": "cardiology", "name": "Cardiology"},
    ).status_code == 401

    patient_post = client.post(
        API + "/specialties",
        headers=_headers(
            client,
            PATIENT_ID,
            ["patient"],
            **{"Idempotency-Key": _key("patient-specialty")},
        ),
        json={"slug": "cardiology", "name": "Cardiology"},
    )
    assert patient_post.status_code == 403

    state["authority_allowed"] = False
    revoked = client.post(
        API + "/specialties",
        headers=_headers(client, **{"Idempotency-Key": _key("revoked-admin")}),
        json={"slug": "cardiology", "name": "Cardiology"},
    )
    assert revoked.status_code == 403
    state["authority_allowed"] = True

    no_etag = client.patch(
        f"{API}/1",
        headers=_headers(client),
        json={"display_name": "Name"},
    )
    assert no_etag.status_code == 428


def test_schedule_proposal_reconcile_closure_and_deactivation(doctor_client):
    client = doctor_client
    specialty = _create_specialty(client).json()
    doctor = _create_doctor(client, specialty["id"]).json()
    doctor_id = doctor["id"]

    initial = _propose(
        client,
        doctor_id,
        _schedule_body(),
        key="first-schedule",
        etag_value='"1"',
    )
    assert initial.status_code == 202
    proposal = initial.json()
    proposal_id = proposal["id"]
    assert proposal["revision"] == 1
    assert proposal["status"] == "pending"
    assert proposal["conflicts"] == []
    assert initial.headers["etag"] == '"1"'
    assert initial.headers["cache-control"] == "no-store"
    replay = _propose(
        client,
        doctor_id,
        _schedule_body(),
        key="first-schedule",
        etag_value='"1"',
    )
    assert replay.status_code == 202
    assert replay.json() == proposal

    pending_conflict = _propose(
        client,
        doctor_id,
        _schedule_body(expected_revision=1),
        key="pending-conflict",
        etag_value='"2"',
    )
    assert pending_conflict.status_code == 409
    assert pending_conflict.json()["error"]["code"] == "proposal_pending"

    pending_reconcile = client.post(
        f"{API}/{doctor_id}/schedules/{proposal_id}/reconcile",
        headers=_headers(
            client,
            DOCTOR_ID,
            ["doctor"],
            **{
                "If-Match": '"1"',
                "Idempotency-Key": _key("reconcile-still-pending"),
            },
        ),
        json={},
    )
    assert pending_reconcile.status_code == 409
    assert pending_reconcile.json()["error"]["code"] == "decision_pending"

    state = client.app.state._test_dependency_state
    state["decisions"][proposal_id] = {
        "proposal_id": proposal_id,
        "doctor_id": doctor_id,
        "revision": 1,
        "state": "accepted",
        "reason_code": None,
        "conflicting_appointment_ids": [],
        "version": 1,
    }
    pending_replay = client.post(
        f"{API}/{doctor_id}/schedules/{proposal_id}/reconcile",
        headers=_headers(
            client,
            DOCTOR_ID,
            ["doctor"],
            **{
                "If-Match": '"1"',
                "Idempotency-Key": _key("reconcile-still-pending"),
            },
        ),
        json={},
    )
    assert pending_replay.status_code == 409
    assert pending_replay.json() == pending_reconcile.json()

    reconciled = client.post(
        f"{API}/{doctor_id}/schedules/{proposal_id}/reconcile",
        headers=_headers(
            client,
            DOCTOR_ID,
            ["doctor"],
            **{"If-Match": '"1"', "Idempotency-Key": _key("reconcile-1")},
        ),
        json={},
    )
    assert reconciled.status_code == 200
    assert reconciled.json()["status"] == "accepted"
    assert reconciled.headers["etag"] == '"2"'
    replayed_reconcile = client.post(
        f"{API}/{doctor_id}/schedules/{proposal_id}/reconcile",
        headers=_headers(
            client,
            DOCTOR_ID,
            ["doctor"],
            **{"If-Match": '"1"', "Idempotency-Key": _key("reconcile-1")},
        ),
        json={},
    )
    assert replayed_reconcile.status_code == 200
    assert replayed_reconcile.json() == reconciled.json()

    schedules = client.get(
        f"{API}/{doctor_id}/schedules",
        headers=_headers(client, DOCTOR_ID, ["doctor"]),
    )
    assert schedules.status_code == 200
    assert schedules.headers["cache-control"] == "no-store"
    assert schedules.json()["items"][0]["id"] == proposal_id

    closure = _propose(
        client,
        doctor_id,
        _schedule_body(expected_revision=1, intervals=[]),
        key="closure-schedule",
        etag_value='"2"',
    )
    assert closure.status_code == 202
    closure_proposal = closure.json()
    state["decisions"][closure_proposal["id"]] = {
        "proposal_id": closure_proposal["id"],
        "doctor_id": doctor_id,
        "revision": 2,
        "state": "accepted",
        "reason_code": None,
        "conflicting_appointment_ids": [],
        "version": 2,
    }
    closure_reconciled = client.post(
        f"{API}/{doctor_id}/schedules/{closure_proposal['id']}/reconcile",
        headers=_headers(
            client,
            DOCTOR_ID,
            ["doctor"],
            **{"If-Match": '"1"', "Idempotency-Key": _key("reconcile-closure")},
        ),
        json={},
    )
    assert closure_reconciled.status_code == 200
    assert closure_reconciled.json()["intervals"] == []

    state["operational"] = {
        "bookable_slot_count": 1,
        "confirmed_booking_count": 0,
    }
    live_slots = client.patch(
        f"{API}/{doctor_id}",
        headers=_headers(client, **{"If-Match": '"3"'}),
        json={"active": False},
    )
    assert live_slots.status_code == 409
    assert live_slots.json()["error"]["code"] == "schedule_not_closed"

    state["operational"] = {
        "bookable_slot_count": 0,
        "confirmed_booking_count": 0,
    }
    inactive = client.patch(
        f"{API}/{doctor_id}",
        headers=_headers(client, **{"If-Match": '"3"'}),
        json={"active": False},
    )
    assert inactive.status_code == 200
    assert inactive.json()["active"] is False
    assert inactive.headers["etag"] == '"4"'
    assert client.get(API + f"?active=false", headers=_headers(client, PATIENT_ID, ["patient"])).json()["items"][0]["id"] == doctor_id

    reactivated = client.patch(
        f"{API}/{doctor_id}",
        headers=_headers(client, **{"If-Match": '"4"'}),
        json={"active": True},
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["active"] is True


def test_schedule_rejection_exposes_conflicts_and_bad_intervals_fail(doctor_client):
    client = doctor_client
    specialty = _create_specialty(client).json()
    doctor = _create_doctor(client, specialty["id"]).json()
    doctor_id = doctor["id"]
    overlap = _schedule_body(
        intervals=[
            {"starts_at": _time_at(4), "ends_at": _time_at(4, 30)},
            {"starts_at": _time_at(4, 15), "ends_at": _time_at(4, 45)},
        ]
    )
    invalid = _propose(
        client, doctor_id, overlap, key="overlap", etag_value='"1"'
    )
    assert invalid.status_code == 422

    proposal_response = _propose(
        client,
        doctor_id,
        _schedule_body(),
        key="rejected-proposal",
        etag_value='"1"',
    )
    proposal = proposal_response.json()
    state = client.app.state._test_dependency_state
    state["decisions"][proposal["id"]] = {
        "proposal_id": proposal["id"],
        "doctor_id": doctor_id,
        "revision": 1,
        "state": "rejected",
        "reason_code": "confirmed_booking_conflict",
        "conflicting_appointment_ids": ["76001"],
        "version": 2,
    }
    rejected = client.post(
        f"{API}/{doctor_id}/schedules/{proposal['id']}/reconcile",
        headers=_headers(
            client,
            DOCTOR_ID,
            ["doctor"],
            **{"If-Match": '"1"', "Idempotency-Key": _key("reconcile-rejected")},
        ),
        json={},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["conflicts"] == ["76001"]
    assert rejected.json()["intervals"] == proposal["intervals"]


def test_documented_private_identity_and_proposal_leaves(doctor_client):
    client = doctor_client
    specialty = _create_specialty(client).json()
    doctor = _create_doctor(client, specialty["id"]).json()
    doctor_id = doctor["id"]
    identity_path = f"/internal/v1/doctors/{doctor_id}/identity"
    user = client.app.state._test_tokens.user(PATIENT_ID, ["patient"], patient_id="500")
    service = client.app.state._test_tokens.appointment_service("doctors:identity")
    identity = client.get(
        identity_path,
        headers={
            "Authorization": "Bearer " + service,
            "X-Delegated-Authorization": "Bearer " + user,
        },
    )
    assert identity.status_code == 200
    assert set(identity.json()) == {"doctor_id", "staff_user_id", "active", "version"}
    assert identity.headers["etag"] == '"1"'
    assert identity.headers["cache-control"] == "no-store"
    assert identity.json()["staff_user_id"] == DOCTOR_ID

    user_only = client.get(identity_path, headers={"Authorization": "Bearer " + user})
    assert user_only.status_code == 401
    missing_delegation = client.get(
        identity_path, headers={"Authorization": "Bearer " + service}
    )
    assert missing_delegation.status_code == 401

    proposal_response = _propose(
        client, doctor_id, _schedule_body(), key="private-proposal"
    )
    proposal = proposal_response.json()
    doctor_user = client.app.state._test_tokens.user(DOCTOR_ID, ["doctor"])
    proposal_service = client.app.state._test_tokens.appointment_service("schedules:read")
    private_proposal = client.get(
        f"/internal/v1/doctors/{doctor_id}/schedule-proposals/{proposal['id']}",
        headers={
            "Authorization": "Bearer " + proposal_service,
            "X-Delegated-Authorization": "Bearer " + doctor_user,
        },
    )
    assert private_proposal.status_code == 200
    assert set(private_proposal.json()) == {
        "proposal", "staff_user_id", "active", "doctor_version"
    }
    assert private_proposal.json()["proposal"] == proposal

    patient_proposal = client.get(
        f"/internal/v1/doctors/{doctor_id}/schedule-proposals/{proposal['id']}",
        headers={
            "Authorization": "Bearer " + proposal_service,
            "X-Delegated-Authorization": "Bearer " + user,
        },
    )
    assert patient_proposal.status_code == 404


def test_postgres_enforces_interval_overlap_and_specialty_count(doctor_client, test_db):
    client = doctor_client
    specialty = _create_specialty(client).json()
    doctor = _create_doctor(client, specialty["id"]).json()
    doctor_id = int(doctor["id"])
    engine = create_engine(test_db.url)
    version_id = randbelow(2**62) + 1
    interval_id = randbelow(2**62) + 1
    start = datetime.now(timezone.utc) + timedelta(days=5)
    end = start + timedelta(minutes=30)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO schedule_versions
                       (id,doctor_id,revision,timezone,slot_minutes,effective_from,status,version)
                       VALUES (:id,:doctor_id,1,'UTC',15,:effective,'pending',1)"""
                ),
                {"id": version_id, "doctor_id": doctor_id, "effective": start},
            )
            connection.execute(
                text(
                    "INSERT INTO schedule_intervals(id,schedule_version_id,starts_at,ends_at) "
                    "VALUES (:id,:version_id,:start,:end)"
                ),
                {"id": interval_id, "version_id": version_id, "start": start, "end": end},
            )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO schedule_intervals(id,schedule_version_id,starts_at,ends_at) "
                        "VALUES (:id,:version_id,:start,:end)"
                    ),
                    {
                        "id": randbelow(2**62) + 1,
                        "version_id": version_id,
                        "start": start + timedelta(minutes=15),
                        "end": end + timedelta(minutes=15),
                    },
                )

        extra_ids = [randbelow(2**62) + 1 for _ in range(20)]
        with engine.begin() as connection:
            for index, specialty_id in enumerate(extra_ids):
                connection.execute(
                    text(
                        "INSERT INTO specialties(id,slug,name,version) "
                        "VALUES (:id,:slug,:name,1)"
                    ),
                    {
                        "id": specialty_id,
                        "slug": f"extra-specialty-{index}-{specialty_id}",
                        "name": f"Extra specialty {index}",
                    },
                )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                for specialty_id in extra_ids:
                    connection.execute(
                        text(
                            "INSERT INTO doctor_specialties(doctor_id,specialty_id) "
                            "VALUES (:doctor_id,:specialty_id)"
                        ),
                        {"doctor_id": doctor_id, "specialty_id": specialty_id},
                    )
    finally:
        engine.dispose()
