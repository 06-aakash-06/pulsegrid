"""Optional crawler health; failures never change Billing readiness."""

from __future__ import annotations

from typing import Any


async def health(ports: Any = None) -> dict[str, str | None]:
    """Return local crawler state without exposing URLs, rows, or error text."""
    if ports is None or not getattr(ports, "enabled", False):
        return {"state": "disabled", "reason": "crawler_disabled"}
    repository = getattr(ports, "repository", None)
    latest_state = getattr(repository, "latest_run_state", None)
    if latest_state is None:
        return {"state": "degraded", "reason": "run_status_unavailable"}
    try:
        state = latest_state()
        if hasattr(state, "__await__"):
            state = await state
    except Exception:
        return {"state": "degraded", "reason": "run_status_unavailable"}
    if state in {"failed", "partial"}:
        return {"state": "degraded", "reason": "recent_crawl_failure"}
    return {"state": "ok", "reason": None}
