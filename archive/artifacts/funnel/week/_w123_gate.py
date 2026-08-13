"""W123–W125: sort/threshold persist + clear-filters + Confirm*."""
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
ws = Path(r"d:\resume-agent\frontend\components\resume-workspace.tsx").read_text(encoding="utf-8")
ok("w123_sort_testids", "jobs-sort-date" in rank and "jobs-sort-score" in rank)
ok("w124_clear_filters", "jobs-clear-filters" in rank)
ok("w124_confirm_star", "Confirm*" in ws)
ok("w125_threshold_ls", "resume-agent-jobs-threshold" in rank)
ok("w126_soft_note_count", "notes" in ws and "confirm-soft-warnings" in ws)

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
    page.evaluate(
        """() => {
          localStorage.setItem('resume-agent-jobs-sort', 'date');
          localStorage.setItem('resume-agent-jobs-threshold', '35');
        }"""
    )
    page.goto(f"{FE}/jobs", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=jobs-sort-date]", timeout=30000)
    page.wait_for_timeout(900)
    date_cls = page.locator("[data-testid=jobs-sort-date]").get_attribute("class") or ""
    ok("w123_sort_restored_date", "bg-white" in date_cls and "text-slate-950" in date_cls, date_cls[:60])
    thr = page.locator("[data-testid=jobs-threshold-value]").inner_text().strip()
    ok("w125_threshold_restored", thr == "35%", thr)
    # Clear filters should appear and reset
    clear = page.locator("[data-testid=jobs-clear-filters]")
    ok("w124_clear_visible", clear.count() > 0)
    clear.click()
    page.wait_for_timeout(500)
    thr2 = page.locator("[data-testid=jobs-threshold-value]").inner_text().strip()
    ok("w124_clear_resets_threshold", thr2 == "0%", thr2)
    page.screenshot(path=str(OUT / "w123-sort-threshold.png"), full_page=False)
    browser.close()

report = {
    "passed": all(c for _, c, _ in CHECKS),
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
}
(OUT / "w123-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
