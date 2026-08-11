"""Module A glue: Phase 2b bullet rewriting + gap analysis, wired against
whatever entries project_for_jd (Phase 2a) actually kept — no assumption
about how many experiences/projects/bullets exist.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.modules.resume_workspace.keyword_rewrite import rewrite_bullet, rewrite_bullets_batch

log = logging.getLogger(__name__)


def rewrite_kept_bullets(
    entries: list[dict[str, Any]],
    *,
    jd_required_skills: list[str],
    jd_keywords: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Sync path (tests/scripts): rewrite each bullet sequentially."""
    trace: list[dict[str, Any]] = []
    out_entries: list[dict[str, Any]] = []
    for entry in entries:
        new_entry = dict(entry)
        bullets = list(entry.get("bullets") or [])
        new_bullets = []
        for b in bullets:
            if not isinstance(b, dict):
                new_bullets.append(b)
                continue
            original_text = str(b.get("text") or "")
            bullet_id = (
                b.get("evidence_from")
                or f"{entry.get('company') or entry.get('name')}::{original_text[:24]}"
            )
            if not original_text:
                new_bullets.append(b)
                continue
            result = rewrite_bullet(
                bullet_text=original_text,
                jd_required_skills=jd_required_skills,
                jd_keywords=jd_keywords,
            )
            new_b = dict(b)
            if result.applied:
                new_b["text"] = result.rewritten
                new_b.setdefault("original_text", original_text)
                trace.append(
                    {
                        "bullet_id": bullet_id,
                        "source": "resume_original",
                        "detail": "rewritten to align with JD terminology",
                        "applied": True,
                    }
                )
            else:
                new_b["text"] = original_text
                trace.append(
                    {
                        "bullet_id": bullet_id,
                        "source": "resume_original",
                        "detail": result.reject_reason or "rewrite rejected, original kept",
                        "applied": False,
                    }
                )
            new_bullets.append(new_b)
        new_entry["bullets"] = new_bullets
        out_entries.append(new_entry)
    return out_entries, trace


async def rewrite_kept_sections_async(
    sections: dict[str, list[dict[str, Any]]],
    *,
    jd_required_skills: list[str],
    jd_keywords: list[str],
    model: str | None = None,
    provider: str | None = None,
) -> dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    """Rewrite kept bullets with one LLM batch per resume module, in parallel.

    Modules (experiences / projects / competitions / …) are rewritten concurrently
    so wall time ≈ slowest module, not the sum of all modules.
    """
    # section -> list of (bid, text, ei, bi)
    per_section: dict[str, list[tuple[str, str, int, int]]] = {}
    snapshots: dict[str, list[dict[str, Any]]] = {}

    for section, entries in sections.items():
        entry_snapshots: list[dict[str, Any]] = []
        collected: list[tuple[str, str, int, int]] = []
        for ei, entry in enumerate(entries or []):
            new_entry = dict(entry)
            bullets = list(entry.get("bullets") or [])
            new_bullets: list[Any] = []
            for bi, b in enumerate(bullets):
                if not isinstance(b, dict):
                    new_bullets.append(b)
                    continue
                original_text = str(b.get("text") or "")
                entry_label = entry.get("company") or entry.get("name")
                bullet_id = str(
                    b.get("evidence_from")
                    or f"{section}:{entry_label}::{ei}:{bi}:{original_text[:24]}"
                )
                new_b = dict(b)
                new_bullets.append(new_b)
                if original_text:
                    collected.append((bullet_id, original_text, ei, bi))
            new_entry["bullets"] = new_bullets
            entry_snapshots.append(new_entry)
        snapshots[section] = entry_snapshots
        per_section[section] = collected

    async def _rewrite_one_module(
        section: str,
        items: list[tuple[str, str, int, int]],
    ) -> tuple[str, dict[str, Any], int]:
        t0 = asyncio.get_running_loop().time()
        if not items:
            return section, {}, 0
        results = await rewrite_bullets_batch(
            bullets=[(bid, text) for bid, text, _ei, _bi in items],
            jd_required_skills=jd_required_skills,
            jd_keywords=jd_keywords,
            model=model,
            provider=provider,
            section=section,
        )
        elapsed_ms = int((asyncio.get_running_loop().time() - t0) * 1000)
        return section, results, elapsed_ms

    module_jobs = [_rewrite_one_module(section, items) for section, items in per_section.items()]
    gathered = await asyncio.gather(*module_jobs, return_exceptions=True)

    results_by_section: dict[str, dict[str, Any]] = {s: {} for s in sections}
    module_timings: dict[str, int] = {}
    for item in gathered:
        if isinstance(item, BaseException):
            log.warning("module rewrite gather failed: %s", item)
            continue
        section, results, elapsed_ms = item
        results_by_section[section] = results
        module_timings[section] = elapsed_ms
    if module_timings:
        log.info("parallel module rewrite timings_ms=%s", module_timings)

    traces: dict[str, list[dict[str, Any]]] = {s: [] for s in sections}
    for section, items in per_section.items():
        results = results_by_section.get(section) or {}
        for bullet_id, original_text, ei, bi in items:
            result = results.get(bullet_id)
            new_b = snapshots[section][ei]["bullets"][bi]
            if result and getattr(result, "applied", False):
                new_b["text"] = result.rewritten
                new_b.setdefault("original_text", original_text)
                traces[section].append(
                    {
                        "bullet_id": bullet_id,
                        "module": section,
                        "source": "resume_original",
                        "detail": "rewritten to align with JD terminology",
                        "applied": True,
                    }
                )
            else:
                new_b["text"] = original_text
                traces[section].append(
                    {
                        "bullet_id": bullet_id,
                        "module": section,
                        "source": "resume_original",
                        "detail": (getattr(result, "reject_reason", None) if result else None)
                        or "rewrite rejected, original kept",
                        "applied": False,
                    }
                )

    return {section: (snapshots[section], traces[section]) for section in sections}


