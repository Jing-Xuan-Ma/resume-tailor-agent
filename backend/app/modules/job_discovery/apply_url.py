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

# Company info / social / directories — never treat as apply targets.
# Note: do NOT put bare "tiktok.com" here — substring match would reject
# careers.tiktok.com / lifeattiktok.com career deep links.
_NON_APPLY_HOST_PARTS = (
    "crunchbase.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "glassdoor.com",
    "levels.fyi",
    "bloomberg.com",
    "businesswire.com",
    "prnewswire.com",
    "wikipedia.org",
)

# Exact social / marketing hosts (not careers ATS).
_NON_APPLY_EXACT_HOSTS = frozenset(
    {
        "tiktok.com",
        "www.tiktok.com",
        "m.tiktok.com",
        "vm.tiktok.com",
    }
)


def normalize_apply_url(url: str | None) -> str | None:
    """Clean markdown/Indeed escapes so URLs parse and open correctly.

    Indeed JD bodies often contain ``https://rb.wd5\\.myworkdayjobs.com/FRS`` —
    the backslash breaks the host (browser may show ``rb.wd5/.myworkdayjobs...``)
    and causes ERR_CONNECTION_CLOSED.
    """
    raw = (url or "").strip()
    if not raw:
        return None
    # Markdown / JobSpy escapes: \. \- \_
    cleaned = re.sub(r"\\([.\-_])", r"\1", raw)
    cleaned = cleaned.strip().rstrip(".,;)")
    if not cleaned.lower().startswith(("http://", "https://")):
        return None
    # Reject obviously broken hosts (backslash leftovers)
    try:
        host = urlparse(cleaned).hostname or ""
    except Exception:
        return None
    if not host or "\\" in host or "\\" in cleaned.split("://", 1)[-1].split("/", 1)[0]:
        return None
    return cleaned


def _host(url: str | None) -> str:
    raw = normalize_apply_url(url) or ""
    if not raw:
        return ""
    try:
        return urlparse(raw).hostname.lower() or ""
    except Exception:
        return ""


def _path_parts(url: str | None) -> list[str]:
    raw = normalize_apply_url(url) or ""
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


def _is_non_apply_host(host: str) -> bool:
    if not host:
        return False
    if host in _NON_APPLY_EXACT_HOSTS:
        return True
    return any(part in host for part in _NON_APPLY_HOST_PARTS)


def is_usable_job_apply_url(url: str | None) -> bool:
    """True if URL looks like a real job apply page (not a dead career-site root)."""
    raw = normalize_apply_url(url)
    if not raw:
        return False
    host = _host(raw)
    if not host:
        return False
    if _is_non_apply_host(host):
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

    # Non-ATS company sites need a careers/jobs path signal
    if not any(part in host for part in _ATS_HOST_PARTS):
        careerish = any(
            k in lower
            for k in (
                "/job",
                "/jobs",
                "/career",
                "/careers",
                "/apply",
                "/position",
                "/resume/",
                "/search/",  # lifeattiktok.com/search/<id>
            )
        )
        if host.endswith("lifeattiktok.com") or host.startswith("careers.tiktok."):
            careerish = careerish or "/search/" in lower or "/resume/" in lower
        if not careerish:
            return False

    return True


def is_ats_or_company_apply_url(url: str | None) -> bool:
    host = _host(url)
    if not host or is_aggregator_url(url):
        return False
    if _is_non_apply_host(host):
        return False
    # TikTok / ByteDance proprietary career sites
    if "lifeattiktok.com" in host or host.startswith("careers.tiktok.com"):
        return is_usable_job_apply_url(url)
    if any(part in host for part in _ATS_HOST_PARTS):
        return True
    # Company career page only when path looks like jobs/careers/apply
    return is_usable_job_apply_url(url)


