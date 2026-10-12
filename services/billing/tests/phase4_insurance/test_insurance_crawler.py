from __future__ import annotations

import asyncio
import json
import socket
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx

from billing_service.features.insurance.contracts import (
    InsuranceValidationError,
    export_validated_policy,
    rule_content_hash,
    validate,
)
from billing_service.features.insurance.crawler import CrawlSource, crawl
from billing_service.features.insurance.estimate import build_estimate_result, calculate_estimate, estimate
from billing_service.features.insurance.extractor import ExtractionError, extract
from billing_service.features.insurance.fetcher import AllowlistedFetcher, FetchError, SourceConfig
from billing_service.features.insurance.health import health

UTC_NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
POLICY_MARKER = "data-pulsegrid-insurance-policy"


def policy(*, revision: int = 1, max_benefit_minor: int = 100_000, **overrides) -> dict:
    result = {
        "policy_code": "SYNTHETIC-CARE",
        "revision": revision,
        "effective_from": "2026-01-01T00:00:00Z",
        "effective_to": "2027-01-01T00:00:00Z",
        "currency": "INR",
        "coverage_bps": 8000,
        "deductible_minor": 5000,
        "max_benefit_minor": max_benefit_minor,
        "covered_charge_codes": ["consultation", "medicine:101"],
    }
    result.update(overrides)
    return result


def policy_page(value: dict) -> bytes:
    payload = json.dumps(value, separators=(",", ":"))
    return (
        '<!doctype html><html><body><script type="application/json" '
        f'{POLICY_MARKER}>{payload}</script></body></html>'
    ).encode("utf-8")


def index_page(*paths: str) -> bytes:
    links = "".join(f'<a href="{path}">policy</a>' for path in paths)
    return f"<!doctype html><html><body>{links}</body></html>".encode("utf-8")


class MemoryRepository:
    def __init__(self, pages: dict[str, bytes], *, provider_id: str = "10") -> None:
        self.provider_id = provider_id
        self.pages = pages
        self.run_counter = 0
        self.source_versions: dict[tuple[str, str, str], dict] = {}
        self.accepted: dict[tuple[str, str, int], str] = {}
        self.persisted_exports = []
        self.outcomes = []

    async def begin_run(self, provider_id: str):
        self.run_counter += 1
        return {"id": str(1000 + self.run_counter), "provider_id": provider_id}

    async def get_provider(self, provider_id: str):
        if provider_id != self.provider_id:
            return None
        return {
            "id": provider_id,
            "synthetic_slug": "synthetic-provider",
            "allowlisted_url": "http://provider.synthetic.test:8123/fixtures/provider/",
        }

    async def list_sources(self, provider_id: str):
        return (CrawlSource("fixture-provider", "/fixtures/provider/"),)

    async def read_source_version(self, provider_id: str, source_id: str, path: str):
        return self.source_versions.get((provider_id, source_id, path))

    async def commit_run(self, run_id, fencing_version, outcome, policies, observations):
        conflicts = 0
        duplicates = 0
        accepted = 0
        changed = 0
        for observation in observations:
            key = (outcome.provider_id, observation.source_id, observation.path)
            old = self.source_versions.get(key)
            if old and old["content_hash"] != observation.content_hash:
                changed += 1
            self.source_versions[key] = {
                "source_version": observation.source_version if old is None or old["content_hash"] != observation.content_hash else old["source_version"],
                "content_hash": observation.content_hash,
            }
        for export in policies:
            key = (outcome.provider_id, export.rule.policy_code, export.rule.revision)
            old_hash = self.accepted.get(key)
            if old_hash is None:
                self.accepted[key] = export.content_hash
                self.persisted_exports.append(export)
                accepted += 1
            elif old_hash == export.content_hash:
                duplicates += 1
            else:
                conflicts += 1
        state = "partial" if conflicts else outcome.state
        error_code = "source_revision_conflict" if conflicts else outcome.error_code
        final = {
            "lease_owned": True,
            "state": state,
            "policies_accepted": accepted,
            "policies_deduplicated": duplicates,
            "policies_quarantined": conflicts,
            "changed_pages": changed,
            "error_code": error_code,
        }
        self.outcomes.append((run_id, outcome, final))
        return final


