"""Explicit local bootstrap for the first synthetic hospital administrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import IntegrityError

from .authentication import new_id, now
from .management import ADMIN_LOCK_KEY, MAX_VERSION
from .models import (
    outbox_events,
    patient_profiles,
    refresh_sessions,
    role_assignments,
    users,
)
from .settings import Settings


def normalize_synthetic_email(value: str) -> str:
    try:
        normalized = validate_email(
            value.strip(),
            check_deliverability=False,
            allow_smtputf8=False,
            test_environment=True,
        ).normalized.lower()
    except EmailNotValidError:
        raise ValueError("Enter a valid existing synthetic account email.") from None
    domain = normalized.rsplit("@", 1)[-1]
    if not domain.endswith(".test"):
        raise ValueError("Bootstrap accepts only synthetic .test accounts.")
    return normalized


def _append_audit(connection, *, user_id: int, patient_id: int, request_id: str):
    metadata = {
        "action": "patient.user.bootstrapped",
        "result": "success",
        "actor_type": "local_operator",
        "resource_user_id": str(user_id),
        "patient_id": str(patient_id),
        "request_id": request_id,
        "correlation_id": request_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    for attempt in range(3):
        try:
            with connection.begin_nested():
                connection.execute(
                    text(
                        "SELECT public.patient_append_audit(:entry_id, "
                        "CAST(:metadata AS jsonb))"
                    ),
                    {
                        "entry_id": new_id(),
                        "metadata": json.dumps(
                            metadata, sort_keys=True, separators=(",", ":")
                        ),
                    },
                )
            return
        except IntegrityError as error:
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", "")
            if constraint != "uq_audit_entries_entry_id" or attempt == 2:
                raise
    raise RuntimeError("Could not allocate a Patient audit identifier.")


def _append_outbox(
    connection, *, user_id: int, version: int, request_id: str
):
    event_type = "patient.user.bootstrapped.v1"
    for _attempt in range(3):
        event_id = new_id()
        occurred_at = now().isoformat()
        envelope = {
            "event_id": str(event_id),
            "event_type": event_type,
            "schema_version": 1,
            "producer": "patient",
            "occurred_at": occurred_at,
            "aggregate_type": "user",
            "aggregate_id": str(user_id),
            "aggregate_version": version,
            "request_id": request_id,
            "correlation_id": request_id,
            "causation_id": None,
            "traceparent": None,
            "payload": {
                "resource_id": str(user_id),
                "version": version,
                "state": "active",
            },
        }
        result = connection.execute(
            postgres_insert(outbox_events)
            .values(
                event_id=event_id,
                aggregate_type="user",
                aggregate_id=user_id,
                aggregate_version=version,
                event_type=event_type,
                envelope=envelope,
            )
            .on_conflict_do_nothing(index_elements=[outbox_events.c.event_id])
            .returning(outbox_events.c.event_id)
        )
        if result.scalar_one_or_none() is not None:
            return
    raise RuntimeError("Could not allocate a Patient outbox identifier.")


def bootstrap_first_admin(email: str, settings: Settings) -> None:
    email = normalize_synthetic_email(email)
    if settings.environment not in {"development", "test"}:
        raise ValueError("First-admin bootstrap is available only in local environments.")
    if settings.db_host not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("First-admin bootstrap requires a loopback database host.")
    if not settings.database_configured:
        raise ValueError("Patient database settings are incomplete.")

    engine = create_engine(
        settings.database_url,
        connect_args=settings.connection_options,
        hide_parameters=True,
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMIN_LOCK_KEY}
            )
            active_admins = connection.scalar(
                select(func.count())
                .select_from(
                    users.join(
                        role_assignments, role_assignments.c.user_id == users.c.id
                    )
                )
                .where(
                    users.c.account_state == "active",
                    role_assignments.c.role == "hospital_admin",
                )
            )
            if active_admins:
                raise ValueError("An active hospital administrator already exists.")

            user = (
                connection.execute(
                    select(users)
                    .where(users.c.email_normalized == email)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if user is None:
                raise ValueError(
                    "The synthetic account does not exist; register it first."
                )
            if user["account_state"] != "active":
                raise ValueError("The synthetic account must be active.")
            if user["version"] >= MAX_VERSION or user["auth_version"] >= MAX_VERSION:
                raise ValueError("The account version cannot be incremented safely.")
            profile = (
                connection.execute(
                    select(patient_profiles).where(
                        patient_profiles.c.user_id == user["id"]
                    )
                )
                .mappings()
                .first()
            )
            roles = set(
                connection.scalars(
                    select(role_assignments.c.role).where(
                        role_assignments.c.user_id == user["id"]
                    )
                ).all()
            )
            if profile is None or "patient" not in roles:
                raise ValueError(
                    "Bootstrap requires an active registered patient account."
                )
            if "hospital_admin" in roles:
                raise ValueError("This account already has administrator access.")

            version = user["version"] + 1
            for attempt in range(3):
                inserted = connection.execute(
                    postgres_insert(role_assignments)
                    .values(id=new_id(), user_id=user["id"], role="hospital_admin")
                    .on_conflict_do_nothing(index_elements=[role_assignments.c.id])
                    .returning(role_assignments.c.id)
                )
                if inserted.scalar_one_or_none() is not None:
                    break
            else:
                raise RuntimeError("Could not allocate a Patient role identifier.")
            connection.execute(
                update(users)
                .where(users.c.id == user["id"])
                .values(
                    version=version,
                    auth_version=user["auth_version"] + 1,
                    updated_at=now(),
                )
            )
            connection.execute(
                update(refresh_sessions)
                .where(
                    refresh_sessions.c.user_id == user["id"],
                    refresh_sessions.c.revoked_at.is_(None),
                )
                .values(revoked_at=now(), updated_at=now())
            )
            request_id = str(uuid4())
            _append_audit(
                connection,
                user_id=user["id"],
                patient_id=profile["id"],
                request_id=request_id,
            )
            _append_outbox(
                connection,
                user_id=user["id"],
                version=version,
                request_id=request_id,
            )
    finally:
        engine.dispose()


def main() -> None:
    settings = Settings.from_env()
    try:
        email = normalize_synthetic_email(input("Existing synthetic account email: "))
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print(f"Grant the first hospital_admin role to {email}?")
    if input("Type yes to continue: ").strip().casefold() != "yes":
        raise SystemExit("Bootstrap cancelled.")
    try:
        bootstrap_first_admin(email, settings)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    print("First hospital administrator bootstrapped. Sign in again to refresh authority.")


if __name__ == "__main__":
    main()
