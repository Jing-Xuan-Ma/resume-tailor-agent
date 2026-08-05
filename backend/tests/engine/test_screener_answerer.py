"""Screener answerer — evidence gate marks review when unsupported."""

from __future__ import annotations

import pytest

from app.modules.form_fill_engine.screener_answerer import (
    answer_screener_question,
    is_likely_screener,
    verify_evidence,
)
from app.modules.form_fill_engine.schemas import InteractiveElement


@pytest.mark.asyncio
async def test_verify_rejects_fabricated_metric():
    draft = "I improved conversion by 99.7% using proprietary quantum ML."
    facts = {"experiences": [{"bullets": ["Built dashboards in Tableau for sales ops"]}]}
    result = await verify_evidence(draft, facts, question="Describe impact")
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_empty_answer_needs_review():
    ans = await answer_screener_question(
        "Describe a time you led a 500-person org redesign",
        {"skills": ["SQL", "Python"]},
        element_index=3,
    )
    assert ans.needs_human_review is True
    assert ans.generated_answer == "" or not ans.evidence_check_passed


def test_is_likely_screener():
    el = InteractiveElement(
        index=0,
        tag="textarea",
        element_type="textarea",
        label="Why do you want to work here? Describe your SQL experience.",
    )
    assert is_likely_screener(el, None) is True
    assert is_likely_screener(el, "email") is False
