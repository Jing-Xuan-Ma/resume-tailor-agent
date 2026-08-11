"""Solve graphical CAPTCHAs via the screen-locate (UI-TARS) skill.

Prefer **one screenshot → locate all click targets (including Confirm) →
click in order**. Re-shot only as fallback when a required point is missing.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_LOCATE_SCRIPT = _REPO_ROOT / ".agents" / "skills" / "screen-locate" / "scripts" / "locate.py"

# TikTok / similar: select 2 same-shape objects, then Confirm.
_DEFAULT_TARGET_INSTRUCTIONS = [
    "在验证码弹窗的图片区域里，定位两个相同形状物体中的第一个，返回其中心点击坐标",
    "在验证码弹窗的图片区域里，定位两个相同形状物体中的第二个（另一个相同形状），返回其中心点击坐标",
]
_DEFAULT_CONFIRM_INSTRUCTION = "在验证码弹窗底部定位 Confirm / 确认 / 输入确认 按钮的中心点击坐标"

# Inter-click gaps (ms). Keep short — UI only needs a frame or two to register selection.
_GAP_BETWEEN_TARGETS_MS = 120
_GAP_BEFORE_CONFIRM_MS = 180
_GAP_AFTER_CONFIRM_MS = 400


def locate_on_image(
    image_path: str | Path,
    instruction: str,
    *,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """Run screen-locate; return parsed JSON (found + coordinates.image)."""
    script = _LOCATE_SCRIPT
    if not script.exists():
        return {
            "found": False,
            "error": "screen_locate_script_missing",
            "path": str(script),
        }
    cmd = [
        "uv",
        "run",
        str(script),
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
            "exit_code": proc.returncode,
            "stderr": (proc.stderr or "")[:500],
        }
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        try:
            start = stdout.rfind("{")
            data = json.loads(stdout[start:]) if start >= 0 else None
            if data is None:
                raise json.JSONDecodeError("no object", stdout, 0)
        except json.JSONDecodeError:
            return {
                "found": False,
                "error": "screen_locate_bad_json",
                "exit_code": proc.returncode,
                "stdout_tail": stdout[-400],
                "stderr": (proc.stderr or "")[:400],
            }
    if proc.returncode != 0 and not data.get("found"):
        data.setdefault("error", f"screen_locate_exit_{proc.returncode}")
    if data.get("success") is False and not data.get("found"):
        data.setdefault("error", data.get("error") or "screen_locate_api_failed")
    data["instruction"] = instruction
    return data


def locate_many_on_image(
    image_path: str | Path,
    instructions: list[str],
    *,
    timeout_s: float = 60.0,
    parallel: bool = True,
) -> list[dict[str, Any]]:
    """Locate multiple targets against the **same** screenshot.

    Runs one screen-locate call per instruction (optionally in parallel),
    all reading ``image_path`` — no extra screenshots.
    """
    if not instructions:
        return []
    if not parallel or len(instructions) == 1:
        return [locate_on_image(image_path, instr, timeout_s=timeout_s) for instr in instructions]

    results: list[dict[str, Any] | None] = [None] * len(instructions)

    def _job(idx: int, instr: str) -> tuple[int, dict[str, Any]]:
        return idx, locate_on_image(image_path, instr, timeout_s=timeout_s)

    with ThreadPoolExecutor(max_workers=min(4, len(instructions))) as pool:
        futs = [pool.submit(_job, i, instr) for i, instr in enumerate(instructions)]
        for fut in as_completed(futs):
            idx, data = fut.result()
            results[idx] = data
    return [r or {"found": False, "error": "locate_failed"} for r in results]


def _image_xy(located: dict[str, Any]) -> tuple[float, float] | None:
    if not located.get("found"):
        return None
    coords = ((located.get("coordinates") or {}).get("image")) or {}
    x, y = coords.get("x"), coords.get("y")
    if x is None or y is None:
        return None
    return float(x), float(y)


def click_image_point(
    page, x: float, y: float, *, viewport_css: tuple[int, int] | None = None
) -> None:
    """Click using screenshot pixel coords mapped onto the Playwright viewport.

    Assumes the screenshot was taken of the full viewport at DPR=1 style
    (Playwright ``page.screenshot`` default is CSS pixels for viewport shots).
    """
    del viewport_css  # reserved for future DPR mapping
    page.mouse.click(float(x), float(y))


def _captcha_image_still_loading(page) -> bool:
    """True when the shape challenge pane shows Loading… (nothing to locate yet)."""
    try:
        # Shape CAPTCHA modal present but image not ready.
        if page.get_by_text(re.compile(r"Select\s+2\s+objects", re.I)).count() == 0:
            return False
        # Visible "Loading..." inside the challenge (not page chrome).
        loc = page.get_by_text(re.compile(r"^\s*Loading\.{0,3}\s*$", re.I))
        if loc.count() and loc.first.is_visible():
            return True
        body = (page.inner_text("body") or "").lower()
        # Modal instruction present + loading token near captcha UI.
        if "select 2 objects" in body and "loading" in body:
            # Prefer the short token; avoid matching unrelated page strings.
            return bool(re.search(r"loading\.{0,3}", body))
    except Exception:
        return False
    return False


def wait_for_captcha_image_ready(page, *, timeout_ms: int = 15000) -> bool:
    """Wait until Loading spinner clears so locate has real objects."""
    deadline = timeout_ms / 1000.0
    import time as _time

    start = _time.time()
    while _time.time() - start < deadline:
        if not _captcha_image_still_loading(page):
            # Brief settle so canvas pixels are painted.
            page.wait_for_timeout(300)
            return True
        page.wait_for_timeout(250)
    return not _captcha_image_still_loading(page)


def solve_graphical_captcha_on_page(
    page,
    *,
    instructions: list[str] | None = None,
    confirm_instruction: str | None = None,
    max_targets: int = 2,
    shot_dir: str | Path | None = None,
    include_confirm: bool = True,
) -> dict[str, Any]:
    """One screenshot → locate all targets (+ Confirm) → click in order.

    Default instructions target TikTok-style "select 2 objects with the same shape".
    Confirm is located from the **same** initial screenshot so its coordinates are
    known before clicking (button may still look disabled until objects are selected).
    """
    out_dir = Path(shot_dir) if shot_dir else Path(tempfile.mkdtemp(prefix="captcha_locate_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    target_instr = list(instructions or _DEFAULT_TARGET_INSTRUCTIONS)[:max_targets]
    confirm_instr = (
        confirm_instruction if confirm_instruction is not None else _DEFAULT_CONFIRM_INSTRUCTION
    )

    ready = wait_for_captcha_image_ready(page)
    if not ready and _captcha_image_still_loading(page):
        return {
            "ok": False,
            "error": "captcha_image_still_loading",
            "shot_dir": str(out_dir),
            "clicks": [],
        }

    shot = out_dir / "captcha_once.png"
    page.screenshot(path=str(shot), full_page=False)

    locate_instr = list(target_instr)
    if include_confirm and confirm_instr:
        locate_instr.append(confirm_instr)

    located_list = locate_many_on_image(shot, locate_instr, parallel=True)

    plan: list[dict[str, Any]] = []
    for instr, located in zip(locate_instr, located_list, strict=True):
        xy = _image_xy(located)
        plan.append(
            {
                "instruction": instr,
                "found": bool(xy),
                "x": xy[0] if xy else None,
                "y": xy[1] if xy else None,
                "locate": {
                    k: located.get(k)
                    for k in ("found", "error", "thought", "action", "success")
                    if k in located
                },
                "role": "confirm" if instr == confirm_instr else "target",
            }
        )

    # Fallback: only re-shot for missing Confirm (targets must come from first shot)
    missing_targets = [p for p in plan if p["role"] == "target" and not p["found"]]
    if missing_targets:
        return {
            "ok": False,
            "error": "captcha_target_not_located",
            "instruction": missing_targets[0]["instruction"],
            "plan": plan,
            "shot": str(shot),
            "shot_dir": str(out_dir),
            "clicks": [],
        }

    confirm_plan = next((p for p in plan if p["role"] == "confirm"), None)

    # Execute clicks: all targets first, then Confirm immediately.
    # Confirm coords come from the first screenshot when available; DOM/re-locate
    # only after targets are selected (button is often disabled before then).
    clicks: list[dict[str, Any]] = []
    target_items = [p for p in plan if p["role"] == "target"]
    for i, item in enumerate(target_items):
        click_image_point(page, float(item["x"]), float(item["y"]))
        clicks.append(
            {
                "instruction": item["instruction"],
                "x": item["x"],
                "y": item["y"],
                "shot": str(shot),
                "role": "target",
            }
        )
        if i < len(target_items) - 1:
            page.wait_for_timeout(_GAP_BETWEEN_TARGETS_MS)

    if include_confirm and confirm_instr:
        page.wait_for_timeout(_GAP_BEFORE_CONFIRM_MS)
        confirmed = False

        # 1) Prefer coords from the same initial screenshot (fast path).
        if confirm_plan and confirm_plan.get("found") and confirm_plan.get("x") is not None:
            click_image_point(page, float(confirm_plan["x"]), float(confirm_plan["y"]))
            clicks.append(
                {
                    "instruction": confirm_instr,
                    "x": confirm_plan["x"],
                    "y": confirm_plan["y"],
                    "shot": str(shot),
                    "role": "confirm",
                }
            )
            confirmed = True

        # 2) After selection: DOM click (Confirm is usually enabled now).
        if not confirmed:
            for name in (r"Confirm", r"确认", r"输入确认"):
                try:
                    btn = page.get_by_role("button", name=re.compile(name, re.I))
                    if btn.count() and btn.first.is_visible():
                        btn.first.click(timeout=1500, force=True)
                        confirmed = True
                        break
                except Exception:
                    continue
            if not confirmed:
                try:
                    loc = page.locator("button, [role=button]").filter(
                        has_text=re.compile(r"Confirm|确认|输入确认", re.I)
                    )
                    if loc.count() and loc.first.is_visible():
                        loc.first.click(timeout=1500, force=True)
                        confirmed = True
                except Exception:
                    pass
            if confirmed:
                if confirm_plan is not None:
                    confirm_plan["found"] = True
                    confirm_plan["dom_fallback"] = True
                clicks.append(
                    {
                        "instruction": "dom_Confirm",
                        "x": None,
                        "y": None,
                        "role": "confirm",
                    }
                )

        # 3) Last resort: re-shot + locate Confirm now that it is lit up.
        if not confirmed:
            shot_fb = out_dir / "captcha_confirm_after_targets.png"
            page.screenshot(path=str(shot_fb), full_page=False)
            located_c = locate_on_image(shot_fb, confirm_instr)
            xy = _image_xy(located_c)
            if xy:
                click_image_point(page, float(xy[0]), float(xy[1]))
                if confirm_plan is not None:
                    confirm_plan["found"] = True
                    confirm_plan["x"], confirm_plan["y"] = xy
                    confirm_plan["fallback_shot"] = str(shot_fb)
                clicks.append(
                    {
                        "instruction": confirm_instr,
                        "x": xy[0],
                        "y": xy[1],
                        "shot": str(shot_fb),
                        "role": "confirm",
                    }
                )
                confirmed = True

        if not confirmed:
            return {
                "ok": False,
                "error": "captcha_confirm_not_found",
                "plan": plan,
                "shot": str(shot),
                "shot_dir": str(out_dir),
                "clicks": clicks,
            }

        page.wait_for_timeout(_GAP_AFTER_CONFIRM_MS)

    return {
        "ok": True,
        "clicks": clicks,
        "plan": plan,
        "shot": str(shot),
        "shot_dir": str(out_dir),
        "mode": "single_screenshot",
    }
