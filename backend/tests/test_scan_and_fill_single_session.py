"""Single-session scan+fill should not cold-start Chromium twice."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.modules.application_engine.browser_session import BrowserSession
from app.modules.ats_connectors.sandbox import sandbox_uri_for


def test_scan_and_fill_pause_launches_browser_once(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.ENABLE_BROWSER_FILL_PAUSE", True)
    monkeypatch.setattr("app.config.settings.ENABLE_BROWSER_AUTOMATION", False)
    monkeypatch.setattr("app.config.settings.BROWSER_HEADLESS", True)
    monkeypatch.setattr("app.config.settings.BROWSER_TIMEOUT_MS", 5000)

    uri = sandbox_uri_for("greenhouse")
    assert uri, "greenhouse sandbox fixture missing"

    launches = {"n": 0}
    real_session = BrowserSession()

    class CountingBrowser:
        def new_page(self):
            page = MagicMock()
            page.goto = MagicMock()
            page.frames = []
            page.main_frame = MagicMock()
            page.locator = MagicMock(
                return_value=MagicMock(
                    first=MagicMock(
                        count=MagicMock(return_value=0),
                        inner_text=MagicMock(return_value=""),
                    )
                )
            )
            page.screenshot = MagicMock()
            return page

        def close(self):
            return None

    class FakePlaywright:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def chromium(self):
            return self

        def launch(self, **kwargs):
            launches["n"] += 1
            return CountingBrowser()

    def fake_sync_playwright():
        return FakePlaywright()

    with patch(
        "playwright.sync_api.sync_playwright",
        fake_sync_playwright,
    ), patch(
        "app.modules.ats_connectors.dom_scan.scan_page_fields",
        return_value=[
            {
                "field_id": "f1",
                "type": "email",
                "label": "Email",
                "name": "email",
                "selector": "input[name=email]",
                "frame_index": 0,
            }
        ],
    ):
        out = real_session.scan_and_fill_pause(
            url=uri,
            build_plan=lambda fields: [
                {
                    "field_id": "f1",
                    "profile_key": "email",
                    "value": "a@b.com",
                    "action": "fill",
                    "confidence": 0.95,
                    "tier": "auto",
                    "label": "Email",
                    "selector": "input[name=email]",
                    "frame_index": 0,
                    "needs_review": False,
                }
            ],
            screenshot_path=str(
                Path(__file__).resolve().parents[2]
                / "artifacts"
                / "funnel"
                / "auto-apply-v2"
                / "_tmp_single_session.png"
            ),
            sandbox=True,
            ats_type="greenhouse",
        )

    assert launches["n"] == 1
    assert out.get("single_session") is True
    assert out.get("paused_before_submit") is True
    assert out.get("submitted") is False
    assert out.get("status") == "filled_paused_before_submit"
