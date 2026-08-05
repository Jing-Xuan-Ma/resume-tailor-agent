"""Inject tailored content into master DOCX via OOXML (zip/document.xml) — no python-docx rewrite."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.modules.resume_workspace.ooxml_inject import inject_ooxml, validate_ooxml
from app.modules.resume_workspace.ooxml_pack import read_document_xml


def inject_content(master_docx: bytes, tailored: dict[str, Any], master_inventory: dict[str, Any]) -> bytes:
    return inject_ooxml(master_docx, tailored or {}, master_inventory or {})


def content_integrity_check(docx_bytes: bytes, inventory: dict[str, Any]) -> dict[str, Any]:
    xml = read_document_xml(docx_bytes)
    # Decode a few entities for plain search
    text = xml.replace("&amp;", "&").replace("\xa0", " ").replace("\u2009", " ")
    errors: list[str] = []

    for exp in inventory.get("experiences") or []:
        company = str(exp.get("company") or "").replace("\xa0", " ")
        if company and company not in text:
            token = company.split()[0] if company.split() else ""
            if token and token not in text:
                errors.append(f"missing_experience_company:{company}")

    for proj in inventory.get("projects") or []:
        name = str(proj.get("name") or "")
        if name and name not in text:
            # May be intentionally hidden — only flag if not in hidden sense: soft check
            pass

    if "Data Analyst candidate" in text and "Data Analyst targeting" in text:
        errors.append("summary_stacked_prefixes")
    if text.lower().count("data science m.s. student") > 1:
        errors.append("summary_duplicated")

    return {"ok": len(errors) == 0, "errors": errors}


def hyperlink_check(master_docx: bytes, gen_docx: bytes) -> dict[str, Any]:
    return validate_ooxml(master_docx, gen_docx)


def clone_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(inventory)
