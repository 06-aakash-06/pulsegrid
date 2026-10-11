"""Clinical policy, transitions, persistence and atomicity on actual PostgreSQL."""

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from records_service.clinical_schemas import Finalize, Grant

PREFIX = "/api/v1/records"
CONTENT = dict(
    summary="Synthetic history",
    assessment="Synthetic diagnosis",
    plan="Synthetic consultation plan",
)
ITEM = dict(
    medicine_id="50",
    quantity=3,
    dosage="Synthetic dose",
    instructions="Synthetic instructions",
)


def headers(token, version=None, key=None):
    out = {
        "Authorization": "Bearer " + token,
        "Idempotency-Key": key or uuid.uuid4().hex,
    }
    if version is not None:
        out["If-Match"] = f'"{version}"'
    return out


def create(fixture, appointment="100", key=None):
    client, app, state, token, *_ = fixture
    result = client.post(
        PREFIX + "/consultations",
        json=dict(appointment_id=appointment, clinical_content=CONTENT),
        headers=headers(token(), key=key),
    )
    assert result.status_code == 201, result.text
    return result


def finalized(fixture, items=None):
    client, app, state, token, *_ = fixture
    c = create(fixture).json()
    h = headers(token(), c["version"])
    result = client.post(
        PREFIX + f"/consultations/{c['id']}/finalize",
        json={"prescription_items": [ITEM] if items is None else items},
        headers=h,
    )
    assert result.status_code == 200, result.text
    return result, h


def counts(dsn):
    with psycopg.connect(**dsn) as conn:
        return {
            t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in (
                "consultations",
                "medical_records",
                "prescriptions",
                "prescription_items",
                "outbox_events",
                "audit_entries",
                "idempotency_requests",
            )
        }


def test_database_author_integrity_preserves_nullable_legacy_rows(database):
    dsn, _ = database
    statement = """INSERT INTO consultations
        (id, appointment_id, patient_id, doctor_id, author_user_id,
         status, revision, clinical_content)
        VALUES (%s, %s, 10, 30, %s, 'draft', 1, '{}'::jsonb)"""
    with psycopg.connect(**dsn) as connection:
        connection.execute(statement, (100, 100, None))
    with psycopg.connect(**dsn) as connection:
        with pytest.raises(psycopg.errors.CheckViolation) as error:
            connection.execute(statement, (101, 101, -1))
        assert error.value.diag.constraint_name == (
            "ck_consultations_author_user_id_nonnegative"
        )
    with psycopg.connect(**dsn) as connection:
        assert connection.execute(
            "SELECT author_user_id FROM consultations WHERE id=100"
        ).fetchone() == (None,)
        assert connection.execute(
            "SELECT count(*) FROM consultations WHERE id=101"
        ).fetchone()[0] == 0


def test_workflow_snapshot_tracks_finalization_and_revocation(clinical):
    client, app, state, token, service, dsn, password = clinical
    consultation = create(clinical).json()
    snapshot_url = "/internal/v1/appointments/100/workflow-snapshot?patient_id=10"
    service_headers = {"Authorization": "Bearer " + service("appointment", "workflow:records-read")}
    draft = client.get(snapshot_url, headers=service_headers)
    assert draft.status_code == 200, draft.text
    assert draft.json()["snapshot"]["consultation"]["status"] == "draft"
    assert draft.json()["next_cursor"] is None
    final = client.post(PREFIX + f"/consultations/{consultation['id']}/finalize",
                        json={"prescription_items": [ITEM]},
                        headers=headers(token(), consultation["version"]))
    assert final.status_code == 200, final.text
    issued = client.get(snapshot_url, headers=service_headers)
    assert issued.status_code == 200, issued.text
    prescription = issued.json()["snapshot"]["consultation"]["prescription"]
    assert prescription["state"] == "issued"
    assert issued.json()["snapshot"]["revision"] > draft.json()["snapshot"]["revision"]
    revoked = client.post(PREFIX + f"/prescriptions/{prescription['id']}/revoke",
                          json={"reason": "Synthetic correction"},
                          headers=headers(token(), prescription["version"]))
    assert revoked.status_code == 200, revoked.text
    after_revoke = client.get(snapshot_url, headers=service_headers)
    assert after_revoke.status_code == 200
    assert after_revoke.json()["snapshot"]["consultation"]["prescription"]["state"] == "revoked"
    assert after_revoke.json()["snapshot"]["revision"] > issued.json()["snapshot"]["revision"]
    denied = client.get(snapshot_url.replace("patient_id=10", "patient_id=11"), headers=service_headers)
    assert denied.status_code == 404


