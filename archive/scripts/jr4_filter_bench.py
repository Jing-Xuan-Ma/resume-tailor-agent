"""JR-4: server-side hard filters on job_listings / discover."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.modules.job_discovery import job_index

client = TestClient(app)


def main() -> int:
    db.init_db()
    # Unique suffix so filters aren't polluted by older seeds
    suffix = uuid4().hex[:8]

    job_index.upsert_lead(
        {
            "title": f"Remote DA {suffix}",
            "company": "RemoteCo",
            "location": "Remote",
            "source_url": f"https://example.com/jr4/remote-{suffix}",
            "source_platform": "remotive",
            "raw_text": f"Data Analyst SQL Tableau remote {suffix}",
        }
    )
    job_index.upsert_lead(
        {
            "title": f"Onsite DA {suffix}",
            "company": "OfficeCo",
            "location": "New York, NY",
            "source_url": f"https://example.com/jr4/onsite-{suffix}",
            "source_platform": "seed",
            "raw_text": f"Data Analyst on-site office SQL {suffix}",
        }
    )
    stale_id, _ = job_index.upsert_lead(
        {
            "title": f"Old DA {suffix}",
            "company": "OldCo",
            "location": "Remote",
            "source_url": f"https://example.com/jr4/old-{suffix}",
            "source_platform": "remotive",
            "raw_text": f"Data Analyst SQL {suffix}",
        }
    )
    old = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    with db.connect() as conn:
        conn.execute("UPDATE job_listings SET scraped_at = ? WHERE id = ?", (old, stale_id))

    remote_hits = db.search_job_listings(
        query=suffix, work_model="remote", status="active", limit=20
    )
    onsite_hits = db.search_job_listings(
        query=suffix, work_model="onsite", status="active", limit=20
    )
    platform_hits = db.search_job_listings(
        query=suffix, source_platform="remotive", status="active", limit=20
    )
    fresh_hits = db.search_job_listings(
        query=suffix, max_age_hours=72, status="active", limit=20
    )

    user = str(uuid4())
    # min_score_100 filter via discover
    # Seed a low-score and high-score-ish by query match
    r = client.post(
        "/api/v1/jobs/discover",
        json={
            "user_id": user,
            "query": suffix,
            "limit": 20,
            "live": False,
            "work_model": "remote",
            "min_score_100": 1,
        },
    )
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    # Discover copies to user jobs; check parsed / scores
    scores_ok = all(float(j.get("match_score") or 0) >= 1 for j in jobs)

    checks = {
        "work_model_remote_only": all(
            (h.get("work_model") or "").lower() == "remote" for h in remote_hits
        )
        and any(suffix in (h.get("title") or "") for h in remote_hits),
        "work_model_onsite_only": all(
            (h.get("work_model") or "").lower() == "onsite" for h in onsite_hits
        )
        and len(onsite_hits) >= 1,
        "source_platform_filter": all(
            (h.get("source_platform") or "").lower() == "remotive" for h in platform_hits
        ),
        "max_age_excludes_stale": all(h.get("id") != stale_id for h in fresh_hits),
        "discover_min_score": scores_ok and len(jobs) >= 1,
    }

    report = {"pass_criteria": checks, "all_pass": all(checks.values()), "counts": {
        "remote": len(remote_hits),
        "onsite": len(onsite_hits),
        "platform": len(platform_hits),
        "fresh": len(fresh_hits),
        "discover": len(jobs),
    }}
    out = ROOT / "artifacts" / "jr-4-bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
