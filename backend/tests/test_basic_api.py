from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_auth_register_login_and_me() -> None:
    email = f"user-{uuid4()}@example.com"
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Test User", "password": "password123"},
    )
    assert register.status_code == 200
    token = register.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200


def test_profile_api_persists_feedback() -> None:
    user_id = uuid4()
    response = client.post(
        "/api/v1/profile/feedback",
        json={"user_id": str(user_id), "feedback": {"note": "Please make it shorter and concise"}},
    )
    assert response.status_code == 200
    assert response.json()["profile"]["verbosity"] == "concise"


def test_phase2_job_discovery_creates_jobs() -> None:
    user_id = uuid4()
    response = client.post(
        "/api/v1/jobs/discover",
        json={"user_id": str(user_id), "query": "data analyst", "location": "Remote", "limit": 2},
    )
    assert response.status_code == 200
    assert len(response.json()["jobs"]) == 2


def test_job_bookmark_and_application_plan_are_manual_review_only() -> None:
    user_id = uuid4()
    ingest = client.post(
        "/api/v1/jobs/ingest",
        json={
            "user_id": str(user_id),
            "raw_text": "Software Engineer\nCompany: Example\nRequirements: Python, FastAPI",
            "source_url": "https://job-boards.greenhouse.io/example/jobs/123",
            "source_platform": "greenhouse",
        },
    )
    assert ingest.status_code == 200
    job = ingest.json()

    bookmark = client.post(
        "/api/v1/jobs/bookmarks",
        json={"user_id": str(user_id), "job_id": job["id"], "notes": "Strong fit"},
    )
    assert bookmark.status_code == 200

    plan = client.post(
        "/api/v1/applications/plan",
        json={
            "user_id": str(user_id),
            "job_id": job["id"],
            "auto_submit": True,
            "user_profile": {"full_name": "Test User", "email": "test@example.com"},
        },
    )
    assert plan.status_code == 200
    body = plan.json()
    assert body["status"] == "prepared_pending_manual_review"
    assert body["plan"]["ats_type"] == "greenhouse"
    assert body["plan"]["can_submit"] is False
    assert body["plan"]["policy"]["manual_review_required"] is True
    assert body["plan"]["policy"]["auto_submit_allowed"] is False

    confirm = client.post(
        f"/api/v1/applications/{body['application_run_id']}/confirm-manual-submit",
        json={"user_id": str(user_id), "confirmation_note": "Reviewed in browser and submitted."},
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "submitted_by_user"


def test_ats_detection_for_common_platforms() -> None:
    cases = [
        ("https://jobs.ashbyhq.com/acme/123", "ashby"),
        ("https://jobs.lever.co/acme/123", "lever"),
        ("https://company.wd5.myworkdayjobs.com/Careers/job/123", "workday"),
        ("https://careers-acme.icims.com/jobs/123", "icims"),
    ]
    for url, ats_type in cases:
        user_id = uuid4()
        ingest = client.post(
            "/api/v1/jobs/ingest",
            json={
                "user_id": str(user_id),
                "raw_text": "Engineer\nRequirements: Python",
                "source_url": url,
            },
        )
        job_id = ingest.json()["id"]
        plan = client.post(
            "/api/v1/applications/plan",
            json={"user_id": str(user_id), "job_id": job_id},
        )
        assert plan.status_code == 200
        assert plan.json()["plan"]["ats_type"] == ats_type


def test_connector_hints_are_exposed_in_application_plan() -> None:
    user_id = uuid4()
    ingest = client.post(
        "/api/v1/jobs/ingest",
        json={
            "user_id": str(user_id),
            "raw_text": "Engineer\nRequirements: Python",
            "source_url": "https://job-boards.greenhouse.io/example/jobs/789",
        },
    )
    job_id = ingest.json()["id"]
    plan = client.post(
        "/api/v1/applications/plan",
        json={
            "user_id": str(user_id),
            "job_id": job_id,
            "user_profile": {"full_name": "Test User", "email": "test@example.com"},
        },
    )
    assert plan.status_code == 200
    body = plan.json()
    assert body["plan"]["ats_type"] == "greenhouse"
    assert any(field["name"] == "linkedin" for field in body["plan"]["fields"])
    assert all("field_name" in answer for answer in body["answers"])
    first_name = next(answer for answer in body["answers"] if answer["field_name"] == "first_name")
    assert "first name" in first_name["aliases"]


@pytest.mark.network
def test_prepare_application_for_job_creates_resume_cover_letter_and_plan() -> None:
    user_id = uuid4()
    ingest = client.post(
        "/api/v1/jobs/ingest",
        json={
            "user_id": str(user_id),
            "raw_text": (
                "Data Analyst\nCompany: Example Co\n"
                "Requirements: Python, SQL, dashboards, reporting"
            ),
            "source_url": "https://job-boards.greenhouse.io/example/jobs/456",
            "source_platform": "greenhouse",
        },
    )
    assert ingest.status_code == 200
    job_id = ingest.json()["id"]

    response = client.post(
        f"/api/v1/jobs/{job_id}/prepare-application",
        json={
            "user_id": str(user_id),
            "include_cover_letter": True,
            "include_application_plan": True,
            "auto_submit": True,
            "user_profile": {"full_name": "Jane Doe", "email": "jane@example.com"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tailored"]["tailored_resume_id"]
    assert body["cover_letter"]["id"]
    assert body["application_plan"]["application_run_id"]
    assert body["application_plan"]["plan"]["ats_type"] == "greenhouse"
    assert body["application_plan"]["plan"]["can_submit"] is False
    assert body["application_plan"]["plan"]["cover_letter_id"] == body["cover_letter"]["id"]
    assert body["application_plan"]["plan"]["artifacts"].get("resume")
    assert body["application_plan"]["plan"]["artifacts"].get("cover_letter")
    resume_answer = next(
        answer for answer in body["application_plan"]["answers"] if answer["field_name"] == "resume"
    )
    assert resume_answer["answer"].endswith(("resume.pdf", "resume.txt"))


def test_auto_submit_mode_submits_when_explicitly_requested() -> None:
    user_id = uuid4()
    ingest = client.post(
        "/api/v1/jobs/ingest",
        json={
            "user_id": str(user_id),
            "raw_text": "Software Engineer\nCompany: Example\nRequirements: Python",
            "source_url": "https://jobs.lever.co/example/123",
            "source_platform": "lever",
        },
    )
    assert ingest.status_code == 200
    job_id = ingest.json()["id"]

    plan = client.post(
        "/api/v1/applications/plan",
        json={
            "user_id": str(user_id),
            "job_id": job_id,
            "auto_submit": True,
            "submit_mode": "auto_submit",
            "user_profile": {"full_name": "Test User", "email": "test@example.com"},
        },
    )
    assert plan.status_code == 200
    body = plan.json()
    assert body["status"] == "prepared_for_auto_submit"
    assert body["plan"]["can_submit"] is True
    assert body["plan"]["policy"]["auto_submit_allowed"] is True

    submit = client.post(
        f"/api/v1/applications/{body['application_run_id']}/auto-submit",
        json={"user_id": str(user_id), "confirm_auto_submit": True},
    )
    assert submit.status_code == 200
    assert submit.json()["status"] == "auto_submitted"
    assert submit.json()["submission_result"]["submitted"] is True
    assert submit.json()["submission_result"]["mode"] == "connector_submit_boundary"


def test_auto_submit_blocked_without_auto_policy() -> None:
    user_id = uuid4()
    ingest = client.post(
        "/api/v1/jobs/ingest",
        json={
            "user_id": str(user_id),
            "raw_text": "Software Engineer\nCompany: Example\nRequirements: Python",
            "source_url": "https://jobs.ashbyhq.com/example/123",
        },
    )
    job_id = ingest.json()["id"]
    plan = client.post(
        "/api/v1/applications/plan",
        json={"user_id": str(user_id), "job_id": job_id, "submit_mode": "manual_review"},
    )
    run_id = plan.json()["application_run_id"]
    submit = client.post(
        f"/api/v1/applications/{run_id}/auto-submit",
        json={"user_id": str(user_id), "confirm_auto_submit": True},
    )
    assert submit.status_code == 409
    assert submit.json()["detail"]["status"] == "blocked_by_policy"


def test_cold_outreach_draft_and_mark_sent() -> None:
    user_id = uuid4()
    ingest = client.post(
        "/api/v1/jobs/ingest",
        json={
            "user_id": str(user_id),
            "raw_text": "Data Analyst\nCompany: Example Co\nRequirements: Python, SQL, dashboards",
            "source_url": "https://job-boards.greenhouse.io/example/jobs/777",
            "source_platform": "greenhouse",
        },
    )
    assert ingest.status_code == 200
    job_id = ingest.json()["id"]

    draft = client.post(
        "/api/v1/outreach/draft",
        json={
            "user_id": str(user_id),
            "job_id": job_id,
            "contact_name": "Alex",
            "channel": "email",
        },
    )
    assert draft.status_code == 200
    body = draft.json()
    assert body["status"] == "draft"
    assert "Data Analyst" in body["subject"]

    sent = client.post(f"/api/v1/outreach/{body['id']}/mark-sent", json={"user_id": str(user_id)})
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent_by_user"