def test_enrolled_workflow_requires_consultation_start(clinical, monkeypatch):
    client, app, state, token, *_ = clinical
    monkeypatch.setenv("PULSEGRID_RECORDS_WORKFLOW_GATE", "true")
    state["workflow_state"] = "booked"
    blocked = client.post(PREFIX + "/consultations",
                          json=dict(appointment_id="100", clinical_content=CONTENT),
                          headers=headers(token()))
    assert blocked.status_code == 409, blocked.text
    state["workflow_state"] = "in_consultation"
    allowed = create(clinical)
    assert allowed.status_code == 201


def test_create_read_update_finalize_and_persistence(clinical):
    client, app, state, token, service, dsn, password = clinical
    c = create(clinical).json()
    assert c["revision"] == c["version"] == 1
    got = client.get(
        PREFIX + "/consultations/" + c["id"],
        headers=headers(token("1", "patient", "10")),
    )
    assert got.json() == c and got.headers["etag"] == '"1"'
    patch = client.patch(
        PREFIX + "/consultations/" + c["id"],
        json={
            "clinical_content": {**CONTENT, "assessment": "Synthetic revised diagnosis"}
        },
        headers=headers(token(), 1),
    )
    assert patch.status_code == 200 and patch.json()["version"] == 2
    stale = client.patch(
        PREFIX + "/consultations/" + c["id"],
        json={"clinical_content": CONTENT},
        headers=headers(token(), 1),
    )
    assert stale.status_code == 412
    result = client.post(
        PREFIX + "/consultations/" + c["id"] + "/finalize",
        json={"prescription_items": [ITEM]},
        headers=headers(token(), 2),
    )
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["consultation"]["status"] == "finalized"
    assert data["record"]["content"]["assessment"] == "Synthetic revised diagnosis"
    assert data["prescription"]["items"][0]["quantity"] == 3
    assert state["hold"]["100"][0] == "finalized"
    assert (
        client.patch(
            PREFIX + "/consultations/" + c["id"],
            json={"clinical_content": CONTENT},
            headers=headers(token(), 3),
        ).status_code
        == 409
    )
    with psycopg.connect(**dsn) as conn:
        assert (
            conn.execute(
                "SELECT clinical_content FROM consultations WHERE id=%s", (c["id"],)
            ).fetchone()[0]
            == data["record"]["content"]
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM audit_heads WHERE chain_id='phase1-anchor'"
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT count(*) FROM outbox_events WHERE published_at IS NOT NULL"
            ).fetchone()[0]
            == 0
        )
    assert (
        client.get(
            PREFIX + "/" + data["record"]["id"],
            headers=headers(token("1", "patient", "10")),
        ).json()
        == data["record"]
    )


@pytest.mark.parametrize(
    "role",
    [
        "doctor",
        "patient",
        "pharmacist",
        "hospital_admin",
        "ops",
        "billing_staff",
        "receptionist",
        "emergency_staff",
    ],
)
def test_unrelated_users_cannot_read_or_modify_clinical(clinical, role):
    client, app, state, token, *_ = clinical
    result, _ = finalized(clinical)
    data = result.json()
    stranger = token("99", role, "99" if role == "patient" else None)
    assert client.get(
        PREFIX + "/" + data["record"]["id"], headers=headers(stranger)
    ).status_code in (403, 404)
    assert client.get(
        PREFIX + "/consultations/" + data["consultation"]["id"],
        headers=headers(stranger),
    ).status_code in (403, 404)
    assert client.patch(
        PREFIX + "/consultations/" + data["consultation"]["id"],
        json={"clinical_content": CONTENT},
        headers=headers(stranger, 2),
    ).status_code in (403, 404)
    assert client.post(
        PREFIX + "/prescriptions/" + data["prescription"]["id"] + "/revoke",
        json={"reason": "Synthetic reason"},
        headers=headers(stranger, 1),
    ).status_code in (403, 404)
    if role != "pharmacist":
        assert client.get(
            PREFIX + "/prescriptions/" + data["prescription"]["id"],
            headers=headers(stranger),
        ).status_code in (403, 404)


