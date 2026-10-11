"""Disposable test-only additions matching the reserved 0006 schema manifest."""

import psycopg
import pytest


@pytest.fixture
def checkin_database(database):
    """Apply the future check-in columns/indexes to this isolated G0 test DB only."""
    with psycopg.connect(
        host=database.db_host,
        port=database.db_port,
        dbname=database.db_name,
        user="appointment_owner",
        password=database.db_password,
    ) as connection:
        connection.execute(
            "ALTER TABLE checkin_links "
            "ADD COLUMN workflow_version BIGINT NOT NULL DEFAULT 1, "
            "ADD COLUMN schedule_fingerprint VARCHAR(64) NOT NULL DEFAULT repeat('0', 64)"
        )
        connection.execute("ALTER TABLE checkin_links ALTER COLUMN workflow_version DROP DEFAULT")
        connection.execute("ALTER TABLE checkin_links ALTER COLUMN schedule_fingerprint DROP DEFAULT")
        connection.execute(
            "ALTER TABLE checkin_links ADD CONSTRAINT ck_checkin_links_check_in_purpose "
            "CHECK (purpose = 'check_in')"
        )
        connection.execute(
            "ALTER TABLE checkin_links ADD CONSTRAINT ck_checkin_links_token_hash_sha256 "
            "CHECK (token_hash ~ '^[0-9a-f]{64}$')"
        )
        connection.execute(
            "ALTER TABLE checkin_links ADD CONSTRAINT ck_checkin_links_workflow_version_safe "
            "CHECK (workflow_version BETWEEN 1 AND 9007199254740991)"
        )
        connection.execute(
            "ALTER TABLE checkin_links ADD CONSTRAINT ck_checkin_links_schedule_fingerprint_sha256 "
            "CHECK (schedule_fingerprint ~ '^[0-9a-f]{64}$')"
        )
        connection.execute(
            "CREATE UNIQUE INDEX uq_checkin_links_live_appointment_purpose "
            "ON checkin_links (appointment_id, purpose) "
            "WHERE consumed_at IS NULL AND revoked_at IS NULL"
        )
    return database