def prefer_official_apply_url(
    *candidates: str | None,
    board_fallback: str | None = None,
) -> str | None:
    """Pick the best URL to open for Apply (usable company ATS first, board last)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in candidates:
        u = normalize_apply_url(raw)
        if not u or u in seen:
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
    fb = normalize_apply_url(board_fallback)
    if fb and (is_aggregator_url(fb) or is_usable_job_apply_url(fb)):
        return fb
    for u in ordered:
        if is_aggregator_url(u):
            return u
    # Never return thin Workday / other unusable ATS as a last resort — caller
    # should show "no link" rather than open a known-dead page.
    for u in ordered:
        if is_usable_job_apply_url(u):
            return u
    return fb if fb and is_aggregator_url(fb) else None


def listing_board_url(listing: dict | None) -> str | None:
    if not listing:
        return None
    meta = listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {}
    for key in ("board_url", "job_url", "jobright_url", "page_url"):
        u = normalize_apply_url(str(meta.get(key) or ""))
        if u and is_aggregator_url(u):
            return u
    source = normalize_apply_url(str(listing.get("source_url") or ""))
    if source and is_aggregator_url(source):
        return source
    return None


def _thin_or_hint_ats_urls(listing: dict) -> list[str]:
    """Collect ATS clues (including thin Workday roots) for the resolver."""
    meta = listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {}
    out: list[str] = []
    seen: set[str] = set()
    for raw in (
        meta.get("apply_url"),
        meta.get("job_url_direct"),
        listing.get("source_url"),
        meta.get("career_url"),
    ):
        u = normalize_apply_url(str(raw or ""))
        if not u or u in seen:
            continue
        host = _host(u)
        if any(p in host for p in _ATS_HOST_PARTS) or "myworkdayjobs" in host:
            seen.add(u)
            out.append(u)
    # Markdown-escaped career roots in JD body
    scan = re.sub(r"\\([.\-_])", r"\1", str(listing.get("raw_text") or ""))
    for m in re.finditer(
        r"https?://[^\s)\"']*(?:myworkdayjobs\.com|greenhouse\.io|lever\.co)/[^\s)\"']*",
        scan,
        re.I,
    ):
        u = normalize_apply_url(m.group(0))
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _try_resolve_deep_link(listing: dict) -> tuple[str | None, dict | None]:
    """Run Apply URL Resolver when no usable deep link is on file.

    Returns (url, resolve_meta) where resolve_meta is stored into listing metadata
    by callers that persist; here we only return it for apply_flow / tests.
    """
    from app.modules.job_discovery.apply_resolver import resolve_apply_url
    from app.modules.job_discovery.apply_resolver.models import ResolveStatus

    hints: dict = {}
    thin_list = _thin_or_hint_ats_urls(listing)
    if thin_list:
        hints["thin_workday_url"] = thin_list[0]
        hints["apply_url"] = thin_list[0]
        hints["career_url"] = thin_list[0]
    meta = listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {}
    for k in ("ats_platform", "ats_org", "platform", "tenant", "site", "host", "wd"):
        if meta.get(k):
            hints[k] = meta.get(k)
    if meta.get("ats_platform"):
        hints["platform"] = meta.get("ats_platform")
    if meta.get("ats_org"):
        hints.setdefault("tenant", meta.get("ats_org"))

    result = resolve_apply_url(
        company=str(listing.get("company") or "") or None,
        title=str(listing.get("title") or "") or None,
        location=str(listing.get("location") or "") or None,
        raw_text=str(listing.get("raw_text") or "") or None,
        hints=hints,
        verify=True,
    )
    info = result.to_dict()
    if result.status in {ResolveStatus.VERIFIED, ResolveStatus.UNVERIFIED} and result.url:
        if is_usable_job_apply_url(result.url):
            return result.url, info
    return None, info


def resolve_listing_apply_url(listing: dict | None) -> str | None:
    """From a job_listings row (or handoff-shaped dict), prefer official apply URL.

    Order:
      1) Usable deep link already on file (Jobright Apply / JobSpy direct / JD)
      2) Apply URL Resolver (Workday/Greenhouse/Lever JSON APIs)
      3) Board / aggregator fallback
    """
    if not listing:
        return None
    meta = listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {}
    platform = str(listing.get("source_platform") or meta.get("source_platform") or "").lower()
    apply = normalize_apply_url(str(meta.get("apply_url") or ""))
    source = normalize_apply_url(str(listing.get("source_url") or ""))
    board = listing_board_url(listing)
    direct = normalize_apply_url(str(meta.get("job_url_direct") or ""))
    from_jd = _extract_ats_url_from_text(str(listing.get("raw_text") or ""))

    # --- 1) Existing usable deep links ---
    if apply and (
        "jobright" in platform
        or meta.get("has_external_apply")
        or "utm_source=jobright" in apply.lower()
    ):
        if is_usable_job_apply_url(apply):
            return apply

    if (
        "jobright" in platform
        and source
        and "jobright.ai" not in source.lower()
        and is_usable_job_apply_url(source)
    ):
        return source

    preferred = prefer_official_apply_url(
        apply if apply and is_usable_job_apply_url(apply) else None,
        direct if direct and is_usable_job_apply_url(direct) else None,
        from_jd,
        source if source and not is_aggregator_url(source) and is_usable_job_apply_url(source) else None,
        board_fallback=None,  # hold board until after resolver
    )
    if preferred and is_usable_job_apply_url(preferred) and not is_aggregator_url(preferred):
        return preferred

    # --- 2) Resolver (only when deep link missing / unusable) ---
    resolved, resolve_info = _try_resolve_deep_link(listing)
    if isinstance(meta, dict) and resolve_info:
        # Annotate in-memory only; persist happens if upsert path copies metadata
        meta["apply_resolve"] = resolve_info
    if resolved:
        return resolved

    # --- 3) Board fallback ---
    return prefer_official_apply_url(
        preferred,
        apply,
        direct,
        from_jd,
        source if source and not is_aggregator_url(source) else None,
        board,
        source,
        board_fallback=board or source,
    )


_ATS_IN_TEXT = re.compile(
    r"https?://(?:(?:boards(?:-api)?|job-boards)\.)?greenhouse\.io/[^\s)\"'\\]+"
    r"|https?://jobs\.lever\.co/[^\s)\"'\\]+"
    r"|https?://(?:jobs|apply)\.ashbyhq\.com/[^\s)\"'\\]+"
    # Allow markdown-escaped dots in host (Indeed JobSpy bodies); normalize later.
    r"|https?://[^\s)\"']*myworkdayjobs(?:\\)?\.(?:com)/[^\s)\"'/\\]+(?:/[^\s)\"'\\]+)+"
    r"|https?://[^\s)\"'\\]+\.icims\.com/[^\s)\"'\\]+",
    re.I,
)


def _extract_ats_url_from_text(text: str) -> str | None:
    if not text:
        return None
    # Normalize common markdown escapes before scanning so hosts parse cleanly.
    scan = re.sub(r"\\([.\-_])", r"\1", text)
    for m in _ATS_IN_TEXT.finditer(scan):
        u = normalize_apply_url(m.group(0))
        if u and is_usable_job_apply_url(u):
            return u
    return None