def test_patient_history_and_pharmacist_minimum_views(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    result, _ = finalized(clinical)
    d = result.json()
    pid = d["prescription"]["id"]
    own = token("1", "patient", "10")
    page = client.get(PREFIX + "/patients/10", headers=headers(own))
    assert page.status_code == 200 and "content" not in page.json()["items"][0]
    assert client.get(PREFIX + "/patients/11", headers=headers(own)).status_code == 404
    pharmacist = token("5", "pharmacist")
    full = client.get(PREFIX + "/prescriptions/" + pid, headers=headers(pharmacist))
    assert (
        full.status_code == 200
        and "clinical_content" not in full.text
        and "dosage" in full.text
    )
    assert (
        client.get(PREFIX + "/prescriptions", headers=headers(pharmacist)).status_code
        == 403
    )
    leaf = client.get(
        "/internal/v1/prescriptions/" + pid + "/dispensing-context",
        headers={
            "Authorization": "Bearer " + service(),
            "X-Delegated-Authorization": "Bearer " + pharmacist,
        },
    )
    assert leaf.status_code == 200, leaf.text
    assert set(leaf.json()) == {
        "prescription_id",
        "consultation_id",
        "appointment_id",
        "patient_id",
        "journey_id",
        "revision",
        "state",
        "items",
        "version",
    }
    assert set(leaf.json()["items"][0]) == {"id", "medicine_id", "quantity"}
    assert not any(
        x in leaf.text
        for x in ("Synthetic", "dosage", "instructions", "clinical_content")
    )
    calls = len(state["calls"])
    client.get(
        "/internal/v1/prescriptions/" + pid + "/dispensing-context",
        headers={
            "Authorization": "Bearer " + service(),
            "X-Delegated-Authorization": "Bearer " + pharmacist,
        },
    )
    assert len(state["calls"]) == calls  # leaf never invokes a dependency
    billing = client.get(
        "/internal/v1/consultations/" + d["consultation"]["id"] + "/charge-context",
        headers={
            "Authorization": "Bearer "
            + service("billing", "consultations:charge-context"),
            "X-Delegated-Authorization": "Bearer " + token("6", "billing_staff"),
        },
    )
    assert billing.status_code == 200 and "Synthetic" not in billing.text


@pytest.mark.parametrize(
    "case",
    [
        "user_only",
        "wrong_scope",
        "wrong_caller",
        "forged_caller",
        "wrong_audience",
        "missing_delegation",
        "wrong_role",
        "other_patient",
    ],
)
def test_private_auth_rejects_invalid_context(clinical, case):
    client, app, state, token, service, *_ = clinical
    result, _ = finalized(clinical)
    pid = result.json()["prescription"]["id"]
    h = {
        "Authorization": "Bearer " + service(),
        "X-Delegated-Authorization": "Bearer " + token("5", "pharmacist"),
    }
    if case == "user_only":
        h["Authorization"] = "Bearer " + token("5", "pharmacist")
    if case == "wrong_scope":
        h["Authorization"] = "Bearer " + service(scope="consultations:charge-context")
    if case == "wrong_caller":
        h["Authorization"] = "Bearer " + service("billing")
    if case == "forged_caller":
        h["Authorization"] = "Bearer " + service(signer="billing")
    if case == "wrong_audience":
        h["Authorization"] = "Bearer " + service(aud="pulsegrid-internal:pharmacy")
    if case == "missing_delegation":
        h.pop("X-Delegated-Authorization")
    if case == "wrong_role":
        h["X-Delegated-Authorization"] = "Bearer " + token("6", "hospital_admin")
    if case == "other_patient":
        h["X-Delegated-Authorization"] = "Bearer " + token("6", "patient", "11")
    assert client.get(
        "/internal/v1/prescriptions/" + pid + "/dispensing-context", headers=h
    ).status_code in (401, 403, 404)


def test_author_access_active_hold_grants_and_amendments(clinical):
    client, app, state, token, *_ = clinical
    result, _ = finalized(clinical)
    data = result.json()
    rid = data["record"]["id"]
    # Finalized author may read their own document but historical listing needs care/grant.
    assert client.get(PREFIX + "/" + rid, headers=headers(token())).status_code == 200
    assert (
        client.get(PREFIX + "/patients/10", headers=headers(token())).status_code == 404
    )
    draft = create(clinical, "102")
    assert (
        client.get(PREFIX + "/patients/10", headers=headers(token())).status_code == 200
    )
    client.post(
        PREFIX + "/consultations/" + draft.json()["id"] + "/finalize",
        json={"prescription_items": []},
        headers=headers(token(), 1),
    )
    assert (
        client.get(PREFIX + "/patients/10", headers=headers(token())).status_code == 404
    )
    grant = client.post(
        PREFIX + "/access-grants",
        json=dict(
            patient_id="10",
            grantee_user_id="20",
            scope="records:read",
            expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        ),
        headers=headers(token("1", "patient", "10")),
    )
    assert grant.status_code == 201, grant.text
    assert (
        client.get(PREFIX + "/patients/10", headers=headers(token())).status_code == 200
    )
    ah = headers(token(), 1)
    amended = client.post(
        PREFIX + "/" + rid + "/amendments",
        json={
            "content": {**CONTENT, "summary": "Synthetic amendment"},
            "reason": "Synthetic correction",
        },
        headers=ah,
    )
    assert amended.status_code == 201, amended.text
    assert amended.json()["supersedes_id"] == rid and amended.json()["revision"] == 2
    assert (
        client.get(
            PREFIX + "/" + rid, headers=headers(token("1", "patient", "10"))
        ).json()["content"]
        == CONTENT
    )
    repeated = client.post(
        PREFIX + "/" + rid + "/amendments",
        json={
            "content": {**CONTENT, "summary": "Synthetic amendment"},
            "reason": "Synthetic correction",
        },
        headers=ah,
    )
    assert repeated.json() == amended.json()
    assert (
        client.post(
            PREFIX + "/" + rid + "/amendments",
            json={"content": CONTENT, "reason": "Synthetic correction"},
            headers=headers(token(), 1),
        ).json()["error"]["code"]
        == "superseded"
    )
    assert (
        client.delete(
            PREFIX + "/access-grants/" + grant.json()["id"],
            headers=headers(token("1", "patient", "10"), 1),
        ).status_code
        == 204
    )
    assert (
        client.get(PREFIX + "/patients/10", headers=headers(token())).status_code == 404
    )
    assert (
        client.post(
            PREFIX + "/" + amended.json()["id"] + "/amendments",
            json={"content": CONTENT, "reason": "Synthetic correction"},
            headers=headers(token(), 1),
        ).status_code
        == 404
    )


def test_prescription_grant_revocation_and_expiry(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    result, _ = finalized(clinical)
    p = result.json()["prescription"]
    body = dict(
        patient_id="10",
        grantee_user_id="21",
        scope="prescriptions:read",
        expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    grant = client.post(
        PREFIX + "/access-grants",
        json=body,
        headers=headers(token("1", "patient", "10")),
    )
    assert grant.status_code == 201
    assert (
        client.get(
            PREFIX + "/prescriptions/" + p["id"], headers=headers(token("21"))
        ).status_code
        == 200
    )
    assert (
        client.get(PREFIX + "/patients/10", headers=headers(token("21"))).status_code
        == 404
    )
    with psycopg.connect(**dsn) as conn:
        conn.execute(
            "UPDATE record_access_grants SET expires_at=now()-interval '1 second' WHERE id=%s",
            (grant.json()["id"],),
        )
    assert (
        client.get(
            PREFIX + "/prescriptions/" + p["id"], headers=headers(token("21"))
        ).status_code
        == 404
    )
    h = headers(token(), 1)
    revoked = client.post(
        PREFIX + "/prescriptions/" + p["id"] + "/revoke",
        json={"reason": "Synthetic withdrawal"},
        headers=h,
    )
    assert (
        revoked.status_code == 200
        and revoked.json()["state"] == "revoked"
        and revoked.headers["etag"] == '"2"'
    )
    assert (
        client.post(
            PREFIX + "/prescriptions/" + p["id"] + "/revoke",
            json={"reason": "Synthetic withdrawal"},
            headers=h,
        ).json()
        == revoked.json()
    )
    noop = client.post(
        PREFIX + "/prescriptions/" + p["id"] + "/revoke",
        json={"reason": "Synthetic withdrawal"},
        headers=headers(token(), 2),
    )
    assert noop.status_code == 200 and noop.json()["version"] == 2


def test_hold_interruption_recovers_same_id_and_finalize_retry(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    h = headers(token())
    body = dict(appointment_id="100", clinical_content=CONTENT)
    state["inject_after_hold"] = True
    failed = client.post(PREFIX + "/consultations", json=body, headers=h)
    assert failed.status_code == 504 and counts(dsn)["consultations"] == 0
    held_id = state["hold"]["100"][1]
    created = client.post(PREFIX + "/consultations", json=body, headers=h)
    assert created.status_code == 201 and created.json()["id"] == held_id
    state["fail_finalize_hold"] = True
    fh = headers(token(), 1)
    result = client.post(
        PREFIX + "/consultations/" + held_id + "/finalize",
        json={"prescription_items": []},
        headers=fh,
    )
    assert result.status_code == 200 and state["hold"]["100"][0] == "active"
    before = counts(dsn)
    state["fail_finalize_hold"] = False
    replay = client.post(
        PREFIX + "/consultations/" + held_id + "/finalize",
        json={"prescription_items": []},
        headers=fh,
    )
    assert (
        replay.json() == result.json()
        and counts(dsn) == before
        and state["hold"]["100"][0] == "finalized"
    )


def test_concurrent_same_key_and_finalization(clinical):
    client, app, state, token, *_ = clinical
    h = headers(token())
    body = dict(appointment_id="100", clinical_content=CONTENT)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(PREFIX + "/consultations", json=body, headers=h),
                range(2),
            )
        )
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json() == results[1].json()
    c = results[0].json()
    fh = headers(token(), 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(
                    PREFIX + "/consultations/" + c["id"] + "/finalize",
                    json={"prescription_items": [ITEM]},
                    headers=fh,
                ),
                range(2),
            )
        )
    assert [r.status_code for r in results] == [200, 200]
    assert results[0].json() == results[1].json()


def test_invalid_medicine_and_failed_dependency_no_partial_effects(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    c = create(clinical).json()
    before = counts(dsn)
    state["inactive_medicine"] = True
    result = client.post(
        PREFIX + "/consultations/" + c["id"] + "/finalize",
        json={"prescription_items": [ITEM]},
        headers=headers(token(), 1),
    )
    assert result.status_code == 422 and counts(dsn) == before
    state["inactive_medicine"] = False
    state["fail"] = 503
    result = client.post(
        PREFIX + "/consultations/" + c["id"] + "/finalize",
        json={"prescription_items": [ITEM]},
        headers=headers(token(), 1),
    )
    assert result.status_code == 503 and counts(dsn) == before


def test_atomic_rollback_on_audit_failure(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    c = create(clinical).json()
    before = counts(dsn)
    with psycopg.connect(**dsn) as conn:
        conn.execute(
            "REVOKE EXECUTE ON FUNCTION records_append_audit(BIGINT,TEXT,BIGINT,TEXT,TEXT,UUID,UUID) FROM records_app"
        )
    result = client.post(
        PREFIX + "/consultations/" + c["id"] + "/finalize",
        json={"prescription_items": [ITEM]},
        headers=headers(token(), 1),
    )
    assert result.status_code == 503 and counts(dsn) == before
    with psycopg.connect(**dsn) as conn:
        assert (
            conn.execute(
                "SELECT status FROM consultations WHERE id=%s", (c["id"],)
            ).fetchone()[0]
            == "draft"
        )
    assert (
        client.get(
            PREFIX + "/consultations/" + c["id"], headers=headers(token())
        ).status_code
        == 503
    )


def test_audit_hash_chain_and_runtime_tampering_denied(clinical):
    client, app, state, token, service, dsn, password = clinical
    result, _ = finalized(clinical)
    data = result.json()
    client.get(
        PREFIX + "/" + data["record"]["id"],
        headers=headers(token("1", "patient", "10")),
    )
    client.get(
        PREFIX + "/" + data["record"]["id"],
        headers=headers(token("99", "patient", "99")),
    )
    with psycopg.connect(**dsn) as conn:
        rows = conn.execute(
            "SELECT sequence,prev_hash,entry_hash,canonical_metadata::text FROM audit_entries WHERE chain_id='records-domain' ORDER BY sequence"
        ).fetchall()
        previous = "0" * 64
        for sequence, prev, entry, canonical in rows:
            assert prev == previous
            assert hashlib.sha256((previous + canonical).encode()).hexdigest() == entry
            assert "Synthetic" not in canonical
            previous = entry
        assert (
            conn.execute(
                "SELECT last_hash FROM audit_heads WHERE chain_id='records-domain'"
            ).fetchone()[0]
            == previous
        )
        assert "denied" in rows[-1][3]
    runtime = {**dsn, "user": "records_app", "password": password}
    attempts = [
        "UPDATE audit_entries SET entry_hash=repeat('0',64)",
        "DELETE FROM audit_entries",
        "UPDATE medical_records SET content='{}'::jsonb",
        "DELETE FROM prescription_items",
        "UPDATE consultations SET clinical_content='{}'::jsonb",
        "UPDATE prescriptions SET patient_id=99",
        "CREATE TABLE forbidden(id integer)",
    ]
    for query in attempts:
        with psycopg.connect(**runtime) as conn:
            with pytest.raises(psycopg.Error):
                conn.execute(query)
    # Demonstrate metadata modification and order changes break verification against the saved anchor.
    seq, prev, entry, meta = rows[-1]
    assert hashlib.sha256((prev + meta + " ").encode()).hexdigest() != entry
    assert rows[1][1] != rows[-1][2]


@pytest.mark.parametrize(
    "claims", [{"aud": "wrong"}, {"iss": "wrong"}, {"exp": 1}, {"token_use": "service"}]
)
def test_bad_user_claims_and_current_authority(clinical, claims):
    client, app, state, token, *_ = clinical
    assert (
        client.get(
            PREFIX + "/consultations", headers=headers(token(**claims))
        ).status_code
        == 401
    )
    state["active"] = False
    assert (
        client.get(PREFIX + "/consultations", headers=headers(token())).status_code
        == 403
    )


def test_idempotency_preconditions_filtering_and_cursor(clinical):
    client, app, state, token, *_ = clinical
    h = headers(token())
    b = dict(appointment_id="100", clinical_content=CONTENT)
    first = client.post(PREFIX + "/consultations", json=b, headers=h)
    assert first.status_code == 201
    assert (
        client.post(
            PREFIX + "/consultations",
            json={
                **b,
                "clinical_content": {**CONTENT, "summary": "Different synthetic text"},
            },
            headers=h,
        ).status_code
        == 409
    )
    create(clinical, "102")
    page = client.get(PREFIX + "/consultations?limit=1", headers=headers(token()))
    assert len(page.json()["items"]) == 1 and page.json()["next_cursor"]
    cursor = page.json()["next_cursor"]
    next_page = client.get(
        PREFIX + "/consultations",
        params={"limit": 1, "cursor": cursor},
        headers=headers(token()),
    )
    assert (
        next_page.status_code == 200
        and next_page.json()["items"][0]["id"] != first.json()["id"]
    )
    assert (
        client.get(
            PREFIX + "/consultations",
            params={"cursor": cursor, "patient_id": "10"},
            headers=headers(token()),
        ).status_code
        == 400
    )
    assert (
        client.get(
            PREFIX + "/consultations",
            params={"cursor": cursor},
            headers=headers(token("1", "patient", "10")),
        ).status_code
        == 400
    )
    assert (
        client.get(
            PREFIX + "/consultations?cursor=garbage", headers=headers(token())
        ).status_code
        == 400
    )
    for query in (
        "unknown=1",
        "limit=0",
        "limit=101",
        "limit=2&limit=3",
        "patient_id=0",
        "appointment_id=9223372036854775808",
    ):
        assert (
            client.get(
                PREFIX + "/consultations?" + query, headers=headers(token())
            ).status_code
            == 422
        )
    cid = first.json()["id"]
    for if_match, status in ((None, 428), ("1", 400), ('"2"', 412)):
        h = headers(token())
        if if_match is not None:
            h["If-Match"] = if_match
        assert (
            client.patch(
                PREFIX + "/consultations/" + cid,
                json={"clinical_content": CONTENT},
                headers=h,
            ).status_code
            == status
        )
    assert (
        client.post(
            PREFIX + "/consultations",
            json={"appointment_id": "102", "clinical_content": CONTENT},
            headers=headers(token()),
        ).json()["error"]["code"]
        == "consultation_exists"
    )


@pytest.mark.parametrize(
    "items",
    [
        [{**ITEM, "quantity": True}],
        [{**ITEM, "quantity": 1.2}],
        [{**ITEM, "quantity": 0}],
        [ITEM, ITEM],
        [{**ITEM, "dosage": ""}],
        [{**ITEM, "unknown": 1}],
    ],
)
def test_prescription_validation(items):
    with pytest.raises(ValueError):
        Finalize(prescription_items=items)


@pytest.mark.parametrize(
    "expiry", ["2026-10-12T10:00:00+05:30", "2026-10-12", 12345678]
)
def test_grant_utc_validation(expiry):
    with pytest.raises(ValueError):
        Grant(
            patient_id="10",
            grantee_user_id="20",
            scope="records:read",
            expires_at=expiry,
        )


def test_distinct_key_finalization_race_and_lifetime_uniqueness(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    c = create(clinical).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(
                    PREFIX + "/consultations/" + c["id"] + "/finalize",
                    json={"prescription_items": [ITEM]},
                    headers=headers(token(), 1),
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in results) == [200, 412]
    with psycopg.connect(**dsn) as conn:
        assert conn.execute("SELECT count(*) FROM medical_records").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM prescriptions").fetchone()[0] == 1
        assert (
            conn.execute("SELECT count(*) FROM prescription_items").fetchone()[0] == 1
        )


def test_lost_hold_body_mismatch_and_scope_denial(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    h = headers(token())
    body = dict(appointment_id="100", clinical_content=CONTENT)
    state["inject_after_hold"] = True
    assert (
        client.post(PREFIX + "/consultations", json=body, headers=h).status_code == 504
    )
    before = counts(dsn)
    assert (
        client.post(
            PREFIX + "/consultations",
            json={
                **body,
                "clinical_content": {**CONTENT, "plan": "Different synthetic plan"},
            },
            headers=h,
        ).status_code
        == 409
    )
    assert counts(dsn) == before
    assert (
        client.post(
            PREFIX + "/consultations", json=body, headers=headers(token("21"))
        ).status_code
        == 404
    )
    assert (
        client.post(
            PREFIX + "/consultations",
            json=body,
            headers=headers(token("1", "patient", "10")),
        ).status_code
        == 403
    )


def test_validation_and_runtime_constraints(clinical):
    client, app, state, token, service, dsn, password = clinical
    for body in (
        {"appointment_id": "0", "clinical_content": CONTENT},
        {
            "appointment_id": "100",
            "clinical_content": {**CONTENT, "diagnosis": "extra"},
        },
        {"appointment_id": "100", "clinical_content": {**CONTENT, "summary": " "}},
        {"appointment_id": "100", "clinical_content": CONTENT, "author_user_id": "20"},
    ):
        assert (
            client.post(
                PREFIX + "/consultations", json=body, headers=headers(token())
            ).status_code
            == 422
        )
    assert (
        client.post(
            PREFIX + "/consultations",
            json={"appointment_id": "100", "clinical_content": CONTENT},
            headers={"Authorization": "Bearer " + token()},
        ).status_code
        == 422
    )
    d = finalized(clinical)[0].json()
    assert (
        client.get(
            PREFIX + "/" + d["record"]["id"] + "?patient_id=10",
            headers=headers(token()),
        ).status_code
        == 422
    )
    runtime = {**dsn, "user": "records_app", "password": password}
    queries = [
        "INSERT INTO prescription_items(id,prescription_id,medicine_id,medicine_snapshot,dosage,instructions,quantity) VALUES (99999,99998,50,'{}','Synthetic','Synthetic',1)",
        "UPDATE outbox_events SET envelope='{}'::jsonb",
        "SELECT records_append_audit(20,'arbitrary clinical text',10,'allowed',NULL,'00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001')",
        "SELECT records_append_audit(NULL,'read',10,'allowed',NULL,'00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001')",
    ]
    for query in queries:
        with psycopg.connect(**runtime) as conn:
            with pytest.raises(psycopg.Error):
                conn.execute(query)


def test_grant_ownership_expiry_and_scoped_listing(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    create(clinical)
    create(clinical, "101")
    page = client.get(
        PREFIX + "/consultations?limit=1", headers=headers(token("1", "patient", "10"))
    )
    assert len(page.json()["items"]) == 1 and page.json()["next_cursor"] is None
    body = dict(
        patient_id="10",
        grantee_user_id="20",
        scope="records:read",
        expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    assert (
        client.post(
            PREFIX + "/access-grants",
            json=body,
            headers=headers(token("2", "patient", "11")),
        ).status_code
        == 404
    )
    for expiry in (
        datetime.now(timezone.utc) - timedelta(seconds=1),
        datetime.now(timezone.utc) + timedelta(days=31),
    ):
        assert (
            client.post(
                PREFIX + "/access-grants",
                json={**body, "expires_at": expiry.isoformat()},
                headers=headers(token("1", "patient", "10")),
            ).status_code
            == 422
        )
    g = client.post(
        PREFIX + "/access-grants",
        json=body,
        headers=headers(token("1", "patient", "10")),
    ).json()
    assert (
        client.delete(
            PREFIX + "/access-grants/" + g["id"],
            headers=headers(token("2", "patient", "11"), 1),
        ).status_code
        == 404
    )


def test_replay_after_pool_restart_retains_original_etag(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    h = headers(token())
    body = dict(appointment_id="100", clinical_content=CONTENT)
    c = client.post(PREFIX + "/consultations", json=body, headers=h)
    assert (
        client.patch(
            PREFIX + "/consultations/" + c.json()["id"],
            json={"clinical_content": CONTENT},
            headers=headers(token(), 1),
        ).status_code
        == 200
    )
    client.portal.call(app.state.database.close)
    client.portal.call(app.state.database.start)
    replay = client.post(PREFIX + "/consultations", json=body, headers=h)
    assert replay.json() == c.json() and replay.headers["etag"] == '"1"'


def test_audit_anchor_detects_delete_reordering_and_tampering(clinical):
    client, app, state, token, service, dsn, *_ = clinical
    finalized(clinical)
    with psycopg.connect(**dsn) as conn:
        rows = conn.execute(
            "SELECT prev_hash,entry_hash,canonical_metadata::text FROM audit_entries WHERE chain_id='records-domain' ORDER BY sequence"
        ).fetchall()
        anchor = conn.execute(
            "SELECT last_hash FROM audit_heads WHERE chain_id='records-domain'"
        ).fetchone()[0]

    def verifies(entries):
        previous = "0" * 64
        for prev, hash, metadata in entries:
            if (
                prev != previous
                or hashlib.sha256((previous + metadata).encode()).hexdigest() != hash
            ):
                return False
            previous = hash
        return previous == anchor

    assert verifies(rows)
    assert not verifies(rows[:-1])
    assert not verifies(list(reversed(rows)))
    tampered = list(rows)
    p, h, m = tampered[0]
    tampered[0] = (p, h, m + " ")
    assert not verifies(tampered)


def test_multiple_roles_select_applicable_current_scope(clinical):
    client, app, state, token, *_ = clinical
    data = finalized(clinical)[0].json()
    mixed = token("21", "doctor", "10", roles=["patient", "doctor"])
    assert (
        client.get(PREFIX + "/patients/10", headers=headers(mixed)).status_code == 200
    )
    assert (
        client.get(
            PREFIX + "/" + data["record"]["id"], headers=headers(mixed)
        ).status_code
        == 200
    )
    assert (
        client.get(
            PREFIX + "/consultations/" + data["consultation"]["id"],
            headers=headers(mixed),
        ).status_code
        == 200
    )
    assert (
        client.get(
            PREFIX + "/prescriptions/" + data["prescription"]["id"],
            headers=headers(mixed),
        ).status_code
        == 200
    )
    mixed_pharmacist = token("21", "doctor", roles=["doctor", "pharmacist"])
    assert (
        client.get(
            PREFIX + "/prescriptions/" + data["prescription"]["id"],
            headers=headers(mixed_pharmacist),
        ).status_code
        == 200
    )
    assert (
        client.get(
            PREFIX + "/" + data["record"]["id"], headers=headers(mixed_pharmacist)
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "mode,status",
    [("timeout", 504), ("malformed", 503), ("oversized", 503), ("redirect", 503)],
)
def test_dependency_failures_prevent_local_clinical_effects(clinical, mode, status):
    client, app, state, token, service, dsn, *_ = clinical
    state["response_mode"] = mode
    before = counts(dsn)
    result = client.post(
        PREFIX + "/consultations",
        json={"appointment_id": "100", "clinical_content": CONTENT},
        headers=headers(token()),
    )
    assert result.status_code == status and counts(dsn) == before


def test_dependency_circuit_opens_without_unsafe_fallback(clinical):
    client, app, state, token, *_ = clinical
    state["fail"] = 503
    for _ in range(3):
        assert (
            client.post(
                PREFIX + "/consultations",
                json={"appointment_id": "100", "clinical_content": CONTENT},
                headers=headers(token()),
            ).status_code
            == 503
        )
    dependency_calls = state["calls"].count(
        "/internal/v1/appointments/100/consultation-context"
    )
    assert dependency_calls == 5
    assert (
        client.post(
            PREFIX + "/consultations",
            json={"appointment_id": "100", "clinical_content": CONTENT},
            headers=headers(token()),
        ).status_code
        == 503
    )
    assert (
        state["calls"].count("/internal/v1/appointments/100/consultation-context")
        == dependency_calls
    )


def test_exact_wire_views_and_openapi(clinical):
    from records_service.clinical_schemas import (
        ChargeContext,
        Consultation,
        DispensingContext,
        FinalizeResult,
        Page,
        Prescription,
        RecordSummary,
    )

    client, app, state, token, service, *_ = clinical
    data = finalized(clinical)[0].json()
    FinalizeResult.model_validate(data)
    Page[Consultation].model_validate(
        client.get(PREFIX + "/consultations", headers=headers(token())).json()
    )
    Page[Prescription].model_validate(
        client.get(PREFIX + "/prescriptions", headers=headers(token())).json()
    )
    Page[RecordSummary].model_validate(
        client.get(
            PREFIX + "/patients/10", headers=headers(token("1", "patient", "10"))
        ).json()
    )
    DispensingContext.model_validate(
        client.get(
            "/internal/v1/prescriptions/"
            + data["prescription"]["id"]
            + "/dispensing-context",
            headers={
                "Authorization": "Bearer " + service(),
                "X-Delegated-Authorization": "Bearer " + token("5", "pharmacist"),
            },
        ).json()
    )
    ChargeContext.model_validate(
        client.get(
            "/internal/v1/consultations/"
            + data["consultation"]["id"]
            + "/charge-context",
            headers={
                "Authorization": "Bearer "
                + service("billing", "consultations:charge-context"),
                "X-Delegated-Authorization": "Bearer " + token("6", "billing_staff"),
            },
        ).json()
    )
    paths = app.openapi()["paths"]
    assert paths[PREFIX + "/consultations"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/Consultation")
    assert {
        p["name"] for p in paths[PREFIX + "/consultations"]["get"]["parameters"]
    } == {"appointment_id", "patient_id", "cursor", "limit"}


def test_missing_and_invalid_signature_fail_closed(clinical):
    client, app, state, token, *_ = clinical
    assert client.get(PREFIX + "/consultations").status_code == 401
    original = token()
    head, payload, signature = original.split(".")
    corrupted = (
        head
        + "."
        + payload
        + "."
        + ("A" if signature[0] != "A" else "B")
        + signature[1:]
    )
    assert (
        client.get(PREFIX + "/consultations", headers=headers(corrupted)).status_code
        == 401
    )
    assert state["calls"] == []


@pytest.mark.parametrize(
    "case",
    ["missing_patient", "inactive_patient", "missing_staff", "non_doctor_grantee"],
)
def test_invalid_foreign_references_fail_before_clinical_mutation(clinical, case):
    client, app, state, token, service, dsn, *_ = clinical
    state[case] = True
    before = counts(dsn)
    if "patient" in case:
        response = client.post(
            PREFIX + "/consultations",
            json={"appointment_id": "100", "clinical_content": CONTENT},
            headers=headers(token()),
        )
    else:
        response = client.post(
            PREFIX + "/access-grants",
            json=dict(
                patient_id="10",
                grantee_user_id="20",
                scope="records:read",
                expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            ),
            headers=headers(token("1", "patient", "10")),
        )
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "invalid_reference"
    )
    assert counts(dsn) == before
