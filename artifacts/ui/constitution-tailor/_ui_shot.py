"""Auth via API + localStorage, then capture master PDF iframe preview."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\ui\constitution-tailor")
API = "http://127.0.0.1:8000"

# login / register demo
with httpx.Client(timeout=30) as client:
    try:
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
    except Exception as exc:
        raise SystemExit(f"auth failed: {exc}")

auth_blob = {"token": token, "user": {"id": user["id"], "email": user["email"], "full_name": user.get("full_name")}}
print("user", user["id"])

row = sqlite3.connect(r"d:\resume-agent\data\app.db").execute(
    "SELECT id, title FROM job_listings WHERE status='active' AND lower(title) LIKE '%data analyst%' ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
job_id, title = row
url = f"http://127.0.0.1:3000/?view=resume&jobId={job_id}"
print("OPEN", title)

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
    print("workspace ok")

    for i in range(150):
        if page.locator("[data-testid=master-pdf-iframe]").count():
            page.wait_for_timeout(6000)
            page.locator("[data-testid=master-pdf-preview]").first.scroll_into_view_if_needed()
            page.wait_for_timeout(1000)
            page.locator("[data-testid=master-pdf-preview]").first.screenshot(
                path=str(OUT / "11-ui-preview.png")
            )
            page.screenshot(path=str(OUT / "12-ui-full.png"), full_page=False)
            print("CAPTURED")
            break
        page.wait_for_timeout(1000)
        if i % 15 == 0:
            print("waiting", i)
    else:
        page.screenshot(path=str(OUT / "12-ui-full.png"), full_page=False)
        print("FAILED no iframe")
        raise SystemExit(2)

    assert "Master template preview" in page.inner_text("body")
    assert "## EDUCATION" not in page.inner_text("body")
    print("UI_PASS", True)
    browser.close()
