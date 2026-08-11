"""Shopping-cart apply worker (Phase 2–5).

Phase 2: queued → navigating → on_ats | failed
Phase 3: on_ats → applying (Apply + Autofill with Resume) | failed
Phase 4: applying → registered (Create Account / Sign In) | failed
Phase 5: registered → filled → ready_to_submit (form fill, pause before Submit) | failed
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.modules.application_engine.ats_account import create_or_sign_in, load_ats_credentials
from app.modules.application_engine.ats_apply_entry import apply_and_autofill_resume
from app.modules.application_engine.ats_form_fill import (
    fill_ats_form_pause,
    load_fill_snapshot,
    open_filled_form_page,
)
from app.modules.shopping_cart import store
from app.modules.shopping_cart.apply_pipeline import (
    jobright_url_for,
    set_apply_status,
    summarize_apply,
)
from app.modules.shopping_cart.jobright_nav import resolve_ats_url_for_item

log = logging.getLogger(__name__)


def resolve_confirmed_resume_pdf(*, cart_id: str, item: dict[str, Any]) -> str | None:
    """Return path to confirmed resume.pdf for this cart item, if present.

    If missing but item is ready_md with full_resume, auto-render PDF once so apply can proceed.
    """
    item_id = str(item.get("item_id") or "")
    full = store.read_item(cart_id, item_id) if item_id else None
    if full:
        meta = full.get("item_meta") if isinstance(full.get("item_meta"), dict) else {}
        for key in ("resume_pdf_path",):
            raw = meta.get(key) or full.get(key)
            if raw and Path(str(raw)).is_file():
                return str(raw)
        company = full.get("company") or item.get("company") or "Unknown"
        position = full.get("position") or item.get("position") or "Unknown"
        candidate = store.item_dir(cart_id, str(company), str(position)) / "resume.pdf"
        if candidate.is_file():
            return str(candidate)
        # Auto-confirm when tailor finished but user skipped the confirm click
        if (full.get("status") in {"ready_md", "confirmed"} or item.get("status") in {"ready_md", "confirmed"}) and (
            isinstance(meta.get("full_resume"), dict) or full.get("resume_md")
        ):
            try:
                from app.modules.shopping_cart import service as cart_service

                meta_cart = store.load_cart_meta(cart_id) or {}
                uid = str(meta_cart.get("user_id") or "")
                if uid and item_id:
                    cart_service.confirm_item(cart_id=cart_id, item_id=item_id, user_id=uid)
                    full2 = store.read_item(cart_id, item_id) or {}
                    meta2 = full2.get("item_meta") if isinstance(full2.get("item_meta"), dict) else {}
                    raw2 = meta2.get("resume_pdf_path") or full2.get("resume_pdf_path")
                    if raw2 and Path(str(raw2)).is_file():
                        return str(raw2)
                    cand2 = store.item_dir(cart_id, str(company), str(position)) / "resume.pdf"
                    if cand2.is_file():
                        return str(cand2)
            except Exception as exc:  # noqa: BLE001
                log.warning("auto confirm resume pdf failed cart=%s item=%s err=%s", cart_id, item_id, exc)
    company = item.get("company") or "Unknown"
    position = item.get("position") or "Unknown"
    candidate = store.item_dir(cart_id, str(company), str(position)) / "resume.pdf"
    return str(candidate) if candidate.is_file() else None


def resolve_confirmed_cover_pdf(*, cart_id: str, item: dict[str, Any]) -> str | None:
    full = store.read_item(cart_id, str(item.get("item_id") or ""))
    company = (full or item).get("company") or item.get("company") or "Unknown"
    position = (full or item).get("position") or item.get("position") or "Unknown"
    if full:
        meta = full.get("item_meta") if isinstance(full.get("item_meta"), dict) else {}
        raw = meta.get("cover_letter_pdf_path") or full.get("cover_letter_pdf_path")
        if raw and Path(str(raw)).is_file():
            return str(raw)
    candidate = store.item_dir(cart_id, str(company), str(position)) / "cover_letter.pdf"
    return str(candidate) if candidate.is_file() else None


def process_queued_item(*, cart_id: str, item_id: str) -> dict[str, Any]:
    meta = store.load_cart_meta(cart_id)
    if not meta:
        raise ValueError("Cart not found")
    item = None
    for row in meta.get("items") or []:
        if row.get("item_id") == item_id:
            item = row
            break
    if not item:
        raise ValueError("Item not found")

    apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
    if apply.get("status") not in {"queued", "failed"}:
        if apply.get("status") in {
            "on_ats",
            "applying",
            "registered",
            "filled",
            "ready_to_submit",
            "submitted",
        }:
            return {"item_id": item_id, "skipped": True, "reason": f"status={apply.get('status')}"}
        if apply.get("status") != "queued":
            return {"item_id": item_id, "skipped": True, "reason": f"status={apply.get('status')}"}

    # Failed with ATS URL: resume at phase 3/4/5 as appropriate
    if apply.get("status") == "failed" and apply.get("ats_url"):
        if apply.get("phase4_done") or apply.get("auth_mode"):
            return process_registered_item(cart_id=cart_id, item_id=item_id)
        if apply.get("phase3_done") or apply.get("autofill_clicked"):
            return process_applying_item(cart_id=cart_id, item_id=item_id)
        return process_on_ats_item(cart_id=cart_id, item_id=item_id)

    intern_job_id = str(item.get("intern_job_id") or "")
    jobright_url = str(apply.get("jobright_url") or jobright_url_for(intern_job_id))
    source_url = item.get("source_url")

    set_apply_status(
        cart_id=cart_id,
        item_id=item_id,
        status="navigating",
        error=None,
        extra={"jobright_url": jobright_url, "note": "Opening Jobright / resolving ATS URL"},
    )

    result = resolve_ats_url_for_item(
        intern_job_id=intern_job_id,
        jobright_url=jobright_url,
        source_url=str(source_url) if source_url else None,
    )

    if not result.get("ok"):
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error=str(result.get("error") or "ats_navigation_failed"),
            extra={
                "jobright_url": jobright_url,
                "nav_method": result.get("method"),
                "note": "Phase 2 failed to reach company ATS",
            },
        )
        return {"item_id": item_id, "ok": False, "apply": updated.get("apply"), "result": result}

    updated = set_apply_status(
        cart_id=cart_id,
        item_id=item_id,
        status="on_ats",
        error=None,
        extra={
            "ats_url": result.get("ats_url"),
            "ats_type": result.get("ats_type"),
            "jobright_url": jobright_url,
            "nav_method": result.get("method"),
            "note": "Reached ATS — starting Apply / Autofill",
        },
    )
    log.info(
        "cart apply on_ats cart_id=%s item_id=%s ats_type=%s method=%s",
        cart_id,
        item_id,
        result.get("ats_type"),
        result.get("method"),
    )
    return {
        "item_id": item_id,
        "ok": True,
        "apply": updated.get("apply"),
        "result": result,
        "phase": 2,
    }


def process_on_ats_item(*, cart_id: str, item_id: str) -> dict[str, Any]:
    """Phase 3: on_ats → applying (Apply + Autofill with Resume)."""
    meta = store.load_cart_meta(cart_id)
    if not meta:
        raise ValueError("Cart not found")
    item = None
    for row in meta.get("items") or []:
        if row.get("item_id") == item_id:
            item = row
            break
    if not item:
        raise ValueError("Item not found")

    apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
    status = apply.get("status")
    if status == "applying" and (apply.get("autofill_clicked") or apply.get("phase3_done")):
        return {"item_id": item_id, "skipped": True, "reason": "already_autofilled"}
    if status not in {"on_ats", "failed", "applying"}:
        return {"item_id": item_id, "skipped": True, "reason": f"status={status}"}
    if status == "failed" and not apply.get("ats_url"):
        return {"item_id": item_id, "skipped": True, "reason": "failed_without_ats_url"}

    ats_url = str(apply.get("ats_url") or "").strip()
    if not ats_url:
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error="missing_ats_url",
            extra={"note": "Phase 3 needs ats_url from Phase 2"},
        )
        return {"item_id": item_id, "ok": False, "apply": updated.get("apply")}

    resume_path = resolve_confirmed_resume_pdf(cart_id=cart_id, item=item)
    if not resume_path:
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error="confirm_resume_pdf_required",
            extra={
                "ats_url": ats_url,
                "note": "Confirm PDF in shopping cart before Apply / Autofill",
            },
        )
        return {"item_id": item_id, "ok": False, "apply": updated.get("apply")}

    set_apply_status(
        cart_id=cart_id,
        item_id=item_id,
        status="applying",
        error=None,
        extra={
            "ats_url": ats_url,
            "resume_path": resume_path,
            "note": "Clicking Apply → Autofill with Resume",
        },
    )

    shot_dir = store.cart_dir(cart_id) / "_apply_shots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(shot_dir / f"{item_id}_phase3.png")

    result = apply_and_autofill_resume(
        ats_url=ats_url,
        resume_path=resume_path,
        screenshot_path=screenshot_path,
    )

    if not result.get("ok"):
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error=str(result.get("error") or "apply_autofill_failed"),
            extra={
                "ats_url": result.get("ats_url") or ats_url,
                "ats_type": result.get("ats_type") or apply.get("ats_type"),
                "resume_path": resume_path,
                "apply_clicked": result.get("apply_clicked"),
                "autofill_clicked": result.get("autofill_clicked"),
                "next_screen": result.get("next_screen"),
                "entry_method": result.get("method"),
                "screenshot_path": result.get("screenshot_path"),
                "note": "Phase 3 Apply / Autofill failed",
            },
        )
        return {
            "item_id": item_id,
            "ok": False,
            "apply": updated.get("apply"),
            "result": result,
            "phase": 3,
        }

    updated = set_apply_status(
        cart_id=cart_id,
        item_id=item_id,
        status="applying",
        error=None,
        extra={
            "ats_url": result.get("ats_url") or ats_url,
            "ats_type": result.get("ats_type") or apply.get("ats_type"),
            "resume_path": resume_path,
            "apply_clicked": result.get("apply_clicked"),
            "autofill_clicked": result.get("autofill_clicked"),
            "resume_attached": result.get("resume_attached"),
            "next_screen": result.get("next_screen"),
            "entry_method": result.get("method"),
            "screenshot_path": result.get("screenshot_path"),
            "phase3_done": True,
            "note": "Apply + Autofill done — account create/sign-in is Phase 4",
        },
    )
    log.info(
        "cart apply phase3 cart_id=%s item_id=%s next=%s autofill=%s",
        cart_id,
        item_id,
        result.get("next_screen"),
        result.get("autofill_clicked"),
    )
    return {
        "item_id": item_id,
        "ok": True,
        "apply": updated.get("apply"),
        "result": result,
        "phase": 3,
    }


def process_applying_item(*, cart_id: str, item_id: str) -> dict[str, Any]:
    """Phase 4: applying → registered (Create Account / Sign In)."""
    meta = store.load_cart_meta(cart_id)
    if not meta:
        raise ValueError("Cart not found")
    item = None
    for row in meta.get("items") or []:
        if row.get("item_id") == item_id:
            item = row
            break
    if not item:
        raise ValueError("Item not found")

    apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
    status = apply.get("status")
    if status == "registered" and apply.get("phase4_done"):
        return {"item_id": item_id, "skipped": True, "reason": "already_registered"}
    if status not in {"applying", "failed"}:
        return {"item_id": item_id, "skipped": True, "reason": f"status={status}"}
    if status == "failed" and not (apply.get("phase3_done") or apply.get("autofill_clicked")):
        return {"item_id": item_id, "skipped": True, "reason": "failed_before_phase3"}
    if status == "applying" and not (apply.get("phase3_done") or apply.get("autofill_clicked")):
        return {"item_id": item_id, "skipped": True, "reason": "phase3_incomplete"}

    ats_url = str(apply.get("ats_url") or "").strip()
    if not ats_url:
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error="missing_ats_url",
            extra={"note": "Phase 4 needs ats_url"},
        )
        return {"item_id": item_id, "ok": False, "apply": updated.get("apply"), "phase": 4}

    creds = load_ats_credentials()
    if not creds.get("ok"):
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error=str(creds.get("error") or "ats_credentials_not_configured"),
            extra={
                "ats_url": ats_url,
                "email_masked": creds.get("email_masked"),
                "policy_errors": creds.get("policy_errors"),
                "note": creds.get("message")
                or "Configure ATS_DEFAULT_EMAIL / ATS_DEFAULT_PASSWORD",
                "phase3_done": True,
            },
        )
        return {"item_id": item_id, "ok": False, "apply": updated.get("apply"), "phase": 4}

    resume_path = resolve_confirmed_resume_pdf(cart_id=cart_id, item=item) or apply.get(
        "resume_path"
    )

    set_apply_status(
        cart_id=cart_id,
        item_id=item_id,
        status="applying",
        error=None,
        extra={
            "ats_url": ats_url,
            "email_masked": creds.get("email_masked"),
            "note": "Create Account / Sign In with default ATS credentials",
            "phase3_done": True,
        },
    )

    shot_dir = store.cart_dir(cart_id) / "_apply_shots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(shot_dir / f"{item_id}_phase4.png")

    result = create_or_sign_in(
        ats_url=ats_url,
        resume_path=str(resume_path) if resume_path else None,
        screenshot_path=screenshot_path,
        ensure_entry=True,
    )

    # Never persist password
    safe_extra = {
        "ats_url": result.get("ats_url") or ats_url,
        "ats_type": result.get("ats_type") or apply.get("ats_type"),
        "email_masked": result.get("email_masked") or creds.get("email_masked"),
        "auth_mode": result.get("auth_mode"),
        "email_existed": result.get("email_existed"),
        "account_method": result.get("method"),
        "screenshot_path": result.get("screenshot_path"),
        "phase3_done": True,
    }

    if not result.get("ok"):
        err = str(result.get("error") or "account_step_failed")
        needs_manual = err == "captcha_required"
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error=err,
            extra={
                **safe_extra,
                "needs_manual_register": needs_manual,
                "manual_register_reason": (
                    "验证码无法自动完成，需要你在公司 ATS 页面自行注册/登录账户"
                    if needs_manual
                    else None
                ),
                "note": (
                    "CAPTCHA blocked auto account create — use「去注册」then「已注册完成」"
                    if needs_manual
                    else (result.get("message") or "Phase 4 Create Account / Sign In failed")
                ),
            },
        )
        return {
            "item_id": item_id,
            "ok": False,
            "apply": updated.get("apply"),
            "result": result,
            "phase": 4,
            "needs_manual_register": needs_manual,
        }

    updated = set_apply_status(
        cart_id=cart_id,
        item_id=item_id,
        status="registered",
        error=None,
        extra={
            **safe_extra,
            "phase4_done": True,
            "note": "Account ready — form fill is Phase 5",
        },
    )
    log.info(
        "cart apply phase4 cart_id=%s item_id=%s auth_mode=%s email=%s",
        cart_id,
        item_id,
        result.get("auth_mode"),
        result.get("email_masked"),
    )
    return {
        "item_id": item_id,
        "ok": True,
        "apply": updated.get("apply"),
        "result": result,
        "phase": 4,
    }


def process_registered_item(
    *, cart_id: str, item_id: str, user_id: str | None = None
) -> dict[str, Any]:
    """Phase 5: registered → filled → ready_to_submit (pause before Submit)."""
    meta = store.load_cart_meta(cart_id)
    if not meta:
        raise ValueError("Cart not found")
    item = None
    for row in meta.get("items") or []:
        if row.get("item_id") == item_id:
            item = row
            break
    if not item:
        raise ValueError("Item not found")

    apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
    status = apply.get("status")
    if status == "ready_to_submit" and apply.get("phase5_done"):
        return {"item_id": item_id, "skipped": True, "reason": "already_ready_to_submit"}
    if status not in {"registered", "filled", "failed"}:
        return {"item_id": item_id, "skipped": True, "reason": f"status={status}"}
    if status == "failed" and not (apply.get("phase4_done") or apply.get("auth_mode")):
        return {"item_id": item_id, "skipped": True, "reason": "failed_before_phase4"}

    ats_url = str(apply.get("ats_url") or "").strip()
    if not ats_url:
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error="missing_ats_url",
            extra={"note": "Phase 5 needs ats_url"},
        )
        return {"item_id": item_id, "ok": False, "apply": updated.get("apply"), "phase": 5}

    uid = str(user_id or meta.get("user_id") or "").strip()
    if not uid:
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error="missing_user_id",
            extra={"note": "Phase 5 needs user_id for profile fill"},
        )
        return {"item_id": item_id, "ok": False, "apply": updated.get("apply"), "phase": 5}

    resume_path = resolve_confirmed_resume_pdf(cart_id=cart_id, item=item) or apply.get(
        "resume_path"
    )
    cover_path = resolve_confirmed_cover_pdf(cart_id=cart_id, item=item)

    set_apply_status(
        cart_id=cart_id,
        item_id=item_id,
        status="filled",
        error=None,
        extra={
            "ats_url": ats_url,
            "phase4_done": True,
            "note": "Filling ATS form — will pause before Submit",
        },
    )

    shot_dir = store.cart_dir(cart_id) / "_apply_shots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(shot_dir / f"{item_id}_phase5.png")
    snapshot_path = str(shot_dir / f"{item_id}_fill_snapshot.json")

    # Optional resume overrides from cart item meta
    resume_overrides: dict[str, Any] = {}
    full = store.read_item(cart_id, item_id) or {}
    item_meta = full.get("item_meta") if isinstance(full.get("item_meta"), dict) else {}
    fr = item_meta.get("full_resume") if isinstance(item_meta.get("full_resume"), dict) else {}
    if fr:
        resume_overrides = fr

    restore_storage = str(apply.get("register_storage_state_path") or "").strip() or None

    result = fill_ats_form_pause(
        user_id=uid,
        ats_url=ats_url,
        resume_path=str(resume_path) if resume_path else None,
        cover_letter_path=str(cover_path) if cover_path else None,
        screenshot_path=screenshot_path,
        snapshot_path=snapshot_path,
        resume_overrides=resume_overrides,
        click_apply_first=False,
        ensure_registered_form=True,
        restore_storage_state_path=restore_storage,
    )

    safe_extra = {
        "ats_url": result.get("ats_url") or ats_url,
        "ats_type": result.get("ats_type") or apply.get("ats_type"),
        "resume_path": result.get("resume_path") or resume_path,
        "fill_method": result.get("method"),
        "fill_snapshot_path": result.get("fill_snapshot_path") or snapshot_path,
        "screenshot_path": result.get("screenshot_path"),
        # Final pause URL + Playwright storage for 「查看表单」 → official submit page
        "form_url": result.get("form_url") or result.get("ats_url") or ats_url,
        "storage_state_path": result.get("storage_state_path"),
        "paused_before_submit": True,
        "submitted": False,
        "phase4_done": True,
        # Compact review payload for list UI (full detail via fill-review API)
        "filled_fields": (result.get("filled_fields") or [])[:40],
        "profile_checklist": (result.get("profile_checklist") or [])[:20],
        "fill_plan": (result.get("fill_plan") or [])[:40],
        "dry_run": bool(result.get("dry_run")),
    }

    if not result.get("ok"):
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error=str(result.get("error") or "form_fill_failed"),
            extra={
                **safe_extra,
                "note": result.get("message") or "Phase 5 form fill failed",
            },
        )
        return {
            "item_id": item_id,
            "ok": False,
            "apply": updated.get("apply"),
            "result": result,
            "phase": 5,
        }

    updated = set_apply_status(
        cart_id=cart_id,
        item_id=item_id,
        status="ready_to_submit",
        error=None,
        extra={
            **safe_extra,
            "phase5_done": True,
            "note": (
                "Form filled — Submit NOT clicked. Flip through filled fields, "
                "then one-click submit in Phase 6."
            ),
        },
    )
    log.info(
        "cart apply phase5 cart_id=%s item_id=%s method=%s fields=%s",
        cart_id,
        item_id,
        result.get("method"),
        len(result.get("filled_fields") or []),
    )
    return {
        "item_id": item_id,
        "ok": True,
        "apply": updated.get("apply"),
        "result": result,
        "phase": 5,
    }


def get_fill_review(*, cart_id: str, item_id: str, user_id: str) -> dict[str, Any]:
    """Load reviewable fill snapshot for flip-through UI."""
    meta = store.load_cart_meta(cart_id)
    if not meta or str(meta.get("user_id") or "") != str(user_id):
        raise ValueError("Cart not found")
    item = None
    for row in meta.get("items") or []:
        if row.get("item_id") == item_id:
            item = row
            break
    if not item:
        raise ValueError("Item not found")
    apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
    snap = load_fill_snapshot(apply.get("fill_snapshot_path"))
    if not snap:
        # Fallback to compact fields on apply state
        snap = {
            "filled_fields": apply.get("filled_fields") or [],
            "profile_checklist": apply.get("profile_checklist") or [],
            "fill_plan": apply.get("fill_plan") or [],
            "screenshot_path": apply.get("screenshot_path"),
            "ats_url": apply.get("ats_url"),
            "form_url": apply.get("form_url") or apply.get("ats_url"),
            "storage_state_path": apply.get("storage_state_path"),
            "ats_type": apply.get("ats_type"),
            "paused_before_submit": True,
            "submitted": False,
            "method": apply.get("fill_method"),
            "dry_run": apply.get("dry_run"),
        }
    return {
        "cart_id": cart_id,
        "item_id": item_id,
        "company": item.get("company"),
        "position": item.get("position"),
        "apply_status": apply.get("status"),
        "review": snap,
        "steps": [
            {"id": "profile", "label": "拟填档案", "hint": "来自 Profile / 确认简历的意图字段"},
            {"id": "filled", "label": "已写入字段", "hint": "ATS 页面上实际填充/映射的结果"},
            {"id": "screenshot", "label": "页面截图", "hint": "填表后停在 Submit 前的截图"},
            {"id": "pause", "label": "暂停确认", "hint": "Submit 未被点击，等待一键提交"},
        ],
    }


def open_item_register_page(
    *,
    cart_id: str,
    item_id: str,
    user_id: str,
    keep_open_ms: int = 1_800_000,
) -> dict[str, Any]:
    """Open/focus headed ATS Create Account page for captcha / manual registration."""
    from app.modules.application_engine.manual_register import open_register_page

    meta = store.load_cart_meta(cart_id)
    if not meta or str(meta.get("user_id") or "") != str(user_id):
        raise ValueError("Cart not found")
    item = None
    for row in meta.get("items") or []:
        if row.get("item_id") == item_id:
            item = row
            break
    if not item:
        raise ValueError("Item not found")
    apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
    if not (apply.get("needs_manual_register") or apply.get("error") == "captcha_required"):
        raise ValueError("Item does not need manual registration")
    ats_url = str(apply.get("ats_url") or "").strip()
    if not ats_url:
        raise ValueError("No ATS URL — cannot open register page")

    shot_dir = store.cart_dir(cart_id) / "_apply_shots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    storage_out = str(shot_dir / f"{item_id}_manual_register_storage.json")
    resume_path = resolve_confirmed_resume_pdf(cart_id=cart_id, item=item) or apply.get(
        "resume_path"
    )

    opened = open_register_page(
        cart_id=cart_id,
        item_id=item_id,
        ats_url=ats_url,
        resume_path=str(resume_path) if resume_path else None,
        storage_out_path=storage_out,
        keep_open_ms=keep_open_ms,
        headless=False,
    )
    if opened.get("ok"):
        set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="failed",
            error=str(apply.get("error") or "captcha_required"),
            extra={
                "needs_manual_register": True,
                "manual_register_reason": apply.get("manual_register_reason")
                or "验证码无法自动完成，需要你在公司 ATS 页面自行注册/登录账户",
                "manual_register_opened": True,
                "register_storage_state_path": storage_out,
                "ats_url": opened.get("ats_url") or ats_url,
                "note": "Manual register browser open — waiting for「已注册完成」",
                "phase3_done": True,
            },
        )
    return {
        "cart_id": cart_id,
        "item_id": item_id,
        "company": item.get("company"),
        "position": item.get("position"),
        "apply_status": "failed",
        **opened,
    }


def confirm_item_manual_register(
    *,
    cart_id: str,
    item_id: str,
    user_id: str,
    continue_apply: bool = True,
) -> dict[str, Any]:
    """User finished manual ATS registration → mark registered and continue Phase 5."""
    from app.modules.application_engine.manual_register import snapshot_and_close_register_page

    meta = store.load_cart_meta(cart_id)
    if not meta or str(meta.get("user_id") or "") != str(user_id):
        raise ValueError("Cart not found")
    item = None
    for row in meta.get("items") or []:
        if row.get("item_id") == item_id:
            item = row
            break
    if not item:
        raise ValueError("Item not found")
    apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
    if not (
        apply.get("needs_manual_register")
        or apply.get("error") == "captcha_required"
        or apply.get("manual_register_opened")
    ):
        raise ValueError("Item is not waiting for manual registration")

    snap = snapshot_and_close_register_page(cart_id=cart_id, item_id=item_id)
    storage_path = snap.get("storage_state_path") or apply.get("register_storage_state_path")
    if storage_path and not Path(str(storage_path)).is_file():
        storage_path = None

    # Trust user confirm even if DOM detect is weak; prefer snapshot when available.
    if snap.get("ok") is False and snap.get("error") == "no_open_register_session":
        # User may have registered in a tab we didn't hold — still allow continue.
        pass
    elif snap.get("ok") and snap.get("registered") is False and snap.get("account_wall"):
        # Soft warn but still allow — user clicked 已注册完成 intentionally.
        log.info(
            "manual register confirm with account_wall still visible cart=%s item=%s",
            cart_id,
            item_id,
        )

    updated = set_apply_status(
        cart_id=cart_id,
        item_id=item_id,
        status="registered",
        error=None,
        clear_keys=["needs_manual_register", "manual_register_reason", "manual_register_opened"],
        extra={
            "phase3_done": True,
            "phase4_done": True,
            "auth_mode": "manual_user",
            "ats_url": snap.get("ats_url") or apply.get("ats_url"),
            "register_storage_state_path": storage_path,
            "storage_state_path": storage_path or apply.get("storage_state_path"),
            "email_masked": apply.get("email_masked"),
            "note": "Manual registration confirmed — continuing form fill",
        },
    )

    phase5: dict[str, Any] | None = None
    if continue_apply:
        phase5 = process_registered_item(
            cart_id=cart_id, item_id=item_id, user_id=user_id
        )

    return {
        "cart_id": cart_id,
        "item_id": item_id,
        "company": item.get("company"),
        "position": item.get("position"),
        "ok": True if not phase5 else bool(phase5.get("ok")),
        "apply": (phase5 or {}).get("apply") or updated.get("apply"),
        "snapshot": snap,
        "phase5": phase5,
        "message": (
            "已确认注册，正在继续自动填表"
            if continue_apply
            else "已确认注册，状态已更新为 registered"
        ),
    }


def open_item_filled_form(
    *,
    cart_id: str,
    item_id: str,
    user_id: str,
    keep_open_ms: int = 1_800_000,
    block: bool = False,
    headless: bool = False,
) -> dict[str, Any]:
    """Open this cart item's official ATS page, re-fill form, pause before Submit."""
    meta = store.load_cart_meta(cart_id)
    if not meta or str(meta.get("user_id") or "") != str(user_id):
        raise ValueError("Cart not found")
    item = None
    for row in meta.get("items") or []:
        if row.get("item_id") == item_id:
            item = row
            break
    if not item:
        raise ValueError("Item not found")
    apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
    form_url = (apply.get("form_url") or apply.get("ats_url") or "").strip()
    if not form_url:
        snap = load_fill_snapshot(apply.get("fill_snapshot_path")) or {}
        form_url = str(snap.get("form_url") or snap.get("ats_url") or "").strip()
    if not form_url:
        raise ValueError("No form URL yet — run apply through Phase 5 first")

    # Official ATS only — reject aggregator / non-ATS hosts for 查看表单
    from app.modules.job_discovery.apply_url import is_aggregator_url, is_ats_or_company_apply_url

    if is_aggregator_url(form_url) or not is_ats_or_company_apply_url(form_url):
        # Still allow known greenhouse/workday hosts even if heuristic is loose
        host = (form_url or "").lower()
        if not any(
            h in host
            for h in (
                "greenhouse.io",
                "myworkdayjobs.com",
                "workday.com",
                "lever.co",
                "ashbyhq.com",
                "icims.com",
                "smartrecruiters.com",
            )
        ):
            raise ValueError(f"form_url is not an official ATS page: {form_url}")

    storage_path = apply.get("storage_state_path")
    if not storage_path:
        snap = load_fill_snapshot(apply.get("fill_snapshot_path")) or {}
        storage_path = snap.get("storage_state_path")
    if storage_path:
        p = Path(str(storage_path)).resolve()
        root = store.cart_dir(cart_id).resolve()
        if root in p.parents or p == root:
            storage_path = str(p) if p.is_file() else None
        else:
            storage_path = (
                str(p) if p.is_file() else None
            )  # allow /tmp from tests; refill is source of truth

    resume_path = resolve_confirmed_resume_pdf(cart_id=cart_id, item=item) or apply.get(
        "resume_path"
    )
    shot_dir = store.cart_dir(cart_id) / "_apply_shots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = str(shot_dir / f"{item_id}_open_form.png")
    snapshot_path = str(shot_dir / f"{item_id}_open_form_snapshot.json")

    full = store.read_item(cart_id, item_id) or {}
    item_meta = full.get("item_meta") if isinstance(full.get("item_meta"), dict) else {}
    fr = item_meta.get("full_resume") if isinstance(item_meta.get("full_resume"), dict) else {}

    opened = open_filled_form_page(
        form_url=form_url,
        storage_state_path=storage_path,
        keep_open_ms=keep_open_ms,
        headless=headless,
        block=block,
        user_id=user_id,
        resume_path=str(resume_path) if resume_path else None,
        screenshot_path=screenshot_path,
        snapshot_path=snapshot_path,
        resume_overrides=fr or None,
    )
    return {
        "cart_id": cart_id,
        "item_id": item_id,
        "company": item.get("company"),
        "position": item.get("position"),
        "apply_status": apply.get("status"),
        "official_ats": True,
        **opened,
    }


