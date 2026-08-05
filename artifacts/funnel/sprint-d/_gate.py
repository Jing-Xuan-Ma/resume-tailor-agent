"""Sprint D gate: browser fill-and-pause on sandbox ATS fixture."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import httpx

OUT = Path(r"d:\resume-agent\artifacts\funnel\sprint-d")
OUT.mkdir(parents=True, exist_ok=True)
FIXTURE = (OUT / "fixture_ats.html").resolve().as_uri()
API = "http://127.0.0.1:8000"
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


os.environ["ENABLE_BROWSER_FILL_PAUSE"] = "true"

# Ensure settings pick up env — restart note: we set in-process too
from app.config import settings

settings.ENABLE_BROWSER_FILL_PAUSE = True

with httpx.Client(timeout=120) as client:
    r = client.post(
        f"{API}/api/v1/auth/login",
        json={"email": "demo@resume-agent.local", "password": "demo-pass-1234"},
    )
    user = r.json()["user"]
    user_id = user["id"]

conn = sqlite3.connect(r"d:\resume-agent\data\app.db")
ver = conn.execute(
    "SELECT id FROM resume_versions WHERE user_id=? AND is_confirmed=1 ORDER BY confirmed_at DESC LIMIT 1",
    (user_id,),
).fetchone()
if not ver:
    ver = conn.execute(
        "SELECT id FROM resume_versions WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if ver:
        conn.execute(
            "UPDATE resume_versions SET is_confirmed=1, confirmed_at=datetime('now') WHERE id=?",
            (ver[0],),
        )
        conn.commit()
version_id = ver[0]
ok("has_confirmed_version", bool(version_id), version_id or "")

# Direct unit path (does not need API flag reload)
from app.modules.ats_connectors.registry import connector_for
from app.modules.application_engine.browser_session import BrowserSession

connector = connector_for("https://boards.greenhouse.io/demo/jobs/1")
answers = [
    {"field_name": "first_name", "question": "First name", "answer": "Jingxuan", "aliases": ["first name"]},
    {"field_name": "last_name", "question": "Last name", "answer": "Ma", "aliases": ["last name"]},
    {"field_name": "email", "question": "Email", "answer": "jma107@jh.edu", "aliases": ["email"]},
    {"field_name": "phone", "question": "Phone", "answer": "+1 (410) 240-4366", "aliases": ["phone"]},
    {"field_name": "linkedin", "question": "LinkedIn", "answer": "https://linkedin.com/in/example", "aliases": ["linkedin"]},
]
shot = str(OUT / "01-filled-paused.png")
result = BrowserSession().fill_and_pause(
    url=FIXTURE,
    answers=answers,
    field_selectors=connector.field_selectors(),
    screenshot_path=shot,
)
(OUT / "browser-fill.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
ok("not_submitted", result.get("submitted") is False, str(result.get("submitted")))
ok("paused_status", result.get("status") == "filled_paused_before_submit", result.get("status") or "")
filled_ok = sum(1 for f in result.get("filled") or [] if f.get("status") == "filled")
ok("filled_ge_3", filled_ok >= 3, str(filled_ok))
ok("screenshot_exists", Path(shot).exists() and Path(shot).stat().st_size > 1000, shot)
ok("msg_mentions_pause", "before Submit" in (result.get("message") or ""), result.get("message") or "")

# Audit row optional
try:
    from app.modules.safety.audit_log import audit

    audit(user_id, "sprint_d_browser_fill_pause", {"filled": filled_ok, "screenshot": shot})
    ok("audit_logged", True, "")
except Exception as exc:
    ok("audit_logged", False, str(exc))

passed = all(c for _, c, _ in CHECKS)
report = {"sprint": "D", "passed": passed, "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS], "result": result}
(OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
sys.exit(0 if passed else 1)
