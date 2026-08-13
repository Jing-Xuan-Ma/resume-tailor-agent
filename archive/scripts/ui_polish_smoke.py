"""UI polish screenshots: /jobs → first job detail → tailor CTA path."""
from __future__ import annotations

from pathlib import Path

OUT = Path(r"d:\resume-agent\artifacts\ui\polish-1")
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

        page.goto(f"{BASE}/jobs", wait_until="networkidle", timeout=60000)
        page.wait_for_selector('[data-testid="ranked-jobs-page"]', timeout=30000)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "01-jobs-list.png"), full_page=True)

        rows = page.locator('[data-testid^="job-row-"]')
        n = rows.count()
        notes = [f"job_rows={n}"]
        if n > 0:
            rows.first.click()
            page.wait_for_selector('[data-testid="job-detail-page"]', timeout=30000)
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUT / "02-job-detail.png"), full_page=True)
            cta = page.locator('[data-testid="cta-customize-resume"]')
            notes.append(f"cta_visible={cta.count() > 0}")
            href = cta.get_attribute("href") if cta.count() else None
            notes.append(f"cta_href={href}")
            if href:
                page.goto(f"{BASE}{href}" if href.startswith("/") else href, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(800)
                demo = page.locator('[data-testid="auth-demo"]')
                if demo.count():
                    demo.click()
                    page.wait_for_timeout(1500)
                page.screenshot(path=str(OUT / "03-workspace-tailor.png"), full_page=True)
                notes.append(f"stepper={page.locator('[data-testid=flow-stepper]').count()}")
                notes.append(f"resume_ws={page.locator('[data-testid=resume-workspace]').count()}")
        else:
            page.screenshot(path=str(OUT / "01b-jobs-empty.png"), full_page=True)

        browser.close()
        (OUT / "NOTES.txt").write_text("\n".join(notes), encoding="utf-8")
        print("\n".join(notes))
        print("wrote", OUT)


if __name__ == "__main__":
    main()
