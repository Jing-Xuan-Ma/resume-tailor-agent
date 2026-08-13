"""Human-path UI selftest for Tailor flow chrome (JD / Tailor / Apply / Outreach).

Simulates clicks through the funnel, asserts stepper labels/numbers, screenshots each step.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui" / "flow-chrome"
OUT.mkdir(parents=True, exist_ok=True)

API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
TOKEN = "dev-extension-token"
DEMO_EMAIL = "demo@resume-agent.local"
DEMO_PASSWORD = "demo-pass-1234"

JD_TEXT = """Data Analyst at Northwind Analytics

About the role
We are hiring a Data Analyst to partner with product and growth teams. You will own SQL pipelines,
dashboard storytelling, and experiment readouts for weekly stakeholder reviews. This role sits at
the intersection of analytics engineering and decision science.

Responsibilities
• Write production-quality SQL against a cloud warehouse (BigQuery / Snowflake)
• Build Tableau or Power BI dashboards used weekly by stakeholders
• Partner on A/B test design and interpret results with clear recommendations
• Document metrics definitions and improve data quality with engineers
• Translate ambiguous business questions into measurable analyses

Requirements
• 2+ years as a Data Analyst or similar
• Strong SQL and analytical storytelling
• Python or R for data wrangling
• Experience with Tableau, Power BI, or Looker
• Clear communication with non-technical stakeholders
• Comfortable with git and collaborative documentation

Preferred
• Experimentation / A/B testing exposure
• dbt or similar transformation tooling
• Familiarity with product analytics funnels
• Cloud data warehouse exposure

