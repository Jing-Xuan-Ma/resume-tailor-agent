"""UI screenshots for Agent2 Tailor & Store (Word PDF preview + Confirm)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\funnel\agent2")
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"

with httpx.Client(timeout=30) as client:
    r = client.post(
        f"{API}/api/v1/auth/login",
        json={"email": "demo@resume-agent.local", "password": "demo-pass-1234"},
    )
    if r.status_code >= 400:
        r = client.post(
            f"{API}/api/v1/auth/register",
            json={
                "email": "demo@resume-agent.local",
                "password": "demo-pass-1234",
                "full_name": "Demo User",
            },
        )
    data = r.json()
    token = data["access_token"]
    user = data["user"]

auth_blob = {
    "token": token,
    "user": {"id": user["id"], "email": user["email"], "full_name": user.get("full_name")},
}

row = sqlite3.connect(r"d:\resume-agent\data\app.db").execute(
    "SELECT id, title, company FROM job_listings WHERE status='active' "
    "AND lower(title) LIKE '%data analyst%' ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
if not row:
    raise SystemExit("no DA job listing")
job_id, title, company = row
url = f"http://127.0.0.1:3000/?view=resume&jobId={job_id}"
print("OPEN", company, title)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    context = browser.new_context(viewport={"width": 1500, "height": 1000})
    page = context.new_page()
    page.goto("http://127.0.0.1:3000/", wait_until="domcontentloaded")
    page.evaluate(
        """(blob) => localStorage.setItem('resume-agent-auth', JSON.stringify(blob))""",
        auth_blob,
    )
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=resume-workspace]", timeout=30000)

    iframe_ok = False
    for i in range(180):
        if page.locator("[data-testid=master-pdf-iframe]").count():
            page.wait_for_timeout(5000)
            page.locator("[data-testid=master-pdf-preview]").first.scroll_into_view_if_needed()
            page.wait_for_timeout(800)
            page.locator("[data-testid=master-pdf-preview]").first.screenshot(
                path=str(OUT / "02-word-pdf-preview.png")
            )
            page.screenshot(path=str(OUT / "03-tailor-workspace.png"), full_page=False)
            iframe_ok = True
            break
        page.wait_for_timeout(1000)
        if i % 20 == 0:
            print("waiting preview", i)
    if not iframe_ok:
        page.screenshot(path=str(OUT / "03-tailor-workspace.png"), full_page=False)
        raise SystemExit("no master PDF iframe")

    body = page.inner_text("body")
    assert "Master template preview" in body or "OOXML" in body
    assert "## EDUCATION" not in body
    assert "**Summary**" not in body

    # Confirm if enabled
    btn = page.locator("[data-testid=confirm-version]")
    if btn.count() and btn.is_enabled():
        btn.click()
        page.wait_for_timeout(2500)
        page.screenshot(path=str(OUT / "04-after-confirm.png"), full_page=False)
        if page.locator("[data-testid=final-save-path]").count():
            print("FINAL", page.locator("[data-testid=final-save-path]").inner_text()[:160])
    else:
        print("confirm disabled — skipping click")
        page.screenshot(path=str(OUT / "04-confirm-disabled.png"), full_page=False)

    browser.close()

meta = {
    "job_id": job_id,
    "title": title,
    "company": company,
    "screenshots": sorted(p.name for p in OUT.glob("*.png")),
}
(OUT / "ui_shot_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("UI_PASS", True)