def _resume_text_blob(resume: dict[str, Any]) -> str:
    parts = [str(resume.get("summary") or ""), str(resume.get("skills_certifications") or "")]
    for section in ("experiences", "projects", "competitions"):
        for entry in resume.get(section) or []:
            if not isinstance(entry, dict):
                continue
            parts.append(str(entry.get("title") or ""))
            parts.append(str(entry.get("name") or ""))
            for b in entry.get("bullets") or []:
                if isinstance(b, dict):
                    parts.append(str(b.get("text") or ""))
    return " ".join(parts).lower()


def build_gap_analysis(
    *,
    tailored_resume: dict[str, Any],
    jd_text: str,
    jd_required_skills: list[str],
    jd_keywords: list[str],
) -> dict[str, Any]:
    """Missing/well-covered keywords, each traceable back to literal JD text.

    A keyword only ever lands in `missing_keywords`/`well_covered` if it is a
    literal substring of `jd_text` (case-insensitive) — never a term the LLM
    invented while parsing skills/keywords, since that parsing step itself
    can hallucinate a plausible-sounding skill that isn't actually in the JD.
    """
    jd_lower = (jd_text or "").lower()
    resume_blob = _resume_text_blob(tailored_resume)

    candidates = []
    seen: set[str] = set()
    for kw in list(jd_required_skills or []) + list(jd_keywords or []):
        kw_clean = str(kw or "").strip()
        key = kw_clean.lower()
        if not kw_clean or key in seen:
            continue
        seen.add(key)
        candidates.append(kw_clean)

    missing: list[str] = []
    covered: list[str] = []
    for kw in candidates:
        kw_l = kw.lower()
        if kw_l not in jd_lower:
            continue
        if kw_l in resume_blob:
            covered.append(kw)
        else:
            missing.append(kw)

    if missing:
        message = (
            "This JD mentions "
            + ", ".join(missing[:8])
            + (" (and more)" if len(missing) > 8 else "")
            + " which your current inventory doesn't show evidence for. "
            "These stay off the resume — no fabricated experience — but you can add real "
            "evidence for any of them (a project, a course, a GitHub repo) and they'll be "
            "considered next time."
        )
    else:
        message = "Your tailored resume already covers the JD's key terms found in your inventory."

    return {
        "missing_keywords": missing,
        "well_covered": covered,
        "message_for_chat_panel": message,
    }
