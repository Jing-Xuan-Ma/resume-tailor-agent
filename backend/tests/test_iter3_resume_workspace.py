"""Iter-3: rewrite -> evidence guard -> diff -> version cap -> confirm -> final_resumes."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_iter3_tailor_loop_confirm_and_version_cap() -> None:
    user = str(uuid4())
    session = client.post(
        "/api/v1/resume-workspace/jd-session",
        json={
            "user_id": user,
            "jd_text": (
                "Data Analyst\nCompany: Acme Analytics\n"
                "Requirements: SQL, Tableau, Python, ETL, stakeholder reporting"
            ),
            "job_id": "mock_job_da_001",
        },
    )
    assert session.status_code == 200, session.text
    session_id = session.json()["session_id"]

    version_ids: list[str] = []
    last_body: dict = {}
    for i in range(5):
        rw = client.post(
            f"/api/v1/resume-workspace/jd-session/{session_id}/rewrite",
            json={
                "user_id": user,
                "session_id": session_id,
                "instruction": f"Tailor resume to match SQL Tableau ETL emphasis round {i + 1}",
                "base_version_id": version_ids[-1] if version_ids else None,
            },
        )
        assert rw.status_code == 200, rw.text
        last_body = rw.json()
        version_ids.append(last_body["new_version_id"])
        delta = last_body.get("content_delta") or {}
        assert "changes" in delta or "changed_fields" in delta, delta
        evidence = (last_body.get("full_resume") or {}).get("evidence_check") or {}
        assert "ok" in evidence or "passed" in evidence, evidence
        exps = last_body["full_resume"].get("experiences") or []
        if exps:
            b0 = (exps[0].get("bullets") or [{}])[0]
            assert b0.get("evidence_from"), b0

    listed = client.get(
        f"/api/v1/resume-workspace/jd-session/{session_id}/versions",
        params={"user_id": user},
    )
    assert listed.status_code == 200, listed.text
    versions = listed.json()["versions"]
    assert len(versions) <= 4, f"expected <=4 versions, got {len(versions)}"

    latest = versions[-1]["id"]
    evidence = (last_body.get("full_resume") or {}).get("evidence_check") or {}
    assert evidence.get("passed", evidence.get("ok")) is True, evidence

    conf = client.post(
        f"/api/v1/resume-workspace/resume-version/{latest}/confirm",
        params={"user_id": user},
    )
    assert conf.status_code == 200, conf.text
    conf_body = conf.json()
    assert conf_body.get("ok") is True
    final_path = Path(conf_body["final_path"])
    assert final_path.exists(), final_path
    files = list(final_path.glob("*"))
    assert any(p.suffix == ".txt" for p in files), files
    assert any(p.name == "meta.json" for p in files), files
    assert any(p.suffix == ".docx" for p in files), files
    assert any(p.suffix == ".pdf" for p in files), files
    meta = json.loads((final_path / "meta.json").read_text(encoding="utf-8"))
    assert "job_id" in meta
    assert meta.get("job_id") == "mock_job_da_001"
    assert meta.get("confirmed_at")
    assert meta.get("apply_status") == "not_started"
    assert meta.get("outreach_status") == "not_started"

    # Preview must be Word-ish PDF without Markdown markers in extracted text
    preview = client.get(
        f"/api/v1/resume-workspace/resume-version/{latest}/preview",
        params={"user_id": user},
    )
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"].startswith("application/pdf")
    assert len(preview.content) > 5000
    # Word PDFs may contain b'##' in compressed streams — check text layer only
    try:
        import fitz

        text = fitz.open(stream=preview.content, filetype="pdf")[0].get_text("text")
        assert "##" not in text
        assert "**" not in text
    except ImportError:
        pass

    export = client.get(
        f"/api/v1/resume-workspace/resume-version/{latest}/export",
        params={"user_id": user, "format": "text"},
    )
    assert export.status_code == 200, export.text


def test_confirm_blocked_when_evidence_fails(monkeypatch) -> None:
    user = str(uuid4())
    session = client.post(
        "/api/v1/resume-workspace/jd-session",
        json={
            "user_id": user,
            "jd_text": "Data Analyst\nCompany: Block Co\nRequirements: SQL",
        },
    )
    session_id = session.json()["session_id"]

    async def _fail(_original, _tailored):
        return {"passed": False, "issues": ["fabricated metric 99%"], "confidence": 0.1}

    from app.modules.resume_workspace.router import workspace_service

    monkeypatch.setattr(workspace_service.evidence_guard, "verify", _fail)

    rw = client.post(
        f"/api/v1/resume-workspace/jd-session/{session_id}/rewrite",
        json={
            "user_id": user,
            "session_id": session_id,
            "instruction": "Tailor resume to match SQL",
        },
    )
    assert rw.status_code == 200, rw.text
    version_id = rw.json()["new_version_id"]
    assert rw.json()["full_resume"]["evidence_check"]["passed"] is False

    conf = client.post(
        f"/api/v1/resume-workspace/resume-version/{version_id}/confirm",
        params={"user_id": user},
    )
    assert conf.status_code == 409, conf.text
    detail = conf.json()["detail"]
    assert detail["status"] == "blocked_by_evidence_guard"
