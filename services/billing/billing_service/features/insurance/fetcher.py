"""Fixture-only HTTP fetcher with DNS pinning, bounds, and safe retries."""

from __future__ import annotations

import asyncio
import ipaddress
import random
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx

from .contracts import InsuranceValidationError, validate_id, validate_source_id

MAX_RESPONSE_BYTES = 256 * 1024
MAX_REDIRECTS = 2
MAX_RETRIES = 2
DEFAULT_REQUEST_TIMEOUT = 1.0
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_ULA_NETWORK = ipaddress.ip_network("fc00::/7")


class FetchError(RuntimeError):
    """Sanitized fetch failure; never includes a URL, body, or raw exception text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceConfig:
    provider_id: str
    source_id: str
    base_url: str
    allowed_ips: frozenset[str]


@dataclass(frozen=True, slots=True)
class _ValidatedSource:
    provider_id: str
    source_id: str
    base_url: str
    scheme: str
    host: str
    port: int
    base_path: str
    allowed_ips: frozenset[str]

    @property
    def host_key(self) -> str:
        return f"{self.host}:{self.port}"


Resolver = Callable[[str, int], Awaitable[tuple[str, ...]]]
Observer = Any


def _emit(observer: Observer | None, method: str, name: str, value: Any, labels: dict[str, str]) -> None:
    if observer is None:
        return
    try:
        if method == "increment":
            getattr(observer, method)(name, labels, value)
        else:
            getattr(observer, method)(name, value, labels)
    except Exception:
        # Instrumentation must never affect crawling.
        return


def _decoded_path(path: str) -> str:
    decoded = path
    for _ in range(8):
        unescaped = unquote(decoded)
        if unescaped == decoded:
            break
        decoded = unescaped
    # A remaining escape could hide a traversal segment from a second decoder.
    if "%" in decoded or "\\" in decoded:
        raise ValueError("encoded fixture path is not canonical")
    return decoded


def _is_fixture_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.is_loopback:
        return True
    if address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified:
        return False
    if isinstance(address, ipaddress.IPv4Address):
        return any(address in network for network in _RFC1918_NETWORKS)
    return address in _ULA_NETWORK


def _normalize_source(config: SourceConfig) -> _ValidatedSource:
    try:
        provider_id = validate_id(config.provider_id, name="provider_id")
        source_id = validate_source_id(config.source_id)
    except InsuranceValidationError as exc:
        raise ValueError("invalid configured source identity") from exc
    parsed = urlsplit(config.base_url)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("fixture sources must be credential-free HTTP origins")
    try:
        port = parsed.port or 80
    except ValueError as exc:
        raise ValueError("invalid fixture source port") from exc
    if not 1 <= port <= 65535:
        raise ValueError("invalid fixture source port")
    host = parsed.hostname.rstrip(".").lower()
    if not host or len(host) > 253:
        raise ValueError("invalid fixture source host")
    try:
        host = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("invalid fixture source host") from exc
    base_path = parsed.path or "/"
    if not base_path.startswith("/") or "\\" in base_path:
        raise ValueError("invalid fixture source path")
    decoded_segments = _decoded_path(base_path).split("/")
    if any(segment in {".", ".."} for segment in decoded_segments):
        raise ValueError("invalid fixture source path")
    if not base_path.endswith("/"):
        base_path += "/"
    addresses: set[str] = set()
    if not config.allowed_ips:
        raise ValueError("fixture source needs pinned addresses")
    for raw_ip in config.allowed_ips:
        try:
            address = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise ValueError("invalid fixture source address") from exc
        if not _is_fixture_address(address):
            raise ValueError("fixture addresses must be explicitly isolated private targets")
        addresses.add(address.compressed)
    base_url = urlunsplit(("http", _authority(host, port), base_path, "", ""))
    return _ValidatedSource(
        provider_id=provider_id,
        source_id=source_id,
        base_url=base_url,
        scheme="http",
        host=host,
        port=port,
        base_path=base_path,
        allowed_ips=frozenset(addresses),
    )


def _authority(host: str, port: int) -> str:
    shown_host = f"[{host}]" if ":" in host else host
    return shown_host if port == 80 else f"{shown_host}:{port}"


class AllowlistedFetcher:
    """Fetch only pages under explicitly configured synthetic fixture origins."""

    def __init__(
        self,
        sources: tuple[SourceConfig, ...] | list[SourceConfig],
        *,
        observer: Observer | None = None,
        concurrency: int = 4,
        per_host_concurrency: int = 2,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        max_redirects: int = MAX_REDIRECTS,
        retries: int = MAX_RETRIES,
        resolver: Resolver | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not 1 <= concurrency <= 8 or not 1 <= per_host_concurrency <= 2:
            raise ValueError("crawler concurrency exceeds the reviewed bounds")
        if not 0 < request_timeout <= DEFAULT_REQUEST_TIMEOUT:
            raise ValueError("request timeout exceeds the reviewed bound")
        if not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES:
            raise ValueError("response size exceeds the reviewed bound")
        if not 0 <= max_redirects <= MAX_REDIRECTS or not 0 <= retries <= MAX_RETRIES:
            raise ValueError("redirect or retry count exceeds the reviewed bound")
        normalized = tuple(_normalize_source(source) for source in sources)
        if not normalized or len({source.source_id for source in normalized}) != len(normalized):
            raise ValueError("fixture source IDs must be configured and unique")
        self._sources = {source.source_id: source for source in normalized}
        self._providers: dict[str, list[_ValidatedSource]] = {}
        for source in normalized:
            self._providers.setdefault(source.provider_id, []).append(source)
        self._observer = observer
        self.concurrency = concurrency
        self.per_host_concurrency = per_host_concurrency
        self._global = asyncio.Semaphore(concurrency)
        self._per_host_limit = per_host_concurrency
        self._per_host: dict[str, asyncio.Semaphore] = {}
        self._request_timeout = request_timeout
        self._max_response_bytes = max_response_bytes
        self._max_redirects = max_redirects
        self._retries = retries
        self._retry_counts: dict[tuple[str, str], int] = {}
        self._resolver = resolver or self._resolve_dns
        self._sleep = sleep
        self._jitter = jitter or (lambda: random.uniform(0.1, 0.5))
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Encoding": "identity",
                "User-Agent": "PulseGrid-Synthetic-Insurance-Crawler/1.0",
            },
        )

    async def __aenter__(self) -> "AllowlistedFetcher":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def consume_retry_count(self, source_id: str, relative_path: str) -> int:
        key = (source_id, relative_path)
        return self._retry_counts.pop(key, 0)

    def host_key(self, source_id: str) -> str:
        source = self._source(source_id)
        return source.host_key

    def sources_for_provider(self, provider_id: Any) -> tuple[_ValidatedSource, ...]:
        normalized_id = validate_id(provider_id, name="provider_id")
        return tuple(self._providers.get(normalized_id, ()))

    def assert_provider_source(self, provider_id: Any, source_id: str, configured_url: str) -> None:
        normalized_id = validate_id(provider_id, name="provider_id")
        source = self._source(source_id)
        normalized_url = _normalize_source(
            SourceConfig(normalized_id, source_id, configured_url, source.allowed_ips)
        )
        if source.provider_id != normalized_id or normalized_url.base_url != source.base_url:
            raise FetchError("source_not_allowlisted")

    def resolve_link(self, source_id: str, current_path: str, href: str) -> str:
        source = self._source(source_id)
        if not isinstance(href, str) or not href or len(href) > 2048:
            raise FetchError("source_not_allowlisted")
        raw = urlsplit(href)
        if raw.scheme or raw.netloc or raw.query or raw.fragment or "\\" in href:
            raise FetchError("source_not_allowlisted")
        current = self._normalize_path(source, current_path)
        candidate = urlsplit(urljoin(f"http://fixture.invalid{current}", href))
        return self._normalize_path(source, candidate.path)

    async def fetch(self, source_id: str, relative_path: str) -> dict[str, Any]:
        source = self._source(source_id)
        path = self._normalize_path(source, relative_path)
        semaphore = self._per_host.setdefault(source.host_key, asyncio.Semaphore(self._per_host_limit))
        async with self._global, semaphore:
            started_ns = time.perf_counter_ns()
            try:
                response = await self._fetch_with_retries(source, path)
                _emit(self._observer, "increment", "pulsegrid_crawler_fetches_total", 1, {"owner": "billing", "outcome": "success"})
                return response
            except FetchError as exc:
                _emit(self._observer, "increment", "pulsegrid_crawler_fetches_total", 1, {"owner": "billing", "outcome": exc.code})
                raise
            finally:
                _emit(
                    self._observer,
                    "observe",
                    "pulsegrid_crawler_fetch_seconds",
                    (time.perf_counter_ns() - started_ns) / 1_000_000_000,
                    {"owner": "billing"},
                )

    async def _fetch_with_retries(self, source: _ValidatedSource, path: str) -> dict[str, Any]:
        url = urljoin(source.base_url, path)
        for attempt in range(self._retries + 1):
            try:
                response, retry_after = await self._request_redirects(source, url)
            except httpx.TimeoutException as exc:
                raise FetchError("request_timeout") from exc
            except (httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                if attempt >= self._retries:
                    raise FetchError("network_error") from exc
                await self._backoff(source.source_id, path, attempt, None)
                continue
            except FetchError as exc:
                # Validation, response-size, and redirect failures are never retried.
                raise exc
            status = response["status"]
            if status == 429 or 500 <= status <= 599:
                if attempt >= self._retries:
                    raise FetchError("upstream_status")
                await self._backoff(source.source_id, path, attempt, retry_after)
                continue
            return response
        raise FetchError("retry_exhausted")

    async def _backoff(self, source_id: str, path: str, attempt: int, retry_after: float | None) -> None:
        delay = self._jitter()
        if not 0.1 <= delay <= 0.5:
            delay = min(0.5, max(0.1, delay))
        if retry_after is not None:
            delay = max(delay, retry_after)
        key = (source_id, path)
        if key not in self._retry_counts and len(self._retry_counts) >= 4096:
            self._retry_counts.pop(next(iter(self._retry_counts)))
        self._retry_counts[key] = self._retry_counts.get(key, 0) + 1
        _emit(self._observer, "increment", "pulsegrid_crawler_retries_total", 1, {"owner": "billing", "outcome": "scheduled"})
        await self._sleep(delay)

    async def _request_redirects(self, source: _ValidatedSource, original_url: str) -> tuple[dict[str, Any], float | None]:
        current_url = original_url
        for redirect_count in range(self._max_redirects + 1):
            target_url, pinned_ip = await self._validate_and_pin(source, current_url)
            headers = {"Host": _authority(source.host, source.port)}
            request = self._client.build_request("GET", target_url, headers=headers)
            response = await self._client.send(request, stream=True, follow_redirects=False)
            location = response.headers.get("location")
            retry_after = self._retry_after(response.headers.get("retry-after"))
            if response.status_code in {301, 302, 303, 307, 308}:
                await response.aclose()
                if not location or redirect_count >= self._max_redirects:
                    raise FetchError("redirect_limit")
                candidate = urljoin(current_url, location)
                # Validate every redirect before connecting to its destination.
                await self._validate_and_pin(source, candidate)
                current_url = candidate
                continue
            encoding = response.headers.get("content-encoding", "identity").strip().lower()
            if encoding not in {"", "identity"}:
                await response.aclose()
                raise FetchError("unsupported_content_encoding")
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > self._max_response_bytes:
                        await response.aclose()
                        raise FetchError("response_too_large")
                except ValueError:
                    await response.aclose()
                    raise FetchError("invalid_content_length")
            body = bytearray()
            try:
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self._max_response_bytes:
                        raise FetchError("response_too_large")
            finally:
                await response.aclose()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if response.status_code < 400 and content_type not in {"text/html", "application/xhtml+xml"}:
                raise FetchError("unsupported_content_type")
            return {
                "body": bytes(body),
                "status": response.status_code,
                "headers": {key.lower(): value for key, value in response.headers.items()},
            }, retry_after
        raise FetchError("redirect_limit")

    async def _validate_and_pin(self, source: _ValidatedSource, url: str) -> tuple[str, str]:
        parsed = urlsplit(url)
        try:
            port = parsed.port or 80
        except ValueError as exc:
            raise FetchError("source_not_allowlisted") from exc
        if (
            parsed.scheme != "http"
            or parsed.hostname is None
            or parsed.hostname.rstrip(".").lower() != source.host
            or port != source.port
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.query
        ):
            raise FetchError("source_not_allowlisted")
        path = self._normalize_path(source, parsed.path or "/")
        try:
            resolved = await self._resolver(source.host, source.port)
        except Exception as exc:
            raise FetchError("source_resolution_failed") from exc
        if not resolved:
            raise FetchError("source_resolution_failed")
        canonical: set[str] = set()
        for raw_ip in resolved:
            try:
                canonical.add(ipaddress.ip_address(raw_ip).compressed)
            except ValueError as exc:
                raise FetchError("source_resolution_failed") from exc
        if not canonical or not canonical.issubset(source.allowed_ips):
            raise FetchError("source_not_allowlisted")
        pinned_ip = sorted(canonical)[0]
        target_host = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
        target_url = urlunsplit(("http", f"{target_host}:{source.port}", path, "", ""))
        return target_url, pinned_ip

    async def _resolve_dns(self, host: str, port: int) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        rows = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return tuple(dict.fromkeys(row[4][0] for row in rows))

    def _source(self, source_id: str) -> _ValidatedSource:
        if not isinstance(source_id, str) or source_id not in self._sources:
            raise FetchError("source_not_allowlisted")
        return self._sources[source_id]

    @staticmethod
    def _normalize_path(source: _ValidatedSource, path: str) -> str:
        if not isinstance(path, str) or not path or len(path) > 2048 or "\\" in path:
            raise FetchError("source_not_allowlisted")
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise FetchError("source_not_allowlisted")
        candidate = urljoin(source.base_url, path)
        target = urlsplit(candidate)
        try:
            decoded_segments = _decoded_path(target.path).split("/")
        except ValueError as exc:
            raise FetchError("source_not_allowlisted") from exc
        if any(segment in {".", ".."} for segment in decoded_segments):
            raise FetchError("source_not_allowlisted")
        normalized_path = target.path or "/"
        if not normalized_path.startswith(source.base_path):
            raise FetchError("source_not_allowlisted")
        return normalized_path

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
            except (TypeError, ValueError, OverflowError):
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0.0, (parsed.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds())
