"""Load unpacked jobright-bridge and click Open Tailor on the local mock.

Verifies the FAB → background → leads API → workspace open path that real Jobright uses.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extensions" / "jobright-bridge"
OUT = ROOT / "artifacts" / "ui" / "jobright-bridge-fab"
OUT.mkdir(parents=True, exist_ok=True)
FE = "http://127.0.0.1:3000"
MOCK = f"{FE}/fixtures/jobright-mock.html"

results: dict = {"checks": [], "ok": True}


def check(name: str, passed: bool, detail: str = "") -> None:
    results["checks"].append({"name": name, "passed": passed, "detail": detail})
    if not passed:
        results["ok"] = False
    print(("PASS" if passed else "FAIL"), name, detail)


def main() -> int:
    if not (EXT / "manifest.json").exists():
        check("extension_dir", False, str(EXT))
        return 1

    with sync_playwright() as p:
        # Prefer system Chrome so MV3 extensions load reliably on Windows.
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(OUT / "chrome-profile"),
                headless=False,
                channel="chrome",
                args=[
                    f"--disable-extensions-except={EXT}",
                    f"--load-extension={EXT}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                viewport={"width": 1280, "height": 900},
            )
        except Exception as e:
            check("launch_chrome_with_extension", False, str(e))
            (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            return 1

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(MOCK, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)

        fab = page.locator("[data-testid=ra-fab-tailor]")
        check("fab_visible", fab.count() > 0, f"count={fab.count()}")
        if fab.count() == 0:
            page.screenshot(path=str(OUT / "01-no-fab.png"), full_page=True)
            ctx.close()
            (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            return 1

        pages_before = len(ctx.pages)
        fab.first.click()
        # Wait for new window/tab from extension (workspace)
        opened = False
        deadline = time.time() + 20
        while time.time() < deadline:
            if len(ctx.pages) > pages_before:
                opened = True
                break
            err = page.locator("#ra-jobright-fab-error")
            if err.count() and err.first.is_visible():
                check("fab_click_opens_agent", False, err.first.inner_text())
                page.screenshot(path=str(OUT / "02-fab-error.png"), full_page=True)
                ctx.close()
                (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
                return 1
            page.wait_for_timeout(400)

        check("fab_click_opens_agent", opened, f"pages_before={pages_before} after={len(ctx.pages)}")
        if opened:
            agent = ctx.pages[-1]
            agent.wait_for_timeout(2000)
            url = agent.url or ""
            check("agent_url_has_job", "jobId=" in url or "view=resume" in url, url[:180])
            agent.screenshot(path=str(OUT / "03-agent-opened.png"), full_page=True)
        else:
            page.screenshot(path=str(OUT / "02-no-open.png"), full_page=True)

        ctx.close()

    (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("OK" if results["ok"] else "FAILED")
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
