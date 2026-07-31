"""Orchestrator: run all job providers concurrently, deduplicate, score, rank."""

import asyncio
from typing import Any

from app import db
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


ALL_PROVIDERS: list[BaseJobProvider] = [
    JobSpyProvider(),
    RemotiveProvider(),
    RemoteOkProvider(),
    HimalayasProvider(),
    JobicyProvider(),
    AdzunaProvider(),
]

# Timeout for the entire discovery pipeline (wall clock). Individual HTTP
# providers also have their own shorter client timeouts.
DISCOVER_TIMEOUT = 25


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

    Returns:
        Normalized job dicts, sorted by match_score descending.
    """
    resume_text = ""
    if user_id:
        latest = db.get_latest_resume(user_id)
        if latest:
            raw = latest.get("raw_text") or ""
            parsed = latest.get("parsed") or {}
            resume_text = f"{raw} {' '.join(str(v) for v in parsed.values() if isinstance(v, str))}"

    loop = asyncio.get_running_loop()

    def _jobspy_sync() -> list[RawJobLead]:
        jsp = next(p for p in ALL_PROVIDERS if p.name == "jobspy")
        raw_jobs = jsp.discover(
            query=query,
            location=location,
            limit=limit * 3,
            sites=sites or ["linkedin", "indeed", "google"],
            hours_old=hours_old,
            country_indeed=country_indeed,
        )
        return [_to_lead(j) for j in raw_jobs]

    async def _run_jobspy() -> list[RawJobLead]:
        try:
            # Use the default executor (shared, bounded) instead of creating a
            # per-request ThreadPoolExecutor that leaks on timeout.
            return await loop.run_in_executor(None, _jobspy_sync)
        except Exception:
            return []

    async def _run_async(provider: BaseJobProvider) -> list[RawJobLead]:
        try:
            return await provider.discover(query=query, location=location, limit=limit * 2)
        except Exception:
            return []

    # Keep a stable task order matching ALL_PROVIDERS so dedup is deterministic.
    ordered_coros: list = []
    for provider in ALL_PROVIDERS:
        if provider.name == "jobspy":
            ordered_coros.append(_run_jobspy())
        else:
            ordered_coros.append(_run_async(provider))

    tasks = [asyncio.ensure_future(coro) for coro in ordered_coros]
    done, pending = await asyncio.wait(tasks, timeout=DISCOVER_TIMEOUT)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    unified: list[dict] = []
    seen: set[tuple] = set()
    # Iterate in original provider order (not set(done) order) for stable dedup.
    for task in tasks:
        if task not in done:
            continue
        try:
            leads = task.result() or []
        except Exception:
            continue
        for lead in leads:
            key = _dedup_key(lead)
            if key in seen:
                continue
            seen.add(key)
            item = _normalize(lead)
            item["match_score"] = score_job({"title": item["title"]}, query, resume_text=resume_text)
            unified.append(item)

    unified.sort(key=lambda x: x.get("match_score") or 0, reverse=True)
    high_quality = [j for j in unified if (j.get("match_score") or 0) >= min_score]
    return (high_quality or unified)[:limit]
