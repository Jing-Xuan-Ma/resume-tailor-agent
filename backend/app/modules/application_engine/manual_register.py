"""Manual ATS account registration handoff (captcha / human verify).

Keeps a headed Playwright browser open so the user can finish Create Account,
then snapshots storage_state so Phase 5 can continue with that session.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

from app.config import settings

log = logging.getLogger(__name__)

_HOLD_LOCK = threading.Lock()
_HOLDS: dict[str, "_ManualRegisterHold"] = {}


def hold_key(cart_id: str, item_id: str) -> str:
    return f"{cart_id}::{item_id}"


class _ManualRegisterHold:
    def __init__(self, *, key: str, ats_url: str, storage_out_path: str) -> None:
        self.key = key
        self.ats_url = ats_url
        self.storage_out_path = storage_out_path
        self.cmd_q: queue.Queue[str] = queue.Queue()
        self.result_q: queue.Queue[dict[str, Any]] = queue.Queue()
        self.opened = threading.Event()
        self.closed = threading.Event()
        self.open_result: dict[str, Any] = {"ok": False}
        self._thread: threading.Thread | None = None

    def start(
        self,
        *,
        resume_path: str | None,
        keep_open_ms: int,
        headless: bool,
        timeout_ms: int,
    ) -> None:
        self._thread = threading.Thread(
            target=self._run,
            kwargs={
                "resume_path": resume_path,
                "keep_open_ms": keep_open_ms,
                "headless": headless,
                "timeout_ms": timeout_ms,
            },
            daemon=True,
            name=f"manual-register-{self.key[:24]}",
        )
        self._thread.start()

    def _activate_browser_window(self) -> None:
        """Best-effort: bring Chromium/Chrome to the front (macOS)."""
        try:
            import subprocess

            subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to set frontmost of '
                    '(first process whose name contains "Chrom" or name contains "Chrome") to true',
                ],
                check=False,
                capture_output=True,
                timeout=3,
            )
        except Exception:
            pass

    def _run(
        self,
        *,
        resume_path: str | None,
        keep_open_ms: int,
        headless: bool,
        timeout_ms: int,
    ) -> None:
        from app.modules.application_engine.ats_account import (
            detect_account_wall,
            detect_registered,
        )
        from app.modules.application_engine.ats_apply_entry import run_apply_autofill_on_page

        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            self.open_result = {"ok": False, "error": f"playwright_unavailable: {exc}"}
            self.opened.set()
            self.closed.set()
            return

        browser = None
        try:
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(headless=headless, channel="chrome")
                except Exception:
                    browser = playwright.chromium.launch(headless=headless)
                context = browser.new_context()
                page = context.new_page()
                page.goto(self.ats_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(800)

                if not detect_account_wall(page) and not detect_registered(page):
                    try:
                        run_apply_autofill_on_page(page, resume_path=resume_path, click_apply=True)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("manual register entry failed key=%s err=%s", self.key, exc)

                try:
                    page.bring_to_front()
                except Exception:
                    pass
                if not headless:
                    self._activate_browser_window()

                final_url = page.url
                self.open_result = {
                    "ok": True,
                    "opened": True,
                    "ats_url": final_url or self.ats_url,
                    "account_wall": detect_account_wall(page),
                    "already_registered": detect_registered(page),
                    "method": "headed_manual_register",
                }
                self.opened.set()

                deadline = time.monotonic() + max(5.0, float(keep_open_ms) / 1000.0)
                while time.monotonic() < deadline and browser.is_connected():
                    try:
                        cmd = self.cmd_q.get(timeout=1.0)
                    except queue.Empty:
                        continue
                    if cmd == "focus":
                        try:
                            page.bring_to_front()
                        except Exception:
                            pass
                        if not headless:
                            self._activate_browser_window()
                        self.result_q.put(
                            {
                                "ok": True,
                                "focused": True,
                                "ats_url": page.url,
                                "account_wall": detect_account_wall(page),
                                "already_registered": detect_registered(page),
                            }
                        )
                    elif cmd == "snapshot":
                        Path(self.storage_out_path).parent.mkdir(parents=True, exist_ok=True)
                        context.storage_state(path=self.storage_out_path)
                        registered = detect_registered(page)
                        wall = detect_account_wall(page)
                        self.result_q.put(
                            {
                                "ok": True,
                                "registered": bool(registered),
                                "account_wall": bool(wall),
                                "ats_url": page.url,
                                "storage_state_path": self.storage_out_path,
                            }
                        )
                    elif cmd == "close":
                        break

                try:
                    browser.close()
                except Exception:
                    pass
        except Exception as exc:  # noqa: BLE001
            log.warning("manual register hold failed key=%s err=%s", self.key, exc)
            if not self.opened.is_set():
                self.open_result = {"ok": False, "error": str(exc), "ats_url": self.ats_url}
                self.opened.set()
            try:
                self.result_q.put({"ok": False, "error": str(exc)})
            except Exception:
                pass
        finally:
            self.closed.set()
            with _HOLD_LOCK:
                if _HOLDS.get(self.key) is self:
                    _HOLDS.pop(self.key, None)

    def request(self, cmd: str, *, timeout_s: float = 45.0) -> dict[str, Any]:
        if self.closed.is_set():
            return {"ok": False, "error": "register_browser_closed"}
        # Drain stale results
        while True:
            try:
                self.result_q.get_nowait()
            except queue.Empty:
                break
        self.cmd_q.put(cmd)
        try:
            return self.result_q.get(timeout=timeout_s)
        except queue.Empty:
            return {"ok": False, "error": "register_browser_timeout"}


def open_register_page(
    *,
    cart_id: str,
    item_id: str,
    ats_url: str,
    resume_path: str | None = None,
    storage_out_path: str,
    keep_open_ms: int = 1_800_000,
    headless: bool = False,
    timeout_ms: int | None = None,
) -> dict[str, Any]:
    """Open (or focus) a headed ATS page for manual Create Account / CAPTCHA."""
    url = (ats_url or "").strip()
    if not url:
        return {"ok": False, "error": "missing_ats_url", "opened": False}
    key = hold_key(cart_id, item_id)
    timeout_ms = int(timeout_ms or settings.BROWSER_TIMEOUT_MS or 30000)

    with _HOLD_LOCK:
        existing = _HOLDS.get(key)
        if existing and not existing.closed.is_set():
            focus = existing.request("focus", timeout_s=15.0)
            return {
                "ok": True,
                "opened": True,
                "focused_existing": True,
                "ats_url": focus.get("ats_url") or existing.ats_url,
                "account_wall": focus.get("account_wall"),
                "already_registered": focus.get("already_registered"),
                "method": "headed_manual_register_focus",
                "message": "已聚焦现有 ATS 注册窗口，请完成验证码并注册/登录。",
            }
        hold = _ManualRegisterHold(key=key, ats_url=url, storage_out_path=storage_out_path)
        _HOLDS[key] = hold

    hold.start(
        resume_path=resume_path,
        keep_open_ms=int(keep_open_ms or 1_800_000),
        headless=bool(headless),
        timeout_ms=timeout_ms,
    )
    if not hold.opened.wait(timeout=max(20.0, timeout_ms / 1000.0 + 10.0)):
        hold.cmd_q.put("close")
        return {"ok": False, "error": "register_browser_open_timeout", "opened": False}

    out = dict(hold.open_result)
    if out.get("ok"):
        out["message"] = (
            "已打开公司 ATS 注册/登录页。请亲自完成验证码并注册，完成后回到购物车点「已注册完成」。"
        )
    return out


def snapshot_and_close_register_page(
    *, cart_id: str, item_id: str, timeout_s: float = 45.0
) -> dict[str, Any]:
    """Ask the held browser to save cookies and close."""
    key = hold_key(cart_id, item_id)
    with _HOLD_LOCK:
        hold = _HOLDS.get(key)
    if not hold or hold.closed.is_set():
        return {"ok": False, "error": "no_open_register_session", "registered": False}

    snap = hold.request("snapshot", timeout_s=timeout_s)
    hold.cmd_q.put("close")
    # Wait briefly for cleanup
    hold.closed.wait(timeout=10.0)
    return snap
