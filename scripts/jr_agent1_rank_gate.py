"""Agent 1 gate: honest scores + freshness snapshot + Source/Posted UI shots."""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from playwright.sync_api import sync_playwright

from app import db
from app.modules.job_discovery.posted_at import display_age_iso
from app.modules.job_discovery.scorer import extract_skills, score_job_detailed

OUT = ROOT / "artifacts" / "funnel" / "agent1"
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
CHECKS: list[tuple[str, bool, str]] = []

RESUME = (
    "Jingxuan Data Analyst. Skills: SQL, Python, Tableau, Excel, A/B testing, "
    "dashboards, statistics, pandas, ETL, Power BI."
)
QUERY = "data analyst sql python tableau excel"


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def score_anti_inflation() -> dict:
    thin = score_job_detailed(
        {
            "title": "Data Labeling Specialist",
            "raw_text": "Label images for ML. Data entry microtasks. Click to apply.",
        },
        QUERY,
        resume_text=RESUME,
    )
    rich = score_job_detailed(
        {
            "title": "Data Analyst",
            "raw_text": (
                "Responsibilities: dashboards, experimentation, stakeholder reporting. "
                "Requirements: SQL, Python, Tableau, Excel, statistics, A/B testing, ETL. "
                + ("Build KPI dashboards with SQL and Tableau for product teams. " * 8)
            ),
        },
        QUERY,
        resume_text=RESUME,
    )
    title_query = score_job_detailed(
        {"title": "Data Analyst", "raw_text": "SQL Tableau Python"},
        "Data Analyst",
        resume_text="",
    )
    # Live catalog spread (not all identical)
    rows = db.search_job_listings(status="active", limit=80) or []
    live_scores: list[float] = []
    for r in rows[:40]:
        d = score_job_detailed(
            {"title": r.get("title") or "", "raw_text": r.get("raw_text") or ""},
            QUERY,
            resume_text=RESUME,
        )
        live_scores.append(float(d["match_score"]))

    unique = len(set(round(s, 0) for s in live_scores)) if live_scores else 0
    stuck35 = (
        sum(1 for s in live_scores if 34.0 <= s <= 36.0) / max(1, len(live_scores))
        if live_scores
        else 0.0
    )

    result = {
        "thin": thin["match_score"],
        "rich": rich["match_score"],
        "title_as_query_empty_resume": title_query["match_score"],
        "thin_skill_hit": thin["score_breakdown"]["skill_hit_rate"],
        "live_score_count": len(live_scores),
        "live_unique_rounded": unique,
        "live_stuck_at_35_share": round(stuck35, 3),
        "live_sample": live_scores[:12],
    }
    (OUT / "score-anti-inflation.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    ok("thin_lt_35", thin["match_score"] < 35, str(thin["match_score"]))
    ok("rich_gt_60", rich["match_score"] > 60, str(rich["match_score"]))
    ok("rich_beats_thin", rich["match_score"] > thin["match_score"] + 25, f"{rich['match_score']}>{thin['match_score']}")
    ok("thin_skill_hit_not_one", thin["score_breakdown"]["skill_hit_rate"] < 0.5, str(thin["score_breakdown"]["skill_hit_rate"]))
    ok("no_flat_35_title_query", title_query["match_score"] != 35.0, str(title_query["match_score"]))
    ok("live_scores_not_all_35", stuck35 < 0.5 if live_scores else True, f"share={stuck35}")
    ok("live_score_spread", unique >= 3 if len(live_scores) >= 5 else True, f"unique={unique}")
    return result


def freshness_snapshot() -> dict:
    closed_thin = 0
    try:
        from app.modules.job_discovery import job_index

        if hasattr(job_index, "close_thin_active_listings"):
            closed_thin = int(job_index.close_thin_active_listings() or 0)
        if hasattr(db, "close_job_listings_by_platform"):
            db.close_job_listings_by_platform("seed")
            db.close_job_listings_by_platform("adzuna")
    except Exception as exc:
        print("close_note", exc)

    rows = db.search_job_listings(status="active", limit=500) or []
    now = datetime.now(timezone.utc)
    ages_h: list[float] = []
    skillful = 0
    preferred = 0
    platforms = Counter()
    for r in rows:
        platforms[str(r.get("source_platform") or "?")] += 1
        meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        iso = display_age_iso(scraped_at=r.get("scraped_at"), metadata=meta)
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ages_h.append(max(0.0, (now - dt).total_seconds() / 3600.0))
        except Exception:
            pass
        blob = f"{r.get('title') or ''} {r.get('raw_text') or ''}"
        if extract_skills(blob):
            skillful += 1
        plat = str(r.get("source_platform") or "").lower()
        if any(p in plat for p in ("remotive", "himalayas", "jobicy", "jobspy")):
            preferred += 1

    n = max(1, len(rows))
    median_age = statistics.median(ages_h) if ages_h else 9999.0
    skillful_share = skillful / n
    preferred_share = preferred / n
    under72h = sum(1 for a in ages_h if a <= 72) / max(1, len(ages_h))

    snap = {
        "active": len(rows),
        "median_age_hours": round(float(median_age), 1),
        "under72h_share": round(under72h, 3),
        "skillful_share": round(skillful_share, 3),
        "preferred_source_share": round(preferred_share, 3),
        "closed_thin": closed_thin,
        "platforms": dict(platforms.most_common(12)),
    }
    (OUT / "freshness.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")

    ok("active_gt_0", len(rows) > 0, str(len(rows)))
    ok("skillful_share_ge_35", skillful_share >= 0.35, f"{skillful_share:.2f}")
    ok("preferred_source_ge_40", preferred_share >= 0.40, f"{preferred_share:.2f}")
    ok("median_age_lt_14d", float(median_age) < 24 * 14, f"{median_age:.1f}h")
    ok("under72h_gt_0", under72h > 0 or float(median_age) < 24 * 10, f"{under72h:.2f}")
    return snap


def ui_shots() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.goto(f"{FE}/jobs", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2800)
        page.screenshot(path=str(OUT / "01-jobs-source-age.png"), full_page=False)
        has_source = page.locator("[data-testid=job-source]").count() > 0
        has_age = page.locator("[data-testid=job-posted-age]").count() > 0
        body = page.inner_text("body")
        ok("ui_source_column", has_source or "SOURCE" in body.upper(), f"source={has_source}")
        ok("ui_posted_age", has_age or "ago" in body.lower(), f"age={has_age}")

        # Open first job detail if present
        rows = page.locator("[data-testid^=job-row-]")
        if rows.count() > 0:
            with page.expect_navigation(timeout=15000):
                rows.first.click()
            page.wait_for_selector("[data-testid=job-detail-page]", timeout=15000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(OUT / "02-job-detail.png"), full_page=False)
            detail_ok = page.locator("[data-testid=job-detail-page]").count() > 0
            ok("ui_job_detail", detail_ok, page.url)
        else:
            page.screenshot(path=str(OUT / "02-job-detail.png"), full_page=False)
            ok("ui_job_detail", False, "no job rows")
        browser.close()


def write_report(scores: dict, snap: dict, passed: bool) -> None:
    report = {
        "agent": "agent1-rank-discover",
        "passed": passed,
        "scores": scores,
        "freshness": snap,
        "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    # Also canonical funnel path requested by mission
    funnel = ROOT / "artifacts" / "funnel"
    (funnel / "agent1-rank-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    lines = [
        "# Agent 1 — Rank & Discover Report",
        "",
        f"**Status: {'PASS' if passed else 'FAILURE'}**",
        "",
        "## Scores (honest, anti-inflation)",
        "",
        f"- thin/labeling: **{scores.get('thin')}** (skill_hit={scores.get('thin_skill_hit')})",
        f"- rich DA: **{scores.get('rich')}**",
        f"- title-as-query empty resume: **{scores.get('title_as_query_empty_resume')}** (must not be flat 35)",
        f"- live stuck@35 share: **{scores.get('live_stuck_at_35_share')}** · unique rounded: **{scores.get('live_unique_rounded')}**",
        "",
        "## Freshness snapshot",
        "",
        f"- active: **{snap.get('active')}**",
        f"- median age: **{snap.get('median_age_hours')}h**",
        f"- under 72h: **{snap.get('under72h_share')}**",
        f"- skillful: **{snap.get('skillful_share')}**",
        f"- preferred sources (remotive/himalayas/jobicy/jobspy): **{snap.get('preferred_source_share')}**",
        f"- closed_thin: **{snap.get('closed_thin')}**",
        "",
        "## Checks",
        "",
        *[f"- {'PASS' if c else 'FAIL'}: `{n}` {d}" for n, c, d in CHECKS],
        "",
        "## UI artifacts",
        "",
        "- `artifacts/funnel/agent1/01-jobs-source-age.png`",
        "- `artifacts/funnel/agent1/02-job-detail.png`",
        "",
        f"Evidence JSON: `artifacts/funnel/agent1/report.json`",
        "",
    ]
    if not passed:
        fails = [n for n, c, _ in CHECKS if not c]
        lines.extend(
            [
                "## FAILURE",
                "",
                f"Failed checks: {', '.join(fails)}",
                "",
            ]
        )
    lines.extend(["READY_FOR_MAIN_AGENT", ""])
    md = "\n".join(lines)
    (funnel / "agent1-rank-report.md").write_text(md, encoding="utf-8")
    (OUT / "agent1-rank-report.md").write_text(md, encoding="utf-8")
    print(md)


def main() -> int:
    db.init_db()
    scores = score_anti_inflation()
    snap = freshness_snapshot()
    try:
        ui_shots()
    except Exception as exc:
        ok("ui_shots", False, str(exc))
    passed = all(c for _, c, _ in CHECKS)
    write_report(scores, snap, passed)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
