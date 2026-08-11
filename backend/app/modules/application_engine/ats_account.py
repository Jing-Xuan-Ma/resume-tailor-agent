"""Phase 4: ATS Create Account / Sign In with default env credentials.

Never clicks final application Submit. Masks secrets in returned payloads/logs.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.modules.ats_connectors.registry import connector_for

log = logging.getLogger(__name__)

EMAIL_SELECTORS = [
    "input[data-automation-id='email']",
    "input[data-automation-id*='email' i]",
    "input[type='email']",
    "input[aria-label*='Email' i]",
    "input[name*='email' i]",
    "input[autocomplete='email']",
]

PASSWORD_SELECTORS = [
    "input[data-automation-id='password']",
    "input[data-automation-id*='password' i]:not([data-automation-id*='verify' i])",
    "input[type='password'][aria-label*='Password' i]",
    "input[type='password'][name*='password' i]",
    "input[type='password']",
]

VERIFY_PASSWORD_SELECTORS = [
    "input[data-automation-id='verifyPassword']",
    "input[data-automation-id*='verify' i]",
    "input[aria-label*='Verify' i]",
    "input[aria-label*='Confirm Password' i]",
    "input[name*='confirm' i][type='password']",
]

CREATE_SUBMIT_SELECTORS = [
    "button[data-automation-id='createAccountSubmitButton']",
    "button:has-text('Create Account')",
    "button:has-text('Create account')",
    "[role=button]:has-text('Create Account')",
]

SIGNIN_SUBMIT_SELECTORS = [
    "button[data-automation-id='signInSubmitButton']",
    "button[data-automation-id*='signIn' i]",
    "button:has-text('Sign In')",
    "button:has-text('Sign in')",
    "button:has-text('Log In')",
    "button:has-text('Log in')",
]

SIGNIN_TAB_SELECTORS = [
    "button[data-testid='tab-signin']",
    "button:has-text('Sign In')",
    "a:has-text('Sign In')",
    "button:has-text('Sign in')",
    "a:has-text('Sign in')",
    "[role=tab]:has-text('Sign In')",
    "text=Already have an account?",
]

CREATE_TAB_SELECTORS = [
    "button[data-testid='tab-create']",
    "button:has-text('Create Account')",
    "a:has-text('Create Account')",
    "[role=tab]:has-text('Create Account')",
]

CAPTCHA_MARKERS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    ".g-recaptcha",
    "#captcha",
    "text=captcha",
    "text=I'm not a robot",
]

EMAIL_EXISTS_PATTERNS = [
    r"already exists",
    r"already registered",
    r"account.*already",
    r"email.*taken",
    r"please sign in",
    r"user already",
]

VALIDATION_PATTERNS = [
    r"does not meet",
    r"password.*requirement",
    r"passwords? do not match",
    r"invalid email",
    r"required",
    r"complexity",
]

REGISTERED_MARKERS = [
    "#stage",
    "input[data-automation-id*='firstName' i]",
    "input[aria-label*='First Name' i]",
    "[data-testid='application-form']",
    "text=My Information",
    "text=Let's get started",
    "text=Contact Information",
]


def mask_email(email: str | None) -> str:
    raw = (email or "").strip()
    if not raw or "@" not in raw:
        return "***"
    local, _, domain = raw.partition("@")
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    return "***"


def sanitize_account_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip/mask secrets before persisting or returning to clients."""
    out = dict(payload)
    secrets: list[str] = []
    for key in ("password", "ats_password", "default_password", "password2", "verify_password"):
        raw = out.get(key)
        if isinstance(raw, str) and raw.strip():
            secrets.append(raw.strip())
    env_pw = (settings.ATS_DEFAULT_PASSWORD or "").strip()
    if env_pw:
        secrets.append(env_pw)

    if "password" in out:
        out["password"] = mask_secret(str(out.get("password") or ""))
    if "email" in out and out.get("email"):
        out["email_masked"] = mask_email(str(out.get("email")))
        out.pop("email", None)
    for key in ("ats_password", "default_password", "password2", "verify_password"):
        if key in out:
            out[key] = mask_secret(str(out.get(key) or ""))
    for secret in secrets:
        for key in ("error", "message", "note", "page_text", "page_snippet"):
            if isinstance(out.get(key), str) and secret in out[key]:
                out[key] = out[key].replace(secret, "***")
    return out


