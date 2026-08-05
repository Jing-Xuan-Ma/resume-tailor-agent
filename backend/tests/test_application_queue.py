"""Phase 4 application queue + Phase 5 commercial boundaries."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _confirmed_version(user: str) -> str:
    session = client.post(
        "/api/v1/resume-workspace/jd-session",
        json={
            "user_id": user,
            "jd_text": "Data Analyst\nCompany: Queue Corp\nSQL Python Tableau",
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
    return version_id


def test_queue_enqueue_process_confirm_per_job() -> None:
    user = str(uuid4())
    version_id = _confirmed_version(user)

    enq = client.post(
        "/api/v1/queue/enqueue",
        json={
            "user_id": user,
            "items": [{"version_id": version_id, "company": "Queue Corp", "position": "Data Analyst"}],
        },
    )
    assert enq.status_code == 200, enq.text
    item_id = enq.json()["items"][0]["id"]
    assert enq.json()["items"][0]["fill_status"] == "queued"

    proc = client.post(
        f"/api/v1/queue/{item_id}/process",
        json={"user_id": user},
    )
    assert proc.status_code == 200, proc.text
    body = proc.json()
    assert body["fill_status"] == "awaiting_confirm"
    assert body["awaiting_confirm"] is True
    assert body["apply_id"]

    denied = client.post(
        f"/api/v1/queue/{item_id}/confirm-submit",
        json={"user_id": user, "acknowledge": False},
    )
    assert denied.status_code == 400

    conf = client.post(
        f"/api/v1/queue/{item_id}/confirm-submit",
        json={"user_id": user, "acknowledge": True},
    )
    assert conf.status_code == 200, conf.text
    assert conf.json()["fill_status"] == "submitted"
    assert conf.json()["awaiting_confirm"] is False
    assert conf.json()["submitted_at"]


def test_queue_skip() -> None:
    user = str(uuid4())
    version_id = _confirmed_version(user)
    enq = client.post(
        "/api/v1/queue/enqueue",
        json={"user_id": user, "items": [{"version_id": version_id}]},
    )
    item_id = enq.json()["items"][0]["id"]
    skip = client.post(f"/api/v1/queue/{item_id}/skip", json={"user_id": user})
    assert skip.status_code == 200
    assert skip.json()["fill_status"] == "skipped"


def test_commercial_boundaries_safe_defaults() -> None:
    res = client.get("/api/v1/commercial/boundaries")
    assert res.status_code == 200
    body = res.json()
    assert body["pause_before_submit_default"] is True
    assert body["auto_click_submit"] is False
    assert body["batch_one_click_all_submit"] is False
    assert body["cold_email_auto_send"] is False
