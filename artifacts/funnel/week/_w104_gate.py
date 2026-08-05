"""W104 freshest chip + W103 outreach safety."""
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


rank = Path(r"d:\resume-agent\frontend\components\ranked-jobs-table.tsx").read_text(encoding="utf-8")
out = Path(r"d:\resume-agent\frontend\components\outreach-step-panel.tsx").read_text(encoding="utf-8")
ok("w103_outreach_no_send", "outreach-no-auto-send" in out)
ok("w104_freshest_source", "jobs-freshest" in rank)

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
    page.wait_for_selector("[data-testid=ranked-jobs-page]", timeout=30000)
    page.wait_for_timeout(1200)
    chip = page.locator("[data-testid=jobs-freshest]")
    ok("w104_freshest_visible", chip.count() > 0, chip.inner_text() if chip.count() else "empty")
    page.screenshot(path=str(OUT / "w104-freshest.png"), full_page=False)
    browser.close()

report = {"passed": all(c for _, c, _ in CHECKS), "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS]}
(OUT / "w104-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