def validate_ats_password(password: str | None) -> dict[str, Any]:
    """Typical Workday-style password rules (configurable via settings)."""
    pw = password or ""
    min_len = int(getattr(settings, "ATS_PASSWORD_MIN_LENGTH", 8) or 8)
    require_upper = bool(getattr(settings, "ATS_PASSWORD_REQUIRE_UPPER", True))
    require_lower = bool(getattr(settings, "ATS_PASSWORD_REQUIRE_LOWER", True))
    require_digit = bool(getattr(settings, "ATS_PASSWORD_REQUIRE_DIGIT", True))
    require_special = bool(getattr(settings, "ATS_PASSWORD_REQUIRE_SPECIAL", True))

    errors: list[str] = []
    if len(pw) < min_len:
        errors.append(f"min_length_{min_len}")
    if require_upper and not re.search(r"[A-Z]", pw):
        errors.append("need_upper")
    if require_lower and not re.search(r"[a-z]", pw):
        errors.append("need_lower")
    if require_digit and not re.search(r"[0-9]", pw):
        errors.append("need_digit")
    if require_special and not re.search(r"[^A-Za-z0-9]", pw):
        errors.append("need_special")
    return {"ok": not errors, "errors": errors}


def load_ats_credentials() -> dict[str, Any]:
    email = (settings.ATS_DEFAULT_EMAIL or "").strip()
    fallback = (getattr(settings, "ATS_FALLBACK_EMAIL", "") or "").strip()
    password = (settings.ATS_DEFAULT_PASSWORD or "").strip()
    if not email or not password:
        return {
            "ok": False,
            "error": "ats_credentials_not_configured",
            "message": "Set ATS_DEFAULT_EMAIL and ATS_DEFAULT_PASSWORD in environment.",
            "email_masked": mask_email(email) if email else None,
        }
    check = validate_ats_password(password)
    if not check["ok"]:
        return {
            "ok": False,
            "error": "ats_password_policy_failed",
            "message": "ATS_DEFAULT_PASSWORD does not meet configured complexity rules.",
            "policy_errors": check["errors"],
            "email_masked": mask_email(email),
        }
    out: dict[str, Any] = {
        "ok": True,
        "email": email,
        "password": password,
        "email_masked": mask_email(email),
    }
    if fallback and fallback.lower() != email.lower():
        out["fallback_email"] = fallback
        out["fallback_email_masked"] = mask_email(fallback)
    return out


def _visible(page, selector: str) -> bool:
    try:
        loc = page.locator(selector).first
        return loc.count() > 0 and loc.is_visible()
    except Exception:
        return False


def _fill_first(page, selectors: list[str], value: str) -> dict[str, Any]:
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() == 0 or not loc.is_visible():
                continue
            loc.fill(value, timeout=3000)
            return {"ok": True, "selector": selector}
        except Exception:
            continue
    return {"ok": False}


def _click_first(page, selectors: list[str], *, skip_submit_application: bool = True) -> dict[str, Any]:
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() == 0 or not loc.is_visible():
                continue
            try:
                text = (loc.inner_text(timeout=600) or "").strip()
            except Exception:
                text = ""
            low = text.lower()
            if skip_submit_application and ("submit application" in low or low == "submit"):
                continue
            loc.click(timeout=4000)
            page.wait_for_timeout(700)
            return {"ok": True, "selector": selector, "text": text}
        except Exception:
            continue
    return {"ok": False}


def _page_text(page) -> str:
    try:
        return (page.locator("body").inner_text(timeout=1500) or "")[:4000]
    except Exception:
        return ""


def _match_any(text: str, patterns: list[str]) -> str | None:
    low = (text or "").lower()
    for pat in patterns:
        if re.search(pat, low):
            return pat
    return None


def detect_captcha(page) -> bool:
    for sel in CAPTCHA_MARKERS:
        if _visible(page, sel):
            return True
    # TikTok / ByteDance shape CAPTCHA overlays often lack classic iframe markers
    try:
        text = (_page_text(page) or "").lower()
        if "select" in text and "same shape" in text:
            return True
        if "confirm" in text and ("refresh" in text or "report a problem" in text):
            # weak signal — only with a modal-looking canvas/img dense region
            if page.locator("canvas, img").count() >= 1 and page.locator("text=Confirm").count():
                return True
    except Exception:
        pass
    return False


def try_solve_captcha_with_screen_locate(page) -> dict[str, Any]:
    """Attempt graphical CAPTCHA via .agents/skills/screen-locate."""
    try:
        from app.modules.application_engine.screen_locate_captcha import (
            solve_graphical_captcha_on_page,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"screen_locate_import_failed:{exc}"}
    try:
        return solve_graphical_captcha_on_page(page)
    except Exception as exc:  # noqa: BLE001
        log.warning("screen-locate captcha solve failed: %s", exc)
        return {"ok": False, "error": f"screen_locate_exception:{exc}"}


