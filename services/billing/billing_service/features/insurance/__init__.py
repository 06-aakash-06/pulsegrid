"""Synthetic fixture-only insurance crawler owned by Billing."""

from .contracts import (
    InsuranceValidationError,
    PolicyRule,
    ValidatedPolicyExport,
    export_validated_policy,
    rule_content_hash,
    validate,
)
from .crawler import CrawlError, CrawlOutcome, CrawlSource, crawl
from .estimate import EstimateCalculation, build_estimate_result, calculate_estimate, estimate
from .extractor import ExtractionError, extract, extract_links
from .fetcher import AllowlistedFetcher, FetchError, SourceConfig
from .health import health
from .repository import SQLAlchemyInsuranceRepository
from .schema import register_tables, schema_spec
from .worker import worker_tick

__all__ = [
    "AllowlistedFetcher",
    "CrawlError",
    "CrawlOutcome",
    "CrawlSource",
    "EstimateCalculation",
    "ExtractionError",
    "FetchError",
    "InsuranceValidationError",
    "PolicyRule",
    "SourceConfig",
    "SQLAlchemyInsuranceRepository",
    "ValidatedPolicyExport",
    "build_estimate_result",
    "calculate_estimate",
    "crawl",
    "estimate",
    "export_validated_policy",
    "extract",
    "extract_links",
    "health",
    "register_routes",
    "register_tables",
    "rule_content_hash",
    "schema_spec",
    "validate",
    "worker_tick",
]


def register_routes(app, ports) -> None:
    """Load FastAPI route code only when the coordinator mounts the feature."""
    from .routes import register_routes as mount_routes

    mount_routes(app, ports)
