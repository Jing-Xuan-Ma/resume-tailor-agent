"""Iter-3 API smoke: rewrite -> diff -> confirm -> final_resumes on disk; version cap."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
USER = str(uuid4())


def main() -> int:
    # Bootstrap master template via rewrite path
    session = client.post(
        "/api/v1/resume-workspace/jd-session",
        json={
            "user_id": USER,
            "jd_text": (
                "Data Analyst\nCompany: Acme Analytics\n"
                "Requirements: SQL, Tableau, Python, ETL, stakeholder reporting"
            ),
            "job_id": "mock_job_da_001",
        },
    )
    assert session.status_code == 200, session.text
    session_id = session.json()["session_id"]

    version_ids = []
    for i in range(5):
        rw = client.post(
            f"/api/v1/resume-workspace/jd-session/{session_id}/rewrite",
            json={
                "user_id": USER,
                "session_id": session_id,
                "instruction": f"Tailor resume to match SQL Tableau ETL emphasis round {i+1}",
                "base_version_id": version_ids[-1] if version_ids else None,
            },
        )
        assert rw.status_code == 200, rw.text
        body = rw.json()
        version_ids.append(body["new_version_id"])
        delta = body.get("content_delta") or {}
        assert "changes" in delta or "changed_fields" in delta, delta
        # Evidence fields present on experiences
        exps = body["full_resume"].get("experiences") or []
        if exps:
            b0 = (exps[0].get("bullets") or [{}])[0]
            assert b0.get("evidence_from"), b0

    listed = client.get(
        f"/api/v1/resume-workspace/jd-session/{session_id}/versions",
        params={"user_id": USER},
    )
    assert listed.status_code == 200, listed.text
    versions = listed.json()["versions"]
    assert len(versions) <= 4, f"expected <=4 versions, got {len(versions)}"

    latest = versions[-1]["id"]
    conf = client.post(
        f"/api/v1/resume-workspace/resume-version/{latest}/confirm",
        params={"user_id": USER},
    )
    assert conf.status_code == 200, conf.text
    conf_body = conf.json()
    assert conf_body.get("ok") is True
    final_path = Path(conf_body["final_path"])
    assert final_path.exists(), final_path
    files = list(final_path.glob("*"))
    assert any(p.suffix == ".txt" for p in files), files
    assert any(p.name == "meta.json" for p in files), files

    # Export gated: confirmed works
    export = client.get(
        f"/api/v1/resume-workspace/resume-version/{latest}/export",
        params={"user_id": USER, "format": "text"},
    )
    assert export.status_code == 200, export.text

    print("PASS")
    print(f"versions={len(versions)} final={final_path}")
    print(f"delta_changes={(body.get('content_delta') or {}).get('change_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
