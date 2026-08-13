"""Iter-1 UI smoke: open ranked jobs, click first row, screenshot both pages."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui" / "iter-1"
OUT.mkdir(parents=True, exist_ok=True)

BASE = "http://127.0.0.1:3000"
API = "http://127.0.0.1:8000"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("PLAYWRIGHT_MISSING")
        return 2

    import urllib.request

    try:
        urllib.request.urlopen(f"{API}/health", timeout=5)
    except Exception as exc:
        print(f"API_DOWN {exc}")
        return 3

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            try:
                browser = p.chromium.launch(headless=True, channel="msedge")
            except Exception:
                browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(f"{BASE}/jobs", wait_until="networkidle", timeout=60000)
        page.wait_for_selector('[data-testid="ranked-jobs-page"]', timeout=30000)
        page.wait_for_selector('[data-testid^="job-row-"]', timeout=30000)
        page.screenshot(path=str(OUT / "jobs-list.png"), full_page=True)

        first = page.locator('[data-testid^="job-row-"]').first
        first.click()
        page.wait_for_selector('[data-testid="job-detail-page"]', timeout=30000)
        page.wait_for_selector('[data-testid="job-detail-title"]', timeout=30000)
        title = page.locator('[data-testid="job-detail-title"]').inner_text()
        page.screenshot(path=str(OUT / "job-detail.png"), full_page=True)
        browser.close()

    print(f"PASS title={title!r}")
    print(f"SHOTS {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
