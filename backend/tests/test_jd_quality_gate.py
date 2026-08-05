"""Unit tests for Jobright-style JD quality gate."""

from app.modules.job_discovery.quality import assess_listing_quality, filter_quality_leads


def _lead(**kwargs):
    base = {
        "title": "Data Analyst",
        "company": "Acme Corp",
        "source_url": "https://example.com/jobs/1",
        "source_platform": "jobspy:indeed",
        "raw_text": "",
        "metadata": {},
    }
    base.update(kwargs)
    return base


def test_rejects_adzuna_ellipsis_teaser():
    body = (
        "Expertise in translating stakeholder needs into actionable business requirements, "
        "validating data solutions and driving successful data product development…"
    )
    lead = _lead(
        source_platform="adzuna",
        raw_text=f"Data Analyst\nCompany: Rangam\n\n{body}",
    )
    v = assess_listing_quality(lead, min_chars=500)
    assert v["ok"] is False
    assert v["reason"] == "adzuna_ad_board"


def test_accepts_full_jd_with_skills():
    body = (
        "Responsibilities\n"
        "Build dashboards and analyze datasets using SQL, Python, and Tableau. "
        "Partner with stakeholders on experimentation and ETL pipelines. "
        "Requirements: 3+ years experience with Excel, statistics, and data visualization. "
        "Nice to have: dbt, Snowflake, Looker."
    ) * 2
    lead = _lead(raw_text=f"Data Analyst\nCompany: Acme\n\n{body}")
    v = assess_listing_quality(lead, min_chars=500)
    assert v["ok"] is True
    assert "sql" in v["skills"] or "python" in v["skills"]


def test_filter_splits_accepted_rejected():
    good_body = (
        "Requirements: SQL, Python, Tableau. Responsibilities include dashboarding, "
        "statistics, and stakeholder communication across analytics initiatives. "
    ) * 5
    leads = [
        _lead(raw_text=f"Data Analyst\n\n{good_body}"),
        _lead(
            title="Earn Extra Cash Now",
            source_platform="adzuna",
            raw_text="Data Analyst\n\nShort teaser…",
        ),
    ]
    ok, bad = filter_quality_leads(leads, min_chars=500)
    assert len(ok) == 1
    assert len(bad) == 1
