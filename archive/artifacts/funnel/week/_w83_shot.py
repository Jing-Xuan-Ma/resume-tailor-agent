"""W83: hide-stale preference persists across navigation."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"

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

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome")
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(FE, wait_until="domcontentloaded")
    page.evaluate("(b)=>localStorage.setItem('resume-agent-auth', JSON.stringify(b))", blob)
    page.evaluate("()=>localStorage.removeItem('resume-agent-hide-stale')")
    page.goto(f"{FE}/jobs", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=jobs-hide-stale]", timeout=30000)
    page.wait_for_timeout(800)
    box = page.locator("[data-testid=jobs-hide-stale] input")
    ok("w83_hide_stale_control", box.count() > 0)
    if not box.is_checked():
        box.check()
    page.wait_for_timeout(300)
    stored = page.evaluate("()=>localStorage.getItem('resume-agent-hide-stale')")
    ok("w83_persisted_to_ls", stored == "1", str(stored))
    page.goto(f"{FE}/jobs", wait_until="domcontentloaded")
    page.wait_for_selector("[data-testid=jobs-hide-stale]", timeout=30000)
    page.wait_for_function(
        "() => localStorage.getItem('resume-agent-hide-stale') === '1'",
        timeout=10000,
    )
    page.wait_for_timeout(400)
    ok("w83_restored_checked", page.locator("[data-testid=jobs-hide-stale] input").is_checked())
    page.screenshot(path=str(OUT / "w83-hide-stale-persist.png"), full_page=False)

    # Confirm shortcut present in tailor source
    fe = Path(r"d:\resume-agent\frontend\components\resume-workspace.tsx").read_text(encoding="utf-8")
    ok("w81_confirm_shortcut", "Ctrl+Shift+Enter" in fe and "keydown" in fe)
    browser.close()

report = {
    "passed": all(c for _, c, _ in CHECKS),
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
}
(OUT / "w83-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
