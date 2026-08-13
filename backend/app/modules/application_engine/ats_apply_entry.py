"""Phase 3: ATS job page → Apply → Autofill with Resume (never Submit).

Reusable by shopping-cart batch worker and single-job Apply workspace.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.modules.ats_connectors.registry import connector_for

log = logging.getLogger(__name__)

APPLY_SELECTORS = [
    "button[data-automation-id='jobPostingApplyButton']",
    "a[data-automation-id='jobPostingApplyButton']",
    "[data-automation-id='jobPostingApplyButton']",
    "button[data-testid='apply-button']",
    "a[data-testid='apply-button']",
    "a.button--primary:has-text('Apply')",
    "a.button:has-text('Apply')",
    "button:has-text('Apply Now')",
    "a:has-text('Apply Now')",
    "button:has-text('Apply for this Job')",
    "a:has-text('Apply for this Job')",
    "button:has-text('Start Application')",
    "a:has-text('Start Application')",
    "button:has-text(\"I'm Interested\")",
    "a:has-text(\"I'm Interested\")",
    "button:has-text('Apply')",
    "a:has-text('Apply')",
    "[role=button]:has-text('Apply')",
]

COOKIE_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button:has-text('Accept All')",
    "button:has-text('Accept all')",
    "button:has-text('I Accept')",
    "button:has-text('Agree')",
]

# Prefer Autofill / resume path; never match final Submit Application.
AUTOFILL_SELECTORS = [
    "button[data-automation-id='applyFlowAutofillWithResume']",
    "a[data-automation-id='applyFlowAutofillWithResume']",
    "[data-automation-id*='Autofill' i]",
    "button:has-text('Autofill with Resume')",
    "a:has-text('Autofill with Resume')",
    "[role=button]:has-text('Autofill with Resume')",
    "button:has-text('Use Resume')",
    "button:has-text('Apply with Resume')",
    "a:has-text('Apply with Resume')",
    "button:has-text('Autofill')",
]

RESUME_FILE_SELECTORS = [
    "input[type='file'][data-automation-id*='file-upload' i]",
    "input[type='file'][data-automation-id*='resume' i]",
    "input[type='file'][name*='resume' i]",
    "input[type='file'][id*='resume' i]",
    "input[type='file']",
]

ACCOUNT_MARKERS = [
    "text=Create Account",
    "text=Sign In",
    "text=Sign in",
    "button:has-text('Create Account')",
    "button:has-text('Sign In')",
    "input[type='password']",
    "[data-automation-id='createAccountSubmitButton']",
    "[data-automation-id*='password' i]",
]

FORM_MARKERS = [
    "input[data-automation-id*='firstName' i]",
    "input[aria-label*='First Name' i]",
    "input[name*='firstName' i]",
    "textarea",
]


def _is_submit_ish(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if "submit application" in t or t == "submit":
        return True
    if "autofill" in t or "resume" in t:
        return False
    # Bare "Apply" on job posting is OK; "Submit" is not.
    return "submit" in t


def _click_first(
    page,
    selectors: list[str],
    *,
    timeout_ms: int = 4000,
) -> dict[str, Any]:
    def _frames() -> list[Any]:
        # Playwright pages can put action buttons/forms inside iframes.
        # Searching frames makes the generic apply/autofill heuristics work across more ATS pages.
        try:
            return list(getattr(page, "frames") or []) or [page.main_frame]
        except Exception:
            return [getattr(page, "main_frame", page)]

    for selector in selectors:
        try:
            for frame in _frames():
                matches = frame.locator(selector)
                n = 0
                try:
                    n = matches.count()
                except Exception:
                    n = 0
                for i in range(n):
                    loc = matches.nth(i)
                    try:
                        if not loc.is_visible():
                            continue
                    except Exception:
                        continue
                    try:
                        text = (loc.inner_text(timeout=800) or "").strip()
                    except Exception:
                        text = ""
                    if _is_submit_ish(text):
                        continue
                    if "manually" in text.lower():
                        continue
                    loc.click(timeout=timeout_ms)
                    page.wait_for_timeout(700)
                    return {"ok": True, "selector": selector, "text": text}
        except Exception:
            continue
    return {"ok": False}


def _dismiss_cookies(page) -> None:
    for selector in COOKIE_SELECTORS:
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=1500)
                page.wait_for_timeout(400)
                return
        except Exception:
            continue


def _wait_for_apply(page, timeout_ms: int = 15000) -> None:
    try:
        page.get_by_role("link", name="Apply").or_(
            page.get_by_role("button", name="Apply")
        ).first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        pass


def _visible(page, selector: str) -> bool:
    try:
        for frame in list(getattr(page, "frames") or []) + [getattr(page, "main_frame", page)]:
            try:
                loc = frame.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _detect_next_screen(page) -> str:
    try:
        stage = page.locator("#stage").first
        if stage.count() and stage.is_visible():
            raw = (stage.inner_text(timeout=500) or "").lower()
            if "resume_attached" in raw:
                return "resume_attached"
            if "create_account" in raw:
                return "create_account"
            if "start_application" in raw:
                return "start_application"
    except Exception:
        pass

    for sel in ACCOUNT_MARKERS:
        if _visible(page, sel):
            return "create_account"
    for sel in FORM_MARKERS:
        if _visible(page, sel):
            return "application_form"
    return "unknown"


def _attach_resume(page, resume_path: str) -> dict[str, Any]:
    path = Path(resume_path)
    if not path.is_file():
        return {"ok": False, "error": "resume_file_missing"}
    for selector in RESUME_FILE_SELECTORS:
        try:
            loc = page.locator(selector).first
            if loc.count() == 0 or not loc.is_visible():
                continue
            loc.set_input_files(str(path), timeout=4000)
            page.wait_for_timeout(400)
            return {"ok": True, "selector": selector, "path": str(path)}
        except Exception:
            continue
    # Hidden file inputs are common on ATS pages after Autofill — allow as fallback.
    for selector in RESUME_FILE_SELECTORS:
        try:
            loc = page.locator(selector).first
            if loc.count() == 0:
                continue
            loc.set_input_files(str(path), timeout=4000)
            page.wait_for_timeout(400)
            return {"ok": True, "selector": selector, "path": str(path), "hidden_input": True}
        except Exception:
            continue
    return {"ok": False, "error": "resume_file_input_not_found", "path": str(path)}


def run_apply_autofill_on_page(
    page,
    *,
    resume_path: str | None,
    click_apply: bool = True,
) -> dict[str, Any]:
    """Operate on an already-open ATS page. Never clicks Submit."""
    apply_click = {"ok": True, "skipped": True}
    if click_apply:
        apply_click = _click_first(page, APPLY_SELECTORS)
        # Apply click usually triggers async navigation / form render.
        # Waiting a bit longer improves next-screen detection and reduces false
        # "apply_or_autofill_not_found" failures.
        page.wait_for_timeout(1200)

    autofill_click = _click_first(page, AUTOFILL_SELECTORS)
    page.wait_for_timeout(1200)

    resume_attach: dict[str, Any] = {"ok": False, "skipped": True}
    if resume_path and (autofill_click.get("ok") or _visible(page, "#after-autofill") or _visible(page, "[data-testid='after-autofill']")):
        resume_attach = _attach_resume(page, resume_path)

    next_screen = _detect_next_screen(page)
    # Some ATS pages render the application form without a stable "#stage" label.
    # If we can already see form markers, treat it as "application_form".
    if next_screen == "unknown" and any(_visible(page, sel) for sel in FORM_MARKERS):
        next_screen = "application_form"
    ok = bool(autofill_click.get("ok")) or (
        bool(apply_click.get("ok"))
        and not apply_click.get("skipped")
        and next_screen in {"create_account", "application_form", "resume_attached"}
    )

    return {
        "ok": ok,
        "apply_clicked": bool(apply_click.get("ok")) and not apply_click.get("skipped"),
        "autofill_clicked": bool(autofill_click.get("ok")),
        "resume_attached": bool(resume_attach.get("ok")),
        "resume_attach": resume_attach,
        "apply_click": apply_click,
        "autofill_click": autofill_click,
        "next_screen": next_screen,
        "page_url": getattr(page, "url", None),
        "submitted": False,
    }


def apply_and_autofill_resume(
    *,
    ats_url: str,
    resume_path: str | None,
    headless: bool | None = None,
    timeout_ms: int | None = None,
    screenshot_path: str | None = None,
) -> dict[str, Any]:
    """Open ATS URL → Apply → Autofill with Resume → optional resume upload. Never Submit."""
    url = (ats_url or "").strip()
    if not url:
        return {"ok": False, "error": "missing_ats_url", "submitted": False}

    if resume_path and not Path(resume_path).is_file():
        return {
            "ok": False,
            "error": "confirm_resume_pdf_required",
            "message": "Confirmed resume PDF missing — confirm PDF in shopping cart first.",
            "resume_path": resume_path,
            "submitted": False,
        }

    timeout_ms = int(timeout_ms or settings.BROWSER_TIMEOUT_MS or 30000)
    headless = settings.BROWSER_HEADLESS if headless is None else bool(headless)
    connector = connector_for(url)
    ats_type = str(getattr(connector, "ats_type", None) or "generic")

    live = bool(
        getattr(settings, "CART_APPLY_LIVE_ENTRY", False)
        or getattr(settings, "ALLOW_LIVE_BROWSER_FILL", False)
    )
    # Local file / fixture always allowed (sandbox).
    is_local = url.startswith("file:") or "fixture_workday" in url or "/artifacts/" in url
    if not live and not is_local:
        return {
            "ok": False,
            "error": "live_entry_disabled",
            "message": "Set CART_APPLY_LIVE_ENTRY=true (or ALLOW_LIVE_BROWSER_FILL=true) for live ATS entry.",
            "ats_url": url,
            "ats_type": ats_type,
            "method": "blocked",
            "submitted": False,
        }

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"playwright_unavailable: {exc}",
            "submitted": False,
        }

    shot = None
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=headless, channel="chrome")
            except Exception:
                browser = playwright.chromium.launch(headless=headless)
            page = browser.new_page()
            page.goto(url, wait_until="commit", timeout=max(timeout_ms, 60000))
            try:
                page.wait_for_load_state("domcontentloaded", timeout=min(20000, max(timeout_ms, 15000)))
            except Exception:
                pass
            page.wait_for_timeout(1500)
            _dismiss_cookies(page)
            _wait_for_apply(page, timeout_ms=15000)
            result = run_apply_autofill_on_page(page, resume_path=resume_path, click_apply=True)
            if screenshot_path:
                Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                shot = screenshot_path
            final_url = page.url
            browser.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("apply_and_autofill failed url=%s err=%s", url, exc)
        return {
            "ok": False,
            "error": str(exc),
            "ats_url": url,
            "ats_type": ats_type,
            "method": "playwright_apply_autofill",
            "submitted": False,
        }

    host = ""
    try:
        host = urlparse(final_url).hostname or ""
    except Exception:
        host = ""

    return {
        **result,
        "ats_url": final_url or url,
        "ats_type": ats_type,
        "host": host,
        "resume_path": resume_path,
        "screenshot_path": shot,
        "method": "playwright_apply_autofill",
        "submitted": False,
        "error": None if result.get("ok") else "apply_or_autofill_not_found",
    }


def workday_entry_fixture_uri() -> str:
    repo = Path(__file__).resolve().parents[4]
    path = repo / "artifacts" / "funnel" / "sprint-j" / "fixture_workday_entry.html"
    return path.resolve().as_uri()
