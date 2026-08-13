"""Agent 3 gate: Greenhouse / Lever / Workday sandbox fill-pause (submitted=false)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

OUT = Path(r"d:\resume-agent\artifacts\funnel\agent3")
OUT.mkdir(parents=True, exist_ok=True)

os.environ["ENABLE_BROWSER_FILL_PAUSE"] = "true"
sys.path.insert(0, r"d:\resume-agent\backend")

from app.config import settings  # noqa: E402

settings.ENABLE_BROWSER_FILL_PAUSE = True

from app.modules.application_engine.browser_session import BrowserSession  # noqa: E402
from app.modules.ats_connectors.registry import connector_for  # noqa: E402
from app.modules.ats_connectors.sandbox import resolve_browser_fill_url  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []
RESULTS: dict[str, dict] = {}


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


CASES = [
    {
        "name": "greenhouse",
        "source_url": "https://boards.greenhouse.io/demo/jobs/1",
        "answers": [
            {"field_name": "first_name", "question": "First name", "answer": "Jingxuan", "aliases": ["first name"]},
            {"field_name": "last_name", "question": "Last name", "answer": "Ma", "aliases": ["last name"]},
            {"field_name": "email", "question": "Email", "answer": "jma107@jh.edu", "aliases": ["email"]},
            {"field_name": "phone", "question": "Phone", "answer": "+1 (410) 240-4366", "aliases": ["phone"]},
            {
                "field_name": "linkedin",
                "question": "LinkedIn Profile",
                "answer": "https://linkedin.com/in/example",
                "aliases": ["linkedin"],
            },
        ],
        "min_filled": 4,
    },
    {
        "name": "lever",
        "source_url": "https://jobs.lever.co/demo/abc123",
        "answers": [
            {"field_name": "full_name", "question": "Full name", "answer": "Jingxuan Ma", "aliases": ["name", "full name"]},
            {"field_name": "email", "question": "Email", "answer": "jma107@jh.edu", "aliases": ["email"]},
            {"field_name": "phone", "question": "Phone", "answer": "+1 (410) 240-4366", "aliases": ["phone"]},
            {
                "field_name": "linkedin",
                "question": "LinkedIn",
                "answer": "https://linkedin.com/in/example",
                "aliases": ["linkedin"],
            },
        ],
        "min_filled": 3,
    },
    {
        "name": "workday",
        "source_url": "https://company.wd5.myworkdayjobs.com/en-US/Careers/job/1",
        "answers": [
            {"field_name": "first_name", "question": "First Name", "answer": "Jingxuan", "aliases": ["first name"]},
            {"field_name": "last_name", "question": "Last Name", "answer": "Ma", "aliases": ["last name"]},
            {"field_name": "email", "question": "Email", "answer": "jma107@jh.edu", "aliases": ["email"]},
            {"field_name": "phone", "question": "Phone", "answer": "+1 (410) 240-4366", "aliases": ["phone"]},
            {
                "field_name": "source",
                "question": "How did you hear about us?",
                "answer": "LinkedIn",
                "aliases": ["source"],
                "type": "select",
            },
        ],
        "min_filled": 4,
    },
]

# Bonus Ashby (same gate folder; does not replace the three required suites)
ASHBY = {
    "name": "ashby",
    "source_url": "https://jobs.ashbyhq.com/demo/role-1",
    "answers": [
        {"field_name": "full_name", "question": "Full name", "answer": "Jingxuan Ma", "aliases": ["name", "full name"]},
        {"field_name": "email", "question": "Email", "answer": "jma107@jh.edu", "aliases": ["email"]},
        {"field_name": "phone", "question": "Phone", "answer": "+1 (410) 240-4366", "aliases": ["phone"]},
        {
            "field_name": "linkedin",
            "question": "LinkedIn",
            "answer": "https://linkedin.com/in/example",
            "aliases": ["linkedin"],
        },
    ],
    "min_filled": 3,
}


def run_case(case: dict, *, required: bool) -> None:
    name = case["name"]
    target = resolve_browser_fill_url(case["source_url"], prefer_sandbox=True)
    connector = connector_for(case["source_url"])
    ok(f"{name}_ats_type", connector.ats_type == name, connector.ats_type)
    ok(f"{name}_sandbox_resolved", bool(target.get("sandbox") and target.get("url")), str(target.get("fixture_path")))
    shot = str(OUT / f"{len(RESULTS) + 1:02d}-{name}-filled-paused.png")
    result = BrowserSession().fill_and_pause(
        url=target["url"],
        answers=case["answers"],
        field_selectors=connector.field_selectors(),
        screenshot_path=shot,
        ats_type=name,
        sandbox=True,
    )
    RESULTS[name] = result
    (OUT / f"{name}-fill.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    filled_ok = sum(1 for f in result.get("filled") or [] if f.get("status") == "filled")
    prefix = name if required else f"bonus_{name}"
    ok(f"{prefix}_not_submitted", result.get("submitted") is False, str(result.get("submitted")))
    ok(
        f"{prefix}_paused_status",
        result.get("status") == "filled_paused_before_submit",
        result.get("status") or "",
    )
    ok(f"{prefix}_filled_ge_{case['min_filled']}", filled_ok >= case["min_filled"], str(filled_ok))
    ok(
        f"{prefix}_screenshot",
        Path(shot).exists() and Path(shot).stat().st_size > 800,
        shot,
    )
    ok(
        f"{prefix}_no_submit_leak",
        not result.get("submit_leaked"),
        result.get("submit_marker") or "",
    )
    ok(
        f"{prefix}_msg_pause",
        "before Submit" in (result.get("message") or ""),
        result.get("message") or "",
    )


for case in CASES:
    run_case(case, required=True)
run_case(ASHBY, required=False)

# UI panel mock screenshot (browser_fill result surface)
ui_html = OUT / "ui-browser-fill-panel.html"
sample = RESULTS.get("greenhouse") or {}
filled_rows = "".join(
    f"<li><b>{f.get('field')}</b> <span>{f.get('status')}</span></li>"
    for f in (sample.get("filled") or [])
)
ui_html.write_text(
    f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>ApplyModePanel · browser_fill</title>
<style>
body{{font-family:system-ui;background:#f8fafc;padding:24px}}
.panel{{max-width:420px;border:1px solid #a7f3d0;border-radius:16px;background:#fff;padding:16px;box-shadow:0 1px 2px #0001}}
.bf{{margin-top:12px;border:1px solid #fde68a;background:#fffbeb;border-radius:12px;padding:10px;font-size:12px;color:#78350f}}
.bf ul{{margin:6px 0 0;padding:0;list-style:none}}
.bf li{{display:flex;justify-content:space-between;padding:2px 0}}
.badge{{display:inline-block;margin-top:8px;background:#fef3c7;color:#92400e;padding:4px 8px;border-radius:8px;font-weight:700;font-size:11px}}
</style></head><body>
<div class="panel" data-testid="apply-mode-panel">
  <h3>Step 5 · How do you want to apply?</h3>
  <div class="badge" data-testid="paused-before-submit">Stopped before Submit — no application was sent.</div>
  <div class="bf" data-testid="browser-fill-result">
    <div><b>Browser fill-pause</b></div>
    <div data-testid="browser-fill-status">status: {sample.get('status')} · submitted: <span data-testid="browser-fill-submitted">{sample.get('submitted')}</span> · sandbox · greenhouse</div>
    <div>filled {sum(1 for f in sample.get('filled') or [] if f.get('status')=='filled')}/{len(sample.get('filled') or [])} fields</div>
    <div>{sample.get('message')}</div>
    <ul data-testid="browser-fill-fields">{filled_rows}</ul>
  </div>
</div>
</body></html>
""",
    encoding="utf-8",
)

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True, channel="chrome")
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 560, "height": 720})
        page.goto(ui_html.resolve().as_uri(), wait_until="domcontentloaded")
        page.screenshot(path=str(OUT / "05-ui-browser-fill-panel.png"), full_page=True)
        browser.close()
    ok("ui_panel_screenshot", (OUT / "05-ui-browser-fill-panel.png").exists(), "05-ui-browser-fill-panel.png")
except Exception as exc:
    ok("ui_panel_screenshot", False, str(exc))

passed = all(c for _, c, _ in CHECKS)
# Required suites must all be present and not submitted
required_ok = all(
    RESULTS.get(n, {}).get("submitted") is False
    and RESULTS.get(n, {}).get("status") == "filled_paused_before_submit"
    for n in ("greenhouse", "lever", "workday")
)
passed = passed and required_ok

report = {
    "agent": 3,
    "module": "apply_ats",
    "passed": passed,
    "submitted": False,
    "suites": {
        name: {
            "status": (RESULTS.get(name) or {}).get("status"),
            "submitted": (RESULTS.get(name) or {}).get("submitted"),
            "filled": sum(
                1 for f in ((RESULTS.get(name) or {}).get("filled") or []) if f.get("status") == "filled"
            ),
            "sandbox": True,
        }
        for name in ("greenhouse", "lever", "workday", "ashby")
    },
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
    "results": RESULTS,
}
(OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"passed": passed, "checks": len(CHECKS)}, indent=2))
sys.exit(0 if passed else 1)
