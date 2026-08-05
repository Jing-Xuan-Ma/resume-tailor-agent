"""Apply URL Resolver — Workday CXS + listing integration."""

from __future__ import annotations

import pytest

from app.modules.job_discovery.apply_resolver.adapters.workday import parse_workday_career_url
from app.modules.job_discovery.apply_resolver.match import pick_best, score_candidate
from app.modules.job_discovery.apply_resolver.models import ApplyCandidate, ResolveStatus
from app.modules.job_discovery.apply_resolver.service import resolve_apply_url
from app.modules.job_discovery.apply_url import (
    is_usable_job_apply_url,
    resolve_listing_apply_url,
)


def test_parse_workday_frs_root():
    conn = parse_workday_career_url("https://rb.wd5.myworkdayjobs.com/FRS")
    assert conn is not None
    assert conn["tenant"] == "rb"
    assert conn["site"] == "FRS"
    assert conn["wd"] == "5"


def test_score_exact_title_beats_partial():
    exact = ApplyCandidate(title="Regulatory Data Analyst", url="https://x/a")
    other = ApplyCandidate(title="Regulatory Data Associate", url="https://x/b")
    assert score_candidate(exact, title="Regulatory Data Analyst") > score_candidate(
        other, title="Regulatory Data Analyst"
    )


def test_pick_best_req_id_boost():
    a = ApplyCandidate(title="Data Analyst", url="https://x/1", req_id="R-0000032890")
    b = ApplyCandidate(title="Regulatory Data Analyst", url="https://x/2", req_id="OTHER")
    best = pick_best(
        [a, b],
        title="Regulatory Data Analyst",
        raw_text="Req R-0000032890",
        min_confidence=0.3,
    )
    assert best is not None
    assert best.req_id == "R-0000032890"


@pytest.mark.network
def test_resolve_fed_workday_live():
    result = resolve_apply_url(
        company="Federal Reserve Bank of New York",
        title="Regulatory Data Analyst",
        location="New York",
        hints={"career_url": "https://rb.wd5.myworkdayjobs.com/FRS"},
        verify=True,
    )
    assert result.status in {ResolveStatus.VERIFIED, ResolveStatus.UNVERIFIED}
    assert result.url
    assert "myworkdayjobs.com" in result.url
    assert "/job/" in result.url.lower()
    assert is_usable_job_apply_url(result.url)
    assert "Regulatory" in (result.candidate.title if result.candidate else "")


@pytest.mark.network
def test_listing_fed_indeed_resolves_deep_link():
    listing = {
        "title": "Regulatory Data Analyst",
        "company": "Federal Reserve Bank of New York",
        "location": "New York, NY",
        "source_platform": "jobspy:indeed",
        "source_url": "https://www.indeed.com/viewjob?jk=2466bdbb34a5abf5",
        "metadata": {"site": "indeed"},
        "raw_text": (
            "Always verify and apply to jobs on Federal Reserve System Careers "
            r"(https://rb.wd5\.myworkdayjobs.com/FRS) or through verified channels."
        ),
    }
    got = resolve_listing_apply_url(listing) or ""
    assert "indeed.com" not in got
    assert "myworkdayjobs.com" in got
    assert "/job/" in got.lower()
    assert "\\" not in got


def test_jobright_usable_greenhouse_skips_resolver():
    listing = {
        "source_platform": "jobright_extension",
        "title": "Embedded Software Engineer Intern",
        "company": "Zipline",
        "source_url": "https://www.indeed.com/viewjob?jk=x",
        "metadata": {
            "apply_url": (
                "https://boards.greenhouse.io/embed/job_app?"
                "token=7765240003&utm_source=jobright"
            ),
            "has_external_apply": True,
            "board_url": "https://www.indeed.com/viewjob?jk=x",
        },
        "raw_text": "",
    }
    got = resolve_listing_apply_url(listing) or ""
    assert "greenhouse.io" in got
    assert "utm_source=jobright" in got