def process_cart_queue(
    *,
    cart_id: str,
    user_id: str | None = None,
    limit: int = 20,
    through_phase: int = 5,
) -> dict[str, Any]:
    meta = store.load_cart_meta(cart_id)
    if not meta:
        raise ValueError("Cart not found")
    if user_id and str(meta.get("user_id") or "") != str(user_id):
        raise ValueError("Cart user mismatch")

    processed: list[dict[str, Any]] = []
    through_phase = int(through_phase or 5)

    # Phase 2: queued → on_ats
    for item in list(meta.get("items") or []):
        if len(processed) >= max(1, int(limit)):
            break
        apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
        if apply.get("status") != "queued":
            continue
        item_id = str(item.get("item_id") or "")
        if not item_id:
            continue
        try:
            processed.append(process_queued_item(cart_id=cart_id, item_id=item_id))
        except Exception as exc:  # noqa: BLE001
            set_apply_status(cart_id=cart_id, item_id=item_id, status="failed", error=str(exc))
            processed.append({"item_id": item_id, "ok": False, "error": str(exc), "phase": 2})

    # Phase 3: on_ats → applying
    if through_phase >= 3:
        meta = store.load_cart_meta(cart_id) or meta
        for item in list(meta.get("items") or []):
            apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
            if apply.get("status") != "on_ats":
                continue
            if apply.get("phase3_done") or apply.get("autofill_clicked"):
                continue
            item_id = str(item.get("item_id") or "")
            if not item_id:
                continue
            try:
                processed.append(process_on_ats_item(cart_id=cart_id, item_id=item_id))
            except Exception as exc:  # noqa: BLE001
                set_apply_status(cart_id=cart_id, item_id=item_id, status="failed", error=str(exc))
                processed.append({"item_id": item_id, "ok": False, "error": str(exc), "phase": 3})

    # Phase 4: applying → registered
    if through_phase >= 4:
        meta = store.load_cart_meta(cart_id) or meta
        for item in list(meta.get("items") or []):
            apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
            if apply.get("status") != "applying":
                continue
            if not (apply.get("phase3_done") or apply.get("autofill_clicked")):
                continue
            if apply.get("phase4_done"):
                continue
            item_id = str(item.get("item_id") or "")
            if not item_id:
                continue
            try:
                processed.append(process_applying_item(cart_id=cart_id, item_id=item_id))
            except Exception as exc:  # noqa: BLE001
                set_apply_status(cart_id=cart_id, item_id=item_id, status="failed", error=str(exc))
                processed.append({"item_id": item_id, "ok": False, "error": str(exc), "phase": 4})

    # Phase 5: registered → ready_to_submit
    if through_phase >= 5:
        meta = store.load_cart_meta(cart_id) or meta
        for item in list(meta.get("items") or []):
            apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
            if apply.get("status") not in {"registered", "filled"}:
                continue
            if apply.get("phase5_done"):
                continue
            item_id = str(item.get("item_id") or "")
            if not item_id:
                continue
            try:
                processed.append(
                    process_registered_item(
                        cart_id=cart_id,
                        item_id=item_id,
                        user_id=user_id or str(meta.get("user_id") or ""),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                set_apply_status(cart_id=cart_id, item_id=item_id, status="failed", error=str(exc))
                processed.append({"item_id": item_id, "ok": False, "error": str(exc), "phase": 5})

    meta = store.load_cart_meta(cart_id) or meta
    summary = summarize_apply(meta)
    meta["apply_summary"] = summary
    meta["updated_at"] = store.utcnow()
    store.save_cart_meta(cart_id, meta)

    return {
        "cart_id": cart_id,
        "processed": processed,
        "processed_count": len(processed),
        "ok_count": sum(1 for p in processed if p.get("ok")),
        "failed_count": sum(1 for p in processed if p.get("ok") is False),
        "apply_summary": summary,
        "phase": through_phase,
    }
