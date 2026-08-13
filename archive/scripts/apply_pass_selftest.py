"""Phase 1 apply-pass: Greenhouse/Lever/Ashby sandbox fill → pause (never Submit).

Writes evidence to artifacts/ui/apply-pass/.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ENABLE_BROWSER_FILL_PAUSE", "true")

OUT = ROOT / "artifacts" / "ui" / "apply-pass"
OUT.mkdir(parents=True, exist_ok=True)

FIXTURES = [
    ("greenhouse", ROOT / "artifacts" / "funnel" / "sprint-i" / "fixture_greenhouse.html", "https://boards.greenhouse.io/demo/jobs/1"),
    ("lever", ROOT / "artifacts" / "funnel" / "sprint-i" / "fixture_lever.html", "https://jobs.lever.co/demo/abc"),
    ("ashby", ROOT / "artifacts" / "funnel" / "agent3" / "fixture_ashby.html", "https://jobs.ashbyhq.com/demo/role"),
]

ANSWERS = [
    {"field_name": "first_name", "question": "First name", "answer": "Jingxuan", "aliases": ["first name"]},
    {"field_name": "last_name", "question": "Last name", "answer": "Ma", "aliases": ["last name"]},
    {"field_name": "email", "question": "Email", "answer": "jma107@jh.edu", "aliases": ["email"]},
    {"field_name": "phone", "question": "Phone", "answer": "+1 (410) 240-4366", "aliases": ["phone"]},
]

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def main() -> int:
    from app.config import settings
    from app.modules.application_engine.browser_session import BrowserSession
    from app.modules.ats_connectors.registry import connector_for
    from app.modules.resume_workspace.apply_flow import confirm_submit, start_apply
    from uuid import uuid4

    settings.ENABLE_BROWSER_FILL_PAUSE = True
    settings.ALLOW_LIVE_BROWSER_FILL = False

    results: dict[str, object] = {}
    ats_ok = 0

    for name, fixture, fake_url in FIXTURES:
        if not fixture.exists():
            ok(f"{name}_fixture", False, str(fixture))
            continue
        connector = connector_for(fake_url)
        shot = str(OUT / f"{name}-filled-paused.png")
        result = BrowserSession().fill_and_pause(
            url=fixture.resolve().as_uri(),
            answers=ANSWERS,
            field_selectors=connector.field_selectors(),
            screenshot_path=shot,
            ats_type=name,
            sandbox=True,
        )
        results[name] = result
        (OUT / f"{name}-browser-fill.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        submitted = bool(result.get("submitted"))
        status = str(result.get("status") or "")
        filled_ok = sum(1 for f in result.get("filled") or [] if f.get("status") == "filled")
        shot_ok = Path(shot).exists() and Path(shot).stat().st_size > 500
        ok(f"{name}_not_submitted", not submitted, str(submitted))
        ok(f"{name}_paused", "pause" in status.lower() or status.endswith("before_submit"), status)
        ok(f"{name}_filled", filled_ok >= 1, str(filled_ok))
        ok(f"{name}_screenshot", shot_ok, shot)
        if not submitted and shot_ok:
            ats_ok += 1

    # Confirm-submit audit path (in-process, no live click)
    user = f"apply-pass-{uuid4().hex[:8]}"
    try:
        # Minimal confirm path: fabricate paused session via start_apply if possible
        from app import db

        db.init_db()
        # Soft check: confirm_submit rejects missing
        try:
            confirm_submit(apply_id="missing", user_id=user, acknowledge=True)
            ok("confirm_missing_raises", False, "expected raise")
        except ValueError:
            ok("confirm_missing_raises", True, "")
    except Exception as exc:
        ok("confirm_path", False, str(exc))

    ok("ats_pass_ge_2", ats_ok >= 2, f"{ats_ok}/3")

    passed = all(c for _, c, _ in CHECKS)
    report = {
        "phase": "P1_auto_apply",
        "passed": passed,
        "ats_ok": ats_ok,
        "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
        "results": results,
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (OUT / "report.md").write_text(
        f"# Apply pass (Phase 1)\n\npassed={passed} ats_ok={ats_ok}/3\n\n"
        + "\n".join(f"- {'PASS' if c else 'FAIL'} `{n}` {d}" for n, c, d in CHECKS)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"passed": passed, "ats_ok": ats_ok}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
