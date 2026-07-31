"""Regression tests for JobSpy scrape timeout behavior.

The previous implementation wrapped scrape_jobs in `with ThreadPoolExecutor(...)`,
whose __exit__ calls shutdown(wait=True). That blocked until the hung scrape
finished and completely negated fut.result(timeout=...).
"""

from __future__ import annotations

import sys
import time
import types
from unittest.mock import MagicMock

import pytest

from app.modules.job_discovery.providers.jobspy_provider import JobSpyProvider


def _install_fake_jobspy(monkeypatch, scrape_fn) -> None:
    fake = types.ModuleType("jobspy")
    fake.scrape_jobs = scrape_fn
    monkeypatch.setitem(sys.modules, "jobspy", fake)


def test_jobspy_timeout_returns_promptly_without_waiting_for_scrape(monkeypatch) -> None:
    """Caller must regain control near `timeout`, not after the scrape finishes."""

    def slow_scrape(**kwargs):
        time.sleep(3)
        frame = MagicMock()
        frame.to_dict.return_value = []
        return frame

    _install_fake_jobspy(monkeypatch, slow_scrape)

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
    # Must not wait for the full 3s scrape. Allow generous CI slack.
    assert elapsed < 1.5, f"timeout path took {elapsed:.2f}s; expected ~0.4s"


def test_jobspy_success_still_returns_jobs(monkeypatch) -> None:
    def fast_scrape(**kwargs):
        frame = MagicMock()
        frame.to_dict.return_value = [
            {
                "title": "Data Analyst",
                "company": "Acme",
                "city": "Remote",
                "state": None,
                "country": "USA",
                "description": "SQL and Python",
                "job_url": "https://example.com/jobs/1",
                "site": "indeed",
            }
        ]
        return frame

    _install_fake_jobspy(monkeypatch, fast_scrape)

    provider = JobSpyProvider()
    jobs = provider.discover(query="data analyst", location="Remote", limit=5, timeout=2)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Analyst"
    assert jobs[0]["company"] == "Acme"
    assert jobs[0]["source_platform"] == "jobspy:indeed"


@pytest.mark.asyncio
async def test_discover_all_survives_slow_jobspy(monkeypatch) -> None:
    """Orchestrator must not hang when JobSpy scrape exceeds its timeout."""
    from app.modules.job_discovery import orchestrator as orch

    def slow_scrape(**kwargs):
        time.sleep(3)
        frame = MagicMock()
        frame.to_dict.return_value = []
        return frame

    _install_fake_jobspy(monkeypatch, slow_scrape)

    # Keep HTTP providers quiet so the test only exercises JobSpy timing.
    async def empty_discover(*, query, location, limit):
        return []

    for provider in orch.ALL_PROVIDERS:
        if provider.name != "jobspy":
            monkeypatch.setattr(provider, "discover", empty_discover)

    # Shorten JobSpy timeout used by the sync path inside discover_all.
    original_discover = orch.JobSpyProvider.discover

    def discover_with_short_timeout(self, **kwargs):
        kwargs.setdefault("timeout", 0.4)
        return original_discover(self, **kwargs)

    monkeypatch.setattr(orch.JobSpyProvider, "discover", discover_with_short_timeout)

    start = time.perf_counter()
    jobs = await orch.discover_all(query="data analyst", location="Remote", limit=3)
    elapsed = time.perf_counter() - start

    assert jobs == []
    assert elapsed < 2.0, f"discover_all took {elapsed:.2f}s with hung JobSpy"
