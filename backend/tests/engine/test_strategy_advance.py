"""Unit tests for multi-step advance + upload instruction shaping."""

from __future__ import annotations

from pathlib import Path

from app.modules.form_fill_engine.schemas import DOMSnapshot, InteractiveElement
from app.modules.form_fill_engine.strategies._common import build_fill_then_advance_or_pause

FIXTURES = Path(__file__).parent / "fixtures"
RESUME = FIXTURES / "sample_resume.pdf"

PROFILE = {
    "first_name": "A",
    "last_name": "B",
    "email": "a@b.com",
    "phone": "1",
    "linkedin": "https://linkedin.com/in/x",
    "work_authorized": "Yes",
    "resume_path": str(RESUME.resolve()),
}


def test_advance_when_next_present():
    snap = DOMSnapshot(
        url="https://acme.myworkdayjobs.com/job",
        page_title="Apply",
        frame_count=1,
        elements=[
            InteractiveElement(index=0, tag="input", element_type="text", label="First Name"),
            InteractiveElement(index=1, tag="input", element_type="email", label="Email"),
            InteractiveElement(index=2, tag="button", element_type="button", label="Next"),
        ],
    )
    instr = build_fill_then_advance_or_pause(snap, PROFILE, ats_label="T")
    actions = [i.action for i in instr]
    assert "fill" in actions
    assert "click" in actions
    assert "wait" in actions
    assert "pause_for_human" not in actions


def test_pause_when_no_next():
    snap = DOMSnapshot(
        url="https://boards.greenhouse.io/x/jobs/1",
        page_title="Apply",
        elements=[
            InteractiveElement(index=0, tag="input", element_type="email", label="Email"),
            InteractiveElement(index=1, tag="input", element_type="file", label="Resume/CV"),
            InteractiveElement(index=2, tag="button", element_type="submit", label="Submit Application"),
        ],
    )
    instr = build_fill_then_advance_or_pause(snap, PROFILE, ats_label="T")
    assert any(i.action == "upload_file" for i in instr)
    upload = next(i for i in instr if i.action == "upload_file")
    assert upload.requires_confirmation is False  # file exists
    assert any(i.action == "pause_for_human" for i in instr)


def test_iframe_elements_carry_frame_index():
    snap = DOMSnapshot(
        url="file:///shell.html",
        frame_count=2,
        elements=[
            InteractiveElement(
                index=0,
                tag="input",
                element_type="text",
                label="First Name",
                frame_index=1,
                in_iframe=True,
            ),
            InteractiveElement(
                index=1,
                tag="button",
                label="Next",
                frame_index=1,
                in_iframe=True,
            ),
        ],
    )
    instr = build_fill_then_advance_or_pause(snap, PROFILE)
    fill = next(i for i in instr if i.action == "fill")
    assert fill.element_index == 0
