"""Bounded asynchronous crawler orchestration and immutable rule staging."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

from .contracts import (
    InsuranceValidationError,
    PolicyRule,
    ValidatedPolicyExport,
    export_validated_policy,
    rule_content_hash,
    validate_id,
    validate_source_id,
)
from .extractor import ExtractionError, extract, extract_links
from .fetcher import FetchError

DEFAULT_GLOBAL_CONCURRENCY = 4
DEFAULT_PER_HOST_CONCURRENCY = 2
DEFAULT_RUN_DEADLINE_SECONDS = 30.0
MAX_PAGES_PER_RUN = 100
MAX_CRAWL_DEPTH = 2


class CrawlError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CrawlSource:
    source_id: str
    start_path: str


@dataclass(frozen=True, slots=True)
class SourceObservation:
    source_id: str
    path: str
    source_version: int
    content_hash: str
    observed_at: str


@dataclass(frozen=True, slots=True)
class CrawlOutcome:
    provider_id: str
    run_id: str
    state: str
    pages_processed: int
    pages_retrieved: int
    pages_failed: int
    pages_invalid: int
    pages_deduplicated: int
    duplicate_links: int
    policies_validated: int
    policies_staged: int
    policies_deduplicated: int
    policies_quarantined: int
    changed_pages: int
    retried_pages: int = 0
    error_code: str | None = None
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "run_id": self.run_id,
            "state": self.state,
            "pages_processed": self.pages_processed,
            "pages_retrieved": self.pages_retrieved,
            "pages_failed": self.pages_failed,
            "pages_invalid": self.pages_invalid,
            "pages_deduplicated": self.pages_deduplicated,
            "duplicate_links": self.duplicate_links,
            "policies_validated": self.policies_validated,
            "policies_staged": self.policies_staged,
            "policies_deduplicated": self.policies_deduplicated,
            "policies_quarantined": self.policies_quarantined,
            "changed_pages": self.changed_pages,
            "retried_pages": self.retried_pages,
            "error_code": self.error_code,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class InsuranceFetcher(Protocol):
    async def fetch(self, source_id: str, relative_path: str) -> dict[str, Any]: ...
    def host_key(self, source_id: str) -> str: ...
    def resolve_link(self, source_id: str, current_path: str, href: str) -> str: ...
    def assert_provider_source(self, provider_id: Any, source_id: str, configured_url: str) -> None: ...


class InsuranceRepository(Protocol):
    async def get_provider(self, provider_id: str) -> Mapping[str, Any] | None: ...
    async def list_sources(self, provider_id: str) -> Sequence[CrawlSource]: ...
    async def begin_run(self, provider_id: str) -> Mapping[str, Any]: ...
    async def read_source_version(self, provider_id: str, source_id: str, path: str) -> Mapping[str, Any] | None: ...
    async def commit_run(
        self,
        run_id: str,
        fencing_version: int | None,
        outcome: CrawlOutcome,
        policies: Sequence[ValidatedPolicyExport],
        observations: Sequence[SourceObservation],
    ) -> Mapping[str, Any] | None: ...


@dataclass(slots=True)
class _Counts:
    scheduled: int = 0
    attempted: int = 0
    processed: int = 0
    retrieved: int = 0
    failed: int = 0
    invalid: int = 0
    deduplicated: int = 0
    duplicate_links: int = 0
    policies_validated: int = 0
    policies_staged: int = 0
    policies_deduplicated: int = 0
    policies_quarantined: int = 0
    changed_pages: int = 0
    retried_pages: int = 0
    first_error: str | None = None
    body_hashes: set[str] = field(default_factory=set)
    paths_seen: set[tuple[str, str]] = field(default_factory=set)
    rule_exports: dict[tuple[str, int], dict[str, list[ValidatedPolicyExport]]] = field(default_factory=dict)
    exports: list[ValidatedPolicyExport] = field(default_factory=list)
    observations: list[SourceObservation] = field(default_factory=list)


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


async def _await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _now_iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _emit(observer: Any, method: str, name: str, value: Any, labels: dict[str, str]) -> None:
    if observer is None:
        return
    try:
        if method == "increment":
            getattr(observer, method)(name, labels, value)
        else:
            getattr(observer, method)(name, value, labels)
    except Exception:
        return


async def crawl(
    provider_id: str,
    fetcher: InsuranceFetcher,
    repository: InsuranceRepository,
    observer: Any,
) -> CrawlOutcome:
    """Create and execute one direct crawl using the frozen four-port signature."""
    normalized_provider_id = validate_id(provider_id, name="provider_id")
    run = await repository.begin_run(normalized_provider_id)
    return await _execute_run(
        normalized_provider_id,
        fetcher,
        repository,
        observer,
        run,
        fencing_version=None,
    )


async def execute_claimed_run(
    claim: Mapping[str, Any], fetcher: InsuranceFetcher, repository: InsuranceRepository, observer: Any
) -> CrawlOutcome:
    """Execute a worker claim; commit_run must check its fencing version atomically."""
    provider_id = validate_id(_value(claim, "provider_id"), name="provider_id")
    run_id = validate_id(_value(claim, "id", _value(claim, "run_id")), name="run_id")
    fencing_version = _value(claim, "fencing_version", _value(claim, "lease_version"))
    if type(fencing_version) is not int or not 1 <= fencing_version <= 9_007_199_254_740_991:
        raise CrawlError("invalid_lease_version")
    return await _execute_run(
        provider_id,
        fetcher,
        repository,
        observer,
        {"id": run_id, "provider_id": provider_id, "fencing_version": fencing_version},
        fencing_version=fencing_version,
    )


async def _execute_run(
    provider_id: str,
    fetcher: InsuranceFetcher,
    repository: InsuranceRepository,
    observer: Any,
    run: Mapping[str, Any],
    *,
    fencing_version: int | None,
    concurrency: int | None = None,
    per_host_concurrency: int | None = None,
    run_deadline_seconds: float = DEFAULT_RUN_DEADLINE_SECONDS,
    max_pages: int = MAX_PAGES_PER_RUN,
    max_depth: int = MAX_CRAWL_DEPTH,
) -> CrawlOutcome:
    concurrency = concurrency or getattr(fetcher, "concurrency", DEFAULT_GLOBAL_CONCURRENCY)
    per_host_concurrency = per_host_concurrency or getattr(
        fetcher, "per_host_concurrency", DEFAULT_PER_HOST_CONCURRENCY
    )
    if not 1 <= concurrency <= 8 or not 1 <= per_host_concurrency <= 2:
        raise ValueError("crawler concurrency exceeds the reviewed bounds")
    if not 0 < run_deadline_seconds <= DEFAULT_RUN_DEADLINE_SECONDS:
        raise ValueError("run deadline exceeds the reviewed bound")
    if not 1 <= max_pages <= MAX_PAGES_PER_RUN or not 0 <= max_depth <= MAX_CRAWL_DEPTH:
        raise ValueError("page or depth limit exceeds the reviewed bound")
    run_id = validate_id(_value(run, "id", _value(run, "run_id")), name="run_id")
    run_started = datetime.now(timezone.utc)
    start_ns = time.perf_counter_ns()
    counts = _Counts()
    try:
        provider = await repository.get_provider(provider_id)
        if provider is None or str(_value(provider, "id", provider_id)) != provider_id:
            raise CrawlError("provider_not_found")
        sources_raw = await repository.list_sources(provider_id)
        sources = tuple(
            CrawlSource(
                source_id=validate_source_id(_value(source, "source_id")),
                start_path=str(_value(source, "start_path")),
            )
            for source in sources_raw
        )
        if not sources:
            raise CrawlError("source_not_configured")
        configured_url = _value(provider, "allowlisted_url")
        if not isinstance(configured_url, str):
            raise CrawlError("source_not_configured")
        for source in sources:
            try:
                fetcher.assert_provider_source(provider_id, source.source_id, configured_url)
            except FetchError as exc:
                raise CrawlError(exc.code) from exc
            except (AttributeError, ValueError) as exc:
                raise CrawlError("source_not_allowlisted") from exc
    except (CrawlError, InsuranceValidationError) as exc:
        safe_code = getattr(exc, "code", "source_not_configured")
        failed_at = datetime.now(timezone.utc)
        failed = CrawlOutcome(
            provider_id=provider_id,
            run_id=run_id,
            state="failed",
            pages_processed=0,
            pages_retrieved=0,
            pages_failed=0,
            pages_invalid=0,
            pages_deduplicated=0,
            duplicate_links=0,
            policies_validated=0,
            policies_staged=0,
            policies_deduplicated=0,
            policies_quarantined=0,
            changed_pages=0,
            error_code=safe_code,
            started_at=_now_iso(run_started),
            completed_at=_now_iso(failed_at),
        )
        committed = await repository.commit_run(run_id, fencing_version, failed, (), ())
        if committed is False or (isinstance(committed, Mapping) and committed.get("lease_owned") is False):
            return replace(failed, error_code="lease_lost")
        _emit(observer, "increment", "pulsegrid_crawler_runs_total", 1, {"owner": "billing", "outcome": "failed"})
        _emit(observer, "observe", "pulsegrid_crawler_run_seconds", (time.perf_counter_ns() - start_ns) / 1_000_000_000, {"owner": "billing"})
        return failed

    queue: asyncio.Queue[tuple[CrawlSource, str, int]] = asyncio.Queue()
    for source in sources:
        key = (source.source_id, source.start_path)
        if key in counts.paths_seen:
            counts.duplicate_links += 1
            continue
        if counts.scheduled >= max_pages:
            break
        counts.paths_seen.add(key)
        counts.scheduled += 1
        queue.put_nowait((source, source.start_path, 0))

    global_semaphore = asyncio.Semaphore(concurrency)
    host_semaphores: dict[str, asyncio.Semaphore] = {}
    host_active: dict[str, int] = {}
    run_time_exceeded = False

    def consume_retries(source_id: str, path: str) -> None:
        consumer = getattr(fetcher, "consume_retry_count", None)
        if consumer is None:
            return
        try:
            retry_count = int(consumer(source_id, path))
        except Exception:
            return
        if retry_count > 0:
            counts.retried_pages += 1
            _emit(observer, "increment", "pulsegrid_crawler_retried_pages_total", 1, {"owner": "billing", "outcome": "retried"})

    async def process_page(source: CrawlSource, path: str, depth: int) -> None:
        host_key = fetcher.host_key(source.source_id)
        host_semaphore = host_semaphores.setdefault(host_key, asyncio.Semaphore(per_host_concurrency))
        async with global_semaphore, host_semaphore:
            host_active[host_key] = host_active.get(host_key, 0) + 1
            _emit(observer, "gauge", "pulsegrid_crawler_active_requests", float(sum(host_active.values())), {"owner": "billing"})
            try:
                counts.attempted += 1
                response = await fetcher.fetch(source.source_id, path)
            except asyncio.CancelledError:
                consume_retries(source.source_id, path)
                counts.failed += 1
                counts.first_error = counts.first_error or "run_deadline_exceeded"
                raise
            except (FetchError, TimeoutError) as exc:
                consume_retries(source.source_id, path)
                counts.failed += 1
                counts.first_error = counts.first_error or getattr(exc, "code", "request_timeout")
                _emit(observer, "increment", "pulsegrid_crawler_pages_total", 1, {"owner": "billing", "outcome": "failed"})
                return
            except Exception:
                consume_retries(source.source_id, path)
                counts.failed += 1
                counts.first_error = counts.first_error or "fetch_error"
                _emit(observer, "increment", "pulsegrid_crawler_pages_total", 1, {"owner": "billing", "outcome": "failed"})
                return
            finally:
                host_active[host_key] = max(0, host_active.get(host_key, 1) - 1)
                _emit(observer, "gauge", "pulsegrid_crawler_active_requests", float(sum(host_active.values())), {"owner": "billing"})

        consume_retries(source.source_id, path)
        status = response.get("status")
        body = response.get("body")
        if type(status) is not int or status < 200 or status > 299 or not isinstance(body, bytes):
            counts.failed += 1
            counts.first_error = counts.first_error or "upstream_status"
            _emit(observer, "increment", "pulsegrid_crawler_pages_total", 1, {"owner": "billing", "outcome": "failed"})
            return
        counts.retrieved += 1
        body_hash = hashlib.sha256(body).hexdigest()
        previous = await repository.read_source_version(provider_id, source.source_id, path)
        previous_hash = _value(previous, "content_hash") if previous is not None else None
        previous_version = _value(previous, "source_version", 0) if previous is not None else 0
        if type(previous_version) is not int or previous_version < 0:
            counts.failed += 1
            counts.first_error = counts.first_error or "source_version_invalid"
            return
        source_version = previous_version if previous_hash == body_hash else previous_version + 1
        if previous_hash is not None and previous_hash != body_hash:
            counts.changed_pages += 1
        observed_at = _now_iso(datetime.now(timezone.utc))
        counts.observations.append(
            SourceObservation(source.source_id, path, source_version, body_hash, observed_at)
        )

        is_content_duplicate = body_hash in counts.body_hashes
        counts.body_hashes.add(body_hash)
        page_rules: tuple[PolicyRule, ...] = ()
        try:
            links = extract_links(body)
            if is_content_duplicate:
                counts.deduplicated += 1
            else:
                page_rules = extract(body, source.source_id)
                counts.policies_validated += len(page_rules)
                for rule in page_rules:
                    content_hash = rule_content_hash(rule)
                    revision_key = (rule.policy_code, rule.revision)
                    variants = counts.rule_exports.setdefault(revision_key, {})
                    prior_exports = variants.setdefault(content_hash, [])
                    if prior_exports:
                        counts.policies_deduplicated += 1
                    prior_exports.append(
                        export_validated_policy(
                            provider_id=provider_id,
                            source_id=source.source_id,
                            source_path=path,
                            source_run_id=run_id,
                            source_version=source_version,
                            content_hash=content_hash,
                            observed_at=observed_at,
                            rule=rule,
                        )
                    )
        except (ExtractionError, InsuranceValidationError) as exc:
            counts.invalid += 1
            counts.first_error = counts.first_error or getattr(exc, "code", "invalid_page")
            _emit(observer, "increment", "pulsegrid_crawler_pages_total", 1, {"owner": "billing", "outcome": "invalid"})
            links = ()

        counts.processed += 1
        _emit(observer, "increment", "pulsegrid_crawler_pages_total", 1, {"owner": "billing", "outcome": "processed"})
        if is_content_duplicate:
            _emit(observer, "increment", "pulsegrid_crawler_pages_deduplicated_total", 1, {"owner": "billing", "outcome": "duplicate"})
        _emit(observer, "increment", "pulsegrid_crawler_extraction_rules_total", len(page_rules), {"owner": "billing", "outcome": "validated"})

        if depth >= max_depth:
            return
        for href in links:
            try:
                child_path = fetcher.resolve_link(source.source_id, path, href)
            except (FetchError, ValueError, AttributeError):
                continue
            key = (source.source_id, child_path)
            if key in counts.paths_seen:
                counts.duplicate_links += 1
                continue
            if counts.scheduled >= max_pages:
                counts.first_error = counts.first_error or "page_limit"
                continue
            counts.paths_seen.add(key)
            counts.scheduled += 1
            queue.put_nowait((source, child_path, depth + 1))

    async def worker() -> None:
        while True:
            source, path, depth = await queue.get()
            try:
                try:
                    await process_page(source, path, depth)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    counts.failed += 1
                    counts.first_error = counts.first_error or "crawl_processing_error"
                    _emit(observer, "increment", "pulsegrid_crawler_pages_total", 1, {"owner": "billing", "outcome": "failed"})
            finally:
                queue.task_done()

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    try:
        async with asyncio.timeout(run_deadline_seconds):
            await queue.join()
    except TimeoutError:
        run_time_exceeded = True
        counts.first_error = counts.first_error or "run_deadline_exceeded"
    finally:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    for _revision_key, variants in counts.rule_exports.items():
        if len(variants) > 1:
            counts.policies_quarantined += len(variants)
            counts.first_error = counts.first_error or "source_revision_conflict"
            continue
        equivalent_exports = next(iter(variants.values()))
        chosen = min(equivalent_exports, key=lambda item: (item.source_id, item.source_path))
        counts.exports.append(chosen)
    counts.exports.sort(key=lambda item: (item.rule.policy_code, item.rule.revision, item.content_hash))
    counts.policies_staged = len(counts.exports)

    completed = datetime.now(timezone.utc)
    if run_time_exceeded:
        counts.failed += max(0, counts.scheduled - counts.attempted)
    has_errors = bool(counts.failed or counts.invalid or counts.policies_quarantined or counts.first_error)
    if not has_errors:
        state = "complete"
    elif counts.processed or counts.retrieved:
        state = "partial"
    else:
        state = "failed"
    outcome = CrawlOutcome(
        provider_id=provider_id,
        run_id=run_id,
        state=state,
        pages_processed=counts.processed,
        pages_retrieved=counts.retrieved,
        pages_failed=counts.failed,
        pages_invalid=counts.invalid,
        pages_deduplicated=counts.deduplicated,
        duplicate_links=counts.duplicate_links,
        policies_validated=counts.policies_validated,
        policies_staged=counts.policies_staged,
        policies_deduplicated=counts.policies_deduplicated,
        policies_quarantined=counts.policies_quarantined,
        changed_pages=counts.changed_pages,
        retried_pages=counts.retried_pages,
        error_code=counts.first_error,
        started_at=_now_iso(run_started),
        completed_at=_now_iso(completed),
    )
    committed = await repository.commit_run(
        run_id,
        fencing_version,
        outcome,
        tuple(counts.exports),
        tuple(counts.observations),
    )
    if committed is False or (isinstance(committed, Mapping) and committed.get("lease_owned") is False):
        outcome = replace(outcome, state="failed", error_code="lease_lost")
    elif isinstance(committed, Mapping):
        outcome = replace(
            outcome,
            state=committed.get("state", outcome.state),
            policies_staged=committed.get("policies_accepted", outcome.policies_staged),
            policies_deduplicated=outcome.policies_deduplicated + committed.get("policies_deduplicated", 0),
            policies_quarantined=outcome.policies_quarantined + committed.get("policies_quarantined", 0),
            changed_pages=committed.get("changed_pages", outcome.changed_pages),
            error_code=committed.get("error_code", outcome.error_code),
        )

    duration = (time.perf_counter_ns() - start_ns) / 1_000_000_000
    _emit(observer, "observe", "pulsegrid_crawler_run_seconds", duration, {"owner": "billing"})
    _emit(observer, "increment", "pulsegrid_crawler_runs_total", 1, {"owner": "billing", "outcome": outcome.state})
    _emit(observer, "increment", "pulsegrid_crawler_pages_deduplicated_total", counts.deduplicated, {"owner": "billing", "outcome": "duplicate"})
    _emit(observer, "increment", "pulsegrid_crawler_pages_failed_total", counts.failed, {"owner": "billing", "outcome": "failed"})
    _emit(observer, "increment", "pulsegrid_crawler_rules_staged_total", counts.policies_staged, {"owner": "billing", "outcome": "staged"})
    return outcome
