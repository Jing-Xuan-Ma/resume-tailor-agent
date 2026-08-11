"""Unit checks for official apply URL preference (Indeed → company ATS)."""

from app.modules.job_discovery.apply_url import (
    is_aggregator_url,
    is_usable_job_apply_url,
    normalize_apply_url,
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
    thin = "https://rb.wd5.myworkdayjobs.com/FRS"
    assert not is_usable_job_apply_url(thin)
    got = prefer_official_apply_url(
        thin,
        "https://www.indeed.com/viewjob?jk=abc",
        board_fallback="https://www.indeed.com/viewjob?jk=abc",
    )
    assert "indeed.com" in (got or "")


def test_normalize_markdown_escaped_workday():
    raw = r"https://rb.wd5\.myworkdayjobs.com/FRS"
    cleaned = normalize_apply_url(raw)
    assert cleaned == "https://rb.wd5.myworkdayjobs.com/FRS"
    assert not is_usable_job_apply_url(raw)
    assert not is_usable_job_apply_url(cleaned)


def test_indeed_jd_with_escaped_workday_falls_back_to_board():
    """Without live network, thin Workday clue alone must not be returned as source.

    Live resolve is covered by test_apply_resolver (network). Here we only assert
    the thin root itself is never treated as usable.
    """
    from app.modules.job_discovery.apply_url import is_usable_job_apply_url, normalize_apply_url

    raw = r"https://rb.wd5\.myworkdayjobs.com/FRS"
    cleaned = normalize_apply_url(raw)
    assert cleaned == "https://rb.wd5.myworkdayjobs.com/FRS"
    assert not is_usable_job_apply_url(cleaned)


def test_jobright_usable_greenhouse_still_preferred():
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


def test_tiktok_social_rejected_but_careers_allowed():
    assert not is_usable_job_apply_url("https://www.tiktok.com/@company")
    assert is_usable_job_apply_url(
        "https://careers.tiktok.com/resume/7670839727059339525/apply"
    )
    assert is_usable_job_apply_url(
        "https://lifeattiktok.com/search/7670839727059339525"
    )


def test_prefer_never_returns_unusable_workday_as_last_resort():
    got = prefer_official_apply_url(
        r"https://rb.wd5\.myworkdayjobs.com/FRS",
        board_fallback=None,
    )
    assert got is None
