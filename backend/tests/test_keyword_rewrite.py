"""Phase 2b keyword rewrite — mechanical intensity-escalation guard.

No live LLM call (see tests/test_llm_failover.py for network smoke tests).
Fakes the model response to prove the *code* rejects an escalated rewrite
("participated in" -> "led") rather than trusting the model not to inflate.
"""

from __future__ import annotations

from app.modules.resume_workspace.keyword_rewrite import rewrite_bullet


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, _messages):
        return _FakeResponse(self._content)


def test_escalated_rewrite_is_rejected_and_original_kept(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.resume_workspace.keyword_rewrite.get_chat_openai",
        lambda **kwargs: _FakeLLM("Led the FastAPI backend migration end to end."),
    )

    result = rewrite_bullet(
        bullet_text="Participated in the FastAPI backend migration.",
        jd_required_skills=["FastAPI"],
        jd_keywords=["backend", "migration"],
    )

    assert result.applied is False
    assert result.reject_reason is not None
    assert result.rewritten == result.original  # never silently apply the escalation


def test_swapped_named_component_is_rejected_and_original_kept(monkeypatch) -> None:
    # Regression test for a real failure found during dogfooding on 2026-08-07:
    # the model kept the ownership level unchanged (no escalation) but silently
    # renamed a specific real component into an unrelated JD buzzword — "Evidence
    # Guard module" (fact-checking) became "data cleaning module", and "FastAPI"
    # was swapped for generic "Python". The intensity-tier guard alone does not
    # catch this; it's a distinct failure mode (factual substitution, not
    # escalation) and needs its own check.
    original = (
        "Built an AI job-application agent (FastAPI, LangGraph, Next.js) that tailors "
        "resumes via RAG over user experience embeddings in Chroma, with an independent "
        "Evidence Guard module rejecting unsupported claims"
    )
    hallucinated_rewrite = (
        "Built an AI job-application agent (Python, LangGraph, Next.js) that tailors "
        "resumes via RAG data pipelines over user experience embeddings in Chroma, with "
        "an independent data cleaning module rejecting unsupported claims"
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.keyword_rewrite.get_chat_openai",
        lambda **kwargs: _FakeLLM(hallucinated_rewrite),
    )

    result = rewrite_bullet(
        bullet_text=original,
        jd_required_skills=["Python", "SQL"],
        jd_keywords=["data cleaning", "data pipelines"],
    )

    assert result.applied is False
    assert "Evidence Guard" in result.reject_reason
    assert result.rewritten == result.original  # never silently apply the substitution


def test_same_tier_rewrite_is_applied(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.resume_workspace.keyword_rewrite.get_chat_openai",
        lambda **kwargs: _FakeLLM("Built the FastAPI backend service used for order processing."),
    )

    result = rewrite_bullet(
        bullet_text="Developed the backend service used for order processing.",
        jd_required_skills=["FastAPI"],
        jd_keywords=["backend"],
    )

    assert result.applied is True
    assert result.rewritten != result.original
    assert result.keyword_score_after >= result.keyword_score_before
