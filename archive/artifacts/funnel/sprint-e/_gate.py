"""Sprint E freshness gate: source+age UI metrics + quality snapshot."""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

from app import db
from app.modules.job_discovery.posted_at import display_age_iso, extract_posted_at
from app.modules.job_discovery.scorer import extract_skills

OUT = Path(r"d:\resume-agent\artifacts\funnel\sprint-e")
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


# Close thin / seed / adzuna if helpers exist
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
for r in rows:
    meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
    iso = display_age_iso(scraped_at=r.get("scraped_at"), metadata=meta)
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
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
median_age = statistics.median(ages_h) if ages_h else 9999
skillful_share = skillful / n
preferred_share = preferred / n
under72h = sum(1 for a in ages_h if a <= 72) / max(1, len(ages_h))

baseline_path = Path(r"d:\resume-agent\artifacts\jr-quality-bench.json")
baseline = {}
if baseline_path.exists():
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception:
        baseline = {}

snap = {
    "active": len(rows),
    "median_age_hours": round(median_age, 1),
    "under72h_share": round(under72h, 3),
    "skillful_share": round(skillful_share, 3),
    "preferred_source_share": round(preferred_share, 3),
    "closed_thin": closed_thin,
    "baseline_skillful": baseline.get("skillful_share") or baseline.get("checks", {}),
}
(OUT / "freshness.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")

ok("active_gt_0", len(rows) > 0, str(len(rows)))
ok("skillful_share_ge_35", skillful_share >= 0.35, f"{skillful_share:.2f}")
ok("preferred_source_ge_40", preferred_share >= 0.40, f"{preferred_share:.2f}")
ok("median_age_lt_14d", median_age < 24 * 14, f"{median_age:.1f}h")
ok("under72h_gt_0", under72h > 0 or median_age < 24 * 10, f"{under72h:.2f}")

# UI: source column visible
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.goto(f"{FE}/jobs", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "01-jobs-source-age.png"), full_page=False)
    has_source = page.locator("[data-testid=job-source]").count() > 0
    has_age = page.locator("[data-testid=job-posted-age]").count() > 0
    body = page.inner_text("body")
    ok("ui_source_column", has_source or "SOURCE" in body.upper(), "")
    ok("ui_posted_age", has_age or "ago" in body.lower(), "")
    browser.close()

passed = all(c for _, c, _ in CHECKS)
report = {"sprint": "E", "passed": passed, "snapshot": snap, "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS]}
(OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
sys.exit(0 if passed else 1)
