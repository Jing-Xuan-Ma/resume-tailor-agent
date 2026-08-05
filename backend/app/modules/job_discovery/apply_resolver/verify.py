"""Lightweight apply-URL verification (HTTP + keyword check). No CAPTCHA bypass."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

VerifyKind = Literal["ok", "fail", "uncertain"]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_CLOSED_HINTS = (
    "no longer accepting",
    "job is closed",
    "position has been filled",
    "this job is no longer available",
    "job posting is no longer available",
    "page not found",
)


@dataclass
class VerifyResult:
    kind: VerifyKind
    detail: str
    status_code: int | None = None


def _tokens(title: str) -> list[str]:
    parts = re.findall(r"[a-z0-9]{3,}", (title or "").lower())
    # drop ultra-common words
    stop = {"the", "and", "for", "with", "job", "jobs", "role", "senior", "junior"}
    return [p for p in parts if p not in stop][:8]


def verify_apply_url(
    url: str,
    *,
    title: str | None = None,
    timeout_s: float = 12.0,
) -> VerifyResult:
    """Light verify: GET status + optional title keyword presence.

    Never tries to solve CAPTCHA / login walls — those return ``uncertain``.
    """
    raw = (url or "").strip()
    if not raw.lower().startswith(("http://", "https://")):
        return VerifyResult("fail", "not an http(s) URL")

    req = urllib.request.Request(
        raw,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            body = resp.read(120_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        code = exc.code
        if code in {401, 403, 429}:
            return VerifyResult("uncertain", f"HTTP {code} (auth/rate-limit/CAPTCHA wall)", code)
        if 400 <= code < 500:
            return VerifyResult("fail", f"HTTP {code}", code)
        return VerifyResult("uncertain", f"HTTP {code}", code)
    except Exception as exc:
        return VerifyResult("uncertain", f"request error: {exc}")

    if code and not (200 <= int(code) < 400):
        return VerifyResult("fail", f"HTTP {code}", int(code))

    low = body.lower()
    if any(h in low for h in _CLOSED_HINTS):
        return VerifyResult("fail", "page indicates job closed/unavailable", int(code) if code else None)

    # Login wall heuristics
    if ("sign in" in low or "log in" in low) and ("password" in low) and len(body) < 8000:
        return VerifyResult("uncertain", "possible login wall", int(code) if code else None)

    if title:
        toks = _tokens(title)
        if toks:
            hits = sum(1 for t in toks if t in low)
            need = max(1, min(2, len(toks) // 2))
            if hits < need:
                # SPA shells often lack keywords in first HTML byte — uncertain, not fail
                if len(body) < 2500 or "window.__" in body or "nomodule" in low:
                    return VerifyResult(
                        "uncertain",
                        f"SPA/empty shell; title tokens {hits}/{len(toks)}",
                        int(code) if code else None,
                    )
                return VerifyResult(
                    "fail",
                    f"title keywords missing ({hits}/{len(toks)})",
                    int(code) if code else None,
                )

    return VerifyResult("ok", f"HTTP {code} + content ok", int(code) if code else 200)
