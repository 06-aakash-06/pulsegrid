"""Frozen Phase 4 insurance wire values and validation helpers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_ID = 9_223_372_036_854_775_807
_POLICY_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)
_SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_CHARGE_CODE = re.compile(r"medicine:([1-9][0-9]{0,18})\Z", re.ASCII)


class InsuranceValidationError(ValueError):
    """A safe validation failure that can be counted without exposing input."""

    def __init__(self, code: str, message: str = "Insurance data failed validation.") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PolicyRule:
    policy_code: str
    revision: int
    effective_from: str
    effective_to: str
    currency: str
    coverage_bps: int
    deductible_minor: int
    max_benefit_minor: int
    covered_charge_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["covered_charge_codes"] = list(self.covered_charge_codes)
        return result


_RULE_FIELDS = frozenset(
    {
        "policy_code",
        "revision",
        "effective_from",
        "effective_to",
        "currency",
        "coverage_bps",
        "deductible_minor",
        "max_benefit_minor",
        "covered_charge_codes",
    }
)


def _utc_time(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise InsuranceValidationError("invalid_policy_time")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise InsuranceValidationError("invalid_policy_time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise InsuranceValidationError("invalid_policy_time", f"{name} must be UTC RFC 3339.")
    return parsed.astimezone(timezone.utc)


def canonical_time(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise InsuranceValidationError("invalid_policy_time")
    precision = "microseconds" if value.microsecond else "seconds"
    return value.astimezone(timezone.utc).isoformat(timespec=precision).replace("+00:00", "Z")


def validate(rule: PolicyRule | Mapping[str, Any]) -> PolicyRule:
    """Return a canonical rule or reject unknown, unsafe, or out-of-range fields."""
    if isinstance(rule, PolicyRule):
        raw = rule.to_dict()
    elif isinstance(rule, Mapping):
        raw = dict(rule)
    else:
        raise InsuranceValidationError("invalid_policy")
    if set(raw) != _RULE_FIELDS:
        raise InsuranceValidationError("invalid_policy_fields")

    policy_code = raw["policy_code"]
    if not isinstance(policy_code, str) or not _POLICY_CODE.fullmatch(policy_code):
        raise InsuranceValidationError("invalid_policy_code")

    revision = raw["revision"]
    if type(revision) is not int or not 1 <= revision <= MAX_SAFE_INTEGER:
        raise InsuranceValidationError("invalid_policy_revision")

    starts = _utc_time(raw["effective_from"], "effective_from")
    ends = _utc_time(raw["effective_to"], "effective_to")
    if ends <= starts:
        raise InsuranceValidationError("invalid_policy_window")

    if raw["currency"] != "INR":
        raise InsuranceValidationError("invalid_policy_currency")

    coverage_bps = raw["coverage_bps"]
    if type(coverage_bps) is not int or not 0 <= coverage_bps <= 10_000:
        raise InsuranceValidationError("invalid_coverage_bps")

    money: dict[str, int] = {}
    for field in ("deductible_minor", "max_benefit_minor"):
        value = raw[field]
        if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
            raise InsuranceValidationError("invalid_policy_amount")
        money[field] = value

    codes = raw["covered_charge_codes"]
    if not isinstance(codes, (list, tuple)) or len(codes) > 100:
        raise InsuranceValidationError("invalid_covered_charge_codes")
    normalized_codes: list[str] = []
    for code in codes:
        if code == "consultation":
            normalized_codes.append(code)
            continue
        if not isinstance(code, str) or not _CHARGE_CODE.fullmatch(code):
            raise InsuranceValidationError("invalid_covered_charge_code")
        medicine_id = int(code.partition(":")[2])
        if medicine_id > MAX_ID or str(medicine_id) != code.partition(":")[2]:
            raise InsuranceValidationError("invalid_covered_charge_code")
        normalized_codes.append(code)
    if len(set(normalized_codes)) != len(normalized_codes):
        raise InsuranceValidationError("duplicate_covered_charge_code")

    return PolicyRule(
        policy_code=policy_code,
        revision=revision,
        effective_from=canonical_time(starts),
        effective_to=canonical_time(ends),
        currency="INR",
        coverage_bps=coverage_bps,
        deductible_minor=money["deductible_minor"],
        max_benefit_minor=money["max_benefit_minor"],
        covered_charge_codes=tuple(normalized_codes),
    )


def canonical_rule_bytes(rule: PolicyRule | Mapping[str, Any]) -> bytes:
    normalized = validate(rule)
    return json.dumps(
        normalized.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def rule_content_hash(rule: PolicyRule | Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_rule_bytes(rule)).hexdigest()


def validate_id(value: Any, *, name: str = "id") -> str:
    if isinstance(value, int) and type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", value, re.ASCII):
        raise InsuranceValidationError("invalid_id", f"{name} must be a canonical positive decimal ID.")
    if int(value) > MAX_ID:
        raise InsuranceValidationError("invalid_id", f"{name} exceeds signed BIGINT range.")
    return value


def validate_source_id(value: Any) -> str:
    if not isinstance(value, str) or not _SOURCE_ID.fullmatch(value):
        raise InsuranceValidationError("invalid_source_id")
    return value


def _validate_source_path(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or len(value) > 2048
        or "?" in value
        or "#" in value
        or "\\" in value
    ):
        raise InsuranceValidationError("invalid_source_path")
    from urllib.parse import unquote

    decoded = value
    for _ in range(8):
        unescaped = unquote(decoded)
        if unescaped == decoded:
            break
        decoded = unescaped
    if "%" in decoded or "\\" in decoded:
        raise InsuranceValidationError("invalid_source_path")
    if any(segment in {".", ".."} for segment in decoded.split("/")):
        raise InsuranceValidationError("invalid_source_path")
    return value


@dataclass(frozen=True, slots=True)
class ValidatedPolicyExport:
    """Provenance-bearing, validated payload consumed by Billing estimate code."""

    provider_id: str
    source_id: str
    source_path: str
    source_run_id: str
    source_version: int
    content_hash: str
    observed_at: str
    rule: PolicyRule

    def __post_init__(self) -> None:
        validate_id(self.provider_id, name="provider_id")
        validate_source_id(self.source_id)
        _validate_source_path(self.source_path)
        validate_id(self.source_run_id, name="source_run_id")
        if type(self.source_version) is not int or not 1 <= self.source_version <= MAX_SAFE_INTEGER:
            raise InsuranceValidationError("invalid_source_version")
        _utc_time(self.observed_at, "observed_at")
        if not isinstance(self.content_hash, str) or self.content_hash != rule_content_hash(self.rule):
            raise InsuranceValidationError("content_hash_mismatch")

    def to_billing_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "source_id": self.source_id,
            "source_path": self.source_path,
            "source_run_id": self.source_run_id,
            "source_version": self.source_version,
            "content_hash": self.content_hash,
            "observed_at": self.observed_at,
            "rule": self.rule.to_dict(),
        }


def export_validated_policy(
    *,
    provider_id: Any,
    source_id: Any,
    source_path: Any,
    source_run_id: Any,
    source_version: Any,
    content_hash: Any,
    observed_at: Any,
    rule: PolicyRule | Mapping[str, Any],
) -> ValidatedPolicyExport:
    normalized = validate(rule)
    if type(source_version) is not int or not 1 <= source_version <= MAX_SAFE_INTEGER:
        raise InsuranceValidationError("invalid_source_version")
    source_path = _validate_source_path(source_path)
    expected_hash = rule_content_hash(normalized)
    if not isinstance(content_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise InsuranceValidationError("invalid_content_hash")
    # The export hash is over the canonical policy object, never arbitrary page bytes.
    if content_hash != expected_hash:
        raise InsuranceValidationError("content_hash_mismatch")
    observed = _utc_time(observed_at, "observed_at")
    return ValidatedPolicyExport(
        provider_id=validate_id(provider_id, name="provider_id"),
        source_id=validate_source_id(source_id),
        source_path=source_path,
        source_run_id=validate_id(source_run_id, name="source_run_id"),
        source_version=source_version,
        content_hash=content_hash,
        observed_at=canonical_time(observed),
        rule=normalized,
    )