def detect_account_wall(page) -> bool:
    return (
        _visible(page, "input[type='password']")
        or _visible(page, "[data-automation-id='createAccountSubmitButton']")
        or _visible(page, "[data-automation-id='signInSubmitButton']")
        or _visible(page, "button:has-text('Create Account')")
    )


def detect_registered(page) -> bool:
    try:
        stage = page.locator("#stage").first
        if stage.count() and stage.is_visible():
            raw = (stage.inner_text(timeout=400) or "").lower()
            if "stage:registered" in raw:
                return True
    except Exception:
        pass
    # Application form visible and create/sign-in buttons gone is a strong signal
    formish = any(_visible(page, sel) for sel in REGISTERED_MARKERS[1:])
    wall = detect_account_wall(page)
    if formish and not wall:
        return True
    if formish and _visible(page, "[data-testid='application-form']"):
        return True
    return False


def _try_create(page, email: str, password: str) -> dict[str, Any]:
    _click_first(page, CREATE_TAB_SELECTORS)
    email_fill = _fill_first(page, EMAIL_SELECTORS, email)
    pw_fill = _fill_first(page, PASSWORD_SELECTORS, password)
    verify_fill = _fill_first(page, VERIFY_PASSWORD_SELECTORS, password)
    submit = _click_first(page, CREATE_SUBMIT_SELECTORS)
    page.wait_for_timeout(800)
    text = _page_text(page)
    return {
        "mode": "create_account",
        "email_filled": bool(email_fill.get("ok")),
        "password_filled": bool(pw_fill.get("ok")),
        "verify_filled": bool(verify_fill.get("ok")),
        "submitted_auth": bool(submit.get("ok")),
        "page_snippet": text[:500],
    }


def _try_signin(page, email: str, password: str) -> dict[str, Any]:
    _click_first(page, SIGNIN_TAB_SELECTORS)
    email_fill = _fill_first(page, EMAIL_SELECTORS, email)
    # Prefer first visible password only (verify field may still exist hidden)
    pw_fill = _fill_first(page, PASSWORD_SELECTORS, password)
    submit = _click_first(page, SIGNIN_SUBMIT_SELECTORS)
    page.wait_for_timeout(800)
    text = _page_text(page)
    return {
        "mode": "sign_in",
        "email_filled": bool(email_fill.get("ok")),
        "password_filled": bool(pw_fill.get("ok")),
        "submitted_auth": bool(submit.get("ok")),
        "page_snippet": text[:500],
    }


def _stage_value(page) -> str:
    try:
        stage = page.locator("#stage").first
        if stage.count() and stage.is_visible():
            return (stage.inner_text(timeout=400) or "").strip().lower()
    except Exception:
        pass
    return ""


