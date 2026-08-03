"""Iter-6: auto-apply dry run fills fields and hard-stops before submit."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _confirmed_version(user: str) -> tuple[str, dict]:
    session = client.post(
        "/api/v1/resume-workspace/jd-session",
        json={
            "user_id": user,
            "jd_text": "Data Analyst\nCompany: DryRun Corp\nSQL Python Tableau",
        },
    )
    assert session.status_code == 200, session.text
    session_id = session.json()["session_id"]
    rw = client.post(
        f"/api/v1/resume-workspace/jd-session/{session_id}/rewrite",
        json={"user_id": user, "session_id": session_id, "instruction": "Tailor"},
    )
    assert rw.status_code == 200, rw.text
    version_id = rw.json()["new_version_id"]
    conf = client.post(
        f"/api/v1/resume-workspace/resume-version/{version_id}/confirm",
        params={"user_id": user},
    )
    assert conf.status_code == 200, conf.text
    return version_id, conf.json()


def test_auto_apply_pauses_before_submit() -> None:
    user = str(uuid4())
    version_id, conf = _confirmed_version(user)
    auto = client.post(
        f"/api/v1/resume-workspace/resume-version/{version_id}/start-apply",
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
    assert body["status"] == "paused_before_submit"
    assert body["paused_before_submit"] is True
    assert body["submitted"] is False
    fields = {f["field"]: f for f in body["filled_fields"]}
    assert fields["email"]["value"]
    assert fields["resume_upload"]["value"]
    assert fields["submit_button"]["value"] == "NOT_CLICKED"


def test_manual_apply_does_not_claim_submit() -> None:
    user = str(uuid4())
    version_id, _ = _confirmed_version(user)
    manual = client.post(
        f"/api/v1/resume-workspace/resume-version/{version_id}/start-apply",
        json={"user_id": user, "mode": "manual"},
    )
    assert manual.status_code == 200, manual.text
    body = manual.json()
    assert body["status"] == "ready_for_manual_apply"
    assert body["paused_before_submit"] is False
    assert body["submitted"] is False
