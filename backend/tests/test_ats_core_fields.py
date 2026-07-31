"""Unit tests for Greenhouse + Lever core-field wiring.

Depth over breadth: these two ATS targets must expose selectors and answers for
first/last (or full name), email, phone, resume, cover letter, LinkedIn, and
submit. Workday/iCIMS stay on thinner fallback overlays.
"""

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.modules.application_engine.browser_session import BrowserSession
from app.modules.application_engine.question_answerer import QuestionAnswerer
from app.modules.ats_connectors.greenhouse import GreenhouseConnector
from app.modules.ats_connectors.lever import LeverConnector
from app.modules.ats_connectors.registry import connector_for


client = TestClient(app)

CORE_PROFILE = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+1-555-0100",
    "linkedin_url": "https://www.linkedin.com/in/janedoe",
    "portfolio_url": "https://jane.dev",
    "github_url": "https://github.com/janedoe",
    "current_company": "Example Analytics",
}


def test_registry_detects_greenhouse_and_lever() -> None:
    assert connector_for("https://job-boards.greenhouse.io/acme/jobs/1").ats_type == "greenhouse"
    assert connector_for("https://boards.greenhouse.io/acme/jobs/1").ats_type == "greenhouse"
    assert connector_for("https://jobs.lever.co/acme/abc").ats_type == "lever"


def test_greenhouse_core_field_selectors() -> None:
    gh = GreenhouseConnector()
    names = {field["name"] for field in gh.fields()}
    assert {"first_name", "last_name", "email", "phone", "resume", "cover_letter", "linkedin"} <= names

    selectors = gh.field_selectors()
    assert "#first_name" in selectors["first_name"]
    assert "#last_name" in selectors["last_name"]
    assert "#email" in selectors["email"]
    assert "#phone" in selectors["phone"]
    assert "#resume" in selectors["resume"]
    assert any("cover" in sel for sel in selectors["cover_letter"])
    assert any("linkedin" in sel.lower() for sel in selectors["linkedin"])
    assert "#submit_app" in gh.submit_selectors()
    assert gh.apply_selectors()


def test_lever_core_field_selectors() -> None:
    lever = LeverConnector()
    names = {field["name"] for field in lever.fields()}
    assert {"full_name", "email", "phone", "resume", "cover_letter", "linkedin"} <= names
    # Lever uses a single name field, not first/last.
    assert "first_name" not in names

    selectors = lever.field_selectors()
    assert "input[name='name']" in selectors["full_name"]
    assert "input[name='email']" in selectors["email"]
    assert "input[name='phone']" in selectors["phone"]
    assert "input[name='resume']" in selectors["resume"]
    assert "input[name='urls[LinkedIn]']" in selectors["linkedin"]
    assert any("textarea" in sel for sel in selectors["cover_letter"])
    assert any("template-btn-submit" in sel for sel in lever.submit_selectors())
    assert any("Apply for this Job" in sel for sel in lever.apply_selectors())


def test_question_answerer_fills_core_profile_fields() -> None:
    answerer = QuestionAnswerer()
    job = {"source_platform": "lever"}

    phone = answerer.answer(
        question="Phone number",
        field_type="text",
        options=None,
        user_profile=CORE_PROFILE,
        job=job,
        field_name="phone",
    )
    assert phone["answer"] == "+1-555-0100"
    assert phone["confidence"] >= 0.75

    full_name = answerer.answer(
        question="Full name",
        field_type="text",
        options=None,
        user_profile=CORE_PROFILE,
        job=job,
        field_name="full_name",
    )
    assert full_name["answer"] == "Jane Doe"

    first = answerer.answer(
        question="First name",
        field_type="text",
        options=None,
        user_profile=CORE_PROFILE,
        job=job,
        field_name="first_name",
    )
    assert first["answer"] == "Jane"

    linkedin = answerer.answer(
        question="LinkedIn Profile",
        field_type="text",
        options=None,
        user_profile=CORE_PROFILE,
        job=job,
        field_name="linkedin",
    )
    assert "linkedin.com" in linkedin["answer"]


def test_question_answerer_reads_cover_letter_text(tmp_path: Path) -> None:
    cover = tmp_path / "cover_letter.txt"
    cover.write_text("Dear hiring manager,\nI am excited to apply.", encoding="utf-8")
    answerer = QuestionAnswerer()
    result = answerer.answer(
        question="Cover letter / additional information",
        field_type="text",
        options=None,
        user_profile=CORE_PROFILE,
        job={},
        field_name="cover_letter",
        artifacts={"cover_letter": str(cover)},
    )
    assert "excited to apply" in result["answer"]


def test_browser_session_cover_letter_text_file_helper(tmp_path: Path) -> None:
    cover = tmp_path / "cover_letter.txt"
    cover.write_text("Hello Lever", encoding="utf-8")
    assert BrowserSession._read_text_file(str(cover)) == "Hello Lever"
    assert BrowserSession._read_text_file(str(tmp_path / "missing.txt")) is None


def test_application_plan_answers_include_phone_for_greenhouse() -> None:
    user_id = uuid4()
    ingest = client.post(
        "/api/v1/jobs/ingest",
        json={
            "user_id": str(user_id),
            "raw_text": "Software Engineer\nCompany: Example\nRequirements: Python",
            "source_url": "https://job-boards.greenhouse.io/example/jobs/42",
            "source_platform": "greenhouse",
        },
    )
    assert ingest.status_code == 200
    job_id = ingest.json()["id"]

    plan = client.post(
        "/api/v1/applications/plan",
        json={
            "user_id": str(user_id),
            "job_id": job_id,
            "user_profile": CORE_PROFILE,
        },
    )
    assert plan.status_code == 200
    body = plan.json()
    assert body["plan"]["ats_type"] == "greenhouse"
    answers = {item["field_name"]: item["answer"] for item in body["answers"]}
    assert answers["first_name"] == "Jane"
    assert answers["last_name"] == "Doe"
    assert answers["email"] == "jane@example.com"
    assert answers["phone"] == "+1-555-0100"
    assert "linkedin.com" in answers["linkedin"]


def test_application_plan_answers_include_core_fields_for_lever() -> None:
    user_id = uuid4()
    ingest = client.post(
        "/api/v1/jobs/ingest",
        json={
            "user_id": str(user_id),
            "raw_text": "Software Engineer\nCompany: Example\nRequirements: Python",
            "source_url": "https://jobs.lever.co/example/abc123",
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
            "user_profile": CORE_PROFILE,
        },
    )
    assert plan.status_code == 200
    body = plan.json()
    assert body["plan"]["ats_type"] == "lever"
    answers = {item["field_name"]: item["answer"] for item in body["answers"]}
    assert answers["full_name"] == "Jane Doe"
    assert answers["email"] == "jane@example.com"
    assert answers["phone"] == "+1-555-0100"
    assert answers["org"] == "Example Analytics"
    assert "linkedin.com" in answers["linkedin"]
    assert "github.com" in answers["github"]
