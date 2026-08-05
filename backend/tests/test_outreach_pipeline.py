"""Cold outreach pipeline: candidate scoring, email finder, JD ingest, linkedin_connect."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.modules.cold_outreach.candidate_scorer import rank_candidates, score_candidate
from app.modules.cold_outreach.email_finder import find_emails, infer_company_domain
from app.modules.cold_outreach.jd_ingest import _parse_from_url

client = TestClient(app)


def test_score_hiring_manager_beats_generic_ta():
    jd = "Join our Data Analytics team building SQL dashboards."
    hm = score_candidate(
        name="Alex Chen",
        title="Data Team Hiring Manager",
        snippet="Leading analytics hiring",
        recent_activity="We're hiring a Data Analyst — DM me",
        jd_text=jd,
        position="Data Analyst",
        company_size="large",
    )
    ta = score_candidate(
        name="Pat Lee",
        title="Talent Acquisition Specialist",
        snippet="Corporate TA",
        jd_text=jd,
        position="Data Analyst",
        company_size="large",
    )
    assert hm["score"] > ta["score"]
    assert hm["stars"] >= 4
    assert "Hiring Manager" in hm["match_reason"] or "hiring" in hm["match_reason"].lower()


def test_rank_candidates_sorts_descending():
    ranked = rank_candidates(
        [
            {"name": "Jamie", "title": "Technical Recruiter", "id": "1"},
            {
                "name": "Alex",
                "title": "Hiring Manager, Analytics",
                "recent_activity": "now hiring data analyst",
                "id": "2",
            },
            {"name": "Sam", "title": "Analytics Manager", "id": "3"},
        ],
        jd_text="Data Analytics team needs a SQL analyst",
        position="Data Analyst",
        company_size="large",
    )
    assert ranked[0]["name"] == "Alex"
    assert ranked[0]["score"] >= ranked[1]["score"] >= ranked[2]["score"]


def test_infer_company_domain():
    assert infer_company_domain("Acme Corp") == "acme.com"
    assert infer_company_domain("", "https://www.stripe.com/careers") == "stripe.com"


def test_parse_jd_url_greenhouse_and_linkedin():
    gh = _parse_from_url("https://boards.greenhouse.io/northwind/jobs/12345")
    assert gh["platform"] == "greenhouse"
    assert "Northwind" in gh["company"] or "northwind" in gh["company"].lower()

    li = _parse_from_url(
        "https://www.linkedin.com/jobs/view/data-analyst-at-acme-corp-4123456789"
    )
    assert li["platform"] == "linkedin"
    assert "Data Analyst" in li["position"]
    assert "Acme" in li["company"]


def test_find_emails_format_inference_no_hunter():
    import asyncio

    result = asyncio.run(find_emails(name="Alex Chen", company="Example Co", use_hunter=False))
    assert result["domain"]
    assert result["hunter_used"] is False
    assert any("alex" in c["email"] for c in result["candidates"])
    assert result["candidates"][0]["confidence_label"] in {"high", "medium", "low"}


def test_api_rank_candidates():
    user_id = uuid4()
    res = client.post(
        "/api/v1/outreach/rank-candidates",
        json={
            "user_id": str(user_id),
            "position": "Data Analyst",
            "jd_text": "Analytics team SQL Python dashboards",
            "company_size": "large",
            "candidates": [
                {"id": "a", "name": "Alex Chen", "title": "Hiring Manager, Data"},
                {"id": "b", "name": "Jamie Lee", "title": "Technical Recruiter"},
            ],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["candidates"]) == 2
    assert body["candidates"][0]["score"] >= body["candidates"][1]["score"]
    assert body["candidates"][0]["match_reason"]


def test_api_find_email_and_linkedin_connect_draft():
    user_id = uuid4()
    lookup = client.post(
        "/api/v1/outreach/find-email",
        json={"user_id": str(user_id), "name": "Alex Chen", "company": "Acme", "use_hunter": False},
    )
    assert lookup.status_code == 200
    emails = lookup.json()
    assert emails["expectancy_note"]
    assert isinstance(emails["candidates"], list)

    draft = client.post(
        "/api/v1/outreach/draft",
        json={
            "user_id": str(user_id),
            "contact_name": "Alex",
            "company": "Acme",
            "channel": "linkedin",
            "template_type": "linkedin_connect",
            "tone": "warm",
        },
    )
    assert draft.status_code == 200
    body = draft.json()
    assert body["metadata"]["template_type"] == "linkedin_connect"
    assert len(body["body"]) <= 300
    assert "Alex" in body["body"]


def test_api_jd_ingest_url_parse_without_network_dependency():
    """Even if fetch fails, URL slug parsing should still return company."""
    user_id = uuid4()
    res = client.post(
        "/api/v1/outreach/jd-ingest",
        json={
            "user_id": str(user_id),
            "url": "https://boards.greenhouse.io/northwind/jobs/999",
            "jd_text_override": "Data Analyst role on the Analytics team. SQL required.",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["platform"] == "greenhouse"
    assert "Analytics" in data["jd_text"] or data["company"]
