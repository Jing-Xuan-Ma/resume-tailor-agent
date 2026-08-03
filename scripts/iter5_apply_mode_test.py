"""Iter-5: confirm resume then manual/auto apply split; auto pauses before submit."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def main() -> int:
    user = str(uuid4())
    session = client.post(
        "/api/v1/resume-workspace/jd-session",
        json={
            "user_id": user,
            "jd_text": "Data Analyst\nCompany: ApplyCo\nRequirements: SQL, Python, Tableau",
        },
    )
    assert session.status_code == 200, session.text
    sid = session.json()["session_id"]
    rw = client.post(
        f"/api/v1/resume-workspace/jd-session/{sid}/rewrite",
        json={"user_id": user, "session_id": sid, "instruction": "Tailor for SQL Tableau"},
    )
    assert rw.status_code == 200, rw.text
    vid = rw.json()["new_version_id"]
    conf = client.post(
        f"/api/v1/resume-workspace/resume-version/{vid}/confirm",
        params={"user_id": user},
    )
    assert conf.status_code == 200, conf.text
    final_path = conf.json().get("final_path")

    manual = client.post(
        f"/api/v1/resume-workspace/resume-version/{vid}/start-apply",
        json={"user_id": user, "mode": "manual", "final_path": final_path, "company": "ApplyCo", "position": "Data Analyst"},
    )
    assert manual.status_code == 200, manual.text
    m = manual.json()
    assert m["status"] == "ready_for_manual_apply"
    assert m["submitted"] is False
    assert m["paused_before_submit"] is False

    auto = client.post(
        f"/api/v1/resume-workspace/resume-version/{vid}/start-apply",
        json={"user_id": user, "mode": "auto", "final_path": final_path, "company": "ApplyCo", "position": "Data Analyst"},
    )
    assert auto.status_code == 200, auto.text
    a = auto.json()
    assert a["status"] == "paused_before_submit"
    assert a["submitted"] is False
    assert a["paused_before_submit"] is True
    assert a["filled_fields"], a

    print("PASS")
    print(f"manual={m['status']} auto={a['status']} submitted={a['submitted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