def create_or_sign_in_on_page(
    page,
    *,
    email: str,
    password: str,
    prefer: str = "create",
) -> dict[str, Any]:
    """Fill Create Account or Sign In on an open page. Never clicks application Submit."""
    if detect_captcha(page):
        solved = try_solve_captcha_with_screen_locate(page)
        if not solved.get("ok"):
            return sanitize_account_payload(
                {
                    "ok": False,
                    "error": "captcha_required",
                    "message": "CAPTCHA detected — screen-locate solve failed.",
                    "captcha_solve": solved,
                    "email_masked": mask_email(email),
                    "submitted": False,
                }
            )
        page.wait_for_timeout(800)
        if detect_captcha(page) and not detect_registered(page):
            return sanitize_account_payload(
                {
                    "ok": False,
                    "error": "captcha_required",
                    "message": "CAPTCHA still present after screen-locate clicks.",
                    "captcha_solve": solved,
                    "email_masked": mask_email(email),
                    "submitted": False,
                }
            )

    if not detect_account_wall(page) and detect_registered(page):
        return sanitize_account_payload(
            {
                "ok": True,
                "already_registered": True,
                "auth_mode": "already_in",
                "email_masked": mask_email(email),
                "submitted": False,
            }
        )

    if not detect_account_wall(page):
        return sanitize_account_payload(
            {
                "ok": False,
                "error": "account_wall_not_found",
                "message": "Create Account / Sign In form not visible.",
                "email_masked": mask_email(email),
                "submitted": False,
            }
        )

    attempts: list[dict[str, Any]] = []
    mode = (prefer or "create").lower()
    if mode not in {"create", "sign_in", "signin"}:
        mode = "create"

    if mode in {"sign_in", "signin"}:
        attempt = _try_signin(page, email, password)
    else:
        attempt = _try_create(page, email, password)
    attempts.append(attempt)

    if detect_registered(page):
        return sanitize_account_payload(
            {
                "ok": True,
                "auth_mode": attempt.get("mode"),
                "email_masked": mask_email(email),
                "attempts": [{"mode": a.get("mode"), "submitted_auth": a.get("submitted_auth")} for a in attempts],
                "submitted": False,
            }
        )

    text = _page_text(page)
    stage = _stage_value(page)
    if detect_captcha(page):
        solved = try_solve_captcha_with_screen_locate(page)
        if solved.get("ok"):
            page.wait_for_timeout(800)
            if detect_registered(page):
                return sanitize_account_payload(
                    {
                        "ok": True,
                        "auth_mode": attempt.get("mode"),
                        "email_masked": mask_email(email),
                        "captcha_solved_via": "screen_locate",
                        "attempts": [
                            {"mode": a.get("mode"), "submitted_auth": a.get("submitted_auth")}
                            for a in attempts
                        ],
                        "submitted": False,
                    }
                )
        return sanitize_account_payload(
            {
                "ok": False,
                "error": "captcha_required",
                "email_masked": mask_email(email),
                "captcha_solve": solved,
                "submitted": False,
            }
        )

    exists = _match_any(text, EMAIL_EXISTS_PATTERNS) or ("email_exists" in stage)
    if exists and attempt.get("mode") == "create_account":
        # Retry once via Sign In with the same email
        attempt2 = _try_signin(page, email, password)
        attempts.append(attempt2)
        if detect_registered(page):
            return sanitize_account_payload(
                {
                    "ok": True,
                    "auth_mode": "sign_in_after_email_exists",
                    "email_masked": mask_email(email),
                    "email_existed": True,
                    "attempts": [
                        {"mode": a.get("mode"), "submitted_auth": a.get("submitted_auth")} for a in attempts
                    ],
                    "submitted": False,
                }
            )
        # Same email cannot create + sign-in failed → try fallback email for Create Account
        fallback = (getattr(settings, "ATS_FALLBACK_EMAIL", "") or "").strip()
        if fallback and fallback.lower() != email.lower():
            _click_first(page, CREATE_TAB_SELECTORS)
            attempt3 = _try_create(page, fallback, password)
            attempts.append({**attempt3, "email_masked": mask_email(fallback)})
            if detect_registered(page):
                return sanitize_account_payload(
                    {
                        "ok": True,
                        "auth_mode": "create_account_fallback_email",
                        "email_masked": mask_email(fallback),
                        "primary_email_existed": True,
                        "used_fallback_email": True,
                        "attempts": [
                            {"mode": a.get("mode"), "submitted_auth": a.get("submitted_auth")}
                            for a in attempts
                        ],
                        "submitted": False,
                    }
                )
            # If fallback also already exists, try sign-in with fallback
            text_fb = _page_text(page)
            if _match_any(text_fb, EMAIL_EXISTS_PATTERNS):
                attempt4 = _try_signin(page, fallback, password)
                attempts.append({**attempt4, "email_masked": mask_email(fallback)})
                if detect_registered(page):
                    return sanitize_account_payload(
                        {
                            "ok": True,
                            "auth_mode": "sign_in_fallback_email",
                            "email_masked": mask_email(fallback),
                            "used_fallback_email": True,
                            "attempts": [
                                {"mode": a.get("mode"), "submitted_auth": a.get("submitted_auth")}
                                for a in attempts
                            ],
                            "submitted": False,
                        }
                    )
            return sanitize_account_payload(
                {
                    "ok": False,
                    "error": "fallback_email_auth_failed",
                    "message": (
                        "Primary email already registered; fallback create/sign-in "
                        "did not reach application form."
                    ),
                    "email_masked": mask_email(fallback),
                    "primary_email_masked": mask_email(email),
                    "email_existed": True,
                    "used_fallback_email": True,
                    "submitted": False,
                }
            )
        return sanitize_account_payload(
            {
                "ok": False,
                "error": "sign_in_failed_after_email_exists",
                "message": "Email already registered; Sign In retry did not reach application form.",
                "email_masked": mask_email(email),
                "email_existed": True,
                "submitted": False,
            }
        )

    validation = _match_any(text, VALIDATION_PATTERNS) or ("validation_error" in stage)
    if validation:
        return sanitize_account_payload(
            {
                "ok": False,
                "error": "validation_failed",
                "message": "Account form validation failed.",
                "validation_pattern": validation if isinstance(validation, str) else "stage",
                "email_masked": mask_email(email),
                "submitted": False,
            }
        )

    return sanitize_account_payload(
        {
            "ok": False,
            "error": "account_step_incomplete",
            "message": "Could not confirm Create Account / Sign In success.",
            "email_masked": mask_email(email),
            "auth_mode": attempt.get("mode"),
            "submitted": False,
        }
    )


