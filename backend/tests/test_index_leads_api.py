"""Tests for Jobright extension leads upsert API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


FULL_JD = """Data Analyst at Northwind Analytics

About the role
Partner with product and growth on SQL, dashboards, and experiments. You will own weekly metrics reviews and translate ambiguous questions into clear analyses for stakeholders across product, marketing, and finance.

Responsibilities
• Production SQL in BigQuery or Snowflake with documented metric definitions
• Tableau dashboards for weekly business reviews and funnel monitoring
• A/B test readouts with recommendations and caveats for decision makers
• Partner with engineers on data quality and pipeline reliability

Requirements
• 2+ years as Data Analyst or similar analytics role
• Strong SQL and analytical storytelling with clear stakeholder communication
• Python or R for data wrangling and lightweight automation
• Tableau, Power BI, or Looker for interactive dashboards
• Comfortable with experimentation concepts and product analytics funnels

Minimum qualifications include SQL, dashboards, and analytical storytelling. What you'll do day to day is turn ambiguous business questions into measurable analyses and reliable reporting.
"""


@pytest.fixture()
def client():
    return TestClient(app)


def test_upsert_lead_requires_token(client: TestClient):
    res = client.post(
        "/api/v1/jobs/index/leads",
        json={
            "title": "Data Analyst",
            "company": "Northwind Analytics",
            "raw_text": FULL_JD,
            "source_url": "https://boards.greenhouse.io/northwind/jobs/1234567",
        },
    )
    assert res.status_code == 401


def test_upsert_lead_ok(client: TestClient):
    res = client.post(
        "/api/v1/jobs/index/leads",
        headers={"X-Extension-Token": "dev-extension-token"},
        json={
            "title": "Data Analyst",
            "company": "Northwind Analytics",
            "location": "Remote",
            "raw_text": FULL_JD,
            "source_url": "https://boards.greenhouse.io/northwind/jobs/999001",
            "jobright_url": "https://jobright.ai/jobs/mock-1",
            "source_platform": "jobright_extension",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"]
    assert data["quality_ok"] is True
    assert "view=resume" in data["workspace_url"]
    assert data["id"] in data["workspace_url"]
    assert "step=apply" in data["apply_step_url"]
    assert "/outreach" in data["outreach_step_url"]
    assert data["id"] in data["outreach_step_url"]


def test_upsert_lead_rejects_thin_jd(client: TestClient):
    res = client.post(
        "/api/v1/jobs/index/leads",
        headers={"X-Extension-Token": "dev-extension-token"},
        json={
            "title": "Data Analyst",
            "company": "Thin Co",
            "raw_text": "Short teaser…",
            "source_url": "https://example.com/jobs/1",
        },
    )
    assert res.status_code == 422


def test_upsert_lead_accepts_jobright_page_url_without_apply(client: TestClient):
    """Closed Jobright posts often have no external Apply link — page URL is enough."""
    res = client.post(
        "/api/v1/jobs/index/leads",
        headers={"X-Extension-Token": "dev-extension-token"},
        json={
            "title": "Masters in AI Specialist Intern to Full Time ONSITE",
            "company": "RJMedex",
            "raw_text": FULL_JD,
            "source_url": None,
            "jobright_url": "https://jobright.ai/jobs/rjmedex-closed-example",
            "source_platform": "jobright_extension",
            "metadata": {"page_url": "https://jobright.ai/jobs/rjmedex-closed-example"},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["quality_ok"] is True
