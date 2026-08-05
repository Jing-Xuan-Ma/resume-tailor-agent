"""Tests for Profile agent tools + location regex / custom_fields."""

from uuid import uuid4

from app.modules.profile import library_service as lib
from app.modules.resume_workspace.agent_tools import AgentToolContext, match_inventory_to_jd
from app.modules.resume_workspace.service import ResumeWorkspaceService


def test_regex_saves_chinese_address_with_fullwidth_colon():
    svc = ResumeWorkspaceService()
    patch = svc._regex_profile_patch(
        "这是我的住址：3700 N Charles Street, Baltimore, MD 21218"
    )
    assert patch["apply"]["location"].startswith("3700 N Charles Street")
    assert "Baltimore" in patch["apply"]["location"]


def test_patch_library_location_and_custom_fields():
    user_id = str(uuid4())
    lib.get_or_seed_library(user_id)
    result = lib.patch_library(
        user_id,
        apply_patch={
            "location": "3700 N Charles Street, Baltimore, MD 21218",
            "custom_fields": {"mailing_note": "Apt near campus"},
        },
    )
    assert "location" in result["changed_apply"]
    assert "custom_fields" in result["changed_apply"]
    apply = lib.get_apply_profile(user_id)
    assert apply["location"].startswith("3700")
    assert (apply.get("custom_fields") or {}).get("mailing_note") == "Apt near campus"


def test_add_inventory_item_via_tool_context():
    user_id = str(uuid4())
    lib.get_or_seed_library(user_id)
    ctx = AgentToolContext(
        user_id=user_id,
        session_id="sess-test",
        workspace=None,
    )
    out = ctx.add_inventory_item(
        "experience",
        {
            "company": "Test Co",
            "title": "Data Analyst Intern",
            "location": "Remote",
            "date_range": "2024",
            "bullets": [{"text": "Built SQL dashboards", "evidence_from": "user_stated"}],
        },
    )
    assert '"ok": true' in out.replace(" ", "").lower() or '"ok":true' in out.replace(" ", "").lower()
    inv = lib.get_master_inventory(user_id)
    companies = [e.get("company") for e in (inv.get("experiences") or [])]
    assert "Test Co" in companies
    assert ctx.state.profile_updated is True


def test_match_inventory_to_jd_scores_sql():
    inv = lib.default_inventory()
    match = match_inventory_to_jd(inv, "Looking for a Data Analyst with strong SQL and Tableau skills.")
    assert match["has_jd"] is True
    assert isinstance(match["top_experiences"], list)
    assert "honest_gaps" in match
