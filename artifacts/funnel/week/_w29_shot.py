"""W29: Jobs hide-stale + detail screenshot self-test."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


with httpx.Client(timeout=60) as client:
    auth = client.post(
        f"{API}/api/v1/auth/login",
        json={"email": "demo@resume-agent.local", "password": "demo-pass-1234"},
    ).json()
blob = {
    "token": auth["access_token"],
    "user": {
        "id": auth["user"]["id"],
        "email": auth["user"]["email"],
        "full_name": auth["user"].get("full_name"),
    },
}

row = sqlite3.connect(r"d:\resume-agent\data\app.db").execute(
    "SELECT id FROM job_listings WHERE status='active' ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
job_id = row[0] if row else None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(FE, wait_until="domcontentloaded")
    page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", blob)

    page.goto(f"{FE}/jobs", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=ranked-jobs-page]", timeout=30000)
    ok("w29_hide_stale_control", page.locator("[data-testid=jobs-hide-stale]").count() > 0, "")
    page.locator("[data-testid=jobs-hide-stale] input").check()
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / "w29-jobs-hide-stale.png"), full_page=False)

    if job_id:
        page.goto(f"{FE}/jobs/{job_id}", wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid=job-detail-page]", timeout=30000)
        body = page.inner_text("body").lower()
        ok("w29_detail_honest", "ats keywords" in body or "skill coverage" in body, "")
        ok("w29_detail_stale_or_age", "stale" in body or "ago" in body or "posted" in body, "")
        page.screenshot(path=str(OUT / "w29-job-detail.png"), full_page=False)
    else:
        ok("w29_detail_honest", False, "no job")

    browser.close()

report = {
    "passed": all(c for _, c, _ in CHECKS),
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
}
(OUT / "w29-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