def create_or_sign_in(
    *,
    ats_url: str,
    resume_path: str | None = None,
    email: str | None = None,
    password: str | None = None,
    headless: bool | None = None,
    timeout_ms: int | None = None,
    screenshot_path: str | None = None,
    ensure_entry: bool = True,
) -> dict[str, Any]:
    """Open ATS URL, optionally re-run Apply/Autofill, then Create Account / Sign In."""
    url = (ats_url or "").strip()
    if not url:
        return sanitize_account_payload({"ok": False, "error": "missing_ats_url", "submitted": False})

    creds = load_ats_credentials()
    if email and password:
        check = validate_ats_password(password)
        if not check["ok"]:
            return sanitize_account_payload(
                {
                    "ok": False,
                    "error": "ats_password_policy_failed",
                    "policy_errors": check["errors"],
                    "email_masked": mask_email(email),
                    "submitted": False,
                }
            )
        creds = {"ok": True, "email": email, "password": password, "email_masked": mask_email(email)}
    if not creds.get("ok"):
        return sanitize_account_payload({**creds, "submitted": False})

    live = bool(
        getattr(settings, "CART_APPLY_LIVE_ENTRY", False)
        or getattr(settings, "ALLOW_LIVE_BROWSER_FILL", False)
    )
    is_local = url.startswith("file:") or "fixture_workday" in url or "/artifacts/" in url
    if not live and not is_local:
        return sanitize_account_payload(
            {
                "ok": False,
                "error": "live_entry_disabled",
                "message": "Set CART_APPLY_LIVE_ENTRY=true for live ATS account steps.",
                "email_masked": creds.get("email_masked"),
                "submitted": False,
            }
        )

    timeout_ms = int(timeout_ms or settings.BROWSER_TIMEOUT_MS or 30000)
    headless = settings.BROWSER_HEADLESS if headless is None else bool(headless)
    connector = connector_for(url)
    ats_type = str(getattr(connector, "ats_type", None) or "generic")

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return sanitize_account_payload(
            {"ok": False, "error": f"playwright_unavailable: {exc}", "submitted": False}
        )

    from app.modules.application_engine.ats_apply_entry import run_apply_autofill_on_page

    shot = None
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=headless, channel="chrome")
            except Exception:
                browser = playwright.chromium.launch(headless=headless)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(800)

            entry = None
            if ensure_entry and not detect_account_wall(page) and not detect_registered(page):
                entry = run_apply_autofill_on_page(page, resume_path=resume_path, click_apply=True)

            result = create_or_sign_in_on_page(
                page,
                email=str(creds["email"]),
                password=str(creds["password"]),
                prefer="create",
            )
            if screenshot_path:
                from pathlib import Path

                Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                shot = screenshot_path
            final_url = page.url
            browser.close()
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "create_or_sign_in failed url=%s email=%s err=%s",
            url,
            mask_email(str(creds.get("email"))),
            exc,
        )
        return sanitize_account_payload(
            {
                "ok": False,
                "error": str(exc),
                "ats_url": url,
                "ats_type": ats_type,
                "email_masked": creds.get("email_masked"),
                "method": "playwright_account",
                "submitted": False,
            }
        )

    host = ""
    try:
        host = urlparse(final_url).hostname or ""
    except Exception:
        host = ""

    out = {
        **result,
        "ats_url": final_url or url,
        "ats_type": ats_type,
        "host": host,
        "screenshot_path": shot,
        "entry": (
            {
                "ok": bool((entry or {}).get("ok")),
                "apply_clicked": (entry or {}).get("apply_clicked"),
                "autofill_clicked": (entry or {}).get("autofill_clicked"),
                "resume_attached": (entry or {}).get("resume_attached"),
                "next_screen": (entry or {}).get("next_screen"),
            }
            if entry
            else None
        ),
        "method": "playwright_account",
        "email_masked": creds.get("email_masked"),
        "submitted": False,
    }
    return sanitize_account_payload(out)
