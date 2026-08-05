"""E2E: iframe + dynamic multi-step + file upload against local ATS fixture."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

SHELL = BACKEND / "tests" / "engine" / "fixtures" / "fixture_ats_shell.html"
RESUME = BACKEND / "tests" / "engine" / "fixtures" / "sample_resume.pdf"
OUT = ROOT / "artifacts" / "form-fill" / "gates-smoke.json"

PROFILE = {
    "first_name": "Jingxuan",
    "last_name": "Ma",
    "email": "jma107@jh.edu",
    "phone": "+1 (410) 240-4366",
    "linkedin": "https://linkedin.com/in/example",
    "work_authorized": "Yes",
    "resume_path": str(RESUME.resolve()),
}


async def main() -> int:
    from playwright.async_api import async_playwright

    from entrypoints.standalone_app.playwright_driver import run_apply_flow

    OUT.parent.mkdir(parents=True, exist_ok=True)
    url = SHELL.resolve().as_uri()

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = await p.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page()
        result = await run_apply_flow(
            page,
            {"resolved_url": url, "id": "gates-iframe-dynamic-upload"},
            PROFILE,
            in_process=True,
            max_loops=6,
        )

        # Read values from the iframe document
        frame = page.frame_locator("#ats-frame")
        values = {
            "first": await frame.locator("#firstName").input_value(),
            "last": await frame.locator("#lastName").input_value(),
            "email": await frame.locator("#email").input_value(),
            "phone": await frame.locator("#phone").input_value(),
            "step2_visible": await frame.locator("#step2.active").count(),
            "linkedin": "",
            "resume_files": 0,
            "work_auth": "",
            "status": "",
        }
        if values["step2_visible"]:
            values["linkedin"] = await frame.locator("#linkedin").input_value()
            values["resume_files"] = await frame.locator("#resume").evaluate(
                "el => (el.files && el.files.length) || 0"
            )
            values["work_auth"] = await frame.locator("#auth").input_value()
            values["status"] = await frame.locator("#status").inner_text()

        await page.screenshot(path=str(OUT.with_suffix(".png")), full_page=True)
        await browser.close()

    iframe_filled = (
        values["first"] == PROFILE["first_name"]
        and values["last"] == PROFILE["last_name"]
        and values["email"] == PROFILE["email"]
    )
    dynamic_ok = values["step2_visible"] >= 1
    upload_ok = values["resume_files"] >= 1
    linkedin_ok = values["linkedin"] == PROFILE["linkedin"]
    paused = any(i.action == "pause_for_human" for i in result.instructions) or result.stage in {
        "awaiting_human_review",
        "ready_to_submit",
    }
    no_real_submit = values["status"] != "SUBMIT_BLOCKED_IN_FIXTURE" or True  # submit click blocked anyway
    # Prefer: we never reached submit status from auto-click
    submit_auto = values["status"] == "SUBMIT_BLOCKED_IN_FIXTURE"

    report = {
        "ok": bool(iframe_filled and dynamic_ok and upload_ok and linkedin_ok and paused and not submit_auto),
        "iframe_filled": iframe_filled,
        "dynamic_step2": dynamic_ok,
        "file_upload": upload_ok,
        "linkedin_filled": linkedin_ok,
        "paused_before_submit": paused and not submit_auto,
        "dom_values": values,
        "stage": result.stage,
        "ats": result.ats.model_dump() if result.ats else None,
        "instruction_actions": [i.action for i in result.instructions],
        "frame_meta_hint": result.meta,
        "summary": result.summary_for_human,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
