"""Unit tests for Claude Desktop handoff helpers (no live GUI)."""

from __future__ import annotations

from unittest.mock import patch

from app.modules.resume_workspace.claude_desktop import goto_claude_desktop


def test_goto_claude_rejects_empty_jd():
    result = goto_claude_desktop("   ")
    assert result["ok"] is False
    assert result["error"] == "empty_jd"


def test_goto_claude_macos_only_on_non_darwin():
    with patch("app.modules.resume_workspace.claude_desktop.platform.system", return_value="Linux"):
        result = goto_claude_desktop("Some JD text")
    assert result["ok"] is False
    assert result["error"] == "macos_only"


def test_goto_claude_happy_path_with_project_id(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        "app.modules.resume_workspace.claude_desktop.platform.system",
        lambda: "Darwin",
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.claude_desktop.set_clipboard",
        lambda text: calls.append(f"clip:{len(text)}"),
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.claude_desktop.activate_claude",
        lambda **_: calls.append("activate"),
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.claude_desktop.open_project_deep_link",
        lambda pid: calls.append(f"deeplink:{pid}"),
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.claude_desktop._click_pinned_project",
        lambda name, **kw: calls.append(f"pin:{name}") or {
            "ok": True,
            "step": "locate_project",
            "method": "heuristic",
            "click": {"x": 100, "y": 300},
        },
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.claude_desktop._composer_point",
        lambda **kw: {"ok": True, "method": "heuristic", "x": 600.0, "y": 720.0},
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.claude_desktop._paste_and_send",
        lambda **kw: calls.append(f"paste:{kw['focus_x']}:{kw['focus_y']}:{len(kw['jd_text'])}"),
    )
    monkeypatch.setattr(
        "app.modules.resume_workspace.claude_desktop.time.sleep",
        lambda *_: None,
    )

    result = goto_claude_desktop(
        "Boeing Data Analytics Intern JD",
        project_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        project_name="Resume",
    )
    assert result["ok"] is True
    assert result["project_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert calls[0].startswith("clip:")
    assert "activate" in calls
    assert "deeplink:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in calls
    assert any(c.startswith("paste:") for c in calls)
