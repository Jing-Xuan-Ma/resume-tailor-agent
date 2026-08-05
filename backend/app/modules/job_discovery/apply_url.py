"""Prefer company / ATS apply URLs over job-board aggregators (Indeed, etc.)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Aggregators / discovery boards — not the company application form.
_AGGREGATOR_HOST_PARTS = (
    "indeed.com",
    "indeed.",
    "linkedin.com",
    "ziprecruiter.com",
    "glassdoor.com",
    "monster.com",
    "simplyhired.com",
    "dice.com",
    "careerbuilder.com",
    "google.com",
    "bing.com",
    "jobright.ai",
)

# Known company ATS / career hosts — preferred for Apply.
_ATS_HOST_PARTS = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workday.com",
    "myworkdayjobs.com",
    "icims.com",
    "smartrecruiters.com",
    "jobvite.com",
    "bamboohr.com",
    "applytojob.com",
    "dover.io",
    "rippling.com",
    "greenhouse",
    "jobs.silkroad.com",
    "contacthr.com",
)


def _host(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw or not raw.lower().startswith(("http://", "https://")):
        return ""
    try:
        return urlparse(raw).hostname.lower() or ""
    except Exception:
        return ""


def _path_parts(url: str | None) -> list[str]:
    raw = (url or "").strip()
    if not raw:
        return []
    try:
        path = urlparse(raw).path or ""
    except Exception:
        return []
    return [p for p in path.split("/") if p]


def is_aggregator_url(url: str | None) -> bool:
    host = _host(url)
    if not host:
        return False
    return any(part in host for part in _AGGREGATOR_HOST_PARTS)


def is_usable_job_apply_url(url: str | None) -> bool:
    """True if URL looks like a real job apply page (not a dead career-site root)."""
    raw = (url or "").strip()
    if not raw or not raw.lower().startswith(("http://", "https://")):
        return False
    host = _host(raw)
    if not host:
        return False
    parts = _path_parts(raw)
    lower = raw.lower()
    parts_l = [p.lower() for p in parts]

    # Workday career roots like https://rb.wd5.myworkdayjobs.com/FRS often ERR_CONNECTION_CLOSED
    # or are not a specific job. Require a job segment or deeper path.
    if "myworkdayjobs.com" in host or host.endswith(".workday.com"):
        if "job" in parts_l:
            return True
        if any(p.startswith("jr") or p.startswith("r-") for p in parts_l):
            return True
        # e.g. /en-US/Careers/job/... needs depth; bare /FRS is not enough
        return len(parts) >= 3

    if "greenhouse.io" in host:
        return "jobs" in parts_l or "job_app" in lower or "embed" in parts_l

    if "lever.co" in host:
        return len(parts) >= 2

    if "ashbyhq.com" in host:
        return len(parts) >= 1

    if "icims.com" in host:
        return "job" in lower or len(parts) >= 2

    # Generic company homepage with no path — weak apply target
    if not parts and not is_aggregator_url(raw):
        return False

    return True


def is_ats_or_company_apply_url(url: str | None) -> bool:
    host = _host(url)
    if not host or is_aggregator_url(url):
        return False
    if any(part in host for part in _ATS_HOST_PARTS):
        return True
    # Non-aggregator http(s) career page — treat as company site.
    return True


def prefer_official_apply_url(
    *candidates: str | None,
    board_fallback: str | None = None,
) -> str | None:
    """Pick the best URL to open for Apply (usable company ATS first, board last)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in candidates:
        u = (raw or "").strip()
        if not u or not u.lower().startswith(("http://", "https://")):
            continue
        if u in seen:
            continue
        seen.add(u)
        ordered.append(u)

    # 1) Usable ATS / company apply pages
    for u in ordered:
        if (
            is_ats_or_company_apply_url(u)
            and not is_aggregator_url(u)
            and is_usable_job_apply_url(u)
        ):
            return u

    # 2) Any remaining usable non-aggregator
    for u in ordered:
        if not is_aggregator_url(u) and is_usable_job_apply_url(u):
            return u

    # 3) Board / aggregator fallback (Indeed etc. — usually opens even when Workday blocks)
    fb = (board_fallback or "").strip()
    if fb and fb.lower().startswith(("http://", "https://")):
        return fb
    for u in ordered:
        if is_aggregator_url(u):
            return u
    for u in ordered:
        return u
    return None


def listing_board_url(listing: dict | None) -> str | None:
    if not listing:
        return None
    meta = listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {}
    for key in ("board_url", "job_url"):
        u = str(meta.get(key) or "").strip()
        if u.lower().startswith(("http://", "https://")) and is_aggregator_url(u):
            return u
    source = str(listing.get("source_url") or "").strip()
    if source and is_aggregator_url(source):
        return source
    return None


def resolve_listing_apply_url(listing: dict | None) -> str | None:
    """From a job_listings row (or handoff-shaped dict), prefer official apply URL.

    Jobright-imported jobs: trust metadata.apply_url verbatim — that is the same
    company Apply link Jobright opens (Greenhouse / Workday / …).
    """
    if not listing:
        return None
    meta = listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {}
    platform = str(listing.get("source_platform") or meta.get("source_platform") or "").lower()
    apply = str(meta.get("apply_url") or "").strip()
    source = listing.get("source_url")
    board = listing_board_url(listing)

    # Jobright already resolved the company Apply destination — use it as-is.
    if apply.lower().startswith(("http://", "https://")) and (
        "jobright" in platform
        or meta.get("has_external_apply")
        or "utm_source=jobright" in apply.lower()
    ):
        return apply

    # Also trust a non-Jobright source_url that was stamped from Jobright Apply.
    src = str(source or "").strip()
    if (
        "jobright" in platform
        and src.lower().startswith(("http://", "https://"))
        and "jobright.ai" not in src.lower()
    ):
        return src

    from_jd = _extract_ats_url_from_text(str(listing.get("raw_text") or ""))
    return prefer_official_apply_url(
        meta.get("apply_url"),
        meta.get("job_url_direct"),
        from_jd,
        source if not is_aggregator_url(source) else None,
        board,
        source,
        board_fallback=board or source,
    )



_ATS_IN_TEXT = re.compile(
    r"https?://(?:(?:boards(?:-api)?|job-boards)\.)?greenhouse\.io/[^\s)\"']+"
    r"|https?://jobs\.lever\.co/[^\s)\"']+"
    r"|https?://(?:jobs|apply)\.ashbyhq\.com/[^\s)\"']+"
    r"|https?://[^\s)\"']*myworkdayjobs\.com/[^\s)\"'/]+(?:/[^\s)\"']+)+"
    r"|https?://[^\s)\"']+\.icims\.com/[^\s)\"']+",
    re.I,
)


def _extract_ats_url_from_text(text: str) -> str | None:
    if not text:
        return None
    for m in _ATS_IN_TEXT.finditer(text):
        u = m.group(0).rstrip(".,;")
        if is_usable_job_apply_url(u):
            return u
    return None
