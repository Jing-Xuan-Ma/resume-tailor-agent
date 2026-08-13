"""Jobright-style quality ingest self-test: real JDs, no ad teasers."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db
from app.modules.job_discovery import job_index
from app.modules.job_discovery.quality import assess_listing_quality, jd_body
from app.modules.job_discovery.scorer import extract_skills, score_job_detailed


async def main() -> int:
    db.init_db()
    ingest = await job_index.ingest_queries(
        queries=[
            "data analyst",
            "analytics engineer",
            "business intelligence analyst",
        ],
        location="",
        limit_per_query=12,
        hours_old=72,
        sites=["indeed", "google"],
        quality_gate=True,
    )

    rows = db.search_job_listings(status="active", limit=300)
    platforms = Counter((r.get("source_platform") or "?") for r in rows)
    quality_ok = []
    quality_bad = []
    for r in rows:
        v = assess_listing_quality(r, min_chars=500)
        (quality_ok if v["ok"] else quality_bad).append((r, v))

    jobspy = [r for r in rows if str(r.get("source_platform") or "").startswith("jobspy")]
    adzuna_active = [r for r in rows if (r.get("source_platform") or "") == "adzuna"]

    # Score sample of quality-ok DA-ish titles with empty resume (title+JD skills path)
    scored = []
    for r, v in quality_ok[:15]:
        detail = score_job_detailed(
            {"title": r.get("title") or "", "raw_text": r.get("raw_text") or ""},
            "data analyst",
            resume_text="sql python tableau excel power bi statistics pandas",
        )
        scored.append(
            {
                "title": r.get("title"),
                "company": r.get("company"),
                "platform": r.get("source_platform"),
                "body_len": v["body_len"],
                "skills": v["skills"][:8],
                "match_score": detail["match_score"],
                "matched": detail["matched_skills"][:8],
                "missing": detail["missing_skills"][:8],
            }
        )

    body_lens = [v["body_len"] for _, v in quality_ok]
    skillful = sum(1 for _, v in quality_ok if v["skills"])
    under72h = 0
    now = datetime.now(timezone.utc)
    for r, _ in quality_ok:
        sa = r.get("scraped_at") or ""
        try:
            dt = datetime.fromisoformat(sa.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).total_seconds() <= 72 * 3600:
                under72h += 1
        except Exception:
            pass

    # Pass criteria (Jobright-like, scoped)
    checks = {
        "ingest_fetched_gt0": ingest.get("fetched", 0) > 0,
        "jobspy_present": len(jobspy) >= 3,
        "adzuna_ads_not_active": len(adzuna_active) == 0,
        "active_quality_ratio_ge_70pct": (len(quality_ok) / max(1, len(rows))) >= 0.70,
        "median_body_len_ge_800": (sorted(body_lens)[len(body_lens) // 2] if body_lens else 0) >= 800,
        "skillful_share_ge_40pct": (skillful / max(1, len(quality_ok))) >= 0.40,
        "sample_scores_not_stuck_at_35": any(s["match_score"] > 40 for s in scored),
        "rejected_or_closed_thin": (ingest.get("rejected_quality", 0) + ingest.get("closed_thin", 0)) >= 0,
    }
    passed = all(checks.values())

    report = {
        "passed": passed,
        "checks": checks,
        "ingest": {
            k: ingest.get(k)
            for k in (
                "fetched",
                "created",
                "updated",
                "rejected_quality",
                "reject_reasons",
                "closed_thin",
                "closed_adzuna",
                "closed_seed",
                "active_total",
                "hours_old",
                "quality_gate",
                "provider_stats",
                "errors",
            )
        },
        "active_total": len(rows),
        "platforms": dict(platforms),
        "quality_ok": len(quality_ok),
        "quality_bad": len(quality_bad),
        "jobspy_count": len(jobspy),
        "adzuna_active": len(adzuna_active),
        "median_body_len": sorted(body_lens)[len(body_lens) // 2] if body_lens else 0,
        "skillful": skillful,
        "quality_ok_scraped_under_72h": under72h,
        "samples": scored[:8],
        "bad_examples": [
            {
                "title": r.get("title"),
                "platform": r.get("source_platform"),
                "reason": v["reason"],
                "body_len": v["body_len"],
                "preview": jd_body(r.get("raw_text") or "")[:160],
            }
            for r, v in quality_bad[:5]
        ],
    }

    out = ROOT / "artifacts" / "jr-quality-bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md = ROOT / "artifacts" / "jr-quality-report.md"
    md.write_text(
        "\n".join(
            [
                "# JR Quality Ingest — real JD gate",
                "",
                f"**Status: {'PASS' if passed else 'FAIL'}**",
                "",
                "## Checks",
                "",
                *[f"- {'PASS' if v else 'FAIL'}: `{k}`" for k, v in checks.items()],
                "",
                f"- active={len(rows)} quality_ok={len(quality_ok)} jobspy={len(jobspy)} adzuna_active={len(adzuna_active)}",
                f"- median_body_len={report['median_body_len']} skillful={skillful}",
                f"- rejected_quality={ingest.get('rejected_quality')} closed_thin={ingest.get('closed_thin')}",
                "",
                f"Evidence: `{out.as_posix()}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({"passed": passed, "checks": checks, "active": len(rows), "jobspy": len(jobspy), "median_body_len": report["median_body_len"]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
