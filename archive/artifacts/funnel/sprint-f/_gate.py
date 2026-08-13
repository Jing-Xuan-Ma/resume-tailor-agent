"""Sprint F gate: HM playbook links + draft after apply path."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\funnel\sprint-f")
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
token, user = auth["access_token"], auth["user"]
user_id = user["id"]
auth_blob = {"token": token, "user": {"id": user_id, "email": user["email"], "full_name": user.get("full_name")}}

row = sqlite3.connect(r"d:\resume-agent\data\app.db").execute(
    "SELECT id, title, company FROM job_listings WHERE status='active' AND lower(title) LIKE '%analyst%' ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
job_id, title, company = row

# API drafts with HM metadata
with httpx.Client(timeout=60) as client:
    d1 = client.post(
        f"{API}/api/v1/outreach/draft",
        json={
            "user_id": user_id,
            "job_id": job_id,
            "company": company,
            "contact_role": "Hiring Manager",
            "template_type": "coffee_chat",
            "channel": "linkedin",
            "tone": "warm",
            "linkedin_url": "https://www.linkedin.com/in/example-hm",
        },
    )
    ok("api_coffee_chat", d1.status_code < 400, str(d1.status_code))
    meta = (d1.json() or {}).get("metadata") or {}
    ok("has_search_hint", bool(meta.get("linkedin_search_hint")), str(meta.get("linkedin_search_hint")))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1440, "height": 1000}).new_page()
    page.goto(FE, wait_until="domcontentloaded")
    page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", auth_blob)
    page.goto(f"{FE}/?view=resume&jobId={job_id}", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=resume-workspace]", timeout=30000)

    ui_vid = None
    last = None
    stable = 0
    for _ in range(120):
        sel = page.locator("[data-testid=version-select]")
        if sel.count():
            cur = sel.input_value()
            if cur and cur == last:
                stable += 1
            else:
                stable = 0
                last = cur
            if cur and stable >= 3:
                ui_vid = cur
                break
        page.wait_for_timeout(1000)
    ok("ui_version", bool(ui_vid), ui_vid or "")
    if ui_vid:
        sqlite3.connect(r"d:\resume-agent\data\app.db").execute(
            "UPDATE resume_versions SET is_confirmed=1, confirmed_at=datetime('now') WHERE id=?",
            (ui_vid,),
        ).connection.commit()
        page.locator("[data-testid=apply-auto]").click()
        page.wait_for_selector("[data-testid=outreach-step-panel]", timeout=20000)
        page.evaluate(
            "() => document.querySelector('[data-testid=outreach-step-panel]')?.scrollIntoView({block:'center'})"
        )
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "01-hm-playbook.png"), full_page=False)
        ok("hm_playbook", page.locator("[data-testid=hm-playbook]").count() > 0, "")
        links = page.locator("[data-testid=hm-linkedin-search]")
        ok("linkedin_search_links_ge_2", links.count() >= 2, str(links.count()))
        href = links.first.get_attribute("href") or ""
        ok("linkedin_href", "linkedin.com/search" in href, href[:80])
        page.fill("[data-testid=outreach-contact-name]", "Sam Hiring")
        page.click("[data-testid=outreach-draft-btn]")
        page.wait_for_selector("[data-testid=outreach-drafts] > div", timeout=15000)
        page.screenshot(path=str(OUT / "02-hm-draft.png"), full_page=False)
        ok("draft_after_find", page.locator("[data-testid=outreach-drafts] > div").count() >= 1, "")
    browser.close()

passed = all(c for _, c, _ in CHECKS)
report = {"sprint": "F", "passed": passed, "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS]}
(OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
sys.exit(0 if passed else 1)
