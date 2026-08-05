"""W132–W133: FlowStepper hrefs."""
from __future__ import annotations

import json
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


step = Path(r"d:\resume-agent\frontend\components\flow-stepper.tsx").read_text(encoding="utf-8")
rank = Path(r"d:\resume-agent\frontend\components\ranked-jobs-table.tsx").read_text(encoding="utf-8")
ok("w132_hrefs_prop", "hrefs?" in step or "hrefs" in step)
ok("w133_ranked_hrefs", "hrefs={{" in rank or 'hrefs={{' in rank or "tailor: \"/?view=resume\"" in rank)

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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1400, "height": 900}).new_page()
    page.goto(FE, wait_until="domcontentloaded")
    page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", blob)
    page.goto(f"{FE}/jobs", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=flow-stepper]", timeout=30000)
    tailor = page.locator("[data-testid=flow-step-tailor]")
    ok("w133_tailor_step_link", tailor.count() > 0)
    tag = tailor.evaluate("el => el.tagName")
    ok("w133_tailor_is_anchor", tag == "A", tag)
    href = tailor.get_attribute("href") or ""
    ok("w133_tailor_href", "view=resume" in href or href.endswith("/") or "resume" in href, href)
    page.screenshot(path=str(OUT / "w133-flow-hrefs.png"), full_page=False)
    browser.close()

report = {"passed": all(c for _, c, _ in CHECKS), "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS]}
(OUT / "w133-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
