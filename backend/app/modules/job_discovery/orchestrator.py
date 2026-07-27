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

    async def _run(provider: BaseJobProvider) -> list[RawJobLead]:
        if provider.name == "jobspy":
            jsp = provider  # type: ignore[assignment]
            raw_jobs = jsp.discover(
                query=query,
                location=location,
                limit=limit * 3,
                sites=sites,
                hours_old=hours_old,
                country_indeed=country_indeed,
            )
            return [_to_lead(j) for j in raw_jobs]
        return await provider.discover(query=query, location=location, limit=limit * 2)

    tasks = [_run(p) for p in ALL_PROVIDERS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    seen: set[tuple] = set()
    unified: list[dict] = []

    for r in results:
        if isinstance(r, Exception):
            continue
        for lead in r:
            key = _dedup_key(lead)
            if key in seen:
                continue
            seen.add(key)
            item = _normalize(lead)
            parsed_for_score = {"title": item["title"]}
            score = score_job(parsed_for_score, query, resume_text=resume_text)
            item["match_score"] = score
            unified.append(item)

    unified.sort(key=lambda x: x.get("match_score") or 0, reverse=True)
    cutoff = max(int(len(unified) * 0.3), limit)
    high_quality = [j for j in unified if (j.get("match_score") or 0) >= min_score]
    return (high_quality or unified)[:limit]
