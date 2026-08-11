"""Phase 5: fill ATS application form and pause before Submit.

Persists a reviewable fill snapshot (fields + plan + screenshot) for flip-through UI.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import settings
from app.modules.ats_connectors.canonical_profile import canonical_apply_profile
from app.modules.ats_connectors.field_mapper import map_fields_rules
from app.modules.ats_connectors.registry import connector_for

log = logging.getLogger(__name__)


def _tier_mappings(mapped: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for m in mapped:
        conf = float(m.get("confidence") or 0)
        action = m.get("action")
        if action in {"skip", "empty"} or not (m.get("value") or "").strip():
            m["tier"] = "empty"
        elif conf >= 0.75 and not m.get("needs_review"):
            m["tier"] = "auto"
        else:
            m["tier"] = "review"
    return mapped


def build_profile_for_cart_item(
    *,
    user_id: str,
    resume_path: str | None,
    cover_letter_path: str | None = None,
    resume_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    folder = str(Path(resume_path).parent) if resume_path else None
    profile = canonical_apply_profile(
        user_id,
        final_path=folder,
        resume_overrides=resume_overrides or {},
    )
    if resume_path and Path(resume_path).is_file():
        profile["resume_path"] = str(resume_path)
    if cover_letter_path and Path(cover_letter_path).is_file():
        profile["cover_letter_path"] = str(cover_letter_path)
    return profile


def profile_checklist(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Reviewable intended values (independent of DOM scan)."""
    resume = profile.get("resume_path") or ""
    return [
        {"field": "full_name", "value": profile.get("full_name") or "", "tier": "auto"},
        {"field": "first_name", "value": profile.get("first_name") or "", "tier": "auto"},
        {"field": "last_name", "value": profile.get("last_name") or "", "tier": "auto"},
        {"field": "email", "value": profile.get("email") or "", "tier": "auto"},
        {"field": "phone", "value": profile.get("phone") or "", "tier": "auto"},
        {"field": "linkedin", "value": profile.get("linkedin") or "", "tier": "review"},
        {"field": "location", "value": profile.get("location") or "", "tier": "review"},
        {"field": "work_authorization", "value": profile.get("work_authorized") or "", "tier": "review"},
        {
            "field": "resume_upload",
            "value": resume,
            "tier": "auto" if resume else "empty",
            "note": None if resume else "missing resume file",
        },
        {
            "field": "submit_button",
            "value": "NOT_CLICKED",
            "tier": "empty",
            "note": "hard stop — pause before submit",
        },
    ]


