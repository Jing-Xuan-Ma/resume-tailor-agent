"""Engine API + orchestration smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.form_fill_engine.schemas import DOMSnapshot, EngineStepRequest
from app.modules.form_fill_engine.service import plan_step

FIXTURES = Path(__file__).parent / "fixtures"

PROFILE = {
    "first_name": "Jingxuan",
    "last_name": "Ma",
    "email": "jma107@jh.edu",
    "phone": "+1 410-240-4366",
    "linkedin": "https://linkedin.com/in/example",
    "resume_path": "D:/tmp/resume.pdf",
    "work_authorized": "Yes",
}


@pytest.fixture
def client():
    return TestClient(app)


def test_engine_health(client: TestClient):
    r = client.get("/engine/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_engine_step_mock(client: TestClient):
    snap = json.loads((FIXTURES / "workday_sample.json").read_text(encoding="utf-8"))
    r = client.post(
        "/engine/step",
        json={
            "dom_snapshot": snap,
            "profile": PROFILE,
            "job_info": {"id": "t1"},
            "mock": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stage"] == "awaiting_human_review"
    assert any(i["action"] == "pause_for_human" for i in body["instructions"])
    assert body["meta"].get("mock") is True


@pytest.mark.asyncio
async def test_plan_step_workday_fills_and_pauses_or_advances():
    snap = DOMSnapshot.model_validate(
        json.loads((FIXTURES / "workday_sample.json").read_text(encoding="utf-8"))
    )
    resp = await plan_step(
        EngineStepRequest(dom_snapshot=snap, profile=PROFILE, job_info={}, allow_submit=False)
    )
    assert resp.ats is not None
    assert resp.ats.ats_type.value == "workday"
    fills = [i for i in resp.instructions if i.action == "fill"]
    assert len(fills) >= 3
    # Fixture has Next → may advance; otherwise pause. Never bare submit.
    assert any(i.action in {"pause_for_human", "click", "wait"} for i in resp.instructions)
    assert not any(i.action == "submit" and not i.requires_confirmation for i in resp.instructions)


@pytest.mark.asyncio
async def test_plan_step_never_auto_submit():
    snap = DOMSnapshot.model_validate(
        json.loads((FIXTURES / "lever_sample.json").read_text(encoding="utf-8"))
    )
    resp = await plan_step(
        EngineStepRequest(dom_snapshot=snap, profile=PROFILE, allow_submit=False)
    )
    assert all(i.action != "submit" for i in resp.instructions)
