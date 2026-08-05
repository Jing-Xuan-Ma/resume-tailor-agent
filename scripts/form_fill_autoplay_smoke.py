"""Live autoplay smoke: local HTML fixture + in-process Engine + Playwright."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

FIXTURE = BACKEND / "tests" / "engine" / "fixtures" / "fixture_workday_form.html"
OUT = ROOT / "artifacts" / "form-fill" / "autoplay-smoke.json"

PROFILE = {
    "first_name": "Jingxuan",
    "last_name": "Ma",
    "email": "jma107@jh.edu",
    "phone": "+1 (410) 240-4366",
    "linkedin": "https://linkedin.com/in/example",
}


async def main() -> int:
    from playwright.async_api import async_playwright

    from entrypoints.standalone_app.playwright_driver import (
        capture_dom_snapshot,
        execute_instruction,
        run_apply_flow,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    url = FIXTURE.resolve().as_uri()

    async with async_playwright() as p:
        # Prefer system Chrome — avoids playwright install CDN when blocked.
        try:
            browser = await p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = await p.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page()
        result = await run_apply_flow(
            page,
            {"resolved_url": url, "id": "fixture-workday"},
            PROFILE,
            in_process=True,
            max_loops=2,
        )

        # Read actual filled values from DOM
        values = await page.evaluate(
            """() => ({
              first: document.querySelector('#firstName')?.value || '',
              last: document.querySelector('#lastName')?.value || '',
              email: document.querySelector('#email')?.value || '',
              phone: document.querySelector('#phone')?.value || '',
              linkedin: document.querySelector('#linkedin')?.value || '',
            })"""
        )
        await page.screenshot(path=str(OUT.with_suffix(".png")))
        await browser.close()

    filled_ok = (
        values["first"] == PROFILE["first_name"]
        and values["last"] == PROFILE["last_name"]
        and values["email"] == PROFILE["email"]
        and values["phone"] == PROFILE["phone"]
    )
    paused = any(i.action == "pause_for_human" for i in result.instructions)
    no_submit_exec = all(i.action != "submit" or i.requires_confirmation for i in result.instructions)

    report = {
        "ok": bool(filled_ok and paused and no_submit_exec),
        "filled_ok": filled_ok,
        "paused_before_submit": paused,
        "dom_values": values,
        "stage": result.stage,
        "ats": result.ats.model_dump() if result.ats else None,
        "instruction_actions": [i.action for i in result.instructions],
        "summary": result.summary_for_human,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
