"""ATS detector unit tests — Workday / Greenhouse / Lever domain rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.form_fill_engine.ats_detector import detect_ats
from app.modules.form_fill_engine.schemas import ATSType, DOMSnapshot

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> DOMSnapshot:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return DOMSnapshot.model_validate(data)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://acme.myworkdayjobs.com/en-US/careers/job/X", ATSType.WORKDAY),
        ("https://boards.greenhouse.io/acme/jobs/1", ATSType.GREENHOUSE),
        ("https://jobs.lever.co/acme/uuid", ATSType.LEVER),
        ("https://unknown-careers.example.com/apply", ATSType.UNKNOWN),
    ],
)
def test_detect_ats_domain_patterns(url: str, expected: ATSType):
    result = detect_ats(url, None)
    assert result.ats_type == expected
    if expected != ATSType.UNKNOWN:
        assert result.confidence >= 0.9
        assert result.detection_method == "domain_pattern"
    else:
        assert result.detection_method == "fallback"
        assert result.confidence == 0.0


def test_detect_ats_from_fixtures():
    for name, expected in [
        ("workday_sample.json", ATSType.WORKDAY),
        ("greenhouse_sample.json", ATSType.GREENHOUSE),
        ("lever_sample.json", ATSType.LEVER),
    ]:
        snap = _load(name)
        result = detect_ats(snap.url, snap)
        assert result.ats_type == expected
        assert result.confidence >= 0.9
