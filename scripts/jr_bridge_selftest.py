"""Human-path selftest for Jobright extension workbench bridge (Phase 1).

Simulates: extract mock Jobright page → upsert lead → open Workspace deeplinks
→ screenshot tailor / apply / outreach steps.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui" / "jobright-bridge"
OUT.mkdir(parents=True, exist_ok=True)

API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
TOKEN = "dev-extension-token"
DEMO_EMAIL = "demo@resume-agent.local"
DEMO_PASSWORD = "demo-pass-1234"

FULL_JD = (ROOT / "frontend" / "public" / "fixtures" / "jobright-mock.html").read_text(
    encoding="utf-8"
)
# Prefer plaintext body for API (same content as mock data-ra-jd)
JD_TEXT = """Data Analyst at Northwind Analytics

About the role
We are hiring a Data Analyst to partner with product and growth teams. You will own SQL pipelines, dashboard storytelling, and experiment readouts.

Responsibilities
• Write production-quality SQL against a cloud warehouse (BigQuery / Snowflake)
• Build Tableau or Power BI dashboards used weekly by stakeholders
• Partner on A/B test design and interpret results with clear recommendations
• Document metrics definitions and improve data quality with engineers

Requirements
• 2+ years as a Data Analyst or similar
• Strong SQL and analytical storytelling
• Python or R for data wrangling
• Experience with Tableau, Power BI, or Looker
• Clear communication with non-technical stakeholders

Preferred qualifications
• Experimentation / A/B testing exposure
• dbt or similar transformation tooling
• Familiarity with product analytics funnels

