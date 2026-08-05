"""Lever public postings JSON API adapter."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from app.modules.job_discovery.apply_resolver.adapters.base import AtsSearchAdapter
from app.modules.job_discovery.apply_resolver.models import ApplyCandidate

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_LEVER_RE = re.compile(r"jobs\.lever\.co/(?P<company>[a-z0-9_-]+)", re.I)


def parse_lever_company(url: str | None) -> dict[str, Any] | None:
    raw = (url or "").strip()
    if not raw or "lever.co" not in raw.lower():
        return None
    m = _LEVER_RE.search(raw)
    if not m:
        return None
    company = m.group("company").lower()
    return {
        "platform": "lever",
        "tenant": company,
        "site": company,
        "host": "api.lever.co",
        "career_url": f"https://jobs.lever.co/{company}",
    }


class LeverAdapter(AtsSearchAdapter):
    name = "lever"

    def detect_hints(self, hints: dict[str, Any]) -> dict[str, Any] | None:
        for key in ("career_url", "apply_url", "source_url", "job_url_direct"):
            conn = parse_lever_company(str(hints.get(key) or ""))
            if conn:
                return conn
        if hints.get("platform") == "lever" and hints.get("tenant"):
            company = str(hints["tenant"])
            return {
                "platform": "lever",
                "tenant": company,
                "site": company,
                "host": "api.lever.co",
                "career_url": f"https://jobs.lever.co/{company}",
            }
        raw = str(hints.get("raw_text") or "")
        for m in re.finditer(r"https?://jobs\.lever\.co/[^\s)\"']+", raw, re.I):
            conn = parse_lever_company(m.group(0).rstrip(".,;)"))
            if conn:
                return conn
        return None

    def career_search_url(self, connection: dict[str, Any], title: str) -> str | None:
        return connection.get("career_url")

    def search(
        self,
        *,
        title: str,
        location: str | None = None,
        connection: dict[str, Any],
        limit: int = 20,
    ) -> list[ApplyCandidate]:
        company = connection["tenant"]
        api = f"https://api.lever.co/v0/postings/{company}?mode=json"
        req = urllib.request.Request(
            api,
            headers={"Accept": "application/json", "User-Agent": _UA},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"lever HTTP {exc.code}") from exc
        except Exception as exc:
            raise RuntimeError(f"lever error: {exc}") from exc

        if not isinstance(data, list):
            data = []
        out: list[ApplyCandidate] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            job_title = str(row.get("text") or row.get("title") or "").strip()
            abs_url = str(row.get("hostedUrl") or row.get("applyUrl") or "").strip()
            job_id = row.get("id")
            if not job_title or not abs_url:
                continue
            cats = row.get("categories") if isinstance(row.get("categories"), dict) else {}
            loc = cats.get("location") if isinstance(cats, dict) else None
            out.append(
                ApplyCandidate(
                    title=job_title,
                    url=abs_url,
                    req_id=str(job_id) if job_id else None,
                    location=str(loc) if loc else None,
                    adapter=self.name,
                    raw=row,
                )
            )
            if len(out) >= max(limit * 3, 40):
                break
        return out
