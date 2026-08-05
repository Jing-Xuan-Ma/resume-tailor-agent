"""Apply field editor helpers + profile persist (Step 5 P0/P1)."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.modules.profile import library_service as lib

client = TestClient(app)


def test_library_upsert_persists_portfolio_and_answers():
    user_id = str(uuid4())
    seeded = lib.get_or_seed_library(user_id)
    apply = dict(seeded.get("apply") or {})
    apply["portfolio_url"] = "https://example.com/portfolio"
    answers = dict(apply.get("answers") or {})
    answers["cover_letter"] = "I am excited about this Data Analyst role."
    apply["answers"] = answers
    apply["work_authorized"] = True

    saved = lib.update_library(user_id, apply_profile=apply)
    got = saved.get("apply") or {}
    assert got.get("portfolio_url") == "https://example.com/portfolio"
    assert (got.get("answers") or {}).get("cover_letter", "").startswith("I am excited")
    assert got.get("work_authorized") is True

    # API surface
    res = client.put(
        f"/api/v1/profile/{user_id}/library",
        json={"apply": {**got, "github_url": "https://github.com/demo"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["apply"]["github_url"] == "https://github.com/demo"
    assert body["apply"]["portfolio_url"] == "https://example.com/portfolio"


def test_field_mapper_tiers_still_available():
    from app.modules.ats_connectors.field_mapper import CONF_AUTO, CONF_REVIEW

    assert CONF_AUTO == 0.85
    assert CONF_REVIEW == 0.5