class FakeFetcher:
    concurrency = 4
    per_host_concurrency = 2

    def __init__(self, pages: dict[str, bytes], *, base_url: str = "http://provider.synthetic.test:8123/fixtures/provider/"):
        self.pages = pages
        self.base_url = base_url
        self.active = 0
        self.max_active = 0
        self.failures: dict[str, int] = {}

    def assert_provider_source(self, provider_id: str, source_id: str, configured_url: str) -> None:
        if provider_id != "10" or source_id != "fixture-provider" or configured_url != self.base_url:
            raise FetchError("source_not_allowlisted")

    def host_key(self, source_id: str) -> str:
        return "provider.synthetic.test:8123"

    def resolve_link(self, source_id: str, current_path: str, href: str) -> str:
        if "://" in href or "?" in href or "#" in href or href.startswith("//"):
            raise FetchError("source_not_allowlisted")
        base = current_path if current_path.endswith("/") else current_path.rsplit("/", 1)[0] + "/"
        if href.startswith("/"):
            result = href
        else:
            result = base + href
        if not result.startswith("/fixtures/provider/") or ".." in result.split("/"):
            raise FetchError("source_not_allowlisted")
        return result

    async def fetch(self, source_id: str, relative_path: str):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.002)
            failures_left = self.failures.get(relative_path, 0)
            if failures_left:
                self.failures[relative_path] = failures_left - 1
                raise FetchError("network_error")
            body = self.pages[relative_path]
            return {"body": body, "status": 200, "headers": {"content-type": "text/html"}}
        finally:
            self.active -= 1


class _Observer:
    def __init__(self):
        self.counters = {}
        self.gauges = {}

    def increment(self, name, labels, value=1):
        self.counters[name] = self.counters.get(name, 0) + value

    def observe(self, name, seconds, labels):
        pass

    def gauge(self, name, value, labels):
        self.gauges[name] = max(self.gauges.get(name, 0), value)


class _LocalHTTPFixture:
    def __init__(self, responder):
        self.responder = responder
        self.server = None
        self.port = None

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def close(self):
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer):
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=1)
            lines = header.decode("latin1").split("\r\n")
            path = lines[0].split(" ")[1]
            host = next(line.split(":", 1)[1].strip() for line in lines[1:] if line.lower().startswith("host:"))
            status, headers, body, delay = await self.responder(host, path)
            if delay:
                await asyncio.sleep(delay)
            reason = {200: "OK", 302: "Found", 429: "Too Many Requests", 503: "Unavailable"}.get(status, "Error")
            response_headers = {
                "Content-Type": headers.get("content-type", "text/html"),
                "Content-Length": str(len(body)),
                "Connection": "close",
                **headers,
            }
            wire = f"HTTP/1.1 {status} {reason}\r\n" + "".join(f"{k}: {v}\r\n" for k, v in response_headers.items()) + "\r\n"
            writer.write(wire.encode("latin1") + body)
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


class ExtractValidationTests(unittest.TestCase):
    def test_valid_extraction_and_canonical_hash(self):
        rules = extract(policy_page(policy()), "fixture-provider")
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].policy_code, "SYNTHETIC-CARE")
        self.assertEqual(rules[0].covered_charge_codes, ("consultation", "medicine:101"))
        self.assertEqual(len(rule_content_hash(rules[0])), 64)

    def test_malformed_json_unknown_fields_and_duplicate_keys_are_rejected(self):
        with self.assertRaises(ExtractionError):
            extract(b"<html><script type='application/json' data-pulsegrid-insurance-policy>{</script></html>", "fixture-provider")
        with self.assertRaises(ExtractionError):
            extract(policy_page(policy(untrusted="field")), "fixture-provider")
        duplicate_key = (
            '<script type="application/json" data-pulsegrid-insurance-policy>'
            '{"policy_code":"A","policy_code":"B"}</script>'
        ).encode()
        with self.assertRaises(ExtractionError):
            extract(duplicate_key, "fixture-provider")

    def test_strict_field_validation_rejects_noncanonical_ids_and_unknown_currency(self):
        with self.assertRaises(InsuranceValidationError):
            validate(policy(covered_charge_codes=["medicine:0101"]))
        with self.assertRaises(InsuranceValidationError):
            validate(policy(currency="USD"))


class CrawlerBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_pages_are_counted_and_rules_are_stored_once(self):
        page = policy_page(policy())
        pages = {
            "/fixtures/provider/": index_page("policy/a.html", "policy/b.html"),
            "/fixtures/provider/policy/a.html": page,
            "/fixtures/provider/policy/b.html": page,
        }
        repository = MemoryRepository(pages)
        fetcher = FakeFetcher(pages)
        outcome = await crawl("10", fetcher, repository, _Observer())
        self.assertEqual(outcome.state, "complete")
        self.assertEqual(outcome.pages_processed, 3)
        self.assertEqual(outcome.pages_deduplicated, 1)
        self.assertEqual(outcome.policies_staged, 1)
        self.assertEqual(len(repository.accepted), 1)

    async def test_changed_policy_revision_increments_source_version(self):
        pages = {
            "/fixtures/provider/": index_page("policy/current.html"),
            "/fixtures/provider/policy/current.html": policy_page(policy(revision=1)),
        }
        repository = MemoryRepository(pages)
        fetcher = FakeFetcher(pages)
        first = await crawl("10", fetcher, repository, _Observer())
        pages["/fixtures/provider/policy/current.html"] = policy_page(policy(revision=2, max_benefit_minor=200_000))
        second = await crawl("10", fetcher, repository, _Observer())
        self.assertEqual(first.policies_staged, 1)
        self.assertEqual(second.policies_staged, 1)
        self.assertEqual(second.changed_pages, 1)
        source = repository.source_versions[("10", "fixture-provider", "/fixtures/provider/policy/current.html")]
        self.assertEqual(source["source_version"], 2)

    async def test_same_revision_changed_content_is_quarantined(self):
        pages = {
            "/fixtures/provider/": index_page("policy/current.html"),
            "/fixtures/provider/policy/current.html": policy_page(policy()),
        }
        repository = MemoryRepository(pages)
        fetcher = FakeFetcher(pages)
        await crawl("10", fetcher, repository, _Observer())
        pages["/fixtures/provider/policy/current.html"] = policy_page(policy(max_benefit_minor=200_000))
        outcome = await crawl("10", fetcher, repository, _Observer())
        self.assertEqual(outcome.state, "partial")
        self.assertEqual(outcome.error_code, "source_revision_conflict")
        self.assertEqual(outcome.policies_quarantined, 1)
        self.assertEqual(len(repository.accepted), 1)

    async def test_same_run_revision_conflict_quarantines_all_variants_deterministically(self):
        pages = {
            "/fixtures/provider/": index_page("policy/a.html", "policy/b.html"),
            "/fixtures/provider/policy/a.html": policy_page(policy(max_benefit_minor=100_000)),
            "/fixtures/provider/policy/b.html": policy_page(policy(max_benefit_minor=200_000)),
        }
        repository = MemoryRepository(pages)
        outcome = await crawl("10", FakeFetcher(pages), repository, _Observer())
        self.assertEqual(outcome.state, "partial")
        self.assertEqual(outcome.error_code, "source_revision_conflict")
        self.assertEqual(outcome.policies_staged, 0)
        self.assertEqual(outcome.policies_quarantined, 2)
        self.assertEqual(len(repository.accepted), 0)

    async def test_network_failure_and_timeout_are_counted_without_rule_replacement(self):
        pages = {"/fixtures/provider/": index_page("policy/a.html")}
        repository = MemoryRepository(pages)
        fetcher = FakeFetcher(pages)
        fetcher.failures["/fixtures/provider/"] = 1
        outcome = await crawl("10", fetcher, repository, _Observer())
        self.assertEqual(outcome.state, "failed")
        self.assertEqual(outcome.pages_failed, 1)
        self.assertEqual(outcome.error_code, "network_error")

    async def test_crawler_respects_global_and_per_host_concurrency(self):
        children = [f"policy/{index}.html" for index in range(16)]
        pages = {"/fixtures/provider/": index_page(*children)}
        pages.update({f"/fixtures/provider/{path}": b"<html></html>" for path in children})
        repository = MemoryRepository(pages)
        fetcher = FakeFetcher(pages)
        observer = _Observer()
        outcome = await crawl("10", fetcher, repository, observer)
        self.assertEqual(outcome.pages_processed, 17)
        self.assertLessEqual(fetcher.max_active, 2)
        self.assertLessEqual(observer.gauges["pulsegrid_crawler_active_requests"], 2)


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_is_disabled_without_ports_and_degraded_on_recent_failures(self):
        self.assertEqual(await health(), {"state": "disabled", "reason": "crawler_disabled"})
        failed_repo = SimpleNamespace(latest_run_state=lambda: asyncio.sleep(0, result="partial"))
        self.assertEqual(
            await health(SimpleNamespace(enabled=True, repository=failed_repo)),
            {"state": "degraded", "reason": "recent_crawl_failure"},
        )
        good_repo = SimpleNamespace(latest_run_state=lambda: asyncio.sleep(0, result="complete"))
        self.assertEqual(
            await health(SimpleNamespace(enabled=True, repository=good_repo)),
            {"state": "ok", "reason": None},
        )


class SecureFetcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_only_up_to_configured_limit_for_transient_status(self):
        attempts = 0

        async def respond(host, path):
            nonlocal attempts
            attempts += 1
            return (503, {"Retry-After": "0"}, b"busy", 0) if attempts <= 3 else (200, {}, b"ok", 0)

        fixture = await _LocalHTTPFixture(respond).start()
        sleeps = []
        source = SourceConfig("10", "fixture-provider", f"http://provider.synthetic.test:{fixture.port}/fixtures/provider/", frozenset({"127.0.0.1"}))
        fetcher = AllowlistedFetcher(
            [source], resolver=lambda _host, _port: asyncio.sleep(0, result=("127.0.0.1",)),
            sleep=lambda delay: asyncio.sleep(0, result=sleeps.append(delay)), jitter=lambda: 0.1,
        )
        try:
            with self.assertRaises(FetchError) as raised:
                await fetcher.fetch("fixture-provider", "/fixtures/provider/a.html")
            self.assertEqual(raised.exception.code, "upstream_status")
            self.assertEqual(attempts, 3)
            self.assertEqual(len(sleeps), 2)
            self.assertEqual(sleeps, [0.1, 0.1])
        finally:
            await fetcher.aclose()
            await fixture.close()

    async def test_transient_connection_failures_retry_boundedly(self):
        attempts = 0
        sleeps = []

        async def handle(request):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise httpx.ConnectError("synthetic connection reset", request=request)
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"ok")

        source = SourceConfig("10", "fixture-provider", "http://provider.synthetic.test:8123/fixtures/provider/", frozenset({"127.0.0.1"}))
        fetcher = AllowlistedFetcher(
            [source],
            resolver=lambda _host, _port: asyncio.sleep(0, result=("127.0.0.1",)),
            sleep=lambda delay: asyncio.sleep(0, result=sleeps.append(delay)),
            jitter=lambda: 0.2,
            transport=httpx.MockTransport(handle),
        )
        try:
            response = await fetcher.fetch("fixture-provider", "/fixtures/provider/a.html")
            self.assertEqual(response["body"], b"ok")
            self.assertEqual(attempts, 3)
            self.assertEqual(sleeps, [0.2, 0.2])
            self.assertEqual(fetcher.consume_retry_count("fixture-provider", "/fixtures/provider/a.html"), 2)
        finally:
            await fetcher.aclose()

    async def test_timeout_is_bounded_and_not_retried(self):
        attempts = 0

        async def respond(host, path):
            nonlocal attempts
            attempts += 1
            return 200, {}, b"late", 0.08

        fixture = await _LocalHTTPFixture(respond).start()
        source = SourceConfig("10", "fixture-provider", f"http://provider.synthetic.test:{fixture.port}/fixtures/provider/", frozenset({"127.0.0.1"}))
        fetcher = AllowlistedFetcher(
            [source], request_timeout=0.02,
            resolver=lambda _host, _port: asyncio.sleep(0, result=("127.0.0.1",)),
            sleep=lambda _delay: asyncio.sleep(0),
        )
        try:
            with self.assertRaises(FetchError) as raised:
                await fetcher.fetch("fixture-provider", "/fixtures/provider/slow.html")
            self.assertEqual(raised.exception.code, "request_timeout")
            self.assertEqual(attempts, 1)
        finally:
            await fetcher.aclose()
            await fixture.close()

    async def test_source_allowlist_rejects_arbitrary_urls_and_public_ip_targets(self):
        with self.assertRaises(ValueError):
            AllowlistedFetcher([
                SourceConfig("10", "fixture-provider", "http://provider.synthetic.test/", frozenset({"8.8.8.8"}))
            ])
        with self.assertRaises(ValueError):
            AllowlistedFetcher([
                SourceConfig("10", "fixture-provider", "http://provider.synthetic.test/", frozenset({"169.254.169.254"}))
            ])

        async def respond(host, path):
            return 200, {}, b"ok", 0

        fixture = await _LocalHTTPFixture(respond).start()
        source = SourceConfig("10", "fixture-provider", f"http://provider.synthetic.test:{fixture.port}/fixtures/provider/", frozenset({"127.0.0.1"}))
        fetcher = AllowlistedFetcher([source], resolver=lambda _host, _port: asyncio.sleep(0, result=("127.0.0.1",)))
        try:
            with self.assertRaises(FetchError):
                await fetcher.fetch("other-source", "/fixtures/provider/")
            with self.assertRaises(FetchError):
                await fetcher.fetch("fixture-provider", "http://169.254.169.254/latest/meta-data/")
            with self.assertRaises(FetchError):
                await fetcher.fetch("fixture-provider", "/outside/metadata/")
            with self.assertRaises(FetchError):
                await fetcher.fetch("fixture-provider", "/fixtures/provider/%25252e%25252e/private.html")
        finally:
            await fetcher.aclose()
            await fixture.close()

    async def test_response_size_and_content_encoding_are_bounded(self):
        async def respond(host, path):
            if path.endswith("compressed.html"):
                return 200, {"Content-Encoding": "gzip"}, b"compressed", 0
            return 200, {}, b"x" * 40, 0

        fixture = await _LocalHTTPFixture(respond).start()
        source = SourceConfig("10", "fixture-provider", f"http://provider.synthetic.test:{fixture.port}/fixtures/provider/", frozenset({"127.0.0.1"}))
        fetcher = AllowlistedFetcher(
            [source], max_response_bytes=32,
            resolver=lambda _host, _port: asyncio.sleep(0, result=("127.0.0.1",)),
        )
        try:
            with self.assertRaises(FetchError) as raised:
                await fetcher.fetch("fixture-provider", "/fixtures/provider/large.html")
            self.assertEqual(raised.exception.code, "response_too_large")
            with self.assertRaises(FetchError) as raised:
                await fetcher.fetch("fixture-provider", "/fixtures/provider/compressed.html")
            self.assertEqual(raised.exception.code, "unsupported_content_encoding")
        finally:
            await fetcher.aclose()
            await fixture.close()

    async def test_redirect_to_forbidden_host_is_rejected_before_request(self):
        requests = []

        async def respond(host, path):
            requests.append((host, path))
            return 302, {"Location": "http://169.254.169.254/latest/meta-data/"}, b"", 0

        fixture = await _LocalHTTPFixture(respond).start()
        source = SourceConfig("10", "fixture-provider", f"http://provider.synthetic.test:{fixture.port}/fixtures/provider/", frozenset({"127.0.0.1"}))
        fetcher = AllowlistedFetcher([source], resolver=lambda _host, _port: asyncio.sleep(0, result=("127.0.0.1",)))
        try:
            with self.assertRaises(FetchError) as raised:
                await fetcher.fetch("fixture-provider", "/fixtures/provider/start.html")
            self.assertEqual(raised.exception.code, "source_not_allowlisted")
            self.assertEqual(len(requests), 1)
        finally:
            await fetcher.aclose()
            await fixture.close()

    async def test_global_and_per_host_request_bounds(self):
        active_by_host = {}
        maximum_by_host = {}
        overall = 0
        overall_max = 0

        async def respond(host, path):
            nonlocal overall, overall_max
            active_by_host[host] = active_by_host.get(host, 0) + 1
            overall += 1
            maximum_by_host[host] = max(maximum_by_host.get(host, 0), active_by_host[host])
            overall_max = max(overall_max, overall)
            await asyncio.sleep(0.01)
            active_by_host[host] -= 1
            overall -= 1
            return 200, {}, b"ok", 0

        fixture = await _LocalHTTPFixture(respond).start()
        sources = [
            SourceConfig(str(10 + index), f"fixture-{index}", f"http://provider-{index}.synthetic.test:{fixture.port}/fixtures/provider-{index}/", frozenset({"127.0.0.1"}))
            for index in range(3)
        ]
        fetcher = AllowlistedFetcher(
            sources,
            concurrency=4,
            per_host_concurrency=2,
            resolver=lambda _host, _port: asyncio.sleep(0, result=("127.0.0.1",)),
        )
        try:
            await asyncio.gather(*(
                fetcher.fetch(source.source_id, f"/fixtures/provider-{index}/page.html")
                for index, source in enumerate(sources)
                for _ in range(5)
            ))
            self.assertLessEqual(overall_max, 4)
            self.assertTrue(all(value <= 2 for value in maximum_by_host.values()))
        finally:
            await fetcher.aclose()
            await fixture.close()


