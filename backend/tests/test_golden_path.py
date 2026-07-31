"""Golden-path acceptance: the always-demoable job application chain.

Chain under test:
  upload resume → auto-discover → pick 1 job → tailor → prepare package
  → confirm manual submit

Also covers edge cases that keep demos from hanging or lying:
  - auto-discover with no resume → 400
  - provider miss → synthetic local fallback still yields jobs
  - hung JobSpy scrape → discover_all returns promptly
"""

from __future__ import annotations

import sys
import time
import types
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)

SAMPLE_RESUME = """Jane Doe
jane@example.com
Data analyst with Python and SQL experience building dashboards.

PROFESSIONAL EXPERIENCE
Data Analyst | Example Analytics | Remote - 2022 - Present
• Built Python and SQL dashboards for weekly business reporting.
• Automated data quality checks and reduced manual review time by 30%.

SKILLS & CERTIFICATIONS
Python, SQL, FastAPI, Tableau
"""


@pytest.fixture
def user_id() -> str:
    return str(uuid4())


@pytest.fixture
def force_empty_providers(monkeypatch):
    """Force discover_all to miss so the router synthetic fallback is exercised."""

    async def _empty(**kwargs):
        return []

    monkeypatch.setattr(
        "app.modules.job_discovery.router.discover_all",
        _empty,
    )


def _upload_resume(user_id: str) -> str:
    response = client.post(
        "/api/v1/resume-tailor/upload-resume",
        json={"user_id": user_id, "resume_text": SAMPLE_RESUME},
    )
    assert response.status_code == 200, response.text
    resume_id = response.json()["resume_id"]
    assert resume_id
    return resume_id


def test_golden_path_upload_discover_tailor_prepare_confirm(
    user_id: str,
    force_empty_providers,
) -> None:
    # 1) Upload resume
    resume_id = _upload_resume(user_id)

    # 2) Auto-discover from resume (no explicit query) → synthetic fallback jobs
    discovered = client.post(
        "/api/v1/jobs/auto-discover",
        json={"user_id": user_id, "limit": 2},
    )
    assert discovered.status_code == 200, discovered.text
    jobs = discovered.json()["jobs"]
    assert len(jobs) >= 1
    assert jobs[0]["source_platform"] == "local_phase2"
    assert "data analyst" in jobs[0]["title"].lower()

    # 3) Pick one job
    job = jobs[0]
    job_id = job["id"]

    # 4) Tailor resume against the chosen JD
    tailored = client.post(
        "/api/v1/resume-tailor/tailor",
        json={
            "user_id": user_id,
            "resume_id": resume_id,
            "jd_text": job["raw_text"],
            "job_id": job_id,
        },
    )
    assert tailored.status_code == 200, tailored.text
    tailored_body = tailored.json()
    assert tailored_body["tailored_resume_id"]
    assert tailored_body["draft_id"]

    # 5) Generate application package (resume + cover letter + plan)
    prepared = client.post(
        f"/api/v1/jobs/{job_id}/prepare-application",
        json={
            "user_id": user_id,
            "resume_id": resume_id,
            "include_cover_letter": True,
            "include_application_plan": True,
            "submit_mode": "manual_review",
            "user_profile": {"full_name": "Jane Doe", "email": "jane@example.com"},
        },
    )
    assert prepared.status_code == 200, prepared.text
    package = prepared.json()
    assert package["tailored"]["tailored_resume_id"]
    assert package["cover_letter"]["id"]
    plan = package["application_plan"]
    assert plan["application_run_id"]
    assert plan["plan"]["can_submit"] is False
    assert plan["plan"]["policy"]["manual_review_required"] is True

    # 6) Manual confirm submission
    confirm = client.post(
        f"/api/v1/applications/{plan['application_run_id']}/confirm-manual-submit",
        json={
            "user_id": user_id,
            "confirmation_note": "Reviewed in browser and submitted.",
        },
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "submitted_by_user"


def test_auto_discover_without_resume_returns_400(user_id: str) -> None:
    response = client.post(
        "/api/v1/jobs/auto-discover",
        json={"user_id": user_id, "limit": 2},
    )
    assert response.status_code == 400
    assert "resume" in response.json()["detail"].lower()


def test_auto_discover_uses_experience_title_when_no_query(
    user_id: str,
    force_empty_providers,
) -> None:
    _upload_resume(user_id)
    response = client.post(
        "/api/v1/jobs/auto-discover",
        json={"user_id": user_id, "limit": 1},
    )
    assert response.status_code == 200, response.text
    job = response.json()["jobs"][0]
    # Derived from first experience title "Data Analyst"
    assert "data analyst" in job["title"].lower()


def test_discover_provider_miss_falls_back_to_synthetic(
    user_id: str,
    force_empty_providers,
) -> None:
    response = client.post(
        "/api/v1/jobs/discover",
        json={
            "user_id": user_id,
            "query": "machine learning engineer",
            "location": "Remote",
            "limit": 2,
        },
    )
    assert response.status_code == 200, response.text
    jobs = response.json()["jobs"]
    assert len(jobs) == 2
    assert all(job["source_platform"] == "local_phase2" for job in jobs)


def test_hung_jobspy_does_not_block_discovery(monkeypatch) -> None:
    """Edge case: hung scrape must return near timeout, not after scrape ends."""
    from app.modules.job_discovery.providers.jobspy_provider import JobSpyProvider

    def slow_scrape(**kwargs):
        time.sleep(3)
        frame = MagicMock()
        frame.to_dict.return_value = []
        return frame

    fake = types.ModuleType("jobspy")
    fake.scrape_jobs = slow_scrape
    monkeypatch.setitem(sys.modules, "jobspy", fake)

    provider = JobSpyProvider()
    start = time.perf_counter()
    result = provider.discover(
        query="data analyst",
        location="Remote",
        limit=5,
        timeout=0.4,
    )
    elapsed = time.perf_counter() - start

    assert result == []
    assert elapsed < 1.5, f"hung scrape path took {elapsed:.2f}s"


def test_tailor_without_uploaded_resume_stays_honest(user_id: str) -> None:
    """No fabrication: empty evidence must not invent experience."""
    response = client.post(
        "/api/v1/resume-tailor/tailor",
        json={
            "user_id": user_id,
            "resume_id": str(uuid4()),
            "jd_text": "Data Analyst\nRequirements: Python, SQL",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    tailored = body.get("tailored_resume") or {}
    assert tailored.get("experiences") in ([], None) or len(tailored.get("experiences") or []) == 0
    summary = (tailored.get("tailoring_summary") or body.get("message") or "").lower()
    assert "upload" in summary or "could not tailor" in summary or "no original" in summary
