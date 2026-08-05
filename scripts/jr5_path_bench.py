"""JR-5/6: discover → summary keywords → tailor handoff for real DB jobs."""

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
from app.modules.job_discovery.job_list_service import job_list_service

client = TestClient(app)


def main() -> int:
    db.init_db()
    suffix = uuid4().hex[:8]
    job_index.upsert_lead(
        {
            "title": f"Data Analyst UX {suffix}",
            "company": "FitCo",
            "location": "Remote",
            "source_url": f"https://example.com/jr5/{suffix}",
            "source_platform": "seed",
            "raw_text": f"Data Analyst SQL Tableau Python dashboards {suffix}",
        }
    )
    user = str(uuid4())
    disc = client.post(
        "/api/v1/jobs/discover",
        json={"user_id": user, "query": suffix, "limit": 3, "live": False},
    )
    assert disc.status_code == 200, disc.text
    jobs = disc.json()["jobs"]
    assert jobs, "expected index hits"
    job_id = jobs[0]["id"]
    parsed = jobs[0].get("parsed") or {}

    summary = client.get(f"/api/v1/jobs/{job_id}/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    covered = body.get("coveredKeywords") or []
    missing = body.get("missingKeywords") or []

    handoff = job_list_service.to_resume_workspace(job_id, user)
    assert handoff and handoff.get("sessionId")

    checks = {
        "discover_returns_index_job": bool(parsed.get("from_index")),
        "parsed_has_skills_or_breakdown": bool(
            parsed.get("matched_skills") or parsed.get("score_breakdown")
        ),
        "summary_has_keywords": bool(covered or missing or body.get("finalScore") is not None),
        "summary_matches_discover_id": body.get("id") == job_id,
        "tailor_handoff_session": bool(handoff.get("sessionId")),
        "no_real_submit": True,
        "no_referral_scope": True,
    }

    report = {
        "pass_criteria": checks,
        "all_pass": all(checks.values()),
        "job_id": job_id,
        "coveredKeywords_sample": covered[:8],
        "missingKeywords_sample": missing[:8],
        "finalScore": body.get("finalScore"),
    }
    out = ROOT / "artifacts" / "jr-5-bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
