"""Workday CXS JSON job search adapter."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from app.modules.job_discovery.apply_resolver.adapters.base import AtsSearchAdapter
from app.modules.job_discovery.apply_resolver.models import ApplyCandidate

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# https://rb.wd5.myworkdayjobs.com/FRS
# https://rb.wd5.myworkdayjobs.com/en-US/FRS/...
_WORKDAY_HOST = re.compile(
    r"^(?P<tenant>[a-z0-9-]+)\.wd(?P<wd>\d+)\.myworkdayjobs\.com$",
    re.I,
)
_SITE_FROM_PATH = re.compile(r"^/(?:[a-z]{2}-[A-Z]{2}/)?(?P<site>[^/]+)", re.I)


def parse_workday_career_url(url: str | None) -> dict[str, Any] | None:
    raw = (url or "").strip()
    if not raw.lower().startswith(("http://", "https://")):
        return None
    try:
        parsed = urlparse(raw)
    except Exception:
        return None
    host = (parsed.hostname or "").lower()
    m = _WORKDAY_HOST.match(host)
    if not m:
        return None
    path = parsed.path or "/"
    sm = _SITE_FROM_PATH.match(path)
    site = sm.group("site") if sm else None
    if not site or site.lower() in {"job", "jobs", "wday"}:
        return None
    # Drop locale-looking segments already handled; reject CXS path segments
    if site.lower() == "wday":
        return None
    return {
        "platform": "workday",
        "tenant": m.group("tenant").lower(),
        "wd": m.group("wd"),
        "site": site,
        "host": host,
        "career_url": f"https://{host}/{site}",
    }


class WorkdayAdapter(AtsSearchAdapter):
    name = "workday"

    def detect_hints(self, hints: dict[str, Any]) -> dict[str, Any] | None:
        for key in ("career_url", "apply_url", "source_url", "job_url_direct", "thin_workday_url"):
            conn = parse_workday_career_url(str(hints.get(key) or ""))
            if conn:
                return conn
        # cached fields
        if hints.get("platform") == "workday" and hints.get("tenant") and hints.get("site"):
            host = hints.get("host") or f"{hints['tenant']}.wd{hints.get('wd') or '5'}.myworkdayjobs.com"
            return {
                "platform": "workday",
                "tenant": hints["tenant"],
                "wd": str(hints.get("wd") or "5"),
                "site": hints["site"],
                "host": host,
                "career_url": hints.get("career_url") or f"https://{host}/{hints['site']}",
            }
        # scan raw_text for any workday career root
        raw = str(hints.get("raw_text") or "")
        for m in re.finditer(r"https?://[^\s)\"']*myworkdayjobs\.com/[^\s)\"']+", raw, re.I):
            cleaned = re.sub(r"\\([.\-_])", r"\1", m.group(0)).rstrip(".,;)")
            conn = parse_workday_career_url(cleaned)
            if conn:
                return conn
        return None

    def career_search_url(self, connection: dict[str, Any], title: str) -> str | None:
        base = connection.get("career_url")
        if not base:
            return None
        from urllib.parse import quote

        return f"{base}?q={quote(title or '')}"

    def search(
        self,
        *,
        title: str,
        location: str | None = None,
        connection: dict[str, Any],
        limit: int = 20,
    ) -> list[ApplyCandidate]:
        tenant = connection["tenant"]
        site = connection["site"]
        host = connection["host"]
        api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        payload = {
            "appliedFacets": {},
            "limit": max(1, min(int(limit), 50)),
            "offset": 0,
            "searchText": title or "",
        }
        if location:
            # location facets vary by tenant; searchText usually enough
            pass
        last_err: Exception | None = None
        data: dict[str, Any] | None = None
        for attempt in range(3):
            req = urllib.request.Request(
                api,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "User-Agent": _UA,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=25) as resp:
                    raw = resp.read()
                data = json.loads(raw.decode("utf-8", "ignore"))
                last_err = None
                break
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"workday CXS HTTP {exc.code}") from exc
            except Exception as exc:
                last_err = exc
                continue
        if last_err is not None or data is None:
            raise RuntimeError(f"workday CXS error: {last_err}")

        postings = data.get("jobPostings") or []
        out: list[ApplyCandidate] = []
        for row in postings:
            if not isinstance(row, dict):
                continue
            path = str(row.get("externalPath") or "").strip()
            job_title = str(row.get("title") or "").strip()
            if not path or not job_title:
                continue
            if not path.startswith("/"):
                path = "/" + path
            # Prefer locale-prefixed deep link (works for FRS and most tenants)
            url = f"https://{host}/en-US/{site}{path}"
            bullets = row.get("bulletFields") or []
            req_id = None
            if isinstance(bullets, list) and bullets:
                req_id = str(bullets[0])
            elif isinstance(bullets, str):
                req_id = bullets
            out.append(
                ApplyCandidate(
                    title=job_title,
                    url=url,
                    req_id=req_id,
                    location=str(row.get("locationsText") or "") or None,
                    posted_on=str(row.get("postedOn") or "") or None,
                    adapter=self.name,
                    raw=row,
                )
            )
        return out
