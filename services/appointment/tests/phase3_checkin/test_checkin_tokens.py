import hashlib

import pytest

from appointment_service import models
from appointment_service.features.checkin import registration


@pytest.mark.parametrize("value", [bytes(16), (1).to_bytes(16, "big"), bytes.fromhex("ff" * 16)])
def test_opaque_token_encoding_is_canonical_128_bit_base62(value):
    token = registration.encode_token(value)
    assert len(token) == 22
    assert registration.canonical_token(token)
    assert registration.token_digest(token) == hashlib.sha256(token.encode("ascii")).hexdigest()


def test_token_parser_rejects_noncanonical_and_out_of_range_values():
    assert not registration.canonical_token("a" * 21)
    assert not registration.canonical_token("z" * 22)
    assert not registration.canonical_token("a" * 21 + "!")
    assert not registration.canonical_token(None)


def test_landing_payload_contains_only_appointment_id_and_opaque_fragment():
    token = registration.encode_token(bytes.fromhex("01" * 16))
    assert registration.landing_path("123", token) == (
        f"/patient/check-in#appointment_id=123&token={token}"
    )
    assert "patient" not in token and "record" not in token


def test_schema_manifest_reuses_the_dormant_owned_table_without_ddl():
    before = dict(models.metadata.tables)
    registration.register_tables(models.metadata)
    manifest = registration.schema_spec()
    assert {"tables", "columns", "indexes", "constraints", "preflight", "runtime_grants"} <= manifest.keys()
    assert manifest["tables"][0]["name"] == "checkin_links"
    assert {column["name"] for column in manifest["columns"]} == {
        "workflow_version",
        "schedule_fingerprint",
    }
    assert models.metadata.tables == before
