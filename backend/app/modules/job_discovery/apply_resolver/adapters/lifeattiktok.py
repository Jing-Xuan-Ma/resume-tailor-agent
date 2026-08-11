"""TikTok / ByteDance LifeAtTikTok public job-search API adapter."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote

from app.modules.job_discovery.apply_resolver.adapters.base import AtsSearchAdapter
from app.modules.job_discovery.apply_resolver.models import ApplyCandidate

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_SEARCH_API = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"

_TIKTOK_HOST_RE = re.compile(
    r"(?:lifeattiktok\.com|careers\.tiktok\.com)",
    re.I,
)

_TIKTOK_COMPANIES = frozenset(
    {
        "tiktok",
        "bytedance",
        "byte dance",
        "tiktok inc",
        "tiktok us",
    }
)


def _connection() -> dict[str, Any]:
    return {
        "platform": "lifeattiktok",
        "tenant": "tiktok",
        "site": "tiktok",
        "host": "api.lifeattiktok.com",
        "career_url": "https://lifeattiktok.com/search",
    }


def parse_lifeattiktok_hint(url: str | None) -> dict[str, Any] | None:
    raw = (url or "").strip()
    if not raw or not _TIKTOK_HOST_RE.search(raw):
        return None
    return _connection()


class LifeAtTikTokAdapter(AtsSearchAdapter):
    name = "lifeattiktok"

    def detect_hints(self, hints: dict[str, Any]) -> dict[str, Any] | None:
        platform = str(hints.get("platform") or "").strip().lower()
        if platform in {"lifeattiktok", "tiktok", "bytedance"}:
            return _connection()

        company = str(hints.get("company") or "").strip().lower()
        if company in _TIKTOK_COMPANIES or company.startswith("tiktok"):
            return _connection()

        for key in ("career_url", "apply_url", "source_url", "job_url_direct"):
            conn = parse_lifeattiktok_hint(str(hints.get(key) or ""))
            if conn:
                return conn

        raw = str(hints.get("raw_text") or "")
        for m in re.finditer(
            r"https?://[^\s)\"']*(?:lifeattiktok\.com|careers\.tiktok\.com)[^\s)\"']*",
            raw,
            re.I,
        ):
            conn = parse_lifeattiktok_hint(m.group(0).rstrip(".,;)"))
            if conn:
                return conn
        return None

    def career_search_url(self, connection: dict[str, Any], title: str) -> str | None:
        base = str(connection.get("career_url") or "https://lifeattiktok.com/search")
        q = quote((title or "").strip())
        return f"{base}?keyword={q}&limit=12&offset=0" if q else base

    def search(
        self,
        *,
        title: str,
        location: str | None = None,
        connection: dict[str, Any],
        limit: int = 20,
    ) -> list[ApplyCandidate]:
        keyword = (title or "").strip()
        if not keyword:
            return []
        # API ranking is keyword-sensitive; shorten to distinctive phrase when long.
        if len(keyword) > 80:
            keyword = keyword[:80].rsplit(" ", 1)[0]

        body = json.dumps(
            {
                "recruitment_id_list": [],
                "job_category_id_list": [],
                "subject_id_list": [],
                "location_code_list": [],
                "keyword": keyword,
                "limit": max(1, min(int(limit or 20), 50)),
                "offset": 0,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            _SEARCH_API,
            data=body,
            headers={
                "Accept": "*/*",
                "Content-Type": "application/json",
                "Origin": "https://lifeattiktok.com",
                "Referer": "https://lifeattiktok.com/",
                "User-Agent": _UA,
                "website-path": "tiktok",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"lifeattiktok HTTP {exc.code}") from exc
        except Exception as exc:
            raise RuntimeError(f"lifeattiktok error: {exc}") from exc

        if int(data.get("code") or 0) != 0:
            raise RuntimeError(f"lifeattiktok api code={data.get('code')} msg={data.get('message')}")

        rows = ((data.get("data") or {}) if isinstance(data.get("data"), dict) else {}).get(
            "job_post_list"
        ) or []
        out: list[ApplyCandidate] = []
        loc_needle = (location or "").strip().lower()
        for row in rows:
            if not isinstance(row, dict):
                continue
            job_id = str(row.get("id") or "").strip()
            job_title = str(row.get("title") or "").strip()
            if not job_id or not job_title:
                continue
            city = ""
            city_info = row.get("city_info")
            if isinstance(city_info, dict):
                city = str(city_info.get("en_name") or city_info.get("i18n_name") or "").strip()
            if loc_needle and city and loc_needle.split(",")[0].strip() not in city.lower():
                # still include — scorer ranks; location filter is soft
                pass
            apply_url = f"https://careers.tiktok.com/resume/{job_id}/apply"
            out.append(
                ApplyCandidate(
                    title=job_title,
                    url=apply_url,
                    req_id=str(row.get("code") or job_id),
                    location=city or None,
                    adapter=self.name,
                    raw={
                        "id": job_id,
                        "code": row.get("code"),
                        "detail_url": f"https://lifeattiktok.com/search/{job_id}",
                    },
                )
            )
        return out
