"""Bounded worker tick for claimed Billing crawler runs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Mapping

from .crawler import execute_claimed_run

MAX_CLAIM_BATCH = 4
MAX_WORKER_CONCURRENCY = 4


async def worker_tick(ports: Any) -> None:
    """Claim at most four runs in a short transaction, then fetch outside locks."""
    if not getattr(ports, "enabled", True):
        return
    now = ports.now() if callable(getattr(ports, "now", None)) else datetime.now(timezone.utc)
    if hasattr(now, "__await__"):
        now = await now
    async with ports.read_session() as session:
        async with session.begin():
            claims = await ports.claim_runs(session, now, MAX_CLAIM_BATCH)
    if not claims:
        return

    semaphore = asyncio.Semaphore(MAX_WORKER_CONCURRENCY)
    repository = ports.repository
    fetcher = ports.fetcher
    observer = getattr(ports, "observer", None)

    async def run_one(claim: Mapping[str, Any]) -> None:
        async with semaphore:
            try:
                await execute_claimed_run(claim, fetcher, repository, observer)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                fail = getattr(repository, "fail_claim", None)
                if fail is not None:
                    code = getattr(exc, "code", "worker_error")
                    await fail(claim, code)
                if observer is not None:
                    try:
                        observer.increment(
                            "pulsegrid_crawler_worker_failures_total",
                            {"owner": "billing", "outcome": getattr(exc, "code", "worker_error")},
                        )
                    except Exception:
                        pass

    await asyncio.gather(*(run_one(claim) for claim in claims))
