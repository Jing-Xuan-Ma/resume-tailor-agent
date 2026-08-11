"""Open Claude Desktop → pinned Resume project → paste JD → send.

macOS-only local automation. Prefers `claude://` deep link when
`CLAUDE_DESKTOP_PROJECT_ID` is set; otherwise uses screen-locate on a
screenshot to click the pinned project named `CLAUDE_DESKTOP_PROJECT_NAME`.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_LOCATE_SCRIPT = _REPO_ROOT / ".agents" / "skills" / "screen-locate" / "scripts" / "locate.py"

_CLAUDE_APP = "Claude"
_SEND_VIA_CMD_ENTER = True  # Claude Desktop: Cmd+Enter sends (plain Return often newlines)

# Backend processes (uvicorn under IDE/launchd) often have a stripped PATH that
# omits /usr/sbin — `screencapture` lives there. Always use absolute paths.
_SCREENCAPTURE = "/usr/sbin/screencapture"
_SIPS = "/usr/bin/sips"
_PBCOPY = "/usr/bin/pbcopy"
_OSASCRIPT = "/usr/bin/osascript"
_OPEN = "/usr/bin/open"


def _uv_bin() -> str:
    return shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    path_parts = [
        "/usr/sbin",
        "/usr/bin",
        "/bin",
        "/usr/local/bin",
        str(Path.home() / ".local" / "bin"),
        env.get("PATH", ""),
    ]
    env["PATH"] = ":".join(p for p in path_parts if p)
    return env


def _run(cmd: list[str], *, timeout: float = 30.0, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
        check=False,
        env=_subprocess_env(),
    )


def _osascript(script: str, *, timeout: float = 30.0) -> str:
    proc = _run([_OSASCRIPT], timeout=timeout, input_text=script)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"osascript_exit_{proc.returncode}")
    return (proc.stdout or "").strip()


def set_clipboard(text: str) -> None:
    proc = _run([_PBCOPY], timeout=15.0, input_text=text)
    if proc.returncode != 0:
        raise RuntimeError(f"pbcopy_failed:{(proc.stderr or '').strip()}")


def claude_installed() -> bool:
    return Path("/Applications/Claude.app").exists()


def activate_claude(*, launch_if_needed: bool = True) -> None:
    if not claude_installed():
        raise RuntimeError("claude_app_not_found:/Applications/Claude.app")
    if launch_if_needed:
        _run([_OPEN, "-a", _CLAUDE_APP], timeout=15.0)
    _osascript(
        f'''
tell application "{_CLAUDE_APP}" to activate
delay 0.35
tell application "System Events"
  tell process "{_CLAUDE_APP}"
    set frontmost to true
  end tell
end tell
'''
    )


def open_project_deep_link(project_id: str) -> None:
    pid = (project_id or "").strip()
    if not pid:
        raise ValueError("empty_project_id")
    url = f"claude://claude.ai/project/{urllib.parse.quote(pid)}"
    proc = _run([_OPEN, url], timeout=15.0)
    if proc.returncode != 0:
        raise RuntimeError(f"open_deeplink_failed:{(proc.stderr or '').strip()}")


def _claude_window_bounds() -> tuple[int, int, int, int]:
    """Return Claude window (x, y, w, h) in macOS global points."""
    out = _osascript(
        f'''
tell application "{_CLAUDE_APP}" to activate
delay 0.4
tell application "System Events"
  tell process "{_CLAUDE_APP}"
    set frontmost to true
    delay 0.2
    if (count of windows) is 0 then error "claude_no_window"
    set p to position of window 1
    set s to size of window 1
    return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
  end tell
end tell
'''
    )
    parts = [int(float(x.strip())) for x in out.split(",")]
    if len(parts) != 4 or parts[2] <= 0 or parts[3] <= 0:
        raise RuntimeError(f"bad_window_bounds:{out}")
    return parts[0], parts[1], parts[2], parts[3]


def _screenshot_region(x: int, y: int, w: int, h: int, dest: Path) -> None:
    # screencapture -R uses points; on Retina the PNG is typically 2×.
    rect = f"{x},{y},{w},{h}"
    proc = _run([_SCREENCAPTURE, "-x", "-R", rect, str(dest)], timeout=20.0)
    if proc.returncode != 0 or not dest.exists() or dest.stat().st_size < 100:
        raise RuntimeError(f"screencapture_failed:{(proc.stderr or '').strip()}")


def _image_size(path: Path) -> tuple[int, int]:
    proc = _run([_SIPS, "-g", "pixelWidth", "-g", "pixelHeight", str(path)], timeout=10.0)
    w = h = 0
    for line in (proc.stdout or "").splitlines():
        if "pixelWidth:" in line:
            w = int(line.split(":")[-1].strip())
        elif "pixelHeight:" in line:
            h = int(line.split(":")[-1].strip())
    if w <= 0 or h <= 0:
        raise RuntimeError(f"sips_bad_size:{(proc.stdout or '').strip()}")
    return w, h


def _locate(image_path: Path, instruction: str, *, timeout_s: float = 90.0) -> dict[str, Any]:
    if not _LOCATE_SCRIPT.exists():
        return {"found": False, "error": "screen_locate_script_missing"}
    cmd = [
        _uv_bin(),
        "run",
        str(_LOCATE_SCRIPT),
        "--image",
        str(image_path),
        "--instruction",
        instruction,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(_REPO_ROOT),
            check=False,
            env=_subprocess_env(),
        )
    except FileNotFoundError:
        return {"found": False, "error": "uv_not_found"}
    except subprocess.TimeoutExpired:
        return {"found": False, "error": "screen_locate_timeout"}

    stdout = (proc.stdout or "").strip()
    if not stdout:
        return {
            "found": False,
            "error": "screen_locate_empty_stdout",
            "stderr": (proc.stderr or "")[:400],
        }
    try:
        # locate.py prints pretty JSON; take last JSON object if mixed
        data = json.loads(stdout)
    except json.JSONDecodeError:
        start = stdout.find("{")
        end = stdout.rfind("}")
        if start < 0 or end <= start:
            return {"found": False, "error": "screen_locate_bad_json", "stdout": stdout[:400]}
        data = json.loads(stdout[start : end + 1])
    if not data.get("found"):
        data.setdefault("error", data.get("error") or "screen_locate_not_found")
    return data


def _click_at(x: float, y: float) -> None:
    _osascript(
        f'''
tell application "System Events"
  click at {{{int(round(x))}, {int(round(y))}}}
end tell
'''
    )


def _heuristic_composer_point(wx: int, wy: int, ww: int, wh: int) -> tuple[float, float]:
    """Main-pane composer (~lower 90%). Calibrated on 1440×900 Claude Desktop."""
    # Skip left sidebar (~260pt) and right project panel (~280pt when open).
    focus_x = wx + 260 + max(120.0, (ww - 260 - 280) * 0.45)
    focus_y = wy + wh * 0.90
    return focus_x, focus_y


def _heuristic_pin_point(wx: int, wy: int, ww: int, wh: int) -> tuple[float, float]:
    """First Pinned row (Resume). Calibrated: (150, 302) on 1440×900."""
    return wx + ww * 0.104, wy + wh * 0.336


def _composer_point(*, use_vision: bool) -> dict[str, Any]:
    wx, wy, ww, wh = _claude_window_bounds()
    if not use_vision:
        hx, hy = _heuristic_composer_point(wx, wy, ww, wh)
        return {"ok": True, "method": "heuristic", "x": hx, "y": hy}

    with tempfile.TemporaryDirectory(prefix="claude-composer-") as tmp:
        shot = Path(tmp) / "composer.png"
        _screenshot_region(wx, wy, ww, wh, shot)
        img_w, img_h = _image_size(shot)
        scale_x = img_w / float(ww)
        scale_y = img_h / float(wh)
        instruction = (
            "定位主内容区里消息输入框（占位符 Write a message / 输入消息）的中心点击坐标；"
            "不要点左侧边栏、不要点 Chat/Cowork 切换、不要点模型选择器"
        )
        located = _locate(shot, instruction, timeout_s=45.0)
        if located.get("found"):
            coords = (located.get("coordinates") or {}).get("image") or {}
            ix, iy = coords.get("x"), coords.get("y")
            if ix is not None and iy is not None:
                return {
                    "ok": True,
                    "method": "locate",
                    "x": wx + (float(ix) / scale_x),
                    "y": wy + (float(iy) / scale_y),
                    "image_coords": {"x": ix, "y": iy},
                    "locate_elapsed": located.get("elapsed_time"),
                }
        hx, hy = _heuristic_composer_point(wx, wy, ww, wh)
        return {
            "ok": True,
            "method": "heuristic",
            "x": hx,
            "y": hy,
            "locate_error": located.get("error"),
        }


def _paste_and_send(*, focus_x: float, focus_y: float, jd_text: str) -> None:
    """Focus composer, re-assert clipboard, paste, then send (Cmd+Enter)."""
    set_clipboard(jd_text)
    cx, cy = int(round(focus_x)), int(round(focus_y))
    send_key = (
        "keystroke return using {command down}"
        if _SEND_VIA_CMD_ENTER
        else "keystroke return"
    )
    _osascript(
        f'''
tell application "{_CLAUDE_APP}" to activate
delay 0.35
tell application "System Events"
  tell process "{_CLAUDE_APP}"
    set frontmost to true
  end tell
  delay 0.15
  click at {{{cx}, {cy}}}
  delay 0.25
  click at {{{cx}, {cy}}}
  delay 0.3
  keystroke "a" using {{command down}}
  delay 0.1
  keystroke "v" using {{command down}}
  delay 0.45
  {send_key}
end tell
'''
    )


def _click_pinned_project(project_name: str, *, use_vision: bool) -> dict[str, Any]:
    wx, wy, ww, wh = _claude_window_bounds()
    if not use_vision:
        sx, sy = _heuristic_pin_point(wx, wy, ww, wh)
        _click_at(sx, sy)
        time.sleep(0.9)
        return {
            "ok": True,
            "step": "locate_project",
            "method": "heuristic",
            "click": {"x": sx, "y": sy},
            "window": {"x": wx, "y": wy, "w": ww, "h": wh},
            "project_name": project_name,
        }

    with tempfile.TemporaryDirectory(prefix="claude-goto-") as tmp:
        shot = Path(tmp) / "claude.png"
        _screenshot_region(wx, wy, ww, wh, shot)
        img_w, img_h = _image_size(shot)
        scale_x = img_w / float(ww)
        scale_y = img_h / float(wh)
        instruction = (
            f"在左侧边栏 Pinned / 置顶列表中，定位名为 {project_name} 的 Project 条目"
            "的中心点击坐标（不要点 Recents 里的同名聊天）"
        )
        located = _locate(shot, instruction, timeout_s=45.0)
        if not located.get("found"):
            # Fall back to heuristic rather than failing the whole handoff.
            sx, sy = _heuristic_pin_point(wx, wy, ww, wh)
            _click_at(sx, sy)
            time.sleep(0.9)
            return {
                "ok": True,
                "step": "locate_project",
                "method": "heuristic_fallback",
                "click": {"x": sx, "y": sy},
                "locate_error": located.get("error"),
                "window": {"x": wx, "y": wy, "w": ww, "h": wh},
            }
        coords = (located.get("coordinates") or {}).get("image") or {}
        ix, iy = coords.get("x"), coords.get("y")
        if ix is None or iy is None:
            sx, sy = _heuristic_pin_point(wx, wy, ww, wh)
        else:
            sx = wx + (float(ix) / scale_x)
            sy = wy + (float(iy) / scale_y)
        _click_at(sx, sy)
        time.sleep(0.9)
        return {
            "ok": True,
            "step": "locate_project",
            "method": "locate",
            "click": {"x": sx, "y": sy},
            "image_coords": {"x": ix, "y": iy},
            "window": {"x": wx, "y": wy, "w": ww, "h": wh},
            "scale": {"x": scale_x, "y": scale_y},
            "locate_elapsed": located.get("elapsed_time"),
        }


def _goto_claude_desktop_impl(
    jd_text: str,
    *,
    project_name: str | None = None,
    project_id: str | None = None,
    auto_send: bool = True,
) -> dict[str, Any]:
    """Copy JD, open Claude Desktop on the Resume project, paste, optionally send."""
    if platform.system() != "Darwin":
        return {"ok": False, "error": "macos_only"}

    text = (jd_text or "").strip()
    if not text:
        return {"ok": False, "error": "empty_jd"}

    name = (project_name or settings.CLAUDE_DESKTOP_PROJECT_NAME or "Resume").strip() or "Resume"
    pid = (project_id if project_id is not None else settings.CLAUDE_DESKTOP_PROJECT_ID or "").strip()
    use_vision = bool(settings.CLAUDE_DESKTOP_USE_VISION)

    steps: list[dict[str, Any]] = []
    try:
        set_clipboard(text)
        steps.append({"step": "clipboard", "ok": True, "chars": len(text)})

        activate_claude(launch_if_needed=True)
        steps.append({"step": "activate", "ok": True, "use_vision": use_vision})

        if pid:
            open_project_deep_link(pid)
            time.sleep(1.2)
            steps.append({"step": "deeplink", "ok": True, "project_id": pid})
        else:
            located = _click_pinned_project(name, use_vision=use_vision)
            steps.append(located)
            if not located.get("ok"):
                return {
                    "ok": False,
                    "error": located.get("error") or "locate_project_failed",
                    "project_name": name,
                    "hint": (
                        "Set CLAUDE_DESKTOP_PROJECT_ID in backend/.env to the UUID from "
                        "https://claude.ai/project/<uuid>. Default path uses heuristics "
                        "(no screenshot); set CLAUDE_DESKTOP_USE_VISION=true only if needed."
                    ),
                    "steps": steps,
                }

        time.sleep(0.6)
        activate_claude(launch_if_needed=False)

        composer = _composer_point(use_vision=use_vision)
        steps.append({"step": "locate_composer", **composer})
        focus_x = float(composer["x"])
        focus_y = float(composer["y"])

        if auto_send:
            _paste_and_send(focus_x=focus_x, focus_y=focus_y, jd_text=text)
            steps.append(
                {
                    "step": "paste_send",
                    "ok": True,
                    "focus": {"x": focus_x, "y": focus_y},
                    "send": "cmd_enter" if _SEND_VIA_CMD_ENTER else "return",
                }
            )
        else:
            set_clipboard(text)
            _click_at(focus_x, focus_y)
            time.sleep(0.25)
            _osascript('tell application "System Events" to keystroke "v" using {command down}')
            steps.append({"step": "paste_only", "ok": True, "focus": {"x": focus_x, "y": focus_y}})

        return {
            "ok": True,
            "project_name": name,
            "project_id": pid or None,
            "chars": len(text),
            "steps": steps,
        }
    except Exception as exc:  # noqa: BLE001 - surface to API
        log.exception("goto_claude_desktop failed")
        return {"ok": False, "error": str(exc), "project_name": name, "steps": steps}


def goto_claude_desktop(
    jd_text: str,
    *,
    project_name: str | None = None,
    project_id: str | None = None,
    auto_send: bool = True,
) -> dict[str, Any]:
    """Public entry with a hard timeout so the HTTP request cannot stay pending forever."""
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeout

    timeout_s = max(15, int(settings.CLAUDE_DESKTOP_TIMEOUT_S or 75))
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(
            _goto_claude_desktop_impl,
            jd_text,
            project_name=project_name,
            project_id=project_id,
            auto_send=auto_send,
        )
        try:
            return fut.result(timeout=timeout_s)
        except FuturesTimeout:
            return {
                "ok": False,
                "project_name": project_name or settings.CLAUDE_DESKTOP_PROJECT_NAME or "Resume",
                "error": f"timeout_after_{timeout_s}s",
                "hint": (
                    "Handoff exceeded timeout (often Screen Recording permission dialog or "
                    "slow vision). Default is heuristic mode — restart backend after pull. "
                    "Prefer CLAUDE_DESKTOP_PROJECT_ID for a fast deep link. "
                    "JD should already be on the clipboard."
                ),
                "steps": [],
            }
