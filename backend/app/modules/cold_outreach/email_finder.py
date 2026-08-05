"""Email lookup waterfall — user-initiated, single-person only.

Priority (design plan §3.2):
  1. Hunter.io email-finder / domain pattern (if HUNTER_API_KEY set)
  2. Local format inference from name + company domain (always available)
  3. Never batch-enumerate or SMTP-probe in a loop (anti-spam boundary)

Returns candidate emails with source + confidence for the user to pick.
SMTP verify is optional and only attempted once per address when enabled.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings

_EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", re.I)


def _slug_name(name: str) -> tuple[str, str]:
    parts = re.findall(r"[a-zA-Z]+", (name or "").strip())
    if not parts:
        return "", ""
    first = parts[0].lower()
    last = parts[-1].lower() if len(parts) > 1 else ""
    return first, last


def infer_company_domain(company: str = "", website: str = "") -> str:
    if website:
        raw = website.strip()
        if "://" not in raw:
            raw = "https://" + raw
        host = urlparse(raw).hostname or ""
        host = host.lower().removeprefix("www.")
        if host and "." in host:
            return host
    company = (company or "").strip().lower()
    if not company:
        return ""
    # crude: Acme Corp → acme.com (user can override)
    slug = re.sub(r"[^a-z0-9]+", "", company.split()[0] if company.split() else company)
    if len(slug) < 2:
        return ""
    return f"{slug}.com"


def _format_candidates(first: str, last: str, domain: str) -> list[dict[str, Any]]:
    if not first or not domain:
        return []
    patterns: list[tuple[str, str, str, float]] = []
    if last:
        patterns.extend(
            [
                (f"{first}.{last}@{domain}", "first.last", "Most common corporate pattern", 0.72),
                (f"{first}{last}@{domain}", "firstlast", "No-separator pattern", 0.48),
                (f"{first[0]}{last}@{domain}", "flast", "Initial + last", 0.55),
                (f"{first}_{last}@{domain}", "first_last", "Underscore pattern", 0.35),
                (f"{first}@{domain}", "first", "First-only (small companies)", 0.30),
            ]
        )
    else:
        patterns.append((f"{first}@{domain}", "first", "First-only (no last name)", 0.40))

    out: list[dict[str, Any]] = []
    for email, pattern, note, conf in patterns:
        if not _EMAIL_RE.match(email):
            continue
        level = "high" if conf >= 0.7 else "medium" if conf >= 0.5 else "low"
        out.append(
            {
                "email": email,
                "source": f"format_inference:{pattern}",
                "source_detail": note,
                "pattern": pattern,
                "confidence": conf,
                "confidence_label": level,
                "smtp_status": "not_checked",
                "recommendation": (
                    "Likely if this domain uses first.last"
                    if pattern == "first.last"
                    else "Lower confidence — prefer LinkedIn if unsure"
                ),
            }
        )
    return out


async def _hunter_email_finder(
    *,
    first: str,
    last: str,
    domain: str,
    full_name: str,
    company: str,
) -> list[dict[str, Any]]:
    api_key = (getattr(settings, "HUNTER_API_KEY", None) or "").strip()
    if not api_key or not domain:
        return []

    results: list[dict[str, Any]] = []
    params: dict[str, str] = {"domain": domain, "api_key": api_key}
    if first:
        params["first_name"] = first
    if last:
        params["last_name"] = last
    if full_name and not (first and last):
        params["full_name"] = full_name

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            # Email Finder
            r = await client.get("https://api.hunter.io/v2/email-finder", params=params)
            if r.status_code == 200:
                data = (r.json() or {}).get("data") or {}
                email = (data.get("email") or "").strip().lower()
                score = float(data.get("score") or 0) / 100.0
                if email and _EMAIL_RE.match(email):
                    level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
                    results.append(
                        {
                            "email": email,
                            "source": "hunter.io:email_finder",
                            "source_detail": f"Hunter score {int(score * 100)}; position={data.get('position') or 'n/a'}",
                            "pattern": data.get("pattern") or "",
                            "confidence": round(score, 2) if score else 0.65,
                            "confidence_label": level,
                            "smtp_status": "hunter_verified" if data.get("verification") else "unknown",
                            "recommendation": "Hunter hit — still confirm before sending",
                        }
                    )

            # Domain pattern (helps explain format inference)
            dr = await client.get(
                "https://api.hunter.io/v2/domain-search",
                params={"domain": domain, "api_key": api_key, "limit": 1},
            )
            if dr.status_code == 200:
                ddata = (dr.json() or {}).get("data") or {}
                pattern = (ddata.get("pattern") or "").strip()
                if pattern and first and last:
                    # hunter pattern tokens: {first}, {last}, {f}, {l}
                    guessed = (
                        pattern.replace("{first}", first)
                        .replace("{last}", last)
                        .replace("{f}", first[:1])
                        .replace("{l}", last[:1])
                    )
                    email = f"{guessed}@{domain}".lower()
                    if _EMAIL_RE.match(email) and not any(x["email"] == email for x in results):
                        results.append(
                            {
                                "email": email,
                                "source": "hunter.io:domain_pattern",
                                "source_detail": f"Domain pattern from Hunter: {pattern}",
                                "pattern": pattern,
                                "confidence": 0.78,
                                "confidence_label": "high",
                                "smtp_status": "not_checked",
                                "recommendation": "Matches published domain pattern",
                            }
                        )
    except Exception as exc:  # noqa: BLE001 — enrichment is best-effort
        results.append(
            {
                "email": "",
                "source": "hunter.io:error",
                "source_detail": f"Hunter request failed: {exc}",
                "pattern": "",
                "confidence": 0.0,
                "confidence_label": "low",
                "smtp_status": "error",
                "recommendation": "Falling back to format inference / LinkedIn",
            }
        )
    return [r for r in results if r.get("email") or r.get("source") == "hunter.io:error"]


async def find_emails(
    *,
    name: str,
    company: str = "",
    domain: str = "",
    website: str = "",
    use_hunter: bool = True,
) -> dict[str, Any]:
    first, last = _slug_name(name)
    resolved_domain = (domain or "").strip().lower().removeprefix("www.") or infer_company_domain(
        company, website
    )

    candidates: list[dict[str, Any]] = []
    hunter_enabled = use_hunter and bool((getattr(settings, "HUNTER_API_KEY", None) or "").strip())

    if hunter_enabled:
        hunter_hits = await _hunter_email_finder(
            first=first,
            last=last,
            domain=resolved_domain,
            full_name=name,
            company=company,
        )
        for h in hunter_hits:
            if h.get("email"):
                candidates.append(h)

    for fmt in _format_candidates(first, last, resolved_domain):
        if any(c.get("email") == fmt["email"] for c in candidates):
            continue
        # If Hunter gave a domain pattern, boost matching format
        candidates.append(fmt)

    # Dedupe + sort by confidence
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in candidates:
        email = (c.get("email") or "").lower()
        if not email or email in seen:
            continue
        seen.add(email)
        unique.append(c)
    unique.sort(key=lambda x: float(x.get("confidence") or 0), reverse=True)
    unique = unique[:5]

    return {
        "name": name,
        "company": company,
        "domain": resolved_domain,
        "hunter_used": hunter_enabled,
        "candidates": unique,
        "expectancy_note": (
            "70%+ of the time there is no public email — that is normal. "
            "Prefer LinkedIn connection request when confidence is low or the list is empty."
        ),
        "empty_reason": (
            None
            if unique
            else (
                "Could not infer a domain — paste company website/domain, or use LinkedIn."
                if not resolved_domain
                else "No candidates generated — check the name spelling."
            )
        ),
    }
