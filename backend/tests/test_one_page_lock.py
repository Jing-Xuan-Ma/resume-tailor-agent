"""Phase 2c one-page enforcement — trim-order and fail-closed guarantees.

No LibreOffice call here (see the dogfood run for real rendering evidence,
logged in DEVLOG.md / devlog/evidence/). This fakes the render step to prove
the *trim loop* behaves correctly: competitions drop before projects before
experiences, at least one experience always survives, and running out of
droppable content fails closed with a clear error instead of silently
shrinking fonts/margins (which this module has no code path to do at all).
"""

from __future__ import annotations

from app.modules.resume_workspace import one_page_lock as opl


def _resume_with(*, competitions=0, projects=0, experiences=1):
    return {
        "candidate_name": "Test Candidate",
        "competitions": [{"name": f"Comp{i}"} for i in range(competitions)],
        "projects": [{"name": f"Project{i}"} for i in range(projects)],
        "experiences": [{"company": f"Co{i}", "title": "Engineer"} for i in range(experiences)],
        "hidden_entries": [],
    }


def test_drops_competitions_before_projects_before_experiences(monkeypatch) -> None:
    # 1 competition, 1 project, 2 experiences -> needs 3 trims to reach 1 page.
    resume = _resume_with(competitions=1, projects=1, experiences=2)
    page_counts = iter([4, 3, 2, 1])  # one render per round; converges on round 3

    monkeypatch.setattr(opl, "inject_content", lambda master, r, inv: b"fake-docx")
    monkeypatch.setattr(
        "app.modules.resume_workspace.template_editor.ResumeTemplateEditor.convert_to_pdf_via_libreoffice",
        staticmethod(lambda docx: b"fake-pdf"),
    )
    monkeypatch.setattr(opl, "_pdf_page_count", lambda pdf: next(page_counts))
    monkeypatch.setattr(opl, "fingerprint_docx", lambda docx: {})
    monkeypatch.setattr(opl, "compare_fingerprints", lambda a, b: {"ok": True, "errors": []})

    result = opl.enforce_one_page(master_docx=b"master", resume=resume, master_inventory={})

    assert result.ok is True
    assert result.page_count == 1
    dropped_order = [line.split("entry ")[-1] for line in result.trim_log if "dropping" in line]
    expected_order = ["[competitions] Comp0", "[projects] Project0", "[experiences] Co1|Engineer"]
    assert dropped_order == expected_order
    assert len(result.trim_log) > 0  # non-silent: every round is logged


def test_never_drops_the_last_experience_and_fails_closed(monkeypatch) -> None:
    # Only 1 experience, nothing else — can never reach one page.
    resume = _resume_with(competitions=0, projects=0, experiences=1)

    monkeypatch.setattr(opl, "inject_content", lambda master, r, inv: b"fake-docx")
    monkeypatch.setattr(
        "app.modules.resume_workspace.template_editor.ResumeTemplateEditor.convert_to_pdf_via_libreoffice",
        staticmethod(lambda docx: b"fake-pdf"),
    )
    monkeypatch.setattr(opl, "_pdf_page_count", lambda pdf: 2)  # always over one page

    result = opl.enforce_one_page(master_docx=b"master", resume=resume, master_inventory={})

    assert result.ok is False
    assert result.error == "exceeds_one_page_no_more_content_to_trim"
    assert "refusing to shrink font/margins" in result.trim_log[-1]
