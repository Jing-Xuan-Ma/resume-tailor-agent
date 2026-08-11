"""Parses an uploaded .docx resume into the structural skeleton consumed by the
tailoring agent (module A.3 `resume_structure`): sections -> entries -> bullets,
with stable ids and no assumptions about how many of anything a resume has.

Section titles that don't match a known canonical type (and aren't covered by a
user's previously confirmed mapping) are reported back as `unmapped_sections`
instead of being silently guessed at — the caller decides what to do with them
(surface a confirmation prompt, fold into "other", etc).
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

# Canonical section type -> title phrases that should map to it. Matching is
# case-insensitive against the whole paragraph text after stripping punctuation.
CANONICAL_SECTIONS: dict[str, list[str]] = {
    "professional_experience": [
        "professional experience",
        "work experience",
        "experience",
        "employment history",
        "employment",
        "work history",
    ],
    "projects": ["projects", "personal projects", "academic projects", "project experience"],
    "education": ["education", "academic background"],
    "skills": [
        "skills",
        "skills & certifications",
        "skills and certifications",
        "technical skills",
        "core competencies",
    ],
    "competitions": ["competitions", "awards", "honors", "honors & awards", "leadership"],
    "summary": ["summary", "professional summary", "objective"],
}

_DATE_RANGE_RE = re.compile(
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{4})"
    r"\s*[-–—to]+\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}|\d{4}|present|current)",
    re.IGNORECASE,
)
_BULLET_PREFIX_RE = re.compile(r"^[•‣◦⁃∙\-\*•‣o]\s+")
_PAST_TENSE_RE = re.compile(r"^\w+ed\b", re.IGNORECASE)
_ING_RE = re.compile(r"^\w+ing\b", re.IGNORECASE)
# Common irregular past-tense resume verbs that don't end in -ed.
_IRREGULAR_PAST_VERBS = {
    "built",
    "led",
    "sold",
    "wrote",
    "spoke",
    "taught",
    "brought",
    "bought",
    "caught",
    "sought",
    "thought",
    "chose",
    "drove",
    "grew",
    "ran",
    "sent",
    "spent",
    "won",
    "wound",
    "spun",
    "spread",
    "set",
    "cut",
    "put",
    "read",
    "held",
    "kept",
    "left",
    "met",
    "paid",
    "sat",
    "stood",
    "sped",
    "shot",
    "shrank",
    "sang",
    "sank",
    "began",
    "broke",
    "drew",
    "gave",
    "found",
    "froze",
    "made",
    "rose",
    "saw",
    "took",
    "understood",
    "went",
}


def _normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9& ]", "", text.strip().lower()).strip()


def _match_canonical_section(heading_text: str, custom_mappings: dict[str, str]) -> str | None:
    norm = _normalize_title(heading_text)
    if not norm:
        return None
    key = heading_text.strip().lower()
    if key in custom_mappings:
        return custom_mappings[key]
    for section_type, phrases in CANONICAL_SECTIONS.items():
        if norm in phrases:
            return section_type
    return None


def _is_bullet_paragraph(paragraph: Any) -> bool:
    text = paragraph.text.strip()
    if _BULLET_PREFIX_RE.match(text):
        return True
    style_name = (paragraph.style.name or "") if paragraph.style else ""
    if "bullet" in style_name.lower() or "list" in style_name.lower():
        return True
    try:
        num_pr = paragraph._p.pPr.numPr  # noqa: SLF001 — python-docx has no public API for this
        return num_pr is not None
    except AttributeError:
        return False


def _is_heading_paragraph(paragraph: Any) -> bool:
    """Section headers only (e.g. "PROFESSIONAL EXPERIENCE") — not entry-level
    headings like a bolded job title/company line, which are Title Case and
    must fall through to the entry-heading path instead."""
    text = paragraph.text.strip()
    if not text or len(text) > 60:
        return False
    style_name = (paragraph.style.name or "") if paragraph.style else ""
    if "heading" in style_name.lower() or "title" in style_name.lower():
        return True
    runs = [r for r in paragraph.runs if r.text.strip()]
    if runs and all(r.bold for r in runs) and text.isupper():
        return True
    return False


def _strip_bullet_prefix(text: str) -> str:
    return _BULLET_PREFIX_RE.sub("", text).strip()


def _detect_verb_tense(bullet_text: str) -> str:
    first_word_match = re.match(r"^[A-Za-z]+", bullet_text)
    if not first_word_match:
        return "present"
    first_word = first_word_match.group(0)
    if _PAST_TENSE_RE.match(first_word) or first_word.lower() in _IRREGULAR_PAST_VERBS:
        return "past"
    if _ING_RE.match(first_word):
        return "present_participle"
    return "present"


def _extract_date_range(line: str) -> str | None:
    match = _DATE_RANGE_RE.search(line)
    return match.group(0) if match else None


def _split_heading_lines(lines: list[str]) -> dict[str, str]:
    """Best-effort split of an entry's non-bullet heading lines into
    title/company/date_range. Never invents values — only extracts what a
    date regex or a ' | '/' - ' separator on the raw text actually contains."""
    entry: dict[str, str] = {"title": "", "company": "", "date_range": ""}
    remaining: list[str] = []
    for line in lines:
        date_range = _extract_date_range(line)
        if date_range and not entry["date_range"]:
            entry["date_range"] = date_range
            residue = line.replace(date_range, "").strip(" |,-–—")
            if residue:
                remaining.append(residue)
        else:
            remaining.append(line)

    if remaining:
        first = remaining[0]
        parts = re.split(r"\s*\|\s*|\s+-\s+", first, maxsplit=1)
        if len(parts) == 2:
            entry["title"], entry["company"] = parts[0].strip(), parts[1].strip()
        else:
            entry["title"] = first.strip()
            if len(remaining) > 1:
                entry["company"] = remaining[1].strip()
    return entry


def parse_resume_structure(
    docx_bytes: bytes, custom_mappings: dict[str, str] | None = None
) -> dict[str, Any]:
    """Returns {"sections": [...], "unmapped_sections": [...]}.

    `custom_mappings` is {normalized raw title (lowercased): canonical section
    type}, typically the caller's previously confirmed decisions so the same
    non-standard heading doesn't need re-confirming on every upload.
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("python-docx is required for resume structure parsing") from exc

    mappings = custom_mappings or {}
    doc = Document(BytesIO(docx_bytes))

    sections: list[dict[str, Any]] = []
    unmapped_sections: list[dict[str, Any]] = []
    seen_unmapped_titles: set[str] = set()

    current_section: dict[str, Any] | None = None
    current_entry: dict[str, Any] | None = None
    pending_heading_lines: list[str] = []
    entry_counter = 0
    bullet_counter = 0

    def _flush_entry() -> None:
        nonlocal current_entry, pending_heading_lines
        if current_section is None:
            pending_heading_lines = []
            return
        if pending_heading_lines:
            entry_id = f"exp_{entry_counter}"
            fields = _split_heading_lines(pending_heading_lines)
            current_entry = {
                "id": entry_id,
                "title": fields["title"],
                "company": fields["company"],
                "date_range": fields["date_range"],
                "bullets": [],
            }
            current_section["entries"].append(current_entry)
        pending_heading_lines = []

    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        if _is_heading_paragraph(paragraph):
            section_type = _match_canonical_section(text, mappings)
            _flush_entry()
            current_entry = None
            if section_type is None:
                key = text.strip().lower()
                if key not in seen_unmapped_titles:
                    seen_unmapped_titles.add(key)
                    unmapped_sections.append({"raw_title": text})
                current_section = None
                continue
            current_section = {"type": section_type, "raw_title": text, "entries": []}
            sections.append(current_section)
            continue

        if current_section is None:
            # Content before any recognized section header — nothing to attach it to.
            continue

        if _is_bullet_paragraph(paragraph):
            _flush_entry()
            if current_entry is None:
                entry_counter += 1
                current_entry = {
                    "id": f"exp_{entry_counter}",
                    "title": "",
                    "company": "",
                    "date_range": "",
                    "bullets": [],
                }
                current_section["entries"].append(current_entry)
            bullet_counter += 1
            bullet_text = _strip_bullet_prefix(text)
            current_entry["bullets"].append(
                {
                    "id": f"b{bullet_counter}",
                    "text": bullet_text,
                    "verb_tense": _detect_verb_tense(bullet_text),
                }
            )
            continue

        # Non-bullet content line inside a section: part of an entry heading.
        if current_entry is not None and current_entry["bullets"]:
            # A previous entry already has bullets — this line starts a new entry.
            current_entry = None
        if not pending_heading_lines:
            entry_counter += 1
        pending_heading_lines.append(text)
        if _extract_date_range(text) is not None:
            # A date range completes an entry's heading block for sections that
            # have no bullets at all (e.g. Education) — flush so the next
            # heading line starts a new entry instead of merging into this one.
            # current_entry is left pointing at the just-flushed entry (not
            # reset to None) so that bullets which follow the heading in
            # bulleted sections still attach to it instead of a fresh one.
            _flush_entry()

    _flush_entry()

    return {"sections": sections, "unmapped_sections": unmapped_sections}
