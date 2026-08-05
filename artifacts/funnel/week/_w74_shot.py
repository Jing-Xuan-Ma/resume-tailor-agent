"""W74: tailor workspace PDF/first-paint + outreach empty hint."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
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
    "SELECT id FROM job_listings WHERE status='active' AND lower(title) LIKE '%data analyst%' "
    "AND scraped_at >= datetime('now','-14 days') ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
job_id = row[0] if row else None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.goto(FE, wait_until="domcontentloaded")
    page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", blob)
    url = f"{FE}/?view=resume&forceOutreach=1" + (f"&jobId={job_id}" if job_id else "")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=resume-workspace]", timeout=30000)
    # Wait for version / preview
    for _ in range(90):
        if page.locator("[data-testid=version-select]").count():
            break
        page.wait_for_timeout(1000)
    page.screenshot(path=str(OUT / "w74-tailor.png"), full_page=False)
    ok(
        "w74_preview_or_stepper",
        page.locator("[data-testid=flow-stepper]").count() > 0
        and (
            page.locator("[data-testid=html-preview-fallback],[data-testid=master-pdf-iframe],[data-testid=preview-first-paint]").count()
            > 0
            or page.locator("[data-testid=version-select]").count() > 0
        ),
        "",
    )
    page.evaluate(
        "() => document.querySelector('[data-testid=outreach-step-panel]')?.scrollIntoView({block:'center'})"
    )
    page.wait_for_timeout(400)
    ok(
        "w74_outreach_empty_or_drafts",
        page.locator("[data-testid=outreach-drafts-empty],[data-testid=outreach-drafts]").count() > 0,
        "",
    )
    page.screenshot(path=str(OUT / "w74-outreach-empty.png"), full_page=False)
    browser.close()

report = {"passed": all(c for _, c, _ in CHECKS), "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS]}
(OUT / "w74-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
