"""Orchestrator: run all job providers concurrently, deduplicate, score, rank."""

import asyncio
import time
from copy import deepcopy
from typing import Any

from app import db
from app.config import settings
from app.modules.job_discovery.providers import (
    AdzunaProvider,
    BaseJobProvider,
    HimalayasProvider,
    JobicyProvider,
    JobSpyProvider,
    RawJobLead,
    RemoteOkProvider,
    RemotiveProvider,
)
from app.modules.job_discovery.scorer import score_job

# Short TTL cache: identical discover queries skip provider fan-out (Iter-7).
_DISCOVER_CACHE: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}
_DISCOVER_CACHE_TTL_SEC = 300.0


def _dedup_key(lead: RawJobLead | dict) -> tuple:
    if isinstance(lead, RawJobLead):
        title = (lead.title or "").strip().lower()
        company = (lead.company or "").strip().lower()
    else:
        title = (lead.get("title") or "").strip().lower()
        company = (lead.get("company") or "").strip().lower()
    return (title, company)


def _to_lead(d: dict) -> RawJobLead:
    return RawJobLead(
        title=d.get("title", "Untitled"),
        company=d.get("company"),
        location=d.get("location"),
        source_url=d.get("source_url"),
        source_platform=d.get("source_platform", "unknown"),
        description=d.get("raw_text", ""),
        metadata=d.get("metadata", {}),
    )


def _normalize(lead: RawJobLead | dict) -> dict:
    if isinstance(lead, RawJobLead):
        return lead.to_dict()
    return lead


def _default_jobspy_sites() -> list[str]:
    raw = (settings.JOB_INDEX_JOBSPY_SITES or "indeed").strip()
    return [s.strip() for s in raw.split(",") if s.strip()]


ALL_PROVIDERS: list[BaseJobProvider] = [
    RemotiveProvider(),
    HimalayasProvider(),
    JobicyProvider(),
    JobSpyProvider(),
    RemoteOkProvider(),
    AdzunaProvider(),
]


def _active_providers() -> list[BaseJobProvider]:
    providers = list(ALL_PROVIDERS)
    if not settings.JOB_INDEX_ENABLE_JOBSPY:
        providers = [p for p in providers if getattr(p, "name", "") != "jobspy"]
    if not settings.JOB_INDEX_ENABLE_ADZUNA:
        providers = [p for p in providers if getattr(p, "name", "") != "adzuna"]
    return providers


async def discover_all(
    *,
    query: str,
    location: str | None = None,
    limit: int = 5,
    min_score: float = 0.5,
    sites: list[str] | None = None,
    hours_old: int | None = None,
    country_indeed: str = "USA",
    user_id: str | None = None,
    skip_cache: bool = False,
    provider_stats: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run all providers concurrently, deduplicate, score against resume, rank.

    Args:
        query: Search query.
        location: Optional location filter.
        limit: Max jobs to return (after dedup + scoring).
        min_score: Minimum match score threshold (0-1).
        sites: JobSpy-specific site list.
        hours_old: JobSpy freshness filter.
        country_indeed: Indeed country code.
        user_id: If provided, use the user's latest resume for scoring.
        skip_cache: When True (ingest path), always hit providers.
        provider_stats: Optional mutable dict filled with per-provider counts/errors.

    Returns:
        Normalized job dicts, sorted by match_score descending.
    """
    cache_key = (
        (query or "").strip().lower(),
        (location or "").strip().lower(),
        int(limit),
        float(min_score),
        tuple(sites or ()),
        hours_old,
        country_indeed,
        user_id or "",
    )
    now = time.monotonic()
    if not skip_cache:
        cached = _DISCOVER_CACHE.get(cache_key)
        if cached and (now - cached[0]) < _DISCOVER_CACHE_TTL_SEC:
            if provider_stats is not None:
                provider_stats["cache_hit"] = True
            return deepcopy(cached[1])

    resume_text = ""
    if user_id:
        latest = db.get_latest_resume(user_id)
        if latest:
            raw = latest.get("raw_text") or ""
            parsed = latest.get("parsed") or {}
            resume_text = f"{raw} {' '.join(str(v) for v in parsed.values() if isinstance(v, str))}"

    jobspy_sites = sites or _default_jobspy_sites()

    async def _run(provider: BaseJobProvider) -> tuple[str, list[RawJobLead], str | None]:
        name = getattr(provider, "name", "unknown")
        try:
            if name == "jobspy":
                jsp = provider  # type: ignore[assignment]
                # JobSpy discover is sync (subprocess.run). Offload so uvicorn
                # keeps serving other requests while the child scrape runs.
                raw_jobs = await asyncio.to_thread(
                    jsp.discover,
                    query=query,
                    location=location,
                    # Cap JobSpy fan-out — boards are slow and crash-prone.
                    limit=min(max(int(limit), 5), 30),
                    sites=jobspy_sites,
                    hours_old=hours_old,
                    country_indeed=country_indeed,
                )
                err = getattr(jsp, "last_error", None)
                return name, [_to_lead(j) for j in raw_jobs], err
            leads = await provider.discover(query=query, location=location, limit=limit * 2)
            err = getattr(provider, "last_error", None)
            return name, leads, err
        except Exception as exc:  # noqa: BLE001
            return name, [], str(exc)

    tasks = [_run(p) for p in _active_providers()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set[tuple] = set()
    unified: list[dict] = []
    local_stats: dict[str, Any] = {}

    for r in results:
        if isinstance(r, Exception):
            local_stats["gather_error"] = str(r)
            continue
        name, leads, err = r
        local_stats[name] = {"count": len(leads), "error": err}
        for lead in leads:
            key = _dedup_key(lead)
            if key in seen:
                continue
            seen.add(key)
            item = _normalize(lead)
            # Score with title + JD body (not title-only).
            parsed_for_score = {
                "title": item.get("title") or "",
                "raw_text": (item.get("raw_text") or "")[:2500],
            }
            score = score_job(parsed_for_score, query, resume_text=resume_text)
            item["match_score"] = score
            unified.append(item)

    if provider_stats is not None:
        provider_stats.clear()
        provider_stats.update(local_stats)
        provider_stats["unified_before_limit"] = len(unified)
        provider_stats["jobspy_sites"] = jobspy_sites

    unified.sort(key=lambda x: x.get("match_score") or 0, reverse=True)
    high_quality = [j for j in unified if (j.get("match_score") or 0) >= min_score]
    result = (high_quality or unified)[:limit]
    if not skip_cache:
        _DISCOVER_CACHE[cache_key] = (now, deepcopy(result))
    return result