Job description
This is a full job description suitable for resume tailoring. Minimum qualifications include SQL,
dashboards, and stakeholder communication. What you'll do day to day is translate ambiguous
business questions into measurable analyses and ship clear recommendations.
"""

EXPECTED_STEPS = [
    ("jobs", "1. Jobs"),
    ("detail", "2. Match"),
    ("jd", "3. JD"),
    ("tailor", "4. Tailor"),
    ("apply", "5. Apply"),
    ("outreach", "6. Outreach"),
]

results: dict = {"checks": [], "ok": True, "notes": []}


def check(name: str, passed: bool, detail: str = ""):
    results["checks"].append({"name": name, "passed": passed, "detail": detail})
    if not passed:
        results["ok"] = False
    print(("PASS" if passed else "FAIL"), name, detail)


def note(msg: str):
    results["notes"].append(msg)
    print("NOTE", msg)


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


def assert_stepper(page, expect_active: str | None = None, context: str = ""):
    stepper = page.locator("[data-testid=flow-stepper]").first
    if stepper.count() == 0:
        check(f"stepper_present_{context}", False, "no flow-stepper")
        return
    check(f"stepper_present_{context}", True)

    # Confirm must NOT appear in the guidance bar
    texts = stepper.inner_text()
    check(
        f"no_confirm_in_stepper_{context}",
        "Confirm" not in texts and "5. Confirm" not in texts,
        texts.replace("\n", " | ")[:200],
    )

    for sid, label in EXPECTED_STEPS:
        chip = page.locator(f"[data-testid=flow-step-{sid}]")
        ok = chip.count() > 0
        check(f"step_{sid}_exists_{context}", ok)
        if ok:
            actual = chip.first.inner_text().strip()
            check(f"step_{sid}_label_{context}", actual == label, f"got={actual!r}")

    # Exactly 6 chips
    n = sum(1 for sid, _ in EXPECTED_STEPS if page.locator(f"[data-testid=flow-step-{sid}]").count())
    check(f"step_count_6_{context}", n == 6, f"n={n}")

    if expect_active:
        chip = page.locator(f"[data-testid=flow-step-{expect_active}]").first
        cls = chip.get_attribute("class") or ""
        check(
            f"active_{expect_active}_{context}",
            "bg-emerald-600" in cls,
            cls[:120],
        )


def shot(page, name: str):
    path = OUT / name
    page.screenshot(path=str(path), full_page=False)
    note(f"screenshot {path.name}")


def main() -> int:
    try:
        h = httpx.get(f"{API}/health", timeout=5)
        check("api_health", h.status_code == 200, h.text[:80])
    except Exception as exc:
        check("api_health", False, str(exc))
        (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return 1

    payload = {
        "title": "Data Analyst",
        "company": "Northwind Analytics",
        "location": "Remote",
        "raw_text": JD_TEXT,
        "source_url": "https://boards.greenhouse.io/northwind/jobs/ui-selftest",
        "jobright_url": f"{FE}/",
        "source_platform": "flow_chrome_selftest",
        "force": True,
    }
    res = httpx.post(
        f"{API}/api/v1/jobs/index/leads",
        headers={"X-Extension-Token": TOKEN, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    check("upsert_lead", res.status_code == 200, res.text[:200])
    if res.status_code != 200:
        (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        return 1
    job_id = res.json()["id"]
    results["job_id"] = job_id

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        ensure_demo_auth(page)

        # --- 1) Jobs list ---
        page.goto(f"{FE}/jobs", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        shot(page, "01-jobs.png")
        assert_stepper(page, expect_active="jobs", context="jobs")

        # --- 2) Match / job detail ---
        page.goto(f"{FE}/jobs/{job_id}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        shot(page, "02-match.png")
        assert_stepper(page, expect_active="detail", context="match")

        # Click into JD via stepper href if present
        jd_chip = page.locator("[data-testid=flow-step-jd]")
        if jd_chip.count() and jd_chip.first.get_attribute("href"):
            jd_chip.first.click()
            page.wait_for_timeout(2000)
        else:
            page.goto(
                f"{FE}/?view=resume&jobId={job_id}&step=jd",
                wait_until="domcontentloaded",
                timeout=90000,
            )
            page.wait_for_timeout(2500)

        # --- 3) JD panel ---
        page.wait_for_selector("[data-testid=resume-workspace]", timeout=45000)
        page.wait_for_timeout(1500)
        shot(page, "03-jd.png")
        assert_stepper(page, expect_active="jd", context="jd")
        check("jd_panel_visible", page.locator("[data-testid=workspace-jd-panel]").count() > 0)
        check("no_qualification_tags", page.locator("[data-testid=qualification-tags]").count() == 0)
        check("jd_required_or_plaintext", page.locator("[data-testid=jd-required], [data-testid=jd-plaintext], [data-testid=jd-overview]").count() > 0)
        check("no_workspace_subtabs", page.locator("[data-testid=workspace-tabs]").count() == 0)

        # Click 4. Tailor in stepper
        tailor_btn = page.locator("[data-testid=flow-step-tailor]")
        check("tailor_chip_clickable", tailor_btn.count() > 0)
        tailor_btn.first.click()
        page.wait_for_timeout(1200)

        # --- 4) Tailor (agent + PDF) ---
        shot(page, "04-tailor.png")
        assert_stepper(page, expect_active="tailor", context="tailor")
        check("tailor_panel_visible", page.locator("[data-testid=workspace-tailor-panel]").count() > 0)
        check("chat_visible", page.locator("[data-testid=workspace-chat]").count() > 0 or page.get_by_text("Resume Agent").count() > 0)
        check("preview_visible", page.locator("[data-testid=resume-preview]").count() > 0)
        # JD should NOT be stacked in tailor panel
        check(
            "jd_not_in_tailor_panel",
            page.locator("[data-testid=workspace-tailor-panel] [data-testid=jd-panel]").count() == 0,
        )
        # Confirm is action button, not stepper chip
        check("confirm_action_btn", page.locator("[data-testid=confirm-version]").count() > 0)
        check("confirm_not_step_chip", page.locator("[data-testid=flow-step-confirm]").count() == 0)

        # Click Apply chip → navigate to dedicated Apply page
        apply_chip = page.locator("[data-testid=flow-step-apply]")
        with page.expect_navigation(timeout=30000):
            apply_chip.first.click()
        page.wait_for_timeout(1000)
        shot(page, "05-apply-page.png")
        check("apply_page_url", "/apply" in page.url, page.url)
        check(
            "apply_workspace_or_gate",
            page.locator("[data-testid=apply-workspace], [data-testid=apply-confirm-gate]").count() > 0
            or "apply" in page.url.lower(),
        )
        # Confirm under PDF (back on tailor) — no inline Step 5/6 cards
        page.go_back()
        page.wait_for_selector("[data-testid=resume-workspace]", timeout=60000)
        page.wait_for_timeout(800)
        check("no_inline_apply_panel", page.locator("[data-testid=apply-mode-panel]").count() == 0)
        check("no_inline_outreach_card", page.locator("[data-testid=outreach-open-card]").count() == 0)
        check("confirm_under_pdf", page.locator("[data-testid=tailor-confirm-card] [data-testid=confirm-version]").count() > 0)

        # --- 6) Outreach page (same-tab navigation) ---
        with page.expect_navigation(timeout=30000):
            page.locator("[data-testid=flow-step-outreach]").first.click()
        page.wait_for_selector("[data-testid=outreach-step-panel]", timeout=30000)
        page.wait_for_timeout(800)
        shot(page, "06-outreach.png")
        assert_stepper(page, expect_active="outreach", context="outreach")
        oh = page.locator("[data-testid=outreach-step-panel] h3").first
        if oh.count():
            ot = oh.inner_text()
            check("outreach_says_step_6", "Step 6" in ot, ot)
            check("outreach_not_step_7", "7. Outreach" not in page.locator("[data-testid=flow-stepper]").inner_text(), ot)

        # Deeplink should land on Tailor (skip JD)
        page.goto(
            f"{FE}/?view=resume&jobId={job_id}&step=tailor&returnTo={FE}/",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        try:
            page.wait_for_selector("[data-testid=resume-workspace]", timeout=60000)
        except Exception as exc:
            shot(page, "07-jobright-deeplink-fail.png")
            check("jobright_lands_on_tailor", False, str(exc))
            browser.close()
            (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            return 1
        page.wait_for_timeout(2000)
        shot(page, "07-jobright-deeplink-tailor.png")
        check(
            "jobright_lands_on_tailor",
            page.locator("[data-testid=workspace-tailor-panel]").count() > 0,
        )
        check(
            "jobright_back_link",
            page.locator("[data-testid=back-to-jobright]").count() > 0,
        )
        assert_stepper(page, expect_active="tailor", context="jobright_deeplink")

        # In-app open (no returnTo) should show ← Jobs, not ← Jobright for mock fixture
        page.goto(
            f"{FE}/?view=resume&jobId={job_id}&step=jd",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        page.wait_for_selector("[data-testid=resume-workspace]", timeout=60000)
        page.wait_for_timeout(1500)
        shot(page, "08-inapp-jd-back-jobs.png")
        check("inapp_back_is_jobs", page.locator("a", has_text="← Jobs").count() > 0)
        check("inapp_no_jobright_back", page.locator("[data-testid=back-to-jobright]").count() == 0)
        check("jd_hides_confirm_btn", page.locator("[data-testid=confirm-version]").count() == 0)

        # Header crowding: measure header height
        header = page.locator("[data-testid=resume-workspace] > header").first
        if header.count():
            box = header.bounding_box()
            if box:
                check("header_height_reasonable", box["height"] < 120, f"h={box['height']}")
                note(f"header box={box}")

        browser.close()

    (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    md = ["# Flow chrome selftest", "", f"**Result:** {'PASS' if results['ok'] else 'FAIL'}", ""]
    for c in results["checks"]:
        md.append(f"- {'✅' if c['passed'] else '❌'} `{c['name']}` {c.get('detail') or ''}")
    md.append("")
    md.append("## Screenshots")
    for pth in sorted(OUT.glob("*.png")):
        md.append(f"- `{pth.name}`")
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print("OK" if results["ok"] else "FAIL")
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
