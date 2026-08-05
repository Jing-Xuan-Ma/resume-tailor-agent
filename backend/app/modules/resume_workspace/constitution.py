"""Load RESUME_CONSTITUTION.md for prompts and Tailor UI."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CONSTITUTION_PATH = _REPO_ROOT / "RESUME_CONSTITUTION.md"

# Compact rules shown on Tailor page + injected into short LLM system prompts.
UI_RULES: list[dict[str, str]] = [
    {
        "id": "no-fabricate",
        "title": "No fabrication",
        "detail": "Never invent employers, titles, dates, degrees, tools, projects, metrics, or certificates.",
    },
    {
        "id": "evidence",
        "title": "Evidence chain",
        "detail": "Every bullet must trace to Master Inventory or a user-confirmed fact.",
    },
    {
        "id": "format-lock",
        "title": "Content only, format locked",
        "detail": "Keep master DOCX styles/layout; LLM edits content slots only.",
    },
    {
        "id": "one-page",
        "title": "One page hard limit",
        "detail": "Fit by showing/hiding overlapping entries — never shrink fonts or margins.",
    },
    {
        "id": "honest-gaps",
        "title": "Honest gaps",
        "detail": "Missing skills stay missing; adjacent experience may show transfer, not fake direct experience.",
    },
    {
        "id": "confirm",
        "title": "Confirm before final",
        "detail": "Final save to data/final_resumes/ only after you click Confirm.",
    },
]

MASTER_TEMPLATE_LABEL = "Jingxuan_Resume_Data Analyst.docx (read-only master)"


@lru_cache(maxsize=1)
def constitution_text() -> str:
    try:
        return _CONSTITUTION_PATH.read_text(encoding="utf-8")
    except OSError:
        return (
            "# Resume Constitution (fallback)\n"
            "No fabrication. Evidence chain. Format lock. One page. "
            "Honest gaps. User confirm before final save.\n"
        )


def constitution_for_llm(*, max_chars: int = 12000) -> str:
    text = constitution_text().strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 80].rstrip() + "\n\n[…truncated — full file is RESUME_CONSTITUTION.md]"


def constitution_system_block() -> str:
    """Short block always prepended to resume-related LLM system prompts."""
    bullets = "\n".join(f"- **{r['title']}**: {r['detail']}" for r in UI_RULES)
    return (
        "Canonical policy: RESUME_CONSTITUTION.md (wins on any conflict).\n"
        f"Master template: {MASTER_TEMPLATE_LABEL}.\n"
        f"Absolute rules:\n{bullets}\n"
        "ATS-hostile glyphs forbidden (no → • ★ etc.). Prefer ASCII separators.\n"
    )


def constitution_api_payload() -> dict:
    return {
        "version": "v1",
        "source": "RESUME_CONSTITUTION.md",
        "master_template": MASTER_TEMPLATE_LABEL,
        "track": "Data Analyst / Analytics",
        "rules": UI_RULES,
        "full_text": constitution_text(),
    }