def write_fill_snapshot(
    *,
    path: Path,
    payload: dict[str, Any],
) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_fill_snapshot(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def fill_ats_form_pause(
    *,
    user_id: str,
    ats_url: str,
    resume_path: str | None,
    cover_letter_path: str | None = None,
    screenshot_path: str | None = None,
    snapshot_path: str | None = None,
    resume_overrides: dict[str, Any] | None = None,
    click_apply_first: bool = False,
    ensure_registered_form: bool = True,
    headless: bool | None = None,
    keep_open_ms: int = 0,
    restore_storage_state_path: str | None = None,
) -> dict[str, Any]:
    """Open company ATS form, fill from profile, hard-stop before Submit. Always reviewable.

    keep_open_ms > 0 leaves the browser open after fill (for 「查看表单」review) then closes.
    headless overrides settings.BROWSER_HEADLESS when set (open-form uses headed).
    restore_storage_state_path reuses cookies from a prior manual-register browser session.
    """
    url = (ats_url or "").strip()
    profile = build_profile_for_cart_item(
        user_id=user_id,
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
        resume_overrides=resume_overrides,
    )
    checklist = profile_checklist(profile)
    connector = connector_for(url)
    ats_type = str(getattr(connector, "ats_type", None) or "generic")

    live = bool(
        getattr(settings, "CART_APPLY_LIVE_ENTRY", False)
        or getattr(settings, "ALLOW_LIVE_BROWSER_FILL", False)
    )
    is_local = url.startswith("file:") or "fixture_workday" in url or "/artifacts/" in url

    base_review = {
        "profile_checklist": checklist,
        "filled_fields": checklist,
        "fill_plan": [],
        "ats_url": url,
        "ats_type": ats_type,
        "submitted": False,
        "paused_before_submit": True,
        "resume_path": profile.get("resume_path") or resume_path,
    }

    if not url:
        out = {**base_review, "ok": False, "error": "missing_ats_url", "method": "none"}
        if snapshot_path:
            out["fill_snapshot_path"] = write_fill_snapshot(path=Path(snapshot_path), payload=out)
        return out

    if not live and not is_local:
        out = {
            **base_review,
            "ok": True,
            "dry_run": True,
            "error": None,
            "method": "dry_run_profile_snapshot",
            "message": (
                "Live ATS fill blocked — saved reviewable profile snapshot only. "
                "Set CART_APPLY_LIVE_ENTRY=true to fill on the company site."
            ),
            "browser_fill": {"status": "blocked_live", "submitted": False, "paused_before_submit": True},
        }
        if snapshot_path:
            out["fill_snapshot_path"] = write_fill_snapshot(path=Path(snapshot_path), payload=out)
        return out

    if not (settings.ENABLE_BROWSER_FILL_PAUSE or settings.ENABLE_BROWSER_AUTOMATION):
        out = {
            **base_review,
            "ok": True,
            "dry_run": True,
            "method": "browser_fill_disabled",
            "message": "ENABLE_BROWSER_FILL_PAUSE is false — reviewable profile snapshot only.",
            "browser_fill": {"status": "browser_fill_disabled", "submitted": False, "paused_before_submit": True},
        }
        if snapshot_path:
            out["fill_snapshot_path"] = write_fill_snapshot(path=Path(snapshot_path), payload=out)
        return out

    from app.modules.application_engine.browser_session import BrowserSession
    from app.modules.application_engine.ats_account import create_or_sign_in_on_page, detect_account_wall, load_ats_credentials
    from app.modules.application_engine.ats_apply_entry import run_apply_autofill_on_page

    def _build_plan(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _tier_mappings(map_fields_rules(fields, profile))

    # For fixture / reopened sessions: may need entry+account before form is visible.
    # Prefer a single browser session via custom open when ensure_registered_form.
    browser_fill: dict[str, Any]
    try:
        from playwright.sync_api import sync_playwright

        timeout_ms = int(settings.BROWSER_TIMEOUT_MS or 30000)
        headless = bool(settings.BROWSER_HEADLESS) if headless is None else bool(headless)
        filled_from_browser: list[dict] = []
        plan: list[dict] = []
        scanned: list[dict] = []
        shot = None
        final_url = url
        submit_leaked = False
        storage_state_path: str | None = None
        if snapshot_path:
            storage_state_path = str(Path(snapshot_path).with_name(Path(snapshot_path).stem + "_storage.json"))
        elif screenshot_path:
            storage_state_path = str(Path(screenshot_path).with_name(Path(screenshot_path).stem + "_storage.json"))

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=headless, channel="chrome")
            except Exception:
                browser = playwright.chromium.launch(headless=headless)
            ctx_kwargs: dict[str, Any] = {}
            restore_path = (restore_storage_state_path or "").strip()
            if restore_path and Path(restore_path).is_file():
                ctx_kwargs["storage_state"] = restore_path
            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(600)

            if ensure_registered_form:
                from app.modules.application_engine.ats_account import detect_registered

                # If still on job posting / account wall, advance using Phase 3–4 helpers.
                # Skip re-auth when restored session already looks registered.
                stage = ""
                try:
                    stage = (page.locator("#stage").inner_text(timeout=300) or "").lower()
                except Exception:
                    stage = ""
                already_in = detect_registered(page) or ("registered" in stage)
                if (
                    not already_in
                    and "registered" not in stage
                    and not page.locator("[data-testid='application-form']").count()
                ):
                    if page.locator("[data-automation-id='jobPostingApplyButton']").count():
                        run_apply_autofill_on_page(page, resume_path=resume_path, click_apply=True)
                    if detect_account_wall(page) and not detect_registered(page):
                        creds = load_ats_credentials()
                        if creds.get("ok"):
                            create_or_sign_in_on_page(
                                page,
                                email=str(creds["email"]),
                                password=str(creds["password"]),
                                prefer="create",
                            )

            from app.modules.ats_connectors.dom_scan import scan_page_fields

            try:
                scanned = scan_page_fields(page)
            except Exception:
                scanned = []
            plan = _build_plan(scanned)
            session = BrowserSession()
            # Reuse private fill helpers via fill_plan execution path
            for item in plan:
                value = str(item.get("value") or "")
                action = item.get("action")
                if action in {"skip", "empty"} or not value.strip():
                    filled_from_browser.append(
                        {
                            "field": item.get("label") or item.get("profile_key") or item.get("field_id"),
                            "value": value,
                            "tier": item.get("tier") or "empty",
                            "status": "skipped",
                            "profile_key": item.get("profile_key"),
                        }
                    )
                    continue
                upload = (item.get("profile_key") or "") in {"resume_path", "cover_letter_path", "resume_upload"}
                try:
                    ok = session._fill_plan_item(page, item, value, upload=upload)
                except Exception:
                    ok = False
                filled_from_browser.append(
                    {
                        "field": item.get("label") or item.get("profile_key") or item.get("field_id"),
                        "value": value,
                        "tier": item.get("tier") or ("auto" if ok else "review"),
                        "status": "filled" if ok else "not_found",
                        "profile_key": item.get("profile_key"),
                        "confidence": item.get("confidence"),
                        "needs_review": item.get("needs_review"),
                    }
                )

            # HARD STOP — never click Submit Application
            try:
                marker = (page.locator("#msg").first.inner_text(timeout=400) or "").strip()
            except Exception:
                marker = ""
            submit_leaked = "SUBMITTED" in marker.upper()

            # Read back DOM values so 「查看表单」/tests can prove the official page is filled
            readback: dict[str, str] = {}
            for key, selectors in {
                "first_name": ["#first_name", "input[name='job_application[first_name]']", "input[autocomplete='given-name']"],
                "last_name": ["#last_name", "input[name='job_application[last_name]']", "input[autocomplete='family-name']"],
                "email": ["#email", "input[name='job_application[email]']", "input[type='email']"],
                "phone": ["#phone", "input[type='tel']"],
            }.items():
                for sel in selectors:
                    try:
                        v = (page.locator(sel).first.input_value(timeout=400) or "").strip()
                    except Exception:
                        v = ""
                    if v:
                        readback[key] = v
                        break

            if screenshot_path:
                Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                shot = screenshot_path
            final_url = page.url
            if storage_state_path:
                Path(storage_state_path).parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=storage_state_path)
            # Optional hold for human review on the official filled Submit page
            if keep_open_ms and keep_open_ms > 0:
                elapsed = 0
                step = 2000
                while elapsed < int(keep_open_ms) and browser.is_connected():
                    page.wait_for_timeout(step)
                    elapsed += step
            browser.close()

        browser_fill = {
            "status": "filled_paused_before_submit",
            "submitted": False,
            "paused_before_submit": True,
            "filled": filled_from_browser,
            "fill_plan": plan,
            "fields": scanned,
            "screenshot_path": shot,
            "submit_leaked": submit_leaked,
            "url": final_url,
            "form_url": final_url,
            "storage_state_path": storage_state_path,
            "ats_type": ats_type,
            "single_session": True,
            "dom_readback": readback,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("fill_ats_form_pause failed url=%s err=%s", url, exc)
        out = {
            **base_review,
            "ok": False,
            "error": str(exc),
            "method": "playwright_fill_pause",
            "browser_fill": {"status": "error", "submitted": False, "paused_before_submit": True},
        }
        if snapshot_path:
            out["fill_snapshot_path"] = write_fill_snapshot(path=Path(snapshot_path), payload=out)
        return out

    # Merge checklist + browser filled rows for flip-through
    filled_fields = list(checklist)
    for row in browser_fill.get("filled") or []:
        filled_fields.append(
            {
                "field": f"ats:{row.get('field')}",
                "value": row.get("value") or "",
                "tier": row.get("tier") or "review",
                "status": row.get("status"),
                "profile_key": row.get("profile_key"),
                "confidence": row.get("confidence"),
                "needs_review": row.get("needs_review"),
            }
        )

    ok = not bool(browser_fill.get("submit_leaked"))
    out = {
        "ok": ok,
        "error": "submit_leaked" if browser_fill.get("submit_leaked") else None,
        "method": "playwright_fill_pause",
        "profile_checklist": checklist,
        "filled_fields": filled_fields,
        "fill_plan": browser_fill.get("fill_plan") or [],
        "browser_fill": browser_fill,
        "ats_url": browser_fill.get("url") or url,
        "form_url": browser_fill.get("form_url") or browser_fill.get("url") or url,
        "storage_state_path": browser_fill.get("storage_state_path"),
        "dom_readback": browser_fill.get("dom_readback") or {},
        "ats_type": ats_type,
        "screenshot_path": browser_fill.get("screenshot_path"),
        "resume_path": profile.get("resume_path") or resume_path,
        "submitted": False,
        "paused_before_submit": True,
        "message": "Form filled on ATS and paused before Submit — review snapshot then one-click later.",
    }
    if snapshot_path:
        out["fill_snapshot_path"] = write_fill_snapshot(path=Path(snapshot_path), payload=out)
    return out


def open_filled_form_page(
    *,
    form_url: str,
    storage_state_path: str | None = None,
    keep_open_ms: int = 1_800_000,
    headless: bool = False,
    block: bool = False,
    # When set, re-fill the official ATS form from profile (cookies alone do not restore DOM values).
    user_id: str | None = None,
    resume_path: str | None = None,
    cover_letter_path: str | None = None,
    screenshot_path: str | None = None,
    snapshot_path: str | None = None,
    resume_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Open the official ATS page with the form filled again, pause before Submit.

    Greenhouse/Workday form field values are not in storage_state — so 「查看表单」
    re-applies the fill on the live company URL, then keeps a headed browser open.
    Never clicks Submit.
    """
    import threading

    url = (form_url or "").strip()
    if not url:
        return {"ok": False, "error": "missing_form_url", "opened": False}

    def _hold() -> dict[str, Any]:
        if user_id:
            return fill_ats_form_pause(
                user_id=str(user_id),
                ats_url=url,
                resume_path=resume_path,
                cover_letter_path=cover_letter_path,
                screenshot_path=screenshot_path,
                snapshot_path=snapshot_path,
                resume_overrides=resume_overrides,
                ensure_registered_form=True,
                headless=headless,
                keep_open_ms=keep_open_ms,
            )
        # Fallback: URL-only (may be blank form without refill)
        from playwright.sync_api import sync_playwright

        state_path = (storage_state_path or "").strip() or None
        if state_path and not Path(state_path).is_file():
            state_path = None
        try:
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(headless=headless, channel="chrome")
                except Exception:
                    browser = playwright.chromium.launch(headless=headless)
                kwargs: dict[str, Any] = {}
                if state_path:
                    kwargs["storage_state"] = state_path
                context = browser.new_context(**kwargs)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_timeout(800)
                elapsed = 0
                step = 2000
                while elapsed < max(5_000, int(keep_open_ms)) and browser.is_connected():
                    page.wait_for_timeout(step)
                    elapsed += step
                try:
                    browser.close()
                except Exception:
                    pass
            return {
                "ok": True,
                "form_url": url,
                "method": "headed_url_only",
                "session_restored": bool(state_path),
                "refilled": False,
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("open_filled_form_page fallback failed url=%s err=%s", url, exc)
            return {"ok": False, "error": str(exc), "form_url": url}

    result_box: dict[str, Any] = {"ok": True}

    def _runner() -> None:
        try:
            out = _hold()
            result_box.update(out if isinstance(out, dict) else {})
        except Exception as exc:  # noqa: BLE001
            result_box.update({"ok": False, "error": str(exc)})

    if block:
        _runner()
    else:
        threading.Thread(target=_runner, daemon=True, name="open-filled-ats-form").start()

    refilled = bool(user_id)
    return {
        "ok": True if not block else bool(result_box.get("ok")),
        "opened": True,
        "form_url": url,
        "session_restored": bool(storage_state_path),
        "storage_state_path": storage_state_path,
        "refilled": refilled,
        "method": "headed_refill_pause" if refilled else "headed_url_only",
        "keep_open_ms": keep_open_ms,
        "result": result_box if block else None,
        "message": (
            "Opened official ATS and re-filled the form for review (Submit not clicked). "
            if refilled
            else "Opened ATS URL (no refill — form may be blank)."
        ),
    }
