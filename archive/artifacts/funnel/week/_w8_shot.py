"""W8: Tailor first-paint screenshot — HTML visible quickly after rewrite response."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"

with httpx.Client(timeout=60) as client:
    auth = client.post(
        f"{API}/api/v1/auth/login",
        json={"email": "demo@resume-agent.local", "password": "demo-pass-1234"},
    ).json()
token, user = auth["access_token"], auth["user"]
blob = {"token": token, "user": {"id": user["id"], "email": user["email"], "full_name": user.get("full_name")}}

row = sqlite3.connect(r"d:\resume-agent\data\app.db").execute(
    "SELECT id FROM job_listings WHERE status='active' "
    "AND lower(title) LIKE '%data analyst%' ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
job_id = row[0] if row else None
assert job_id, "no job"

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.goto(FE + "/", wait_until="domcontentloaded", timeout=60000)
    page.evaluate(
        """(blob) => localStorage.setItem('resume-agent-auth', JSON.stringify(blob))""",
        blob,
    )
    url = f"{FE}/?view=resume&jobId={job_id}"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("[data-testid=resume-workspace]", timeout=30000)
    except Exception as exc:
        ok("w8_workspace", False, str(exc))
        page.screenshot(path=str(OUT / "w8-first-paint-fail.png"), full_page=True)
        browser.close()
        raise SystemExit(1)

    try:
        page.wait_for_selector(
            "[data-testid='html-preview-fallback'], [data-testid='preview-first-paint'], [data-testid='master-pdf-iframe'], [data-testid='preview-empty-skeleton']",
            timeout=180000,
        )
    except Exception as exc:
        ok("w8_preview_appeared", False, str(exc))
        page.screenshot(path=str(OUT / "w8-first-paint-fail.png"), full_page=True)
        browser.close()
        raise SystemExit(1)

    # Prefer detecting HTML first-paint if present during/after tailor
    html = page.locator("[data-testid='html-preview-fallback'], [data-testid='preview-first-paint']")
    pdf = page.locator("[data-testid='master-pdf-iframe']")
    skeleton = page.locator("[data-testid='preview-empty-skeleton']")
    # Poll up to 90s for content
    has_html = False
    has_pdf = False
    for i in range(90):
        has_html = html.count() > 0
        has_pdf = pdf.count() > 0
        if has_html or has_pdf:
            break
        page.wait_for_timeout(1000)
    ok("w8_first_paint_html_or_pdf", has_html or has_pdf, f"html={has_html} pdf={has_pdf} skeleton={skeleton.count()>0}")
    page.screenshot(path=str(OUT / "w8-first-paint.png"), full_page=True)
    score = 5 if has_html else (4 if has_pdf else 2)
    report = {
        "passed": all(c for _, c, _ in CHECKS),
        "score_tailor_speed": score,
        "has_html": has_html,
        "has_pdf": has_pdf,
        "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
    }
    (OUT / "w8-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    browser.close()
    raise SystemExit(0 if report["passed"] else 1)
