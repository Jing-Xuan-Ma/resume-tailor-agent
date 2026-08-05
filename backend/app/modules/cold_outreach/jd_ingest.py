"""Paste a JD URL → extract company / position / JD text for outreach scoring.

Supports Greenhouse, Lever, and LinkedIn Jobs URL patterns with a lightweight
HTTP fetch. Falls back to URL-slug parsing when the page cannot be fetched.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_OG_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_DESC = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_META_DESC = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    t = unescape(_TAG_RE.sub(" ", text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _parse_from_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = unquote(parsed.path or "")
    company = ""
    position = ""
    platform = "unknown"

    if "greenhouse.io" in host or "boards.greenhouse" in host:
        platform = "greenhouse"
        # boards.greenhouse.io/{company}/jobs/{id}
        # job-boards.greenhouse.io/{company}/jobs/{id}
        m = re.search(r"greenhouse\.io/([^/]+)/jobs/", host + path, re.I)
        if not m:
            m = re.search(r"/([^/]+)/jobs/\d+", path, re.I)
        if m:
            company = m.group(1).replace("-", " ").title()
    elif "lever.co" in host:
        platform = "lever"
        # jobs.lever.co/{company}/{id}
        m = re.search(r"lever\.co/([^/]+)", host + path, re.I)
        if m:
            company = m.group(1).replace("-", " ").title()
    elif "linkedin.com" in host:
        platform = "linkedin"
        # /jobs/view/data-analyst-at-acme-123456
        m = re.search(r"/jobs/view/([^/?#]+)", path, re.I)
        if m:
            slug = m.group(1)
            slug = re.sub(r"-\d+$", "", slug)
            if "-at-" in slug:
                role, _, firm = slug.partition("-at-")
                position = role.replace("-", " ").title()
                company = firm.replace("-", " ").title()
            else:
                position = slug.replace("-", " ").title()

    return {"company": company, "position": position, "platform": platform}


def _split_title(title: str) -> tuple[str, str]:
    """Best-effort 'Role at Company' / 'Role | Company' split."""
    t = _clean(title)
    for sep in (" at ", " | ", " - ", " — ", " · "):
        if sep in t:
            left, right = t.split(sep, 1)
            # strip site suffixes
            right = re.split(r"\s*[|\-–—]\s*(LinkedIn|Greenhouse|Lever|Jobs).*$", right, flags=re.I)[
                0
            ]
            return left.strip(), right.strip()
    return t, ""


async def ingest_jd_url(url: str, *, jd_text_override: str = "") -> dict[str, Any]:
    url = (url or "").strip()
    if not url:
        return {
            "ok": False,
            "error": "URL required",
            "company": "",
            "position": "",
            "jd_text": "",
            "platform": "unknown",
            "source_url": "",
        }
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    from_url = _parse_from_url(url)
    company = from_url.get("company") or ""
    position = from_url.get("position") or ""
    platform = from_url.get("platform") or "unknown"
    jd_text = (jd_text_override or "").strip()
    fetch_status = "skipped"
    page_title = ""

    try:
        async with httpx.AsyncClient(
            timeout=12.0,
            follow_redirects=True,
            headers={"User-Agent": "ResumeAgentOutreach/1.0 (+local; JD metadata only)"},
        ) as client:
            resp = await client.get(url)
            fetch_status = f"http_{resp.status_code}"
            if resp.status_code < 400:
                html = resp.text[:200_000]
                og = _OG_TITLE.search(html)
                title_m = _TITLE_RE.search(html)
                page_title = _clean((og.group(1) if og else "") or (title_m.group(1) if title_m else ""))
                role, firm = _split_title(page_title)
                if role and not position:
                    position = role
                if firm and not company:
                    company = firm
                if not jd_text:
                    desc = ""
                    for rx in (_OG_DESC, _META_DESC):
                        m = rx.search(html)
                        if m:
                            desc = _clean(m.group(1))
                            break
                    # Greenhouse often embeds job title in JSON-ish blobs — keep desc + title
                    jd_text = "\n\n".join(x for x in [page_title, desc] if x)
    except Exception as exc:  # noqa: BLE001
        fetch_status = f"error:{type(exc).__name__}"

    ok = bool(company or position or jd_text)
    return {
        "ok": ok,
        "error": None if ok else "Could not extract company/position — paste them manually",
        "company": company,
        "position": position,
        "jd_text": jd_text,
        "platform": platform,
        "source_url": url,
        "page_title": page_title,
        "fetch_status": fetch_status,
    }