class BillingExportTests(unittest.TestCase):
    def test_validated_export_and_estimate_follow_frozen_integer_formula(self):
        validated = validate(policy())
        content_hash = rule_content_hash(validated)
        exported = export_validated_policy(
            provider_id="10",
            source_id="fixture-provider",
            source_path="/fixtures/provider/policy/current.html",
            source_run_id="1001",
            source_version=3,
            content_hash=content_hash,
            observed_at="2026-10-12T11:00:00Z",
            rule=validated,
        )
        invoice = {
            "id": "2001",
            "version": 4,
            "balance_minor": 40_000,
            "items": [
                {"charge_code": "consultation", "amount_minor": 30_000},
                {"charge_code": "medicine:101", "amount_minor": 20_000},
                {"charge_code": "medicine:102", "amount_minor": 10_000},
            ],
        }
        before = json.dumps(invoice, sort_keys=True)
        calculation = calculate_estimate(invoice, validated, UTC_NOW)
        self.assertEqual(calculation.eligible_minor, 50_000)
        self.assertEqual(calculation.estimate_minor, 36_000)
        result = build_estimate_result(
            estimate_id="3001",
            invoice_snapshot=invoice,
            policy=exported,
            rules_id="4001",
            source_fetched_at=UTC_NOW,
            now=UTC_NOW,
        )
        self.assertEqual(result["currency"], "INR")
        self.assertIs(result["is_simulated"], True)
        self.assertEqual(result["source_run_id"], "1001")
        self.assertEqual(json.dumps(invoice, sort_keys=True), before)
        frozen_result = estimate(
            {
                **invoice,
                "_insurance": {
                    "estimate_id": "3001",
                    "provider_id": exported.provider_id,
                    "rules_id": "4001",
                    "source_run_id": exported.source_run_id,
                    "source_id": exported.source_id,
                    "source_path": exported.source_path,
                    "source_version": exported.source_version,
                    "content_hash": exported.content_hash,
                    "observed_at": exported.observed_at,
                    "source_fetched_at": UTC_NOW,
                },
            },
            validated,
            UTC_NOW,
        )
        self.assertEqual(frozen_result, result)

    def test_paid_balance_caps_estimate_at_zero_and_stale_source_is_labeled(self):
        validated = validate(policy())
        exported = export_validated_policy(
            provider_id="10", source_id="fixture-provider", source_path="/fixtures/provider/policy/current.html",
            source_run_id="1001", source_version=1, content_hash=rule_content_hash(validated),
            observed_at="2026-10-12T11:00:00Z", rule=validated,
        )
        result = build_estimate_result(
            estimate_id="3002",
            invoice_snapshot={"id": "2002", "version": 2, "balance_minor": 0, "items": [{"charge_code": "consultation", "amount_minor": 200_000}]},
            policy=exported,
            rules_id="4002",
            source_fetched_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
            now=UTC_NOW,
        )
        self.assertEqual(result["estimate_minor"], 0)
        self.assertEqual(result["freshness_state"], "stale")

    def test_export_rejects_hash_mismatch_and_estimate_rejects_out_of_range_amount(self):
        validated = validate(policy())
        with self.assertRaises(InsuranceValidationError):
            export_validated_policy(
                provider_id="10", source_id="fixture-provider", source_path="/policy.html",
                source_run_id="1001", source_version=1, content_hash="0" * 64,
                observed_at="2026-10-12T11:00:00Z", rule=validated,
            )
        with self.assertRaises(InsuranceValidationError):
            calculate_estimate(
                {"id": "2001", "version": 1, "balance_minor": 1, "items": [{"charge_code": "consultation", "amount_minor": 9_007_199_254_740_992}]},
                validated,
                UTC_NOW,
            )


if __name__ == "__main__":
    unittest.main()
