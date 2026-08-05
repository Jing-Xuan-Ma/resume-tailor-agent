"""DOCX format fingerprint + comparison for RG format lock (OOXML shell, not content length)."""

from __future__ import annotations

import hashlib
import re
from io import BytesIO
from typing import Any
from zipfile import ZipFile

SHELL_PARTS = (
    "word/styles.xml",
    "word/numbering.xml",
    "word/settings.xml",
    "word/fontTable.xml",
    "word/theme/theme1.xml",
)


def fingerprint_docx(docx_bytes: bytes) -> dict[str, Any]:
    with ZipFile(BytesIO(docx_bytes)) as z:
        names = set(z.namelist())
        shell = {}
        for part in SHELL_PARTS:
            if part in names:
                shell[part] = hashlib.sha256(z.read(part)).hexdigest()[:16]
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        rels = ""
        if "word/_rels/document.xml.rels" in names:
            rels = z.read("word/_rels/document.xml.rels").decode("utf-8", errors="ignore")

    headings = re.findall(
        r"<w:t[^>]*>((?:EDUCATION|PROFESSIONAL EXPERIENCE|PROJECTS|COMPETITIONS|SKILLS &amp; CERTIFICATIONS|SKILLS & CERTIFICATIONS))</w:t>",
        xml,
    )
    headings = [h.replace("&amp;", "&").upper() for h in headings]
    hyperlinks = len(re.findall(r"<w:hyperlink", xml))
    ext = len(re.findall(r'TargetMode="External"', rels))
    pg_mar = re.findall(r"<w:pgMar[^/]*/>", xml)
    pg_sz = re.findall(r"<w:pgSz[^/]*/>", xml)
    return {
        "shell": shell,
        "heading_labels": headings,
        "hyperlinks": hyperlinks,
        "external_rels": ext,
        "pgMar": pg_mar,
        "pgSz": pg_sz,
        "paragraph_count": len(re.findall(r"<w:p[ >]", xml)),
    }


def compare_fingerprints(master: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    # Shell parts (styles/numbering/theme/…) must be byte-identical
    ms, gs = master.get("shell") or {}, generated.get("shell") or {}
    for part, hv in ms.items():
        if gs.get(part) != hv:
            errors.append(f"shell_changed:{part}")

    if master.get("pgMar") != generated.get("pgMar"):
        errors.append("page_margins_changed")
    if master.get("pgSz") != generated.get("pgSz"):
        errors.append("page_size_changed")

    if generated.get("hyperlinks", 0) < master.get("hyperlinks", 0):
        errors.append(f"hyperlinks {master.get('hyperlinks')}->{generated.get('hyperlinks')}")
    if generated.get("external_rels", 0) < master.get("external_rels", 0):
        errors.append(f"external_rels {master.get('external_rels')}->{generated.get('external_rels')}")

    required = {"EDUCATION", "PROFESSIONAL EXPERIENCE", "PROJECTS", "SKILLS & CERTIFICATIONS"}
    gen_heads = set(generated.get("heading_labels") or [])
    missing = required - gen_heads
    if missing:
        errors.append(f"missing_headings {sorted(missing)}")

    # Paragraph count may drop when hiding entries. Small growth can happen when
    # carving a new experience and swapping a project (spacer differences) — warn only.
    mp = master.get("paragraph_count", 0)
    gp = generated.get("paragraph_count", 0)
    if gp > mp + 2:
        errors.append(f"paragraph_count_grew {mp}->{gp}")
    elif gp > mp:
        warnings.append(f"paragraph_count_grew {mp}->{gp} (carve/swap spacer)")
    elif gp < mp:
        warnings.append(f"paragraph_count_shrunk {mp}->{gp} (hide ok)")

    score = 10
    score -= min(8, len(errors) * 2)
    score -= min(2, len(warnings))
    return {
        "ok": len(errors) == 0,
        "score": max(0, score),
        "errors": errors,
        "warnings": warnings,
    }
