"""Phase 2c: enforce a strict one-page resume via content trimming, never
font/margin/line-spacing shrinking.

Renders the actual DOCX -> PDF (LibreOffice headless) and measures the real
page count, not a character-count heuristic. If the render comes out over
one page, drops the single lowest-relevance experience/project/competition
entry and retries, logging every round. Font size, line spacing, and margins
live in the master template's locked style shell (see format_lock.py) and
are never touched here -- that would be exactly the "缩字号/压行距逃避问题"
the plan forbids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

import pdfplumber

from app.modules.resume_workspace.format_lock import compare_fingerprints, fingerprint_docx
from app.modules.resume_workspace.master_inject import inject_content
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor

_MAX_TRIM_ROUNDS = 5


@dataclass
class OnePageResult:
    ok: bool
    docx_bytes: bytes | None
    pdf_bytes: bytes | None
    page_count: int | None
    trim_log: list[str] = field(default_factory=list)
    fingerprint_check: dict[str, Any] | None = None
    error: str | None = None
    # The resume dict actually used for the last render attempt — after any
    # trim rounds, this reflects what really survived (fewer entries than the
    # caller passed in, if trimming happened). Callers should sync their own
    # in-memory resume/UI state to this rather than the pre-trim input.
    final_resume: dict[str, Any] | None = None


def _pdf_page_count(pdf_bytes: bytes) -> int:
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        return len(pdf.pages)


def _entry_key(section: str, item: dict[str, Any]) -> str:
    if section == "experiences":
        return f"{item.get('company')}|{item.get('title')}"
    return str(item.get("name") or item)


def _droppable_entries(resume: dict[str, Any]) -> list[tuple[str, str]]:
    """(section, key) pairs still safe to cut, lowest-priority first.

    Education, summary, and the skills line are never touched here, and at
    least one experience always survives. When entries carry a
    `_relevance_score` (set by quality_gate.project_for_jd's JD-relevance
    ranking), the globally lowest-scoring entry is cut first regardless of
    section — no fixed "competitions always go before projects" assumption.
    Without scores (e.g. called on a resume that skipped project_for_jd),
    falls back to competitions -> projects -> experiences[1:] as a generic,
    least-essential-first default.
    """
    scored: list[tuple[str, str, float]] = []
    for c in resume.get("competitions") or []:
        scored.append(("competitions", _entry_key("competitions", c), c.get("_relevance_score")))
    for p in resume.get("projects") or []:
        scored.append(("projects", _entry_key("projects", p), p.get("_relevance_score")))
    experiences = resume.get("experiences") or []
    for e in experiences[1:]:
        scored.append(("experiences", _entry_key("experiences", e), e.get("_relevance_score")))

    if scored and all(s is not None for _, _, s in scored):
        scored.sort(key=lambda row: row[2])
        return [(section, key) for section, key, _score in scored]
    return [(section, key) for section, key, _score in scored]


def _drop_entry(resume: dict[str, Any], section: str, key: str) -> dict[str, Any]:
    trimmed = dict(resume)
    items = list(resume.get(section) or [])
    kept = [it for it in items if _entry_key(section, it) != key]
    trimmed[section] = kept
    hidden = list(resume.get("hidden_entries") or [])
    hidden.append({"kind": section.rstrip("s"), "key": key, "reason": "one_page_trim"})
    trimmed["hidden_entries"] = hidden
    return trimmed


def enforce_one_page(
    *,
    master_docx: bytes,
    resume: dict[str, Any],
    master_inventory: dict[str, Any],
) -> OnePageResult:
    trim_log: list[str] = []
    current = dict(resume)

    for round_num in range(_MAX_TRIM_ROUNDS + 1):
        try:
            docx_bytes = inject_content(master_docx, current, master_inventory)
        except Exception as exc:  # noqa: BLE001 - surfaced to caller via error field
            trim_log.append(f"round {round_num}: OOXML injection failed: {exc}")
            return OnePageResult(
                ok=False,
                docx_bytes=None,
                pdf_bytes=None,
                page_count=None,
                trim_log=trim_log,
                error=f"inject_failed: {exc}",
            )
        try:
            pdf_bytes = ResumeTemplateEditor.convert_to_pdf_via_libreoffice(docx_bytes)
        except Exception as exc:  # noqa: BLE001 - surfaced to caller via error field
            trim_log.append(f"round {round_num}: PDF render failed: {exc}")
            return OnePageResult(
                ok=False,
                docx_bytes=docx_bytes,
                pdf_bytes=None,
                page_count=None,
                trim_log=trim_log,
                error=f"pdf_render_failed: {exc}",
            )
        page_count = _pdf_page_count(pdf_bytes)
        trim_log.append(f"round {round_num}: rendered {page_count} page(s)")

        if page_count <= 1:
            fingerprint_check = compare_fingerprints(
                fingerprint_docx(master_docx), fingerprint_docx(docx_bytes)
            )
            return OnePageResult(
                ok=True,
                docx_bytes=docx_bytes,
                pdf_bytes=pdf_bytes,
                page_count=page_count,
                trim_log=trim_log,
                fingerprint_check=fingerprint_check,
                final_resume=current,
            )

        droppable = _droppable_entries(current)
        if not droppable:
            trim_log.append(
                "no more droppable entries (competitions/projects/experiences exhausted); "
                "refusing to shrink font/margins to force-fit — needs human review"
            )
            return OnePageResult(
                ok=False,
                docx_bytes=docx_bytes,
                pdf_bytes=pdf_bytes,
                page_count=page_count,
                trim_log=trim_log,
                error="exceeds_one_page_no_more_content_to_trim",
                final_resume=current,
            )
        section, key = droppable[0]
        trim_log.append(
            f"round {round_num}: {page_count} pages > 1 — dropping lowest-relevance "
            f"entry [{section}] {key}"
        )
        current = _drop_entry(current, section, key)

    trim_log.append(f"exceeded max trim rounds ({_MAX_TRIM_ROUNDS}) without reaching one page")
    return OnePageResult(
        ok=False,
        docx_bytes=None,
        pdf_bytes=None,
        page_count=None,
        trim_log=trim_log,
        final_resume=current,
        error="max_trim_rounds_exceeded",
    )
