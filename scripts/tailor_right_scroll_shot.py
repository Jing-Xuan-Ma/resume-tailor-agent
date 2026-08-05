"""Screenshot tailor right-scroll layout."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "ui" / "tailor-simplify"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:3000/?view=resume", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        if page.locator("[data-testid='auth-gate']").count():
            page.locator("[data-testid='auth-demo']").click()
            page.wait_for_timeout(2500)
            page.goto("http://127.0.0.1:3000/?view=resume", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

        page.screenshot(path=str(OUT / "01-full.png"))
        right = page.locator("[data-testid='right-scroll-column']")
        jd = page.locator("[data-testid='jd-panel']")
        info = {
            "right": right.count(),
            "jd": jd.count(),
            "li": page.locator("[data-testid='jd-panel'] li").count(),
            "has_required": "Required" in (jd.inner_text() if jd.count() else ""),
            "has_preferred": "Preferred" in (jd.inner_text() if jd.count() else ""),
        }
        if right.count():
            box = right.evaluate(
                """el => ({
                  scrollHeight: el.scrollHeight,
                  clientHeight: el.clientHeight,
                  canScroll: el.scrollHeight > el.clientHeight + 8
                })"""
            )
            info["scroll"] = box
            right.evaluate("el => { el.scrollTop = Math.min(600, el.scrollHeight); }")
            page.wait_for_timeout(300)
            page.screenshot(path=str(OUT / "05-right-scrolled.png"))
            right.evaluate("el => { el.scrollTop = 0; }")
            page.wait_for_timeout(200)
            page.screenshot(path=str(OUT / "06-right-top.png"))

        (OUT / "scroll-check.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        print(json.dumps(info, indent=2))
        browser.close()
        return 0 if info.get("right") and info.get("li", 0) >= 7 else 1


if __name__ == "__main__":
    raise SystemExit(main())
