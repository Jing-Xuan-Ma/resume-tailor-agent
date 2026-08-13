"""HTTP client for Jobright mini-sites list + job detail pages."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

LIST_URL = "https://jobright.ai/swan/mini-sites/list"
DETAIL_URL = "https://jobright.ai/jobs/info/{job_id}"
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.S,
)


class JobrightClient:
    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_UA,
        timeout: float = 45.0,
        sleep_s: float = 0.35,
        retries: int = 3,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.sleep_s = sleep_s
        self.retries = max(1, int(retries))

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        accept: str = "application/json",
    ) -> bytes:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
            "Origin": "https://www.intern-list.com",
            "Referer": "https://www.intern-list.com/",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        last_err: Exception | None = None
        for attempt in range(self.retries):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read()
                if self.sleep_s > 0:
                    time.sleep(self.sleep_s)
                return body
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "ignore")[:300]
                last_err = RuntimeError(f"HTTP {e.code} for {url}: {detail}")
                if e.code in {429, 500, 502, 503, 504} and attempt + 1 < self.retries:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                raise last_err from e
            except Exception as e:  # noqa: BLE001 - retry timeouts/network
                last_err = e
                if attempt + 1 < self.retries:
                    time.sleep(1.2 * (attempt + 1))
                    continue
                raise
        raise RuntimeError(f"request failed for {url}: {last_err}")

    def fetch_list_page(
        self,
        category: str,
        *,
        position: int = 0,
        count: int = 20,
    ) -> dict[str, Any]:
        """POST list API; pagination uses query params position/count (not body)."""
        qs = urllib.parse.urlencode({"position": int(position), "count": int(count)})
        url = f"{LIST_URL}?{qs}"
        raw = self._request(url, method="POST", payload={"category": category})
        body = json.loads(raw.decode("utf-8"))
        if not body.get("success"):
            raise RuntimeError(f"List API failed for {category}: {body}")
        return body.get("result") or {}

    def iter_list(
        self,
        category: str,
        *,
        limit: int = 1000,
        page_size: int = 20,
        max_pages: int | None = None,
        since_posted_at: int | None = None,
        stop_on_known_ids: set[str] | None = None,
        known_streak_stop: int = 8,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        """Fetch up to `limit` jobs for one category.

        List is newest-first. When `since_posted_at` is set, stop once items are
        older/equal to the watermark. When `stop_on_known_ids` is set, stop after
        `known_streak_stop` consecutive already-known ids (incremental mode).

        Returns (jobs, total, meta).
        """
        page_size = max(1, min(int(page_size), 50))
        limit = max(0, int(limit))
        if max_pages is not None and max_pages > 0:
            limit = min(limit, int(max_pages) * page_size)
        jobs: list[dict[str, Any]] = []
        seen: set[str] = set()
        total = 0
        position = 0
        pages = 0
        stopped_reason = "limit_or_end"
        known = stop_on_known_ids or set()
        known_streak = 0
        while len(jobs) < limit:
            result = self.fetch_list_page(category, position=position, count=page_size)
            pages += 1
            total = int(result.get("total") or 0)
            batch = result.get("jobList") or []
            if not batch:
                stopped_reason = "empty_page"
                break
            new_in_batch = 0
            hit_watermark = False
            for item in batch:
                job_id = str(item.get("jobId") or "").strip()
                if not job_id or job_id in seen:
                    continue
                posted_raw = item.get("postedAt")
                try:
                    posted_i = int(posted_raw) if posted_raw is not None else None
                except (TypeError, ValueError):
                    posted_i = None
                if since_posted_at is not None and posted_i is not None:
                    if posted_i <= since_posted_at:
                        hit_watermark = True
                        stopped_reason = "watermark"
                        break
                if job_id in known:
                    known_streak += 1
                    if known_streak >= known_streak_stop:
                        hit_watermark = True
                        stopped_reason = "known_streak"
                        break
                    continue
                known_streak = 0
                seen.add(job_id)
                jobs.append(item)
                new_in_batch += 1
                if len(jobs) >= limit:
                    stopped_reason = "limit"
                    break
            if hit_watermark or len(jobs) >= limit:
                break
            if new_in_batch == 0 and not known:
                stopped_reason = "no_new_in_page"
                break
            position += len(batch)
            if max_pages is not None and pages >= max_pages:
                stopped_reason = "max_pages"
                break
            if position >= total:
                stopped_reason = "end"
                break
        return jobs[:limit], total, {
            "pages": pages,
            "position": position,
            "stopped_reason": stopped_reason,
        }

    def fetch_detail(self, job_id: str) -> dict[str, Any]:
        """GET /jobs/info/{jobId} and parse props.pageProps.dataSource."""
        url = DETAIL_URL.format(job_id=job_id)
        html = self._request(url, method="GET", accept="text/html").decode("utf-8", "ignore")
        m = _NEXT_DATA_RE.search(html)
        if not m:
            raise RuntimeError(f"__NEXT_DATA__ missing for job {job_id}")
        next_data = json.loads(m.group(1))
        page_props = (next_data.get("props") or {}).get("pageProps") or {}
        data_source = page_props.get("dataSource")
        if not isinstance(data_source, dict):
            raise RuntimeError(f"dataSource missing for job {job_id}")
        return {
            "job_id": job_id,
            "detail_url": url,
            "data_source": data_source,
            "page_props": page_props,
        }
