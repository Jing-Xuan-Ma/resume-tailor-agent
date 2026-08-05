"""Screenshot tailor workspace for visual QA."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui" / "tailor-simplify"
OUT.mkdir(parents=True, exist_ok=True)

from playwright.sync_api import sync_playwright


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:3000/?view=resume", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)

        if page.locator("[data-testid='auth-gate']").count():
            demo = page.locator("[data-testid='auth-demo']")
            if demo.count():
                demo.first.click()
            else:
                page.fill("input[type='email']", "demo@resume-agent.local")
                page.fill("input[type='password']", "demo-pass-1234")
                page.locator("button:has-text('Login')").first.click()
            page.wait_for_timeout(2500)
            page.goto("http://127.0.0.1:3000/?view=resume", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

        page.screenshot(path=str(OUT / "01-full.png"), full_page=False)

        # Ensure tailor workspace visible
        ws = page.locator('[data-testid="resume-workspace"]')
        chat = page.locator('[data-testid="workspace-chat"]')
        jd = page.locator('[data-testid="jd-panel"]')
        preview = page.locator('[data-testid="resume-preview"]')

        checks = {
            "workspace": ws.count() > 0,
            "chat": chat.count() > 0,
            "jd_panel": jd.count() > 0,
            "preview": preview.count() > 0,
            "no_keyword_gap": page.locator("text=Keyword Gap").count() == 0,
            "no_diff_panel": page.locator("text=Content Diff").count() == 0,
            "qualification_heading": page.locator("text=Qualification").count() > 0,
        }

        if jd.count():
            jd.first.screenshot(path=str(OUT / "02-jd-panel.png"))
        if chat.count():
            chat.first.screenshot(path=str(OUT / "03-chat.png"))

        page.screenshot(path=str(OUT / "04-after-checks.png"), full_page=False)
        browser.close()

        report = OUT / "checks.json"
        import json

        report.write_text(json.dumps({"checks": checks, "all_pass": all(checks.values())}, indent=2), encoding="utf-8")
        print(json.dumps({"checks": checks, "all_pass": all(checks.values())}, indent=2))
        print("screenshots:", OUT)
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
