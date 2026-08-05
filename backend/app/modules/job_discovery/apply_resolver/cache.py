"""Company → ATS tenant/site cache (JSON under data/)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# apply_resolver/ → job_discovery → modules → app → backend → repo root
CACHE_PATH = Path(__file__).resolve().parents[5] / "data" / "ats_company_map.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _key(company: str) -> str:
    return re.sub(r"\s+", " ", (company or "").strip().lower())


def load_cache() -> dict[str, Any]:
    if not CACHE_PATH.exists():
        return {"companies": {}}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"companies": {}}


def save_cache(data: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_company_ats(company: str) -> dict[str, Any] | None:
    key = _key(company)
    if not key:
        return None
    companies = load_cache().get("companies") or {}
    hit = companies.get(key)
    return hit if isinstance(hit, dict) else None


def put_company_ats(
    company: str,
    *,
    platform: str,
    tenant: str | None = None,
    site: str | None = None,
    host: str | None = None,
    career_url: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    key = _key(company)
    if not key:
        return
    data = load_cache()
    companies = data.setdefault("companies", {})
    row = {
        "company": company,
        "platform": platform,
        "tenant": tenant,
        "site": site,
        "host": host,
        "career_url": career_url,
        "updated_at": _now(),
    }
    if extra:
        row.update(extra)
    companies[key] = row
    save_cache(data)
