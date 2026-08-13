"""Self-test E2E: critical funnel UI paths until satisfied."""
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
    health = client.get(f"{API}/health").json()
    jobspy = client.get(f"{API}/api/v1/jobs/providers/jobspy/health").json()
ok("api_healthy", health.get("status") == "healthy", str(health))
ok("jobspy_ok", jobspy.get("status") == "ok", str(jobspy)[:120])

blob = {
    "token": auth["access_token"],
    "user": {
        "id": auth["user"]["id"],
        "email": auth["user"]["email"],
        "full_name": auth["user"].get("full_name"),
    },
}
uid = auth["user"]["id"]

row = sqlite3.connect(r"d:\resume-agent\data\app.db").execute(
    "SELECT id FROM job_listings WHERE status='active' "
    "AND scraped_at >= datetime('now','-30 days') ORDER BY scraped_at DESC LIMIT 1"
).fetchone()
ok("db_has_job", bool(row))
job_id = row[0] if row else None

ws = Path(r"d:\resume-agent\frontend\components\resume-workspace.tsx").read_text(encoding="utf-8")
ap = Path(r"d:\resume-agent\frontend\components\apply-mode-panel.tsx").read_text(encoding="utf-8")
ou = Path(r"d:\resume-agent\frontend\components\outreach-step-panel.tsx").read_text(encoding="utf-8")
ok("policy_confirm_shortcut", "Ctrl+Shift+Enter" in ws)
ok("policy_never_submit_ui", "apply-never-submit" in ap)
ok("policy_no_auto_send", "outreach-no-auto-send" in ou)
ok("policy_apply_always_visible", "waiting_version" in ws and "<ApplyModePanel" in ws)
ok("policy_soft_confirm_star", "Confirm*" in ws)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(FE, wait_until="domcontentloaded")
    page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", blob)

    # 1) Ranked jobs
    page.goto(f"{FE}/jobs", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=ranked-jobs-page]", timeout=30000)
    page.wait_for_timeout(1000)
    ok("ui_ranked", page.locator("[data-testid=ranked-jobs-page]").count() > 0)
    ok("ui_jobspy_chip", page.locator("[data-testid=jobspy-health-chip]").count() > 0)
    ok("ui_tailor_cta", page.locator("[data-testid^=job-tailor-]").count() > 0)
    ok("ui_flow_jobs", page.locator("[data-testid=flow-step-jobs]").count() > 0)
    page.keyboard.press("/")
    page.wait_for_timeout(200)
    focused = page.evaluate("() => document.activeElement?.getAttribute('data-testid')")
    ok("ui_slash_focus_search", focused == "jobs-search", str(focused))
    page.screenshot(path=str(OUT / "selftest-01-ranked.png"), full_page=False)

    # 2) Job detail
    assert job_id
    page.goto(f"{FE}/jobs/{job_id}", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=job-detail-page]", timeout=30000)
    page.wait_for_timeout(1200)
    ok("ui_detail", page.locator("[data-testid=job-detail-page]").count() > 0)
    ok("ui_scored_or_score", page.locator("[data-testid=job-detail-score]").count() > 0)
    ok("ui_customize_cta", page.locator("[data-testid=cta-customize-resume]").count() > 0)
    page.screenshot(path=str(OUT / "selftest-02-detail.png"), full_page=False)

    # 3) Tailor — wait for version like main gate
    page.goto(f"{FE}/?view=resume&jobId={job_id}", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=resume-workspace]", timeout=45000)
    ui_vid = None
    last = None
    stable = 0
    for _ in range(90):
        # Apply panel should be visible even before version (always-on)
        if page.locator("[data-testid=apply-mode-panel]").count() > 0:
            break
        page.wait_for_timeout(500)
    ok("ui_apply_panel_early", page.locator("[data-testid=apply-mode-panel]").count() > 0)
    ok("ui_never_submit", page.locator("[data-testid=apply-never-submit]").count() > 0)

    for _ in range(90):
        sel = page.locator("[data-testid=version-select]")
        if sel.count():
            cur = sel.input_value()
            if cur and cur == last:
                stable += 1
            else:
                stable = 0
                last = cur
            if cur and stable >= 2:
                ui_vid = cur
                break
        page.wait_for_timeout(1000)
    ok("ui_tailor_version", bool(ui_vid), ui_vid or "timeout")
    ok("ui_confirm_btn", page.locator("[data-testid=confirm-version]").count() > 0)
    ok("ui_kbd_hints", page.locator("[data-testid=tailor-kbd-hints]").count() > 0)
    ok("ui_chat", page.locator("[data-testid=workspace-chat]").count() > 0)

    # Esc closes paste
    if page.locator("text=Paste JD").count():
        page.locator("text=Paste JD").first.click()
        page.wait_for_selector("[data-testid=paste-jd-box]", timeout=5000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        ok("ui_esc_closes_paste", page.locator("[data-testid=paste-jd-box]").count() == 0)
    else:
        ok("ui_esc_closes_paste", True, "no paste button")

    # Outreach visible once version exists
    for _ in range(30):
        if page.locator("[data-testid=outreach-step-panel]").count() > 0:
            break
        page.wait_for_timeout(500)
    ok("ui_outreach_panel", page.locator("[data-testid=outreach-step-panel]").count() > 0, ui_vid or "")
    ok("ui_no_auto_send", page.locator("[data-testid=outreach-no-auto-send]").count() > 0)
    ok("ui_hm_playbook", page.locator("[data-testid=hm-playbook]").count() > 0)

    page.locator("[data-testid=apply-mode-panel]").scroll_into_view_if_needed()
    page.screenshot(path=str(OUT / "selftest-04-apply.png"), full_page=False)
    if page.locator("[data-testid=outreach-step-panel]").count():
        page.locator("[data-testid=outreach-step-panel]").scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / "selftest-05-outreach.png"), full_page=False)
    page.screenshot(path=str(OUT / "selftest-03-tailor.png"), full_page=False)

    # 4) Profile
    page.goto(f"{FE}/?view=profile", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=profile-panel]", timeout=30000)
    page.wait_for_timeout(800)
    ok("ui_profile", page.locator("[data-testid=profile-panel]").count() > 0)
    ok("ui_profile_save", page.locator("[data-testid=profile-save]").count() > 0)
    page.screenshot(path=str(OUT / "selftest-06-profile.png"), full_page=False)

    browser.close()

passed = all(c for _, c, _ in CHECKS)
report = {
    "suite": "selftest_e2e",
    "passed": passed,
    "pass_count": sum(1 for _, c, _ in CHECKS if c),
    "total": len(CHECKS),
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
    "user_id": uid,
    "job_id": job_id,
}
(OUT / "selftest-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if passed else 1)
