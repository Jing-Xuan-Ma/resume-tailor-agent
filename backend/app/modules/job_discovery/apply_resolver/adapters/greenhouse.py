"""Greenhouse boards public JSON API adapter."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.modules.job_discovery.apply_resolver.adapters.base import AtsSearchAdapter
from app.modules.job_discovery.apply_resolver.models import ApplyCandidate

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_BOARD_RE = re.compile(
    r"(?:boards(?:-api)?|job-boards)\.greenhouse\.io/(?:embed/job_app\?.*?for=)?(?P<board>[a-z0-9_-]+)",
    re.I,
)
_BOARD_PATH = re.compile(
    r"greenhouse\.io/(?P<board>[a-z0-9_-]+)(?:/jobs/|/job_app)",
    re.I,
)


def parse_greenhouse_board(url: str | None) -> dict[str, Any] | None:
    raw = (url or "").strip()
    if not raw or "greenhouse" not in raw.lower():
        return None
    m = _BOARD_RE.search(raw) or _BOARD_PATH.search(raw)
    board = m.group("board").lower() if m else None
    if not board or board in {"embed", "v1", "boards"}:
        # try query for=
        try:
            qs = parse_qs(urlparse(raw).query)
            board = (qs.get("for") or [None])[0]
        except Exception:
            board = None
    if not board:
        return None
    board = str(board).lower()
    return {
        "platform": "greenhouse",
        "tenant": board,
        "site": board,
        "host": "boards-api.greenhouse.io",
        "career_url": f"https://boards.greenhouse.io/{board}",
    }


class GreenhouseAdapter(AtsSearchAdapter):
    name = "greenhouse"

    def detect_hints(self, hints: dict[str, Any]) -> dict[str, Any] | None:
        for key in ("career_url", "apply_url", "source_url", "job_url_direct"):
            conn = parse_greenhouse_board(str(hints.get(key) or ""))
            if conn:
                return conn
        if hints.get("platform") == "greenhouse" and hints.get("tenant"):
            board = str(hints["tenant"])
            return {
                "platform": "greenhouse",
                "tenant": board,
                "site": board,
                "host": "boards-api.greenhouse.io",
                "career_url": f"https://boards.greenhouse.io/{board}",
            }
        raw = str(hints.get("raw_text") or "")
        for m in re.finditer(r"https?://[^\s)\"']*greenhouse\.io/[^\s)\"']+", raw, re.I):
            conn = parse_greenhouse_board(m.group(0).rstrip(".,;)"))
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
        board = connection["tenant"]
        api = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
        req = urllib.request.Request(
            api,
            headers={"Accept": "application/json", "User-Agent": _UA},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"greenhouse HTTP {exc.code}") from exc
        except Exception as exc:
            raise RuntimeError(f"greenhouse error: {exc}") from exc

        jobs = data.get("jobs") or []
        needle = (title or "").lower()
        out: list[ApplyCandidate] = []
        for row in jobs:
            if not isinstance(row, dict):
                continue
            job_title = str(row.get("title") or "").strip()
            abs_url = str(row.get("absolute_url") or "").strip()
            job_id = row.get("id")
            if not job_title or not abs_url:
                continue
            # Prefer title-relevant rows; still return broader list for scorer
            if needle and needle.split()[0] not in job_title.lower() and needle not in job_title.lower():
                # keep but scorer will rank; include all up to soft cap
                pass
            loc = None
            locs = row.get("location")
            if isinstance(locs, dict):
                loc = locs.get("name")
            elif isinstance(locs, str):
                loc = locs
            out.append(
                ApplyCandidate(
                    title=job_title,
                    url=abs_url,
                    req_id=str(job_id) if job_id is not None else None,
                    location=str(loc) if loc else None,
                    adapter=self.name,
                    raw=row,
                )
            )
            if len(out) >= max(limit * 3, 30):
                break
        return out
