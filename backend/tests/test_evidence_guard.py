import json

import pytest

from app.modules.resume_core.evidence_guard import EvidenceGuardNode


@pytest.mark.asyncio
async def test_evidence_guard_flags_unsupported_metrics() -> None:
    guard = EvidenceGuardNode()

    result = await guard.verify(
        original_resume={
            "experiences": [{"bullets": ["Built API integrations for internal reporting."]}]
        },
        tailored_resume={
            "experiences": [
                {
                    "bullets": [
                        {
                            "text": "Built API integrations and increased revenue by 95%.",
                            "evidence_from": "exp-1",
                        }
                    ]
                }
            ]
        },
    )

    assert result["passed"] is False
    assert any("unsupported metric" in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_evidence_guard_passes_supported_claims() -> None:
    guard = EvidenceGuardNode()

    result = await guard.verify(
        original_resume={
            "experiences": [{"bullets": ["Reduced API latency by 40% using FastAPI caching."]}]
        },
        tailored_resume={
            "experiences": [
                {
                    "bullets": [
                        {
                            "text": "Reduced API latency by 40% using FastAPI caching.",
                            "evidence_from": "exp-1",
                            "original_text": "Reduced API latency by 40% using FastAPI caching.",
                        }
                    ]
                }
            ]
        },
    )

    assert result["passed"] is True


# ---------------------------------------------------------------------------
# Phase 2d: mocked LLM-layer tests (no live network call).
#
# The two tests above hit a real LLM and are the project's existing live
# smoke coverage for this module. These additions instead fake the model's
# response to prove the *code* — not the model's good behavior on any given
# day — is what enforces zero-fabrication: a claim the model forgets to rule
# on fails closed rather than silently passing, and a bounded retry recovers
# from one transient bad response instead of needlessly blocking a clean
# resume. Both gaps were found and fixed during real dogfooding (see
# DEVLOG.md, 2026-08-07 Phase 2d entry).
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def ainvoke(self, _messages):
        if not self._responses:
            raise RuntimeError("no more fake responses queued")
        return _FakeResponse(self._responses.pop(0))


def _guard_with_fake_llm(responses: list[str]) -> EvidenceGuardNode:
    guard = EvidenceGuardNode()
    guard._llm = _FakeLLM(responses)  # bypass _get_llm(), which would build a real client
    return guard


_MOCK_ORIGINAL = {
    "experiences": [{"company": "Acme", "bullets": ["Built a backend service in Python."]}]
}


def _mock_tailored(claim_text: str) -> dict:
    return {
        "experiences": [
            {
                "company": "Acme",
                "bullets": [
                    {
                        "text": claim_text,
                        "evidence_from": "acme-1",
                        "original_text": "Built a backend service in Python.",
                    },
                ],
            }
        ]
    }


@pytest.mark.asyncio
async def test_claim_missing_from_findings_fails_closed_not_passes() -> None:
    # Model returns a well-formed response but never rules on id=0 at all,
    # on both the initial attempt and the retry.
    empty_findings = json.dumps({"passed": True, "findings": []})
    guard = _guard_with_fake_llm([empty_findings, empty_findings])

    result = await guard.verify(
        _MOCK_ORIGINAL, _mock_tailored("Built a backend service in Python.")
    )

    assert result["passed"] is False
    assert any("did not return a verdict" in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_retry_recovers_from_one_bad_response() -> None:
    # First attempt: malformed/truncated JSON. Second attempt: complete and clean.
    good = json.dumps({
        "passed": True,
        "findings": [{"id": "0", "classification": "SUPPORTED", "claim": "x"}],
    })
    guard = _guard_with_fake_llm(["{not valid json", good])

    result = await guard.verify(
        _MOCK_ORIGINAL, _mock_tailored("Built a backend service in Python.")
    )

    assert result["passed"] is True
    assert result["issues"] == []


@pytest.mark.asyncio
async def test_llm_fabricated_verdict_fails_the_claim() -> None:
    fabricated_response = json.dumps({
        "passed": False,
        "findings": [{"id": "0", "classification": "FABRICATED", "claim": "x"}],
    })
    guard = _guard_with_fake_llm([fabricated_response])

    result = await guard.verify(
        _MOCK_ORIGINAL,
        _mock_tailored("Led a 12-person team to renegotiate the company's entire cloud contract."),
    )

    assert result["passed"] is False
    assert any("FABRICATED" in issue for issue in result["issues"])
