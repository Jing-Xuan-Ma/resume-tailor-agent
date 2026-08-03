"""Iter-4: run quality gate on 3 sample JDs with projection + content-only tailor."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient

from app.main import app
from app.modules.resume_workspace.quality_gate import project_for_jd, run_quality_gate
from app.modules.resume_workspace.service import MOCK_RESUME

SAMPLE_JDS = [
    (
        "da_sql_tableau",
        """Data Analyst
Company: Contoso Insights
Requirements: advanced SQL, Tableau dashboards, Python data cleaning, stakeholder reporting, ETL pipelines
""",
    ),
    (
        "risk_analytics",
        """Risk Analyst Intern
Company: Harbor Insurance
Requirements: credit risk, Monte Carlo, Python, R, claims modeling, statistical modeling, SQL
""",
    ),
    (
        "data_eng_flavor",
        """Analytics Engineer
Company: Streamly
Requirements: Python, SQL, Apache Airflow, ETL, data modeling, Tableau, documentation
""",
    ),
]


def main() -> int:
    client = TestClient(app)
    user = str(uuid4())
    results = []

    for key, jd in SAMPLE_JDS:
        projected = project_for_jd(MOCK_RESUME, jd)
        gate = run_quality_gate(projected, jd)
        session = client.post(
            "/api/v1/resume-workspace/jd-session",
            json={"user_id": user, "jd_text": jd},
        )
        assert session.status_code == 200, session.text
        sid = session.json()["session_id"]
        rw = client.post(
            f"/api/v1/resume-workspace/jd-session/{sid}/rewrite",
            json={
                "user_id": user,
                "session_id": sid,
                "instruction": "Tailor resume to match this JD; emphasize relevant skills",
            },
        )
        assert rw.status_code == 200, rw.text
        body = rw.json()
        api_gate = (body.get("content_delta") or {}).get("quality_gate") or {}
        full = body["full_resume"]
        # No fabrication of evidence
        for exp in full.get("experiences") or []:
            for b in exp.get("bullets") or []:
                assert b.get("evidence_from"), (key, b)

        ok = gate["ok"] and api_gate.get("ok", True)
        results.append(
            {
                "jd": key,
                "ok": ok,
                "hidden": len(projected.get("hidden_entries") or []),
                "skills_head": str(projected.get("skills_certifications") or "")[:80],
                "errors": gate["errors"],
                "api_errors": api_gate.get("errors"),
            }
        )

    failed = [r for r in results if not r["ok"]]
    for r in results:
        print(f"{r['jd']}: ok={r['ok']} hidden={r['hidden']} errors={r['errors']}")
    if failed:
        print("FAIL")
        return 1
    print("PASS 3/3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
