"""Verify category classify + filter + backfill."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.modules.job_discovery import job_index
from app.modules.job_discovery.categories import classify_job, slug_for_label

client = TestClient(app)


def main() -> int:
    db.init_db()
    checks: dict[str, bool] = {}

    checks["ai_agent_before_swe"] = (
        classify_job(title="AI Agent Engineer", raw_text="LLM multi-agent LangChain")["category"]
        == "ai_agent"
    )
    checks["da_classify"] = (
        classify_job(title="Data Analyst", raw_text="SQL Tableau dashboards")["category"]
        == "data_analysis"
    )
    checks["swe_classify"] = (
        classify_job(title="Software Engineer", raw_text="backend APIs Java")["category"]
        == "software_engineering"
    )
    checks["risk_classify"] = (
        classify_job(title="Risk Analyst", raw_text="insurance actuarial")["category"]
        == "risk_analytics"
    )
    checks["slug_label"] = slug_for_label("Risk / Insurance Analytics") == "risk_analytics"

    suffix = uuid4().hex[:6]
    job_index.upsert_lead(
        {
            "title": f"Data Analyst {suffix}",
            "company": "CatCo",
            "location": "Remote",
            "source_url": f"https://example.com/cat/da-{suffix}",
            "source_platform": "seed",
            "raw_text": f"Data Analyst SQL Tableau {suffix}",
        }
    )
    job_index.upsert_lead(
        {
            "title": f"Software Engineer {suffix}",
            "company": "EngCo",
            "location": "Remote",
            "source_url": f"https://example.com/cat/swe-{suffix}",
            "source_platform": "seed",
            "raw_text": f"Software Engineer backend Python {suffix}",
        }
    )

    n = db.backfill_listing_categories(classify_job)
    checks["backfill_ran"] = n >= 1

    da_hits = db.search_job_listings(query=suffix, category="data_analysis", limit=20)
    swe_hits = db.search_job_listings(query=suffix, category="software_engineering", limit=20)
    checks["filter_da"] = all(h.get("category") == "data_analysis" for h in da_hits) and len(da_hits) >= 1
    checks["filter_swe"] = all(h.get("category") == "software_engineering" for h in swe_hits) and len(swe_hits) >= 1

    r = client.get(
        "/api/v1/jobs/list",
        params={
            "user_id": str(uuid4()),
            "category": "Data Analysis",
            "search": suffix,
            "threshold": 0,
        },
    )
    checks["list_api_ok"] = r.status_code == 200
    jobs = r.json().get("jobs") or []
    checks["list_filtered"] = all(
        (j.get("category") == "data_analysis") or ("Analyst" in (j.get("title") or ""))
        for j in jobs
    ) and any(suffix in (j.get("title") or "") for j in jobs)

    cats = client.get("/api/v1/jobs/categories")
    checks["categories_api"] = cats.status_code == 200 and len(cats.json().get("categories") or []) == 6

    report = {
        "pass_criteria": checks,
        "all_pass": all(checks.values()),
        "counts": db.count_job_listings_by_category("active"),
        "list_jobs": len(jobs),
        "backfill": n,
    }
    out = ROOT / "artifacts" / "jr-categories-bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
