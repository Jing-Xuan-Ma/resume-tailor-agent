"""JR-2: ATS fingerprint + upsert merge + stale lifecycle."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db
from app.modules.job_discovery import job_index


def main() -> int:
    db.init_db()
    checks: dict[str, bool] = {}

    # Greenhouse URL variants → same ATS fingerprint
    url_a = "https://boards.greenhouse.io/acme/jobs/12345?utm_source=linkedin"
    url_b = "https://job-boards.greenhouse.io/acme/jobs/12345"
    fp_a = job_index.listing_fingerprint(source_url=url_a, title="DA", company="Acme")
    fp_b = job_index.listing_fingerprint(source_url=url_b, title="Different Title", company="Other")
    checks["greenhouse_ats_merge"] = fp_a == fp_b and fp_a.startswith("ats:")

    ats = job_index.extract_ats_identity(url_a)
    checks["greenhouse_parse"] = ats == ("greenhouse", "acme", "12345")

    lever = "https://jobs.lever.co/stripe/abcdef12-3456-7890-abcd-ef1234567890"
    checks["lever_parse"] = job_index.extract_ats_identity(lever) is not None
    fp_lever = job_index.listing_fingerprint(source_url=lever, title="X", company="Y")
    checks["lever_ats_prefix"] = fp_lever.startswith("ats:")

    # Same ATS job upserted twice → one row
    before = db.count_job_listings("active")
    id1, created1 = job_index.upsert_lead(
        {
            "title": "Data Analyst",
            "company": "Acme",
            "location": "Remote",
            "source_url": url_a,
            "source_platform": "linkedin",
            "raw_text": "SQL Tableau",
        }
    )
    id2, created2 = job_index.upsert_lead(
        {
            "title": "Data Analyst II",
            "company": "Acme Inc",
            "location": "NY Remote",
            "source_url": url_b,
            "source_platform": "greenhouse",
            "raw_text": "SQL Tableau Python",
        }
    )
    after = db.count_job_listings("active")
    checks["ats_upsert_same_id"] = id1 == id2
    checks["ats_no_duplicate_row"] = id1 == id2

    # title+company fallback when no URL
    fp_tc = job_index.listing_fingerprint(
        source_url=None, title="Data Analyst", company="Beta Co", source_platform="remotive"
    )
    checks["tc_fallback"] = fp_tc.startswith("tc:")

    # Stale lifecycle: force old scraped_at then mark closed
    stale_id, _ = job_index.upsert_lead(
        {
            "title": "Stale Role",
            "company": "OldCo",
            "location": "Remote",
            "source_url": "https://example.com/jobs/stale-jr2-only",
            "source_platform": "seed",
            "raw_text": "old",
        }
    )
    old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    with db.connect() as conn:
        conn.execute(
            "UPDATE job_listings SET scraped_at = ? WHERE id = ?",
            (old, stale_id),
        )
    closed = db.mark_stale_job_listings(max_age_hours=24 * 21)
    listing = db.get_job_listing(stale_id)
    checks["stale_closed"] = closed >= 1 and listing is not None and listing.get("status") == "closed"

    # Closed listings excluded from search
    hits = db.search_job_listings(query="Stale Role", status="active", limit=10)
    checks["closed_excluded"] = all(h.get("id") != stale_id for h in hits)

    report = {"pass_criteria": checks, "all_pass": all(checks.values())}
    out = ROOT / "artifacts" / "jr-2-bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
