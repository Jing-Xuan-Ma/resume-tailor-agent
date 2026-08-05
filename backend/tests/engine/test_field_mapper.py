"""Field mapper Tier 1 rule coverage for common profile fields."""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.form_fill_engine.field_mapper import map_all_fields, map_field
from app.modules.form_fill_engine.schemas import DOMSnapshot, InteractiveElement

FIXTURES = Path(__file__).parent / "fixtures"

SAMPLE_PROFILE = {
    "first_name": "Jingxuan",
    "last_name": "Ma",
    "full_name": "Jingxuan Ma",
    "email": "jma107@jh.edu",
    "phone": "+1 (410) 240-4366",
    "linkedin": "https://linkedin.com/in/example",
    "location": "Baltimore, MD",
    "work_authorized": "Yes",
    "needs_sponsorship": "Yes",
    "resume_path": "D:/tmp/resume.pdf",
}


def test_map_common_fields_rules():
    cases = [
        ("First Name", "first_name", "Jingxuan"),
        ("Last Name", "last_name", "Ma"),
        ("Email Address", "email", "jma107@jh.edu"),
        ("Phone Number", "phone", "+1 (410) 240-4366"),
        ("LinkedIn Profile", "linkedin", "https://linkedin.com/in/example"),
        ("E-mail", "email", "jma107@jh.edu"),
        ("Mobile", "phone", "+1 (410) 240-4366"),
    ]
    for i, (label, key, value) in enumerate(cases):
        el = InteractiveElement(index=i, tag="input", element_type="text", label=label)
        result = map_field(el, SAMPLE_PROFILE)
        assert result.match_method == "rule", label
        assert result.matched_profile_key == key, label
        assert result.value_to_fill == value, label
        assert result.confidence >= 0.9


def test_map_workday_fixture():
    data = json.loads((FIXTURES / "workday_sample.json").read_text(encoding="utf-8"))
    snap = DOMSnapshot.model_validate(data)
    mappings = map_all_fields(snap.elements, SAMPLE_PROFILE)
    by_label = {
        next(e.label for e in snap.elements if e.index == m.element_index): m
        for m in mappings
        if m.value_to_fill
    }
    assert by_label["First Name"].matched_profile_key == "first_name"
    assert by_label["Email Address"].value_to_fill == SAMPLE_PROFILE["email"]
    assert by_label["Phone Number"].matched_profile_key == "phone"


def test_unmatched_returns_empty():
    el = InteractiveElement(index=0, tag="input", element_type="text", label="Favorite color")
    result = map_field(el, SAMPLE_PROFILE)
    assert result.match_method in {"unmatched", "semantic"}
    if result.match_method == "unmatched":
        assert result.value_to_fill is None
