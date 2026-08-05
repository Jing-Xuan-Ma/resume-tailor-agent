"""URL resolver re-export for standalone apply entrypoint."""

from __future__ import annotations

# Prefer existing job_discovery apply resolver when available.
try:
    from app.modules.job_discovery.apply_resolver.models import ResolveResult, ResolveStatus
except ImportError:  # pragma: no cover
    ResolveResult = None  # type: ignore
    ResolveStatus = None  # type: ignore


def resolve_apply_url(job: dict) -> str | None:
    """Return best resolved apply URL from job dict or nested resolver result."""
    for key in ("resolved_url", "apply_url", "url", "job_url"):
        val = job.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    nested = job.get("apply_resolve") or job.get("resolve_result") or {}
    if isinstance(nested, dict):
        url = nested.get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None
