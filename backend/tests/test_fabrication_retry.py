"""Phase 2d: a flagged claim goes back through Phase 2a's decision engine
(logged, accountable) instead of being silently deleted."""

from __future__ import annotations

import json

from app.modules.resume_workspace import fabrication_retry as fr


def test_extract_flagged_claim_texts_dedupes_same_claim_from_two_guard_layers() -> None:
    issues = [
        "experiences: claim adds unsupported metric(s) 95% : Increased revenue by 95%.",
        "experiences: llm_fact_check FABRICATED claim: Increased revenue by 95%.",
    ]
    claims = fr.extract_flagged_claim_texts(issues)
    assert claims == ["Increased revenue by 95%."]


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


async def test_flagged_claim_never_silently_survives_as_keep(monkeypatch) -> None:
    # Even if Phase 2a's own re-scoring says "keep" (e.g. it's topically
    # relevant to the JD), a claim the evidence guard already rejected must
    # come back as "drop" — the guard's rejection is final, not a suggestion.
    fake_decision = json.dumps(
        [
            {
                "id": "flagged-0",
                "decision": "keep",
                "relevance_score": 0.9,
                "reason": "Very relevant to the JD.",
            },
        ]
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.decision_engine.get_chat_openai",
        lambda **kwargs: _FakeLLM(fake_decision),
    )

    decisions = await fr.rerun_flagged_claims_through_phase_2a(
        flagged_claim_texts=["Increased revenue by 95%."],
        jd_title="Backend Engineer",
        jd_required_skills=["Python"],
        jd_keywords=[],
    )

    assert len(decisions) == 1
    assert decisions[0].decision == "drop"
    assert "证据核查已标记" in decisions[0].reason


def test_no_flagged_claims_returns_empty_without_calling_decision_engine() -> None:
    import asyncio

    decisions = asyncio.run(
        fr.rerun_flagged_claims_through_phase_2a(
            flagged_claim_texts=[],
            jd_title="x",
            jd_required_skills=[],
            jd_keywords=[],
        )
    )
    assert decisions == []
