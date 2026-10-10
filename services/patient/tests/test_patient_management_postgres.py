"""Patient management API/database checks against an explicitly isolated PostgreSQL DB."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url

from patient_service.main import create_app
from patient_service.bootstrap_admin import bootstrap_first_admin
from patient_service.models import (
    audit_entries,
    outbox_events,
    patient_profiles,
    refresh_sessions,
    role_assignments,
    users,
)
from patient_service.settings import Settings

TEST_DATABASE_URL = os.environ.get("PULSEGRID_PATIENT_MANAGEMENT_TEST_DB_URL", "")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set PULSEGRID_PATIENT_MANAGEMENT_TEST_DB_URL to an isolated migrated PostgreSQL test DB.",
)


def _write_public_jwk(path: Path, key, kid: str, service: str | None = None):
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    data.update(kid=kid, alg="RS256", use="sig")
    if service:
        data["service"] = service
    return data


@pytest.fixture
def context(tmp_path, monkeypatch):
    url = make_url(TEST_DATABASE_URL)
    if (
        not url.host
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or not url.database
        or not url.database.endswith("_test")
        or not url.username
        or not url.password
    ):
        pytest.fail(
            "Management integration tests require a password-configured loopback database whose name ends in _test."
        )
    prefix = "PULSEGRID_PATIENT_AUTH_"
    user_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    user_jwks = tmp_path / "user-jwks.json"
    user_jwks.write_text(
        json.dumps({"keys": [_write_public_jwk(user_jwks, user_key, "patient-test")]})
    )
    service_keys = {}
    service_jwks_items = []
    for service in ("appointment", "doctor", "records", "emergency", "billing"):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        service_keys[service] = key
        service_jwks_items.append(
            _write_public_jwk(
                tmp_path / f"{service}-jwks.json",
                key,
                f"{service}-test",
                service,
            )
        )
    service_jwks = tmp_path / "service-jwks.json"
    service_jwks.write_text(json.dumps({"keys": service_jwks_items}))
    monkeypatch.setenv(prefix + "JWKS_PATH", str(user_jwks))
    monkeypatch.setenv(prefix + "SERVICE_JWKS_PATH", str(service_jwks))
    monkeypatch.setenv(prefix + "ORIGINS", "")
    monkeypatch.setenv(prefix + "ALLOW_HTTP", "false")

    settings = Settings(
        db_host=url.host,
        db_port=url.port or 5432,
        db_name=url.database,
        db_user=url.username,
        db_password=url.password,
    )
    app = create_app(settings)
    engine = create_engine(
        settings.database_url,
        connect_args=settings.connection_options,
        hide_parameters=True,
    )
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0004_patient_management_audit"
        )
    client = TestClient(app)
    with client:
        yield {
            "client": client,
            "engine": engine,
            "settings": settings,
            "user_key": user_key,
            "service_keys": service_keys,
        }
    engine.dispose()


def _seed_user(context, label: str, roles: list[str], state: str = "active"):
    user_id = secrets.randbelow(2**62) + 1
    patient_id = secrets.randbelow(2**62) + 1
    email = f"synthetic-{uuid4().hex}@example.test"
    with context["engine"].begin() as connection:
        connection.execute(
            insert(users).values(
                id=user_id,
                email_normalized=email,
                password_hash="$argon2id$synthetic-test-hash",
                account_state=state,
            )
        )
        connection.execute(
            insert(patient_profiles).values(
                id=patient_id,
                user_id=user_id,
                display_name=label,
            )
        )
        for role in roles:
            connection.execute(
                insert(role_assignments).values(
                    id=secrets.randbelow(2**62) + 1,
                    user_id=user_id,
                    role=role,
                )
            )
    return {
        "id": user_id,
        "patient_id": patient_id,
        "email": email,
        "name": label,
        "roles": roles,
        "state": state,
        "version": 1,
        "auth_version": 1,
    }


def _user_token(context, account, *, roles=None, auth_version=None):
    current = int(time.time())
    claims = {
        "iss": "pulsegrid-patient",
        "aud": "pulsegrid-api",
        "sub": str(account["id"]),
        "jti": secrets.token_urlsafe(20),
        "iat": current,
        "nbf": current,
        "exp": current + 300,
        "token_use": "access",
        "roles": account["roles"] if roles is None else roles,
        "auth_version": account["auth_version"] if auth_version is None else auth_version,
        "patient_id": str(account["patient_id"]),
    }
    return jwt.encode(claims, context["user_key"], algorithm="RS256", headers={"kid": "patient-test"})


def _service_token(context, caller: str, scope: str):
    current = int(time.time())
    return jwt.encode(
        {
            "iss": f"pulsegrid-service:{caller}",
            "aud": "pulsegrid-internal:patient",
            "sub": caller,
            "jti": secrets.token_urlsafe(20),
            "iat": current,
            "nbf": current,
            "exp": current + 60,
            "token_use": "service",
            "scopes": [scope],
        },
        context["service_keys"][caller],
        algorithm="RS256",
        headers={"kid": f"{caller}-test"},
    )


def _user_headers(context, account, **kwargs):
    return {"Authorization": "Bearer " + _user_token(context, account, **kwargs)}


def _service_headers(context, caller, scope, delegated):
    return {
        "Authorization": "Bearer " + _service_token(context, caller, scope),
        "X-Delegated-Authorization": "Bearer " + _user_token(context, delegated),
    }


def test_first_admin_bootstrap_is_explicit_and_transactional(context):
    with context["engine"].begin() as connection:
        connection.execute(
            text("DELETE FROM role_assignments WHERE role='hospital_admin'")
        )
    account = _seed_user(context, "Synthetic Bootstrap", ["patient"])
    with context["engine"].begin() as connection:
        current = datetime.now(timezone.utc)
        connection.execute(
            insert(refresh_sessions).values(
                id=secrets.randbelow(2**62) + 1,
                user_id=account["id"],
                family_id=secrets.randbelow(2**62) + 1,
                token_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
                expires_at=current + timedelta(days=1),
                family_expires_at=current + timedelta(days=7),
            )
        )

    bootstrap_first_admin(account["email"], context["settings"])
    with context["engine"].connect() as connection:
        stored = connection.execute(
            select(users).where(users.c.id == account["id"])
        ).mappings().one()
        assert stored["version"] == 2
        assert stored["auth_version"] == 2
        assert "hospital_admin" in connection.scalars(
            select(role_assignments.c.role).where(
                role_assignments.c.user_id == account["id"]
            )
        ).all()
        session = connection.execute(
            select(refresh_sessions).where(
                refresh_sessions.c.user_id == account["id"]
            )
        ).mappings().one()
        assert session["revoked_at"] is not None
        assert connection.scalar(
            select(outbox_events.c.event_id).where(
                outbox_events.c.aggregate_id == account["id"],
                outbox_events.c.event_type == "patient.user.bootstrapped.v1",
            )
        ) is not None
    with pytest.raises(ValueError, match="active hospital administrator"):
        bootstrap_first_admin(account["email"], context["settings"])


def test_self_profile_round_trip_validation_and_atomic_database_effects(context):
    patient = _seed_user(context, "Synthetic Self", ["patient"])
    headers = _user_headers(context, patient)
    client = context["client"]

    original = client.get("/api/v1/patients/me", headers=headers)
    assert original.status_code == 200
    assert original.headers["etag"] == '"1"'
    assert original.json() == {
        "id": str(patient["patient_id"]),
        "user_id": str(patient["id"]),
        "display_name": patient["name"],
        "version": 1,
    }

    changed = client.patch(
        "/api/v1/patients/me",
        headers={**headers, "If-Match": '"1"'},
        json={
            "display_name": "  Updated Synthetic Patient  ",
            "date_of_birth": "2001-02-03",
            "synthetic_contact": "synthetic-contact-02",
        },
    )
    assert changed.status_code == 200
    assert changed.headers["etag"] == '"2"'
    assert changed.json() == {
        "id": str(patient["patient_id"]),
        "user_id": str(patient["id"]),
        "display_name": "Updated Synthetic Patient",
        "version": 2,
        "date_of_birth": "2001-02-03",
        "synthetic_contact": "synthetic-contact-02",
    }
    assert client.patch(
        "/api/v1/patients/me",
        headers={**headers, "If-Match": '"1"'},
        json={"display_name": "Stale write"},
    ).status_code == 412
    assert client.patch(
        "/api/v1/patients/me", headers=headers, json={"display_name": "Missing ETag"}
    ).status_code == 428
    assert client.patch(
        "/api/v1/patients/me",
        headers={**headers, "If-Match": 'W/"2"'},
        json={"display_name": "Bad ETag"},
    ).status_code == 400
    assert client.patch(
        "/api/v1/patients/me",
        headers={**headers, "If-Match": '"2"'},
        json={"date_of_birth": "2999-01-01"},
    ).status_code == 422
    assert client.patch(
        "/api/v1/patients/me",
        headers={**headers, "If-Match": '"2"'},
        json={"roles": ["hospital_admin"]},
    ).status_code == 422
    assert client.patch(
        "/api/v1/patients/me?unexpected=1",
        headers={**headers, "If-Match": '"2"'},
        json={"display_name": "Unknown query"},
    ).status_code == 422

    with context["engine"].connect() as connection:
        stored = connection.execute(
            select(patient_profiles).where(patient_profiles.c.id == patient["patient_id"])
        ).mappings().one()
        assert stored["display_name"] == "Updated Synthetic Patient"
        assert stored["version"] == 2
        assert connection.scalar(
            select(outbox_events.c.event_id).where(
                outbox_events.c.aggregate_id == patient["patient_id"],
                outbox_events.c.event_type == "patient.profile.updated.v1",
            )
        ) is not None
        assert connection.scalar(
            select(audit_entries.c.sequence).where(
                audit_entries.c.chain_id == "patient",
                audit_entries.c.canonical_metadata["action"].astext
                == "patient.profile.updated",
            )
        ) is not None


def test_profile_authorization_and_filtered_keyset_pagination(context):
    receptionist = _seed_user(context, "Synthetic Receptionist", ["receptionist"])
    group = "Casey " + uuid4().hex[:10]
    patient = _seed_user(context, group + " Synthetic 01", ["patient"])
    second = _seed_user(context, group + " Synthetic 02", ["patient"])
    third = _seed_user(context, group + " Synthetic 03", ["patient"])
    client = context["client"]
    reception_headers = _user_headers(context, receptionist)

    first_page = client.get(
        f"/api/v1/patients?q=  {group.upper()}  &limit=2", headers=reception_headers
    )
    assert first_page.status_code == 200
    assert first_page.headers["cache-control"] == "no-store"
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["next_cursor"]
    second_page = client.get(
        "/api/v1/patients",
        params={"q": group.casefold(), "limit": "2", "cursor": first_page.json()["next_cursor"]},
        headers=reception_headers,
    )
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1
    returned_ids = [item["id"] for item in first_page.json()["items"] + second_page.json()["items"]]
    assert set(returned_ids) == {
        str(patient["patient_id"]),
        str(second["patient_id"]),
        str(third["patient_id"]),
    }
    changed_filter = client.get(
        "/api/v1/patients",
        params={
            "q": group + " different",
            "limit": "2",
            "cursor": first_page.json()["next_cursor"],
        },
        headers=reception_headers,
    )
    assert changed_filter.status_code == 400
    assert client.get(
        "/api/v1/patients?offset=1", headers=reception_headers
    ).status_code == 422
    assert client.get(
        "/api/v1/patients?limit=101", headers=reception_headers
    ).status_code == 422
    assert client.get(
        f"/api/v1/patients/{second['patient_id']}",
        headers=_user_headers(context, patient),
    ).status_code == 404
    assert client.get("/api/v1/patients", headers=_user_headers(context, patient)).status_code == 403
    assert client.get(
        f"/api/v1/patients/{second['patient_id']}", headers=reception_headers
    ).headers["etag"] == '"1"'

    updated = client.patch(
        f"/api/v1/patients/{third['patient_id']}",
        headers={**reception_headers, "If-Match": '"1"'},
        json={"display_name": "Updated by Reception"},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Updated by Reception"


def test_admin_role_state_updates_revoke_sessions_and_preserve_admin_access(context):
    admin = _seed_user(context, "Synthetic Admin", ["patient", "hospital_admin"])
    user_group = "Synthetic Staff " + uuid4().hex[:10]
    target = _seed_user(context, user_group + " Target", ["patient"])
    with context["engine"].begin() as connection:
        current = datetime.now(timezone.utc)
        connection.execute(
            insert(refresh_sessions).values(
                id=secrets.randbelow(2**62) + 1,
                user_id=target["id"],
                family_id=secrets.randbelow(2**62) + 1,
                token_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
                expires_at=current + timedelta(days=1),
                family_expires_at=current + timedelta(days=7),
            )
        )

    client = context["client"]
    admin_headers = _user_headers(context, admin)
    listed = client.get(
        "/api/v1/patients/users",
        params={"q": user_group, "role": "patient", "state": "active", "limit": "10"},
        headers=admin_headers,
    )
    assert listed.status_code == 200
    assert any(item["id"] == str(target["id"]) for item in listed.json()["items"])
    other_target = _seed_user(context, user_group + " Other", ["patient"])
    first_user_page = client.get(
        "/api/v1/patients/users",
        params={"q": user_group, "role": "patient", "limit": "1"},
        headers=admin_headers,
    )
    assert first_user_page.status_code == 200
    assert len(first_user_page.json()["items"]) == 1
    assert first_user_page.json()["next_cursor"]
    next_user_page = client.get(
        "/api/v1/patients/users",
        params={
            "q": user_group.casefold(),
            "role": "patient",
            "limit": "1",
            "cursor": first_user_page.json()["next_cursor"],
        },
        headers=admin_headers,
    )
    assert next_user_page.status_code == 200
    assert len(next_user_page.json()["items"]) == 1
    assert first_user_page.json()["items"][0]["id"] != next_user_page.json()["items"][0]["id"]
    assert other_target["id"] in {
        int(first_user_page.json()["items"][0]["id"]),
        int(next_user_page.json()["items"][0]["id"]),
    }
    details = client.get(
        f"/api/v1/patients/users/{target['id']}", headers=admin_headers
    )
    assert details.status_code == 200
    assert details.headers["etag"] == '"1"'

    roles_changed = client.patch(
        f"/api/v1/patients/users/{target['id']}/roles",
        headers={**admin_headers, "If-Match": '"1"'},
        json={"roles": ["patient", "doctor"]},
    )
    assert roles_changed.status_code == 200
    assert roles_changed.headers["etag"] == '"2"'
    assert roles_changed.json()["roles"] == ["doctor", "patient"]
    assert roles_changed.json()["auth_version"] == 2
    assert client.get(
        f"/api/v1/patients/{target['patient_id']}",
        headers=_user_headers(context, target),
    ).status_code == 403

    state_changed = client.patch(
        f"/api/v1/patients/users/{target['id']}/account-state",
        headers={**admin_headers, "If-Match": '"2"'},
        json={"state": "disabled", "reason": "synthetic fixture deactivation"},
    )
    assert state_changed.status_code == 200
    assert state_changed.json()["state"] == "disabled"
    assert state_changed.json()["version"] == 3
    assert state_changed.json()["auth_version"] == 3
    assert client.patch(
        f"/api/v1/patients/users/{admin['id']}/roles",
        headers={**admin_headers, "If-Match": '"1"'},
        json={"roles": ["patient"]},
    ).json()["error"]["code"] == "last_admin"
    assert client.patch(
        f"/api/v1/patients/users/{admin['id']}/account-state",
        headers={**admin_headers, "If-Match": '"1"'},
        json={"state": "disabled", "reason": "synthetic test"},
    ).json()["error"]["code"] == "last_admin"

    with context["engine"].connect() as connection:
        stored = connection.execute(
            select(users).where(users.c.id == target["id"])
        ).mappings().one()
        assert stored["version"] == 3
        assert stored["auth_version"] == 3
        assert stored["account_state"] == "disabled"
        session = connection.execute(
            select(refresh_sessions).where(refresh_sessions.c.user_id == target["id"])
        ).mappings().one()
        assert session["revoked_at"] is not None
        assert connection.scalar(
            select(outbox_events.c.event_id).where(
                outbox_events.c.aggregate_id == target["id"],
                outbox_events.c.event_type == "patient.user.roles_changed.v1",
            )
        ) is not None
        assert connection.scalar(
            select(outbox_events.c.event_id).where(
                outbox_events.c.aggregate_id == target["id"],
                outbox_events.c.event_type == "patient.user.account_state_changed.v1",
            )
        ) is not None
        reasons = connection.execute(
            text(
                "SELECT canonical_metadata::text FROM audit_entries "
                "WHERE chain_id='patient' AND canonical_metadata->>'action'="
                "'patient.user.account_state_changed' AND "
                "canonical_metadata->>'resource_user_id'=:user_id"
            ),
            {"user_id": str(target["id"])},
        ).scalar_one()
        assert "synthetic fixture deactivation" not in reasons


def test_administration_lock_prevents_concurrent_removal_of_both_admins(context):
    with context["engine"].begin() as connection:
        connection.execute(
            text("DELETE FROM role_assignments WHERE role='hospital_admin'")
        )
    first = _seed_user(context, "Synthetic Admin Race A", ["patient", "hospital_admin"])
    second = _seed_user(context, "Synthetic Admin Race B", ["patient", "hospital_admin"])
    client = context["client"]

    def remove(actor, target):
        return client.patch(
            f"/api/v1/patients/users/{target['id']}/roles",
            headers={**_user_headers(context, actor), "If-Match": '"1"'},
            json={"roles": ["patient"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda pair: remove(*pair),
                ((first, second), (second, first)),
            )
        )
    assert sorted(response.status_code for response in results) == [200, 403]
    with context["engine"].connect() as connection:
        active_admins = connection.scalar(
            text(
                "SELECT count(*) FROM users u JOIN role_assignments r "
                "ON r.user_id=u.id WHERE u.account_state='active' "
                "AND r.role='hospital_admin' AND u.id IN (:first_id,:second_id)"
            ),
            {"first_id": first["id"], "second_id": second["id"]},
        )
        assert active_admins == 1


def test_private_status_leaves_require_service_scope_and_delegated_authority(context):
    admin = _seed_user(context, "Synthetic Private Admin", ["patient", "hospital_admin"])
    receptionist = _seed_user(context, "Synthetic Private Reception", ["receptionist"])
    patient = _seed_user(context, "Synthetic Private Patient", ["patient"])
    client = context["client"]

    status = client.get(
        f"/internal/v1/patients/{patient['patient_id']}/status",
        headers=_service_headers(context, "records", "patients:status", receptionist),
    )
    assert status.status_code == 200
    assert status.json() == {
        "patient_id": str(patient["patient_id"]),
        "active": True,
        "version": 1,
    }
    assert status.headers["etag"] == '"1"'
    assert client.get(
        f"/internal/v1/patients/{patient['patient_id']}/status",
        headers=_service_headers(context, "billing", "patients:status", receptionist),
    ).status_code == 403

    staff = client.get(
        f"/internal/v1/users/{patient['id']}/staff-status",
        headers=_service_headers(context, "doctor", "users:staff-status", admin),
    )
    assert staff.status_code == 200
    assert staff.json() == {
        "user_id": str(patient["id"]),
        "active": True,
        "roles": ["patient"],
        "version": 1,
    }
    self_status = client.get(
        f"/internal/v1/users/{patient['id']}/staff-status",
        headers=_service_headers(context, "records", "users:staff-status", patient),
    )
    assert self_status.status_code == 200
    assert client.get(
        f"/internal/v1/users/{admin['id']}/staff-status",
        headers=_service_headers(context, "records", "users:staff-status", patient),
    ).status_code == 403
    invalid = client.get(
        "/internal/v1/patients/9223372036854775807/status",
        headers=_service_headers(context, "appointment", "patients:status", receptionist),
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_reference"
