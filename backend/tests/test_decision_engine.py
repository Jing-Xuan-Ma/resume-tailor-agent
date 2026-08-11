"""Phase 2a decision engine — mechanical anti-hallucination guarantees.

No live LLM call here (see tests/test_llm_failover.py for network smoke
tests). This test fakes the model response to prove the *code*, not the
model, is what enforces zero-fabrication: a hallucinated id never survives,
and an id the model silently skips fails closed to "keep" rather than
vanishing.
"""

from __future__ import annotations

import json

from app.modules.resume_workspace.decision_engine import ExperienceItem, score_experience_items


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, _messages):
        return _FakeResponse(self._content)

    async def ainvoke(self, _messages):
        return _FakeResponse(self._content)


def test_hallucinated_id_is_dropped_and_missing_id_fails_closed(monkeypatch) -> None:
    items = [
        ExperienceItem(id="real-1", text="FastAPI backend work", source="test"),
        ExperienceItem(id="real-2", text="React frontend work", source="test"),
    ]
    # Model: judges real-1, invents "fake-99" out of thin air, silently skips real-2.
    fake_content = json.dumps(
        [
            {"id": "real-1", "decision": "keep", "relevance_score": 0.9, "reason": "Matches JD."},
            {
                "id": "fake-99",
                "decision": "keep",
                "relevance_score": 1.0,
                "reason": "Invented item.",
            },
        ]
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.decision_engine.get_chat_openai",
        lambda **kwargs: _FakeLLM(fake_content),
    )

    decisions = score_experience_items(
        jd_title="Backend Engineer",
        jd_required_skills=["Python"],
        jd_keywords=[],
        items=items,
    )

    by_id = {d.item_id: d for d in decisions}
    assert set(by_id) == {"real-1", "real-2"}, "hallucinated id must never appear in output"
    assert by_id["real-1"].decision == "keep"
    assert by_id["real-1"].reason == "Matches JD."
    # real-2 was never ruled on by the model — must fail closed to "keep", not vanish.
    assert by_id["real-2"].decision == "keep"
    assert by_id["real-2"].relevance_score == 0.0


def test_drop_without_reason_is_rejected(monkeypatch) -> None:
    items = [ExperienceItem(id="real-1", text="Unrelated skill", source="test")]
    # Model tries to drop an item without giving a human-readable reason.
    fake_content = json.dumps(
        [
            {"id": "real-1", "decision": "drop", "relevance_score": 0.0, "reason": ""},
        ]
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.decision_engine.get_chat_openai",
        lambda **kwargs: _FakeLLM(fake_content),
    )

    decisions = score_experience_items(
        jd_title="Backend Engineer",
        jd_required_skills=["Python"],
        jd_keywords=[],
        items=items,
    )

    # The reasonless "drop" is rejected outright; the item still needs a
    # ruling, so it fails closed to "keep" rather than disappearing.
    assert len(decisions) == 1
    assert decisions[0].decision == "keep"
