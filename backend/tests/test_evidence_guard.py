import pytest

from app.modules.resume_tailor.nodes.evidence_guard import EvidenceGuardNode


@pytest.mark.asyncio
async def test_evidence_guard_flags_unsupported_metrics() -> None:
    guard = EvidenceGuardNode()

    result = await guard.verify(
        original_resume={"experiences": [{"bullets": ["Built API integrations for internal reporting."]}]},
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
        original_resume={"experiences": [{"bullets": ["Reduced API latency by 40% using FastAPI caching."]}]},
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
