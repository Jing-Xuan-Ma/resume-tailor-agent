"""Tests for resume content diff / highlight paths."""

from app.modules.resume_workspace.diff import compute_resume_diff


def test_diff_marks_changed_and_unchanged_bullets():
    before = {
        "summary": "Same summary",
        "skills_certifications": "Python, SQL",
        "experiences": [
            {
                "company": "Acme",
                "title": "DA",
                "bullets": [{"text": "Kept bullet"}, {"text": "Old wording"}],
            }
        ],
        "projects": [{"name": "Proj A", "bullets": [{"text": "Old project"}]}],
    }
    after = {
        "summary": "Same summary",
        "skills_certifications": "Python, SQL, Tableau",
        "experiences": [
            {
                "company": "Acme",
                "title": "DA",
                "bullets": [{"text": "Kept bullet"}, {"text": "New wording"}],
            }
        ],
        "projects": [{"name": "Proj A", "bullets": [{"text": "Old project"}]}],
        "hidden_entries": [{"kind": "project", "key": "Other"}],
    }
    delta = compute_resume_diff(before, after)
    paths = {c["path"] for c in delta["changes"]}
    assert "skills_certifications" in paths
    assert "experiences[0].bullets[1]" in paths
    assert "summary" not in paths
    assert "summary" in delta["unchanged_paths"]
    assert "experiences[0].bullets[0]" in delta["unchanged_paths"]
    assert delta["hidden_entries"]
    assert delta["change_count"] >= 2
