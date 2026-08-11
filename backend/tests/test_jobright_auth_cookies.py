"""Jobright Cookie-Editor / storage_state helpers for live Original Job Post nav."""

from __future__ import annotations

from app.modules.shopping_cart.jobright_nav import cookie_editor_to_playwright, load_jobright_auth


def test_cookie_editor_to_playwright_same_site_and_expires() -> None:
    raw = [
        {
            "domain": ".jobright.ai",
            "name": "SESSION_ID",
            "value": "abc",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "lax",
            "expirationDate": 1791188745.6,
        },
        {
            "domain": ".jobright.ai",
            "name": "x",
            "value": "1",
            "sameSite": "no_restriction",
            "secure": True,
        },
    ]
    out = cookie_editor_to_playwright(raw)
    assert out[0]["sameSite"] == "Lax"
    assert out[0]["expires"] == 1791188745.6
    assert out[0]["httpOnly"] is True
    assert out[1]["sameSite"] == "None"


def test_load_jobright_auth_finds_repo_data_files() -> None:
    auth = load_jobright_auth()
    # Local session files may or may not exist in CI; shape must be stable.
    assert set(auth) >= {"storage_state", "cookies_path", "cookies", "source"}
    assert isinstance(auth["cookies"], list)
