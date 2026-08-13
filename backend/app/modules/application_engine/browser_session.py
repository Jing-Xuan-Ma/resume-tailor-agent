"""Browser apply is no longer in-process Playwright.

Use ghost-driver-mcp + `.agents/skills/jobright-apply` in the Agent chat.
This class stays as a dry-run boundary so planners/connectors keep compiling.
"""

from __future__ import annotations

from typing import Any


_MOVED = (
    "Browser apply moved to Agent chat "
    "(.agents/skills/jobright-apply + ghost-driver-mcp). Never auto-click Submit."
)


class BrowserSession:
    mode = "agent_mcp"

    def open(self, url: str | None) -> dict:
        return {"mode": self.mode, "url": url, "opened": False, "message": _MOVED}

    def submit(self, **kwargs: Any) -> dict:
        return {
            "submitted": False,
            "status": "moved_to_agent_mcp",
            "paused_before_submit": True,
            "message": _MOVED,
        }

    def fill_and_pause(self, **kwargs: Any) -> dict:
        return self.submit(**kwargs)

    def scan_and_fill_pause(self, **kwargs: Any) -> dict:
        return self.submit(**kwargs)

    def fill_form_pause(self, **kwargs: Any) -> dict:
        return self.submit(**kwargs)

    def apply_and_autofill_resume(self, **kwargs: Any) -> dict:
        return self.submit(**kwargs)

    def create_or_sign_in(self, **kwargs: Any) -> dict:
        return self.submit(**kwargs)

    def _click_apply(self, page: Any) -> bool:  # noqa: ARG002
        return False

    def _launch_browser(self, _playwright: Any) -> Any:  # noqa: ARG002
        raise RuntimeError(_MOVED)
