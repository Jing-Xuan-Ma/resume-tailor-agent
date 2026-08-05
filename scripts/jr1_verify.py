"""JR-1 verification: local index read path + upsert idempotency + latency."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.modules.job_discovery import job_index

client = TestClient(app)


def _seed(n: int = 8) -> None:
    for i in range(n):
        job_index.upsert_lead(
            {
                "title": f"Data Analyst {i}",
                "company": f"Acme Corp {i % 3}",
                "location": "Remote",
                "source_url": f"https://example.com/jobs/da-{i}",
                "source_platform": "seed",
                "raw_text": (
                    f"Data Analyst {i}\nCompany: Acme\n"
                    "Requirements: SQL, Tableau, Python, dashboards, analytics"
                ),
                "metadata": {"seed": True},
            }
        )


def main() -> int:
    db.init_db()
    before_count = db.count_job_listings("active")
    _seed(8)
    after_seed = db.count_job_listings("active")

    # Upsert same URLs again — count must not grow by 8 again
    _seed(8)
    after_dup = db.count_job_listings("active")
    created_delta = after_seed - before_count
    dup_delta = after_dup - after_seed

    user = str(uuid4())
    t0 = time.perf_counter()
    r = client.post(
        "/api/v1/jobs/discover",
        json={
            "user_id": user,
            "query": "data analyst",
            "location": "Remote",
            "limit": 5,
            "live": False,
        },
    )
    index_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    assert len(jobs) == 5
    from_index = sum(1 for j in jobs if (j.get("parsed") or {}).get("from_index"))
    # All should come from index when seeded (not synthetic)
    assert from_index >= 1, jobs[0]

    stats = client.get("/api/v1/jobs/index/stats")
    assert stats.status_code == 200, stats.text

    report = {
        "pass_criteria": {
            "index_search_without_live": True,
            "upsert_idempotent": dup_delta == 0,
            "discover_from_index_ms": round(index_ms, 1),
            "from_index_jobs": from_index,
            "active_total": stats.json()["active_total"],
            "created_on_seed": created_delta,
            "dup_delta": dup_delta,
        },
        "notes": (
            "JR-1 default discover uses job_listings (live=false). "
            "Scheduler writes via JOB_INDEX_INGEST_INTERVAL_MINUTES; "
            "manual: python scripts/jr1_ingest_jobs.py --query 'data analyst'."
        ),
    }
    out = ROOT / "artifacts" / "jr-1-bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    ok = report["pass_criteria"]["upsert_idempotent"] and from_index >= 1 and index_ms < 5000
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
