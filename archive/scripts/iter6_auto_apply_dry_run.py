"""Iter-6: auto-apply dry run with profile fill; hard stop before submit."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app

OUT = ROOT / "artifacts" / "ui" / "iter-6"
OUT.mkdir(parents=True, exist_ok=True)
client = TestClient(app)


def main() -> int:
    user = str(uuid4())
    session = client.post(
        "/api/v1/resume-workspace/jd-session",
        json={"user_id": user, "jd_text": "Data Analyst\nCompany: DryRun Corp\nSQL Python Tableau"},
    ).json()
    vid = client.post(
        f"/api/v1/resume-workspace/jd-session/{session['session_id']}/rewrite",
        json={"user_id": user, "session_id": session["session_id"], "instruction": "Tailor"},
    ).json()["new_version_id"]
    conf = client.post(
        f"/api/v1/resume-workspace/resume-version/{vid}/confirm",
        params={"user_id": user},
    ).json()
    auto = client.post(
        f"/api/v1/resume-workspace/resume-version/{vid}/start-apply",
        json={
            "user_id": user,
            "mode": "auto",
            "company": conf.get("company"),
            "position": conf.get("position"),
            "final_path": conf.get("final_path"),
        },
    )
    assert auto.status_code == 200, auto.text
    body = auto.json()
    assert body["paused_before_submit"] is True
    assert body["submitted"] is False
    fields = {f["field"]: f.get("value") for f in body["filled_fields"]}
    assert fields.get("email")
    assert fields.get("resume_upload")
    assert fields.get("submit_button") == "NOT_CLICKED"

    evidence = OUT / "auto-apply-dry-run.json"
    evidence.write_text(json.dumps(body, indent=2), encoding="utf-8")
    print("PASS")
    print(f"status={body['status']} evidence={evidence}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
