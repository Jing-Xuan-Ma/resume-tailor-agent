"""Capture live UI polish screens for display."""
from __future__ import annotations

from pathlib import Path

OUT = Path(r"d:\resume-agent\artifacts\ui\live")
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:3000"


def main() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # 1) Ranked jobs
        page.goto(f"{BASE}/jobs", wait_until="networkidle", timeout=60000)
        page.wait_for_selector('[data-testid="ranked-jobs-page"]')
        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "live-01-jobs.png"), full_page=False)

        # 2) Detail
        row = page.locator('[data-testid^="job-row-"]').first
        row.click()
        page.wait_for_selector('[data-testid="job-detail-page"]')
        page.wait_for_timeout(400)
        page.screenshot(path=str(OUT / "live-02-detail.png"), full_page=False)

        # 3) Tailor via CTA + demo auth
        page.locator('[data-testid="cta-customize-resume"]').click()
        page.wait_for_timeout(800)
        if page.locator('[data-testid="auth-demo"]').count():
            page.locator('[data-testid="auth-demo"]').click()
            page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "live-03-auth-or-tailor.png"), full_page=False)
        page.wait_for_selector('[data-testid="resume-workspace"]', timeout=20000)
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "live-04-tailor.png"), full_page=False)

        browser.close()
        print("OK", OUT)


if __name__ == "__main__":
    main()
