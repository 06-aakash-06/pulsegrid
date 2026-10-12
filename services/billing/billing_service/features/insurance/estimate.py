"""Integer-only, non-authoritative insurance estimate calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .contracts import (
    MAX_SAFE_INTEGER,
    InsuranceValidationError,
    PolicyRule,
    ValidatedPolicyExport,
    canonical_time,
    export_validated_policy,
    validate,
    validate_id,
)


@dataclass(frozen=True, slots=True)
class EstimateCalculation:
    eligible_minor: int
    estimate_minor: int
    calculated_at: str


def _safe_minor(value: Any, field: str) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SAFE_INTEGER:
        raise InsuranceValidationError("invalid_invoice_snapshot", f"{field} is outside the safe integer range.")
    return value


def calculate_estimate(
    invoice_snapshot: Mapping[str, Any], rule: PolicyRule, now: datetime
) -> EstimateCalculation:
    """Calculate exact eligible and benefit amounts from a Billing snapshot."""
    normalized = validate(rule)
    if not isinstance(invoice_snapshot, Mapping):
        raise InsuranceValidationError("invalid_invoice_snapshot")
    if set(invoice_snapshot) != {"id", "version", "balance_minor", "items"}:
        raise InsuranceValidationError("invalid_invoice_snapshot")
    validate_id(invoice_snapshot["id"], name="invoice_id")
    version = invoice_snapshot["version"]
    if type(version) is not int or not 1 <= version <= MAX_SAFE_INTEGER:
        raise InsuranceValidationError("invalid_invoice_snapshot")
    balance_minor = _safe_minor(invoice_snapshot["balance_minor"], "balance_minor")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise InsuranceValidationError("invalid_estimate_time")
    calculated_at = now.astimezone(timezone.utc)
    starts = datetime.fromisoformat(normalized.effective_from.replace("Z", "+00:00"))
    ends = datetime.fromisoformat(normalized.effective_to.replace("Z", "+00:00"))
    if not starts <= calculated_at < ends:
        raise InsuranceValidationError("insurance_rule_not_effective")

    items = invoice_snapshot["items"]
    if not isinstance(items, (list, tuple)):
        raise InsuranceValidationError("invalid_invoice_snapshot")
    covered = set(normalized.covered_charge_codes)
    eligible_minor = 0
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {"charge_code", "amount_minor"}:
            raise InsuranceValidationError("invalid_invoice_snapshot")
        charge_code = item["charge_code"]
        if not isinstance(charge_code, str):
            raise InsuranceValidationError("invalid_invoice_snapshot")
        amount_minor = _safe_minor(item["amount_minor"], "amount_minor")
        if charge_code in covered:
            eligible_minor += amount_minor
            if eligible_minor > MAX_SAFE_INTEGER:
                raise InsuranceValidationError("invoice_amount_overflow")

    after_deductible = max(0, eligible_minor - normalized.deductible_minor)
    percentage_benefit = after_deductible * normalized.coverage_bps // 10_000
    if percentage_benefit > MAX_SAFE_INTEGER:
        raise InsuranceValidationError("estimate_amount_overflow")
    estimate_minor = min(normalized.max_benefit_minor, percentage_benefit, balance_minor)
    return EstimateCalculation(
        eligible_minor=eligible_minor,
        estimate_minor=estimate_minor,
        calculated_at=canonical_time(calculated_at),
    )


def build_estimate_result(
    *,
    estimate_id: Any,
    invoice_snapshot: Mapping[str, Any],
    policy: ValidatedPolicyExport,
    rules_id: Any,
    source_fetched_at: datetime,
    now: datetime,
) -> dict[str, Any]:
    """Build the frozen EstimateResult wire shape from validated stored provenance."""
    if not isinstance(policy, ValidatedPolicyExport):
        raise InsuranceValidationError("unvalidated_policy_export")
    normalized = validate(policy.rule)
    calculation = calculate_estimate(invoice_snapshot, normalized, now)
    if not isinstance(source_fetched_at, datetime) or source_fetched_at.tzinfo is None:
        raise InsuranceValidationError("invalid_source_time")
    freshness = (
        "fresh"
        if now.astimezone(timezone.utc) - source_fetched_at.astimezone(timezone.utc) <= timedelta(hours=24)
        else "stale"
    )
    return {
        "id": validate_id(estimate_id, name="estimate_id"),
        "invoice_id": validate_id(invoice_snapshot["id"], name="invoice_id"),
        "invoice_version": invoice_snapshot["version"],
        "provider_id": policy.provider_id,
        "policy_code": normalized.policy_code,
        "rules_id": validate_id(rules_id, name="rules_id"),
        "rule_revision": normalized.revision,
        "source_run_id": policy.source_run_id,
        "currency": "INR",
        "eligible_minor": calculation.eligible_minor,
        "estimate_minor": calculation.estimate_minor,
        "calculated_at": calculation.calculated_at,
        "freshness_state": freshness,
        "is_simulated": True,
        "version": 1,
    }


def estimate(invoice_snapshot: Mapping[str, Any], rule: PolicyRule, now: datetime) -> dict[str, Any]:
    """Frozen estimate interface returning the complete simulated EstimateResult.

    The Billing adapter adds an internal ``_insurance`` context after reading the
    invoice and accepted rule in its local transaction. No context value is
    accepted from the HTTP request.
    """
    if not isinstance(invoice_snapshot, Mapping) or "_insurance" not in invoice_snapshot:
        raise InsuranceValidationError("estimate_context_required")
    if set(invoice_snapshot) != {"id", "version", "balance_minor", "items", "_insurance"}:
        raise InsuranceValidationError("invalid_invoice_snapshot")
    context = invoice_snapshot["_insurance"]
    required = {
        "estimate_id",
        "provider_id",
        "rules_id",
        "source_run_id",
        "source_id",
        "source_path",
        "source_version",
        "content_hash",
        "observed_at",
        "source_fetched_at",
    }
    if not isinstance(context, Mapping) or set(context) != required:
        raise InsuranceValidationError("estimate_context_invalid")
    core_snapshot = {key: invoice_snapshot[key] for key in ("id", "version", "balance_minor", "items")}
    if set(core_snapshot) != {"id", "version", "balance_minor", "items"}:
        raise InsuranceValidationError("invalid_invoice_snapshot")
    policy_export = export_validated_policy(
        provider_id=context["provider_id"],
        source_id=context["source_id"],
        source_path=context["source_path"],
        source_run_id=context["source_run_id"],
        source_version=context["source_version"],
        content_hash=context["content_hash"],
        observed_at=context["observed_at"],
        rule=rule,
    )
    source_fetched_at = context["source_fetched_at"]
    if isinstance(source_fetched_at, str):
        try:
            source_fetched_at = datetime.fromisoformat(
                source_fetched_at[:-1] + "+00:00" if source_fetched_at.endswith("Z") else source_fetched_at
            )
        except ValueError as exc:
            raise InsuranceValidationError("invalid_source_time") from exc
    return build_estimate_result(
        estimate_id=context["estimate_id"],
        invoice_snapshot=core_snapshot,
        policy=policy_export,
        rules_id=context["rules_id"],
        source_fetched_at=source_fetched_at,
        now=now,
    )