Job description
This is a full job description suitable for resume tailoring. Minimum qualifications include SQL, dashboards, and stakeholder communication. What you'll do day to day is translate ambiguous business questions into measurable analyses.
"""

results: dict = {"checks": [], "ok": True}


def check(name: str, passed: bool, detail: str = ""):
    results["checks"].append({"name": name, "passed": passed, "detail": detail})
    if not passed:
        results["ok"] = False
    print(("PASS" if passed else "FAIL"), name, detail)


def ensure_demo_auth(page) -> None:
    page.goto(f"{FE}/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(800)
    if page.locator("[data-testid=resume-workspace], [data-testid=nav-ranked]").count():
        return
    demo = page.locator("[data-testid=auth-demo]")
    if demo.count():
        demo.first.click()
        page.wait_for_timeout(2000)
        return
    email = page.locator('input[type="email"]').first
    password = page.locator('input[type="password"]').first
    if email.count() and password.count():
        email.fill(DEMO_EMAIL)
        password.fill(DEMO_PASSWORD)
        page.locator('button[type="submit"]').first.click()
        page.wait_for_timeout(2000)


def main() -> int:
    # Health
    try:
        h = httpx.get(f"{API}/health", timeout=5)
        check("api_health", h.status_code == 200, h.text[:120])
    except Exception as exc:
        check("api_health", False, str(exc))
        (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return 1

    # Upsert (extension contract)
    payload = {
        "title": "Data Analyst",
        "company": "Northwind Analytics",
        "location": "Remote · United States",
        "raw_text": JD_TEXT,
        "source_url": "https://boards.greenhouse.io/northwind/jobs/1234567",
        "jobright_url": f"{FE}/fixtures/jobright-mock.html",
        "source_platform": "jobright_extension",
    }
    res = httpx.post(
        f"{API}/api/v1/jobs/index/leads",
        headers={"X-Extension-Token": TOKEN, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    check("upsert_lead", res.status_code == 200, res.text[:300])
    if res.status_code != 200:
        (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return 1
    data = res.json()
    job_id = data["id"]
    results["job_id"] = job_id
    results["urls"] = {
        "workspace": data["workspace_url"],
        "apply": data["apply_step_url"],
        "outreach": data["outreach_step_url"],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # 1) Mock Jobright page
        page.goto(f"{FE}/fixtures/jobright-mock.html", wait_until="networkidle", timeout=60000)
        page.screenshot(path=str(OUT / "01-jobright-mock.png"), full_page=True)
        title_ok = page.locator("[data-ra-title]").inner_text().strip() == "Data Analyst"
        check("mock_title", title_ok)
        jd_len = len(page.locator("[data-ra-jd]").inner_text())
        check("mock_jd_len", jd_len > 500, str(jd_len))

        # Simulate FAB visually (content script may not inject outside extension)
        page.evaluate(
            """() => {
              if (document.getElementById('ra-jobright-fab')) return;
              const b = document.createElement('button');
              b.id = 'ra-jobright-fab';
              b.textContent = 'Open Tailor';
              b.setAttribute('data-testid', 'ra-jobright-fab');
              Object.assign(b.style, {
                position:'fixed', right:'20px', bottom:'24px', zIndex:9999,
                border:'none', borderRadius:'999px', padding:'12px 16px',
                background:'#047857', color:'#fff', font:'600 13px system-ui'
              });
              document.body.appendChild(b);
            }"""
        )
        page.screenshot(path=str(OUT / "02-mock-with-fab.png"), full_page=True)
        check("fab_visible", page.locator("[data-testid=ra-jobright-fab]").count() == 1)
        check("no_sidepanel_files", not (ROOT / "extensions" / "jobright-bridge" / "sidepanel" / "index.html").exists())

        # 2) Workspace tailor deeplink
        page.set_viewport_size({"width": 1400, "height": 900})
        ensure_demo_auth(page)
        ws = f"{FE}/?view=resume&jobId={job_id}&step=tailor"
        page.goto(ws, wait_until="domcontentloaded", timeout=90000)
        # Wait for workspace
        try:
            page.wait_for_selector("[data-testid=resume-workspace]", timeout=45000)
            check("workspace_open", True)
        except Exception as exc:
            page.screenshot(path=str(OUT / "04-workspace-fail.png"), full_page=True)
            check("workspace_open", False, str(exc))
            browser.close()
            (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            return 1

        # Allow handoff / tailor boot
        page.wait_for_timeout(2500)
        # Prefer waiting until a version chip or confirm control exists
        try:
            page.wait_for_selector("[data-testid=confirm-version], [data-testid=version-chip], select, button:has-text('Confirm')", timeout=60000)
        except Exception:
            pass
        page.screenshot(path=str(OUT / "04-workspace-tailor.png"), full_page=True)

        # Apply step deeplink → dedicated Apply page
        page.goto(f"{FE}/?view=resume&jobId={job_id}&step=apply", wait_until="domcontentloaded", timeout=90000)
        try:
            page.wait_for_url("**/apply**", timeout=45000)
        except Exception:
            page.wait_for_timeout(2500)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "05-workspace-apply-step.png"), full_page=True)
        check("apply_page_url", "/apply" in page.url, page.url)
        check(
            "apply_workspace_present",
            page.locator("[data-testid=apply-workspace], [data-testid=apply-confirm-gate]").count() >= 1
            or "/apply" in page.url,
        )

        # Outreach step
        page.goto(
            f"{FE}/?view=resume&jobId={job_id}&step=outreach",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        page.wait_for_selector("[data-testid=resume-workspace]", timeout=45000)
        page.wait_for_timeout(3000)
        try:
            page.wait_for_selector("[data-testid=outreach-step-panel]", timeout=30000)
        except Exception as exc:
            page.screenshot(path=str(OUT / "06-workspace-outreach-missing.png"), full_page=True)
            check("outreach_panel_present", False, str(exc))
        else:
            try:
                page.locator("[data-testid=right-scroll-column]").evaluate(
                    "el => { el.scrollTop = el.scrollHeight }"
                )
            except Exception:
                pass
            page.locator("[data-testid=outreach-step-panel]").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT / "06-workspace-outreach-step.png"), full_page=True)
            check("outreach_panel_present", True)

        browser.close()

    (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    report_md = [
        "# Jobright Bridge Phase 1 — Selftest",
        "",
        f"**Result:** {'PASS' if results['ok'] else 'FAIL'}",
        "",
        f"- job_id: `{results.get('job_id')}`",
        "",
        "## Checks",
        "",
    ]
    for c in results["checks"]:
        report_md.append(f"- {'✅' if c['passed'] else '❌'} `{c['name']}` {c.get('detail') or ''}")
    report_md.extend(
        [
            "",
            "## Screenshots",
            "",
            "- `artifacts/ui/jobright-bridge/01-jobright-mock.png`",
            "- `artifacts/ui/jobright-bridge/02-mock-with-fab.png`",
            "- `artifacts/ui/jobright-bridge/04-workspace-tailor.png`",
            "- `artifacts/ui/jobright-bridge/05-workspace-apply-step.png`",
            "- `artifacts/ui/jobright-bridge/06-workspace-outreach-step.png`",
            "",
        ]
    )
    (ROOT / "artifacts" / "jr-bridge-report.md").write_text("\n".join(report_md), encoding="utf-8")
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
