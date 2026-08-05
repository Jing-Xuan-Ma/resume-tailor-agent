"""Unit checks for official apply URL preference (Indeed → company ATS)."""

from app.modules.job_discovery.apply_url import (
    is_aggregator_url,
    prefer_official_apply_url,
    resolve_listing_apply_url,
)


def test_prefer_greenhouse_over_indeed():
    got = prefer_official_apply_url(
        "https://www.indeed.com/viewjob?jk=abc",
        "https://job-boards.greenhouse.io/amperesand/jobs/4062231009?utm_source=jobright",
        board_fallback="https://www.indeed.com/viewjob?jk=abc",
    )
    assert "greenhouse.io" in got


def test_aggregator_detection():
    assert is_aggregator_url("https://www.indeed.com/viewjob?jk=1")
    assert is_aggregator_url("https://www.linkedin.com/jobs/view/1")
    assert not is_aggregator_url("https://boards.greenhouse.io/acme/jobs/1")


def test_resolve_listing_uses_job_url_direct():
    listing = {
        "source_url": "https://www.indeed.com/viewjob?jk=x",
        "metadata": {
            "board_url": "https://www.indeed.com/viewjob?jk=x",
            "job_url_direct": "https://jobs.silkroad.com/NYU/jobs/1",
            "apply_url": "https://jobs.silkroad.com/NYU/jobs/1",
        },
        "raw_text": "",
    }
    assert "silkroad.com" in (resolve_listing_apply_url(listing) or "")


def test_resolve_listing_extracts_ats_from_jd_body():
    listing = {
        "source_url": "https://www.indeed.com/viewjob?jk=x",
        "metadata": {},
        "raw_text": "Apply at https://boards.greenhouse.io/acme/jobs/99 today",
    }
    assert "greenhouse.io" in (resolve_listing_apply_url(listing) or "")


def test_reject_thin_workday_career_root():
    from app.modules.job_discovery.apply_url import is_usable_job_apply_url

    thin = "https://rb.wd5.myworkdayjobs.com/FRS"
    assert not is_usable_job_apply_url(thin)
    got = prefer_official_apply_url(
        thin,
        "https://www.indeed.com/viewjob?jk=abc",
        board_fallback="https://www.indeed.com/viewjob?jk=abc",
    )
    assert "indeed.com" in (got or "")


def test_jobright_apply_url_trusted_even_if_thin_workday():
    """Jobright Apply href is authoritative — do not replace with Indeed."""
    listing = {
        "source_platform": "jobright_extension",
        "source_url": "https://rb.wd5.myworkdayjobs.com/FRS",
        "metadata": {
            "apply_url": "https://rb.wd5.myworkdayjobs.com/FRS",
            "has_external_apply": True,
        },
        "raw_text": "",
    }
    assert resolve_listing_apply_url(listing) == "https://rb.wd5.myworkdayjobs.com/FRS"


def test_jobright_utm_greenhouse_preferred():
    listing = {
        "source_platform": "jobright_extension",
        "source_url": "https://www.indeed.com/viewjob?jk=x",
        "metadata": {
            "apply_url": "https://job-boards.greenhouse.io/embed/job_app?for=amperesand&token=1&utm_source=jobright",
            "has_external_apply": True,
            "board_url": "https://www.indeed.com/viewjob?jk=x",
        },
        "raw_text": "",
    }
    got = resolve_listing_apply_url(listing) or ""
    assert "greenhouse.io" in got
    assert "utm_source=jobright" in got
