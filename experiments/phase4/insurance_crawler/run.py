#!/usr/bin/env python3
"""Reproducible synthetic sequential-versus-bounded insurance crawler benchmark."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from billing_service.features.insurance.contracts import rule_content_hash
from billing_service.features.insurance.crawler import CrawlSource, crawl
from billing_service.features.insurance.extractor import ExtractionError, extract
from billing_service.features.insurance.fetcher import AllowlistedFetcher, SourceConfig

ROOT = Path(__file__).resolve().parents[3]
LEVEL_PAGES = {"low": 10, "medium": 100, "high": 300}
CONCURRENCY_LEVELS = (1, 4, 8)
PER_HOST_CONCURRENCY = 2
FIXTURE_HOSTS = tuple(f"insurer-{index}.synthetic.test" for index in range(3))
POLICY_FIELDS = (
    "policy_code",
    "revision",
    "effective_from",
    "effective_to",
    "currency",
    "coverage_bps",
    "deductible_minor",
    "max_benefit_minor",
    "covered_charge_codes",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def policy(*, policy_code: str, revision: int = 1, benefit: int = 125_000, coverage_bps: int = 8000) -> dict[str, Any]:
    return {
        "policy_code": policy_code,
        "revision": revision,
        "effective_from": "2026-01-01T00:00:00Z",
        "effective_to": "2027-01-01T00:00:00Z",
        "currency": "INR",
        "coverage_bps": coverage_bps,
        "deductible_minor": 5_000,
        "max_benefit_minor": benefit,
        "covered_charge_codes": ["consultation", "medicine:101"],
    }


def policy_page(value: dict[str, Any]) -> bytes:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return (
        '<!doctype html><html><body><script type="application/json" '
        'data-pulsegrid-insurance-policy>' + body + "</script></body></html>"
    ).encode("utf-8")


def index_page(paths: list[str]) -> bytes:
    links = "".join(f'<a href="{path}">policy</a>' for path in paths)
    return f"<!doctype html><html><body>{links}</body></html>".encode("utf-8")


@dataclass(frozen=True)
class PageFixture:
    body: bytes
    kind: str
    expected_rule: dict[str, Any] | None
    response_delay: float
    transient_503: bool


@dataclass
class TrialFixture:
    seed: int
    delay_ms: int
    total_pages: int
    provider_ids: tuple[str, ...]
    base_urls: dict[str, str]
    pages: dict[tuple[str, str], PageFixture]
    truth_rules: set[tuple[str, int, str]]
    input_hash: str
    category_counts: dict[str, int]


def generate_fixture(seed: int, total_pages: int, delay_ms: int, port: int) -> TrialFixture:
    """Generate the complete in-memory page set and truth manifest for one trial."""
    if total_pages not in LEVEL_PAGES.values():
        raise ValueError("total_pages must match a frozen benchmark level")
    provider_ids = ("10", "11", "12")
    page_kinds: dict[tuple[str, str], str] = {}
    provider_paths: dict[str, list[str]] = {host: [] for host in FIXTURE_HOSTS}
    base_urls = {
        provider_id: f"http://{host}:{port}/fixtures/{host}/"
        for provider_id, host in zip(provider_ids, FIXTURE_HOSTS)
    }
    page_count = total_pages - len(FIXTURE_HOSTS)
    counts_per_provider = [page_count // 3] * 3
    for index in range(page_count % 3):
        counts_per_provider[index] += 1

    policies_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for provider_index, host in enumerate(FIXTURE_HOSTS):
        provider_id = provider_ids[provider_index]
        for page_index in range(counts_per_provider[provider_index]):
            path = f"/fixtures/{host}/policy/{page_index:03d}.html"
            provider_paths[host].append(path)
            if provider_index == 0 and page_index == 0:
                current = policy(policy_code=f"SHARED-{seed}", benefit=40_000)
                kind = "conflict_original"
            elif provider_index == 0 and page_index == 1:
                current = policy(policy_code=f"SHARED-{seed}", benefit=90_000)
                kind = "conflict_variant"
            else:
                current = policy(
                    policy_code=f"P{seed % 10_000}-{provider_index}-{page_index}",
                    benefit=100_000 + provider_index * 1000 + page_index,
                    coverage_bps=5000 + (page_index % 50) * 100,
                )
                kind = "valid"
            policies_by_key[(host, path)] = current
            # Kind assignment is completed below after exact workload partitions.
            page_kinds[(host, path)] = kind

    all_paths = [(host, path) for host in FIXTURE_HOSTS for path in provider_paths[host]]
    duplicate_count = round(total_pages * 0.10)
    invalid_or_timeout_count = max(1, round(total_pages * 0.05))
    transient_count = max(1, round(total_pages * 0.05))

    safe_sources = [
        key for key in all_paths
        if page_kinds[key] not in {"conflict_original", "conflict_variant"}
    ]
    duplicate_targets = safe_sources[-duplicate_count:] if duplicate_count else []
    duplicate_sources_by_host = {
        host: [key for key in safe_sources if key[0] == host and key not in duplicate_targets]
        for host in FIXTURE_HOSTS
    }
    if any(not duplicate_sources_by_host[target[0]] for target in duplicate_targets):
        raise RuntimeError("fixture generator needs an in-provider source page for each duplicate")
    duplicate_map: dict[tuple[str, str], tuple[str, str]] = {}
    for target in duplicate_targets:
        duplicate_map[target] = duplicate_sources_by_host[target[0]][0]
    duplicate_sources = {source for source in duplicate_map.values()}

    unavailable = set(duplicate_targets)
    candidate_paths = [
        key for key in all_paths
        if key not in unavailable and key not in duplicate_sources and page_kinds[key] == "valid"
    ]
    if len(candidate_paths) < invalid_or_timeout_count + transient_count:
        candidate_paths = [key for key in all_paths if key not in unavailable and key not in duplicate_sources]
    bad_paths = candidate_paths[:invalid_or_timeout_count]
    timeout_count = invalid_or_timeout_count // 2
    timeout_paths = set(bad_paths[:timeout_count])
    invalid_paths = set(bad_paths[timeout_count:])
    unavailable.update(bad_paths)
    transient_candidates = [
        key for key in all_paths
        if key not in unavailable and page_kinds[key] == "valid"
    ]
    transient_paths = set(transient_candidates[:transient_count])

    pages: dict[tuple[str, str], PageFixture] = {}
    truth_rules: set[tuple[str, int, str]] = set()
    category_counts = {name: 0 for name in ("index", "valid", "duplicate", "invalid", "timeout", "transient", "conflict")}
    input_digest = hashlib.sha256()

    for provider_index, host in enumerate(FIXTURE_HOSTS):
        provider_id = provider_ids[provider_index]
        paths = provider_paths[host]
        root_path = f"/fixtures/{host}/"
        root_body = index_page([f"policy/{index:03d}.html" for index in range(len(paths))])
        pages[(host, root_path)] = PageFixture(root_body, "index", None, delay_ms / 1000, False)
        category_counts["index"] += 1
        input_digest.update(host.encode("ascii") + b"\0" + root_path.encode("ascii") + b"\0" + root_body)

    for key in all_paths:
        host, path = key
        original_rule = policies_by_key[key]
        if key in duplicate_map:
            source_key = duplicate_map[key]
            source_rule = policies_by_key[source_key]
            body = policy_page(source_rule)
            fixture = PageFixture(body, "duplicate", source_rule, delay_ms / 1000, False)
            truth_rules.add((source_rule["policy_code"], source_rule["revision"], rule_content_hash(source_rule)))
            category_counts["duplicate"] += 1
        elif key in timeout_paths:
            body = policy_page(original_rule)
            fixture = PageFixture(body, "timeout", original_rule, 1.05, False)
            category_counts["timeout"] += 1
        elif key in invalid_paths:
            invalid_rule = dict(original_rule)
            invalid_rule["coverage_bps"] = 10_001
            body = policy_page(invalid_rule)
            fixture = PageFixture(body, "invalid", None, delay_ms / 1000, False)
            category_counts["invalid"] += 1
        elif page_kinds[key] == "conflict_original":
            body = policy_page(original_rule)
            fixture = PageFixture(body, "conflict", original_rule, delay_ms / 1000, False)
            category_counts["conflict"] += 1
        elif page_kinds[key] == "conflict_variant":
            body = policy_page(original_rule)
            fixture = PageFixture(body, "conflict", original_rule, delay_ms / 1000, False)
            # Same policy revision, different content: it must be quarantined.
            category_counts["conflict"] += 1
        else:
            body = policy_page(original_rule)
            is_transient = key in transient_paths
            fixture = PageFixture(body, "transient" if is_transient else "valid", original_rule, delay_ms / 1000, is_transient)
            truth_rules.add((original_rule["policy_code"], original_rule["revision"], rule_content_hash(original_rule)))
            category_counts["transient" if is_transient else "valid"] += 1
        pages[key] = fixture
        input_digest.update(host.encode("ascii") + b"\0" + path.encode("ascii") + b"\0" + body)

    if sum(category_counts.values()) != total_pages:
        raise RuntimeError(f"fixture page partition mismatch: {category_counts}")
    for provider_index, host in enumerate(FIXTURE_HOSTS):
        if 1 + len(provider_paths[host]) > 100:
            raise RuntimeError("fixture exceeds the frozen per-provider page cap")
    return TrialFixture(
        seed=seed,
        delay_ms=delay_ms,
        total_pages=total_pages,
        provider_ids=provider_ids,
        base_urls=base_urls,
        pages=pages,
        truth_rules=truth_rules,
        input_hash=input_digest.hexdigest(),
        category_counts=category_counts,
    )


class SyntheticHTTPFixture:
    def __init__(self, fixture: TrialFixture, base_delay_ms: int) -> None:
        self.fixture = fixture
        self.base_delay_ms = base_delay_ms
        self.server: asyncio.AbstractServer | None = None
        self.port: int | None = None
        self.attempts: dict[tuple[str, str], int] = {}
        self.success_bodies: dict[tuple[str, str], bytes] = {}

    async def start(self) -> "SyntheticHTTPFixture":
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = int(self.server.sockets[0].getsockname()[1])
        return self

    async def close(self) -> None:
        assert self.server is not None
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
            lines = request_headers.decode("latin1").split("\r\n")
            path = lines[0].split(" ")[1]
            authority = next(line.split(":", 1)[1].strip() for line in lines[1:] if line.lower().startswith("host:"))
            host = authority.rsplit(":", 1)[0].strip("[]").lower()
            key = (host, path)
            page = self.fixture.pages.get(key)
            if page is None:
                status, headers, body, delay = 404, {}, b"not found", self.base_delay_ms / 1000
            else:
                attempt = self.attempts.get(key, 0) + 1
                self.attempts[key] = attempt
                if page.transient_503 and attempt == 1:
                    status, headers, body, delay = 503, {"Retry-After": "0"}, b"busy", self.base_delay_ms / 1000
                else:
                    status, headers, body, delay = 200, {}, page.body, page.response_delay
            if delay:
                await asyncio.sleep(delay)
            reason = {200: "OK", 302: "Found", 404: "Not Found", 503: "Unavailable"}.get(status, "Error")
            response_headers = {
                "Content-Type": "text/html",
                "Content-Length": str(len(body)),
                "Connection": "close",
                **headers,
            }
            wire = f"HTTP/1.1 {status} {reason}\r\n" + "".join(f"{name}: {value}\r\n" for name, value in response_headers.items()) + "\r\n"
            writer.write(wire.encode("latin1") + body)
            await writer.drain()
            if page is not None and status == 200:
                self.success_bodies[key] = body
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


class MemoryRepository:
    """Disposable benchmark sink modeling source versions and immutable rule writes."""

    def __init__(self, fixture: TrialFixture, port: int) -> None:
        self.fixture = fixture
        self.port = port
        self.runs = 0
        self.source_versions: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.accepted: dict[tuple[str, int], str] = {}

    async def begin_run(self, provider_id: str):
        self.runs += 1
        return {"id": str(50_000 + self.runs), "provider_id": provider_id}

    async def get_provider(self, provider_id: str):
        if provider_id not in self.fixture.provider_ids:
            return None
        index = self.fixture.provider_ids.index(provider_id)
        host = FIXTURE_HOSTS[index]
        return {
            "id": provider_id,
            "synthetic_slug": f"synthetic-insurer-{index}",
            "allowlisted_url": f"http://{host}:{self.port}/fixtures/{host}/",
        }

    async def list_sources(self, provider_id: str):
        index = self.fixture.provider_ids.index(provider_id)
        host = FIXTURE_HOSTS[index]
        return (CrawlSource(f"fixture-provider-{index}", f"/fixtures/{host}/"),)

    async def read_source_version(self, provider_id: str, source_id: str, path: str):
        return self.source_versions.get((provider_id, source_id, path))

    async def commit_run(self, run_id, fencing_version, outcome, policies, observations):
        accepted = 0
        duplicates = 0
        quarantined = 0
        changed = 0
        for observation in observations:
            key = (outcome.provider_id, observation.source_id, observation.path)
            previous = self.source_versions.get(key)
            if previous is not None and previous["content_hash"] != observation.content_hash:
                changed += 1
            self.source_versions[key] = {
                "source_version": observation.source_version,
                "content_hash": observation.content_hash,
            }
        for policy_export in policies:
            key = (policy_export.rule.policy_code, policy_export.rule.revision)
            previous_hash = self.accepted.get(key)
            if previous_hash is None:
                self.accepted[key] = policy_export.content_hash
                accepted += 1
            elif previous_hash == policy_export.content_hash:
                duplicates += 1
            else:
                quarantined += 1
        return {
            "lease_owned": True,
            "state": "partial" if quarantined else outcome.state,
            "policies_accepted": accepted,
            "policies_deduplicated": duplicates,
            "policies_quarantined": quarantined,
            "changed_pages": changed,
            "error_code": "source_revision_conflict" if quarantined else outcome.error_code,
        }


class MetricObserver:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    def increment(self, name: str, labels: dict[str, str], value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def observe(self, name: str, seconds: float, labels: dict[str, str]) -> None:
        pass

    def gauge(self, name: str, value: float, labels: dict[str, str]) -> None:
        pass


async def run_trial(seed: int, total_pages: int, delay_ms: int, concurrency: int) -> dict[str, Any]:
    empty_fixture = TrialFixture(seed, delay_ms, total_pages, ("10", "11", "12"), {}, {}, set(), "", {})
    server = SyntheticHTTPFixture(empty_fixture, delay_ms)
    await server.start()
    assert server.port is not None
    fixture = generate_fixture(seed, total_pages, delay_ms, server.port)
    server.fixture = fixture
    repository = MemoryRepository(fixture, server.port)
    sources = []
    for index, provider_id in enumerate(fixture.provider_ids):
        host = FIXTURE_HOSTS[index]
        sources.append(
            SourceConfig(
                provider_id=provider_id,
                source_id=f"fixture-provider-{index}",
                base_url=fixture.base_urls[provider_id],
                allowed_ips=frozenset({"127.0.0.1"}),
            )
        )
    observer = MetricObserver()
    fetcher = AllowlistedFetcher(
        sources,
        observer=observer,
        concurrency=concurrency,
        per_host_concurrency=PER_HOST_CONCURRENCY,
        resolver=lambda _host, _port: asyncio.sleep(0, result=("127.0.0.1",)),
        jitter=lambda: 0.1,
    )
    try:
        started_ns = time.perf_counter_ns()
        if concurrency == 1:
            outcomes = []
            for provider_id in fixture.provider_ids:
                outcomes.append(await crawl(provider_id, fetcher, repository, observer))
        else:
            outcomes = await asyncio.gather(*(
                crawl(provider_id, fetcher, repository, observer)
                for provider_id in fixture.provider_ids
            ))
        duration = (time.perf_counter_ns() - started_ns) / 1_000_000_000
        processed = sum(outcome.pages_processed for outcome in outcomes)
        failed = sum(outcome.pages_failed for outcome in outcomes)
        duplicates = sum(outcome.pages_deduplicated for outcome in outcomes)
        attempted_unique = processed + failed
        retried_pages = sum(outcome.retried_pages for outcome in outcomes)
        retry_count = observer.counters.get("pulsegrid_crawler_retries_total", 0)
        attempts_total = sum(server.attempts.values())

        expected_fields = 0
        correct_fields = 0
        extracted_policy_pages = 0
        invalid_correctly_rejected = 0
        invalid_total = 0
        observed_pages = set()
        for provider_id, _source_id, path in repository.source_versions:
            provider_index = fixture.provider_ids.index(provider_id)
            observed_pages.add((FIXTURE_HOSTS[provider_index], path))
        for host, path in observed_pages:
            fixture_page = fixture.pages.get((host, path))
            if fixture_page is None or fixture_page.kind == "index":
                continue
            body = fixture_page.body
            if fixture_page.kind == "invalid":
                invalid_total += 1
                try:
                    extract(body, f"fixture-{host}")
                except ExtractionError:
                    invalid_correctly_rejected += 1
                continue
            if fixture_page.expected_rule is None:
                continue
            expected_fields += len(POLICY_FIELDS)
            try:
                parsed = extract(body, f"fixture-{host}")
            except ExtractionError:
                continue
            if parsed:
                extracted_policy_pages += 1
            actual = parsed[0].to_dict() if parsed else {}
            for field in POLICY_FIELDS:
                if actual.get(field) == fixture_page.expected_rule[field]:
                    correct_fields += 1

        expected_rules = fixture.truth_rules
        actual_rules = {
            (policy_code, revision, content_hash)
            for (policy_code, revision), content_hash in repository.accepted.items()
        }
        true_positive = len(expected_rules & actual_rules)
        precision = true_positive / len(actual_rules) if actual_rules else None
        recall = true_positive / len(expected_rules) if expected_rules else None
        field_accuracy = correct_fields / expected_fields if expected_fields else None
        duplicate_percent = duplicates / processed if processed else None
        failure_percent = failed / attempted_unique if attempted_unique else None

        quarantined_rules = sum(outcome.policies_quarantined for outcome in outcomes)
        actual_classes = {
            "valid_policy_extraction": extracted_policy_pages,
            "duplicate_content_deduplicated": duplicates,
            "invalid_page_rejected": invalid_correctly_rejected,
            "timeout_page_failed": failed,
            "transient_page_retried": retried_pages,
            "conflicting_rule_variants_quarantined": quarantined_rules,
        }
        return {
            "seed": seed,
            "level": next(name for name, count in LEVEL_PAGES.items() if count == total_pages),
            "delay_ms": delay_ms,
            "concurrency": concurrency,
            "per_host_concurrency": PER_HOST_CONCURRENCY,
            "providers": len(fixture.provider_ids),
            "pages_expected": total_pages,
            "pages_attempted_unique": attempted_unique,
            "pages_processed": processed,
            "pages_retrieved": sum(outcome.pages_retrieved for outcome in outcomes),
            "pages_failed": failed,
            "pages_invalid": sum(outcome.pages_invalid for outcome in outcomes),
            "pages_deduplicated": duplicates,
            "duplicate_percent": duplicate_percent,
            "pages_retried": retried_pages,
            "request_retries": retry_count,
            "http_attempts": attempts_total,
            "duration_seconds": duration,
            "pages_per_second": processed / duration if duration else None,
            "failure_percent": failure_percent,
            "field_accuracy": field_accuracy,
            "fields_correct": correct_fields,
            "fields_expected": expected_fields,
            "valid_policy_pages_extracted": extracted_policy_pages,
            "invalid_pages_rejected": invalid_correctly_rejected,
            "invalid_pages_expected": invalid_total,
            "rules_accepted": len(actual_rules),
            "rules_expected": len(expected_rules),
            "rule_precision": precision,
            "rule_recall": recall,
            "rules_quarantined": quarantined_rules,
            "fixture_categories": fixture.category_counts,
            "observed_classes": actual_classes,
            "input_sha256": fixture.input_hash,
            "output_rule_sha256": sha256(json.dumps(sorted(actual_rules), separators=(",", ":")).encode()),
            "states": sorted(outcome.state for outcome in outcomes),
        }
    finally:
        await fetcher.aclose()
        await server.close()


def sample_summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    n = len(ordered)
    if not n:
        return {"count": 0, "min": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "mean": 0.0, "stdev": 0.0}

    def nearest_rank(p: float) -> float:
        return ordered[max(0, math.ceil(p * n) - 1)]

    return {
        "count": n,
        "min": ordered[0],
        "p50": nearest_rank(0.50),
        "p95": nearest_rank(0.95),
        "p99": nearest_rank(0.99),
        "max": ordered[-1],
        "mean": statistics.mean(ordered),
        "stdev": statistics.stdev(ordered) if n > 1 else 0.0,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_svg(path: Path, rows: list[dict[str, Any]]) -> None:
    groups = sorted({(row["level"], row["delay_ms"]) for row in rows})
    width, height = 1000, 540
    top, bottom = 55, 460
    panel_gap = 65
    colors = {1: "#64748b", 4: "#2563eb", 8: "#16a34a"}
    duration_max = max(float(row["duration_seconds"]) for row in rows) or 1.0
    throughput_max = max(float(row["pages_per_second"]) for row in rows if row["pages_per_second"] is not None) or 1.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#172033}.title{font-size:18px;font-weight:700}.axis{font-size:12px}.legend{font-size:12px}</style>',
        '<text x="500" y="26" text-anchor="middle" class="title">Synthetic crawler: whole-run duration and throughput</text>',
        '<text x="20" y="45" class="axis">Duration (seconds)</text>',
        '<text x="20" y="287" class="axis">Processed pages per second</text>',
    ]
    left, plot_width, panel_height = 70, 880, 180
    bar_group_width = plot_width / max(1, len(groups))
    for panel_index, (metric, maximum, y_origin) in enumerate((("duration_seconds", duration_max, 60), ("pages_per_second", throughput_max, 300))):
        parts.append(f'<line x1="{left}" y1="{y_origin + panel_height}" x2="{left + plot_width}" y2="{y_origin + panel_height}" stroke="#64748b"/>')
        for group_index, group in enumerate(groups):
            group_rows = [row for row in rows if (row["level"], row["delay_ms"]) == group]
            center = left + group_index * bar_group_width + bar_group_width / 2
            bar_width = min(24, bar_group_width / 5)
            for member_index, concurrency in enumerate(CONCURRENCY_LEVELS):
                member = next((row for row in group_rows if row["concurrency"] == concurrency and row["seed"] == min(r["seed"] for r in group_rows)), None)
                if member is None:
                    continue
                value = float(member[metric])
                bar_height = panel_height * value / maximum
                x = center + (member_index - 1) * (bar_width + 4) - bar_width / 2
                y = y_origin + panel_height - bar_height
                parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="{colors[concurrency]}"/>')
            label = f"{group[0]} / {group[1]} ms"
            parts.append(f'<text x="{center:.1f}" y="{y_origin + panel_height + 18}" text-anchor="middle" class="axis">{label}</text>')
    for index, concurrency in enumerate(CONCURRENCY_LEVELS):
        x = 720 + (index % 3) * 90
        parts.append(f'<rect x="{x}" y="500" width="12" height="12" fill="{colors[concurrency]}"/><text x="{x + 18}" y="510" class="legend">global {concurrency}</text>')
    parts.append('<text x="70" y="530" class="axis">Bars show the first seed in each group; CSV and report include every trial.</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"


def _memory_bytes() -> int | None:
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (ValueError, OSError, AttributeError):
        return None


def _summary_report(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Synthetic insurance crawler benchmark",
        "",
        "This report uses only generated synthetic provider pages served on loopback. The persistence adapter is a disposable in-memory contract fake; PostgreSQL migration, locks, and production networking were not exercised.",
        "",
        "## Trial results",
        "",
        "| Level | Delay | Global slots | Seeds | Pages/s mean ± SD | Duration p50/p95/p99 (s) | Field accuracy | Duplicate % | Failure % | Retried pages | Rule P/R |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    group_keys = sorted({(row["level"], row["delay_ms"], row["concurrency"]) for row in rows})
    for level, delay, concurrency in group_keys:
        group = [row for row in rows if row["level"] == level and row["delay_ms"] == delay and row["concurrency"] == concurrency]
        durations = [float(row["duration_seconds"]) for row in group]
        ptiles = sample_summary(durations)
        throughput = [float(row["pages_per_second"]) for row in group]
        accuracy = [float(row["field_accuracy"]) for row in group if row["field_accuracy"] is not None]
        duplicates = [float(row["duplicate_percent"]) for row in group if row["duplicate_percent"] is not None]
        failures = [float(row["failure_percent"]) for row in group if row["failure_percent"] is not None]
        precisions = [float(row["rule_precision"]) for row in group if row["rule_precision"] is not None]
        recalls = [float(row["rule_recall"]) for row in group if row["rule_recall"] is not None]
        mean = statistics.mean(throughput) if throughput else 0.0
        sd = statistics.stdev(throughput) if len(throughput) > 1 else 0.0
        lines.append(
            f"| {level} | {delay} ms | {concurrency} | {','.join(str(row['seed']) for row in group)} | "
            f"{mean:.3f} ± {sd:.3f} | {ptiles['p50']:.3f}/{ptiles['p95']:.3f}/{ptiles['p99']:.3f} | "
            f"{statistics.mean(accuracy) * 100:.2f}% | {statistics.mean(duplicates) * 100:.2f}% | "
            f"{statistics.mean(failures) * 100:.2f}% | {sum(int(row['pages_retried']) for row in group)} | "
            f"{statistics.mean(precisions) * 100:.2f}%/{statistics.mean(recalls) * 100:.2f}% |"
        )
    lines.extend(["", "## Sequential versus bounded concurrency", "", "Speedup is the paired seed ratio of sequential duration divided by the bounded run duration. Duration difference is sequential minus bounded. No threshold is treated as an acceptance target.", ""])
    lines.extend([
        "| Level | Delay | Compared slots | Paired duration speedup mean ± SD | Duration saved seconds mean ± SD | Throughput delta pages/s mean ± SD |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for level, delay in sorted({(row["level"], row["delay_ms"]) for row in rows}):
        baseline = {row["seed"]: row for row in rows if row["level"] == level and row["delay_ms"] == delay and row["concurrency"] == 1}
        for concurrency in (4, 8):
            proposed = {row["seed"]: row for row in rows if row["level"] == level and row["delay_ms"] == delay and row["concurrency"] == concurrency}
            paired_seeds = sorted(set(baseline) & set(proposed))
            if not paired_seeds:
                continue
            ratios = [baseline[seed]["duration_seconds"] / proposed[seed]["duration_seconds"] for seed in paired_seeds]
            seconds_saved = [baseline[seed]["duration_seconds"] - proposed[seed]["duration_seconds"] for seed in paired_seeds]
            throughput_delta = [proposed[seed]["pages_per_second"] - baseline[seed]["pages_per_second"] for seed in paired_seeds]
            ratio_mean = statistics.mean(ratios)
            ratio_sd = statistics.stdev(ratios) if len(ratios) > 1 else 0.0
            saved_mean = statistics.mean(seconds_saved)
            saved_sd = statistics.stdev(seconds_saved) if len(seconds_saved) > 1 else 0.0
            delta_mean = statistics.mean(throughput_delta)
            delta_sd = statistics.stdev(throughput_delta) if len(throughput_delta) > 1 else 0.0
            lines.append(f"| {level} | {delay} ms | 1 → {concurrency} | {ratio_mean:.3f} ± {ratio_sd:.3f}× | {saved_mean:.3f} ± {saved_sd:.3f} | {delta_mean:.3f} ± {delta_sd:.3f} |")
    lines.extend(["", "## Interpretation limits", "", "- Concurrency 8 is an experiment setting; the deployment default remains 4, and per-host concurrency remains 2.", "- Invalid pages are reported as rejected and excluded from field accuracy. Timed-out pages have no extracted field denominator and remain in the failure denominator.", "- Duplicate percentage is duplicate content pages divided by successfully processed unique URLs. Failure percentage is failed unique page requests divided by attempted unique page requests. HTTP retries do not inflate either denominator.", "- Fixture delay, loopback server behavior, Python scheduling, and in-memory repository timings are local measurements. They do not establish production crawl capacity or PostgreSQL transaction performance.", ""])
    return "\n".join(lines)


async def run_benchmark(args: argparse.Namespace) -> Path:
    levels = tuple(LEVEL_PAGES) if args.level == "all" else (args.level,)
    seeds = [args.seed, *args.repeat_seeds]
    jobs: list[tuple[str, int, int, int]] = []
    for level in levels:
        for seed_index, seed in enumerate(seeds):
            order = CONCURRENCY_LEVELS if seed_index % 2 == 0 else (8, 4, 1)
            for concurrency in order:
                jobs.append((level, seed, 20, concurrency))
    if args.level == "all" or args.include_100ms_sensitivity:
        for seed_index, seed in enumerate(seeds):
            order = (1, 4) if seed_index % 2 == 0 else (4, 1)
            for concurrency in order:
                jobs.append(("high", seed, 100, concurrency))

    rows: list[dict[str, Any]] = []
    input_hashes: list[str] = []
    start_utc = utc_now()
    for index, (level, seed, delay, concurrency) in enumerate(jobs, start=1):
        print(f"[{index}/{len(jobs)}] {level} delay={delay}ms slots={concurrency} seed={seed}", flush=True)
        row = await run_trial(seed, LEVEL_PAGES[level], delay, concurrency)
        rows.append(row)
        input_hashes.append(row["input_sha256"])
        if row["pages_attempted_unique"] != row["pages_expected"]:
            raise RuntimeError(f"workload page accounting mismatch: {row}")
        if row["pages_deduplicated"] != row["fixture_categories"]["duplicate"]:
            raise RuntimeError(f"duplicate fixture was not fully deduplicated: {row}")
        if row["pages_failed"] != row["fixture_categories"]["timeout"]:
            raise RuntimeError(f"failure accounting differs from timeout truth: {row}")
        if row["pages_retried"] != row["fixture_categories"]["transient"]:
            raise RuntimeError(f"retry accounting differs from transient truth: {row}")
        expected_extraction_pages = sum(
            row["fixture_categories"][category]
            for category in ("valid", "duplicate", "transient", "conflict")
        )
        if row["valid_policy_pages_extracted"] != expected_extraction_pages:
            raise RuntimeError(f"extraction page coverage differs from synthetic truth: {row}")
        if row["invalid_pages_rejected"] != row["fixture_categories"]["invalid"]:
            raise RuntimeError(f"invalid page rejection differs from synthetic truth: {row}")
        if row["rules_quarantined"] != row["fixture_categories"]["conflict"]:
            raise RuntimeError(f"conflict quarantine differs from synthetic truth: {row}")
        if row["fields_correct"] != row["fields_expected"]:
            raise RuntimeError(f"field extraction differs from synthetic truth: {row}")
        if row["rule_precision"] != 1 or row["rule_recall"] != 1:
            raise RuntimeError(f"accepted policy set differs from synthetic truth: {row}")

    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_columns = [
        "seed", "level", "delay_ms", "concurrency", "per_host_concurrency", "providers", "pages_expected",
        "pages_attempted_unique", "pages_processed", "pages_retrieved", "pages_failed", "pages_invalid",
        "pages_deduplicated", "duplicate_percent", "pages_retried", "request_retries", "http_attempts",
        "duration_seconds", "pages_per_second", "failure_percent", "field_accuracy", "fields_correct", "fields_expected",
        "valid_policy_pages_extracted", "invalid_pages_rejected", "invalid_pages_expected", "rules_accepted", "rules_expected", "rule_precision", "rule_recall",
        "rules_quarantined", "input_sha256", "output_rule_sha256", "states",
    ]
    _write_csv(output_dir / "summary.csv", rows, summary_columns)
    confusion_rows = []
    for row in rows:
        fixture_counts = row["fixture_categories"]
        comparisons = (
            ("valid_policy_extraction", fixture_counts["valid"] + fixture_counts["duplicate"] + fixture_counts["transient"] + fixture_counts["conflict"], row["valid_policy_pages_extracted"], "pages"),
            ("duplicate_content_deduplicated", fixture_counts["duplicate"], row["pages_deduplicated"], "pages"),
            ("invalid_page_rejected", fixture_counts["invalid"], row["invalid_pages_rejected"], "pages"),
            ("timeout_page_failed", fixture_counts["timeout"], row["pages_failed"], "pages"),
            ("transient_page_retried", fixture_counts["transient"], row["pages_retried"], "pages"),
            ("conflicting_rule_variants_quarantined", fixture_counts["conflict"], row["rules_quarantined"], "rule_variants"),
        )
        for category, expected, observed, unit in comparisons:
            confusion_rows.append({
                "seed": row["seed"], "level": row["level"], "delay_ms": row["delay_ms"],
                "concurrency": row["concurrency"], "fixture_class": category,
                "expected": expected, "observed": observed, "observed_unit": unit,
                "correct": expected == observed,
            })
    incorrect_comparisons = [row for row in confusion_rows if not row["correct"]]
    if incorrect_comparisons:
        raise RuntimeError(f"fixture confusion contains incorrect classifications: {incorrect_comparisons[:3]}")
    _write_csv(output_dir / "fixture_confusion.csv", confusion_rows, ["seed", "level", "delay_ms", "concurrency", "fixture_class", "expected", "observed", "observed_unit", "correct"])
    _write_svg(output_dir / "latency.svg", rows)
    report = _summary_report(rows)
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    end_utc = utc_now()
    lock_path = ROOT / "services/billing/requirements.lock"
    lock_hash = sha256(lock_path.read_bytes()) if lock_path.exists() else "unavailable"
    summary_hash = sha256((output_dir / "summary.csv").read_bytes())
    output_hashes = {
        name: sha256((output_dir / name).read_bytes())
        for name in ("summary.csv", "fixture_confusion.csv", "report.md", "latency.svg")
    }
    manifest = {
        "run_id": output_dir.name,
        "generated_at_utc": end_utc,
        "started_at_utc": start_utc,
        "ended_at_utc": end_utc,
        "generation_command": " ".join(sys.argv),
        "component_commit": _git_value("rev-parse", "HEAD"),
        "baseline_commit": _git_value("rev-parse", "HEAD"),
        "baseline": "same parser, validation, allowlist, retry policy, and repository contract using one global in-flight request",
        "working_tree_status_at_run": _git_value("status", "--porcelain"),
        "dependency_lock_sha256": lock_hash,
        "python_version": platform.python_version(),
        "httpx_version": httpx.__version__,
        "postgresql_version": None,
        "redis_version": None,
        "topology": "one in-process async coordinator; three synthetic HTTP hosts resolved to 127.0.0.1; in-memory Billing repository contract fake",
        "network_location": "loopback only; no external network requests",
        "hardware": {
            "os": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "logical_cpus": os.cpu_count(),
            "memory_bytes": _memory_bytes(),
        },
        "resource_limits": {"process_count": 1, "imposed_cpu_or_memory_limit": None, "note": "host limits not queried"},
        "timer": {"name": "time.perf_counter_ns", "resolution_seconds": time.get_clock_info("perf_counter").resolution},
        "levels_total_pages": LEVEL_PAGES,
        "seeds": seeds,
        "concurrency_levels": list(CONCURRENCY_LEVELS),
        "per_host_concurrency": PER_HOST_CONCURRENCY,
        "default_deployment_concurrency": 4,
        "fixture_parameters": {
            "providers": 3,
            "page_cap_per_provider": 100,
            "base_delays_ms": [20, 100],
            "duplicate_target_fraction": 0.10,
            "transient_503_target_fraction": 0.05,
            "invalid_or_timeout_target_fraction": 0.05,
            "timeout_delay_seconds": 1.05,
            "retry_count": 2,
            "retry_jitter_seconds": 0.1,
        },
        "input_sha256_by_trial": input_hashes,
        "summary_sha256": summary_hash,
        "output_sha256_by_file": output_hashes,
        "raw_page_retention": "none; pages exist only in process memory during the trial",
        "metrics_denominators": {
            "pages_per_second": "successfully processed unique URLs divided by whole batch wall duration",
            "duplicate_percent": "duplicate content pages divided by successfully processed unique URLs",
            "failure_percent": "failed unique page requests divided by attempted unique page requests; retries excluded",
            "field_accuracy": "correct extracted fields divided by expected fields from successfully retrieved valid/conflict/duplicate pages; invalid and timed-out fixtures excluded",
            "rule_precision_recall": "exact accepted canonical rules versus unique valid fixture truth; conflicting revision is not in accepted truth",
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=404)
    parser.add_argument("--repeat-seeds", type=lambda raw: [int(value) for value in raw.split(",") if value], default=[405, 406])
    parser.add_argument("--level", choices=("low", "medium", "high", "all"), default="low")
    parser.add_argument("--include-100ms-sensitivity", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run_benchmark(args))
    print(f"Results written: {result}")


if __name__ == "__main__":
    main()
