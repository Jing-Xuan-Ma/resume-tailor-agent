"""Regression: merge_runs must not treat <w:tab/> as <w:t> or drop right-align tabs."""

from __future__ import annotations

from app.modules.resume_workspace.ooxml_merge_runs import (
    _T_RE,
    _run_text,
    merge_runs_in_document,
    merge_runs_in_paragraph,
)
from app.modules.resume_workspace.master_template import ensure_master_template_bytes
from app.modules.resume_workspace.ooxml_pack import read_document_xml
from app.modules.resume_workspace.master_inject import inject_content


DEGREE_RUN_WITH_TAB = (
    '<w:r><w:rPr><w:sz w:val="20"/></w:rPr>'
    '<w:t xml:space="preserve"> </w:t><w:tab/><w:t>Baltimore, US</w:t></w:r>'
)


def test_t_re_does_not_match_w_tab():
    """<w:tab/> starts with the characters <w:t — the text regex must not match it."""
    matches = list(_T_RE.finditer(DEGREE_RUN_WITH_TAB))
    assert [m.group(2) for m in matches] == [" ", "Baltimore, US"]
    assert _run_text(DEGREE_RUN_WITH_TAB) == " Baltimore, US"


def test_merge_preserves_tab_inside_run():
    p = (
        '<w:p><w:pPr><w:tabs><w:tab w:val="right" w:pos="11338"/></w:tabs>'
        '<w:jc w:val="both"/></w:pPr>'
        '<w:r><w:rPr><w:sz w:val="20"/></w:rPr>'
        '<w:t xml:space="preserve">Master of Science in </w:t></w:r>'
        '<w:r><w:rPr><w:sz w:val="20"/><w:rFonts w:hint="eastAsia"/></w:rPr>'
        "<w:t>Data Science</w:t></w:r>"
        f"{DEGREE_RUN_WITH_TAB}</w:p>"
    )
    out = merge_runs_in_paragraph(p)
    assert "<w:tab/>" in out
    assert "&lt;w:t&gt;" not in out
    assert "Baltimore, US" in out


def test_master_inject_keeps_education_degree_tabs():
    master = ensure_master_template_bytes()
    assert master, "master template missing"
    # Minimal tailored pass-through: inject still runs merge_runs first.
    inventory = {
        "summary": "",
        "education": [],
        "experiences": [],
        "projects": [],
        "skills": "",
    }
    tailored = dict(inventory)
    out = inject_content(master, tailored, inventory)
    xml = read_document_xml(out)
    master_xml = read_document_xml(master)
    # Run-level tabs (self-closing) must survive inject/merge — pPr tab defs alone are not enough.
    assert xml.count("<w:tab/>") == master_xml.count("<w:tab/>")
    assert xml.count("<w:tab/>") >= 2
    assert "&lt;w:t&gt;" not in xml
    assert "Baltimore, US" in xml
    assert "Cork, Ireland" in xml
    # Spot-check Master degree paragraph still has tab immediately before location text.
    assert "<w:tab/><w:t>Baltimore, US</w:t>" in xml or "> </w:t><w:tab/><w:t>Baltimore, US</w:t>" in xml
    # merge_runs_in_document alone must be idempotent on tab preservation
    merged = merge_runs_in_document(master_xml)
    assert merged.count("<w:tab/>") == master_xml.count("<w:tab/>")
