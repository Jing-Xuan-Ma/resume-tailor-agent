"""W71: job detail scored-for-user screenshot."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"

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
    "SELECT id FROM job_listings WHERE status='active' "
    "AND scraped_at >= datetime('now','-14 days') ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
assert row, "no fresh job"
job_id = row[0]

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(FE, wait_until="domcontentloaded")
    page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", blob)
    page.goto(f"{FE}/jobs/{job_id}", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=job-detail-page]", timeout=30000)
    page.wait_for_timeout(1500)
    badge = page.locator("[data-testid=scored-for-user]")
    ok("w71_scored_for_user_visible", badge.count() > 0, badge.inner_text() if badge.count() else "")
    page.screenshot(path=str(OUT / "w71-scored-for-user.png"), full_page=False)
    browser.close()

report = {"passed": all(c for _, c, _ in CHECKS), "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS]}
(OUT / "w71-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
