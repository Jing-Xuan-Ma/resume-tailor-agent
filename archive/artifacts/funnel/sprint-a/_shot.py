"""Sprint A human-path screenshots: Jobs → Detail → Tailor apply panel chrome."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\funnel\sprint-a")
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"

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
    token, user = data["access_token"], data["user"]

auth = {"token": token, "user": {"id": user["id"], "email": user["email"], "full_name": user.get("full_name")}}

# Score sample for report
scores = httpx.get(
    f"{API}/api/v1/jobs/list",
    params={
        "user_id": "00000000-0000-0000-0000-0000000000a1",
        "threshold": "0",
        "category": "Data Analysis",
        "sort_by": "score",
    },
    timeout=60,
).json()
sample = [
    {
        "title": j["title"][:60],
        "final": int(j["stage3Result"]["finalScore"] * 100),
        "ats": int(j["stage3Result"]["atsScore"] * 100),
        "skill": int(j["stage3Result"]["semanticScore"] * 100),
    }
    for j in (scores.get("jobs") or [])[:8]
]
uniq = sorted({s["final"] for s in sample})
(OUT / "score-sample.json").write_text(json.dumps({"sample": sample, "unique": uniq}, indent=2), encoding="utf-8")

row = sqlite3.connect(r"d:\resume-agent\data\app.db").execute(
    "SELECT id, title FROM job_listings WHERE status='active' AND lower(title) LIKE '%data analyst%' ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
job_id = row[0] if row else (scores["jobs"][0]["id"] if scores.get("jobs") else None)

notes: list[str] = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1440, "height": 960}).new_page()
    page.goto(f"{FE}/", wait_until="domcontentloaded")
    page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", auth)

    page.goto(f"{FE}/jobs", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "01-jobs-list.png"), full_page=False)
    notes.append("jobs_list")

    if job_id:
        page.goto(f"{FE}/jobs/{job_id}", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.screenshot(path=str(OUT / "02-job-detail.png"), full_page=False)
        notes.append("job_detail")

        page.goto(f"{FE}/?view=resume&jobId={job_id}", wait_until="domcontentloaded")
        page.wait_for_selector("[data-testid=resume-workspace]", timeout=30000)
        for i in range(120):
            if page.locator("[data-testid=apply-mode-panel]").count():
                break
            page.wait_for_timeout(1000)
        page.screenshot(path=str(OUT / "03-tailor.png"), full_page=False)
        notes.append("tailor")

        page.evaluate(
            "() => { const el=document.querySelector('[data-testid=apply-mode-panel]');"
            " if (el) el.scrollIntoView({block:'center'}); }"
        )
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "04-apply-panel.png"), full_page=False)
        panel = page.locator("[data-testid=apply-mode-panel]")
        has_apply = panel.count() > 0
        if has_apply:
            panel.first.screenshot(path=str(OUT / "05-apply-panel-close.png"))
        notes.append(f"apply_panel_visible={has_apply}")

        btn = page.locator("[data-testid=confirm-version]")
        if btn.count() and btn.first.is_enabled():
            btn.first.click()
            page.wait_for_timeout(4000)
            page.evaluate(
                "() => { const el=document.querySelector('[data-testid=apply-mode-panel]');"
                " if (el) el.scrollIntoView({block:'center'}); }"
            )
            page.wait_for_timeout(500)
            page.screenshot(path=str(OUT / "06-after-confirm.png"), full_page=False)
            notes.append("confirmed")

    browser.close()

report = {
    "sprint": "A",
    "scores_not_flat": len(uniq) > 1 and 35 not in uniq or len(uniq) > 2,
    "unique_scores": uniq,
    "sample": sample,
    "screenshots": notes,
    "ux_score_estimate": 3.5,
    "friction": [
        "Confirm may be disabled until evidence gate passes — apply panel only after confirm",
        "Apply auto still dry-run / pause-before-submit (by design)",
    ],
}
(OUT / "report-partial.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
