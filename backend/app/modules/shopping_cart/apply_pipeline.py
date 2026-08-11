"""Shopping-cart apply task model (Phase 1–5).

Status machine per cart item:
  idle → queued → navigating → on_ats → applying → registered → filled →
  ready_to_submit → submitted | failed

Phase 1 queues; Phase 2 → on_ats; Phase 3 Apply+Autofill; Phase 4 account;
Phase 5 form fill → ready_to_submit.
"""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.modules.shopping_cart import store

APPLY_STATUSES = (
    "idle",
    "queued",
    "navigating",
    "on_ats",
    "applying",
    "registered",
    "filled",
    "ready_to_submit",
    "submitted",
    "failed",
)

# Items must be at least ready_md (or confirmed) before apply can start.
_APPLY_ELIGIBLE = frozenset({"ready_md", "confirmed"})


def jobright_url_for(intern_job_id: str) -> str:
    template = (settings.JOBRIGHT_JOB_URL_TEMPLATE or "").strip()
    jid = str(intern_job_id or "").strip()
    if not template or not jid:
        return f"https://jobright.ai/jobs/info/{jid}" if jid else ""
    return template.replace("{intern_job_id}", jid)


def default_apply_payload(*, intern_job_id: str = "") -> dict[str, Any]:
    return {
        "status": "idle",
        "error": None,
        "jobright_url": jobright_url_for(intern_job_id),
        "ats_url": None,
        "ats_type": None,
        "updated_at": store.utcnow(),
        "timeline": [],
    }


def _ensure_apply(item: dict[str, Any]) -> dict[str, Any]:
    apply = item.get("apply")
    if not isinstance(apply, dict):
        apply = default_apply_payload(intern_job_id=str(item.get("intern_job_id") or ""))
    else:
        apply = {
            **default_apply_payload(intern_job_id=str(item.get("intern_job_id") or "")),
            **apply,
        }
        if not apply.get("jobright_url") and item.get("intern_job_id"):
            apply["jobright_url"] = jobright_url_for(str(item["intern_job_id"]))
    item["apply"] = apply
    return apply


def set_apply_status(
    *,
    cart_id: str,
    item_id: str,
    status: str,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
    clear_keys: list[str] | None = None,
) -> dict[str, Any]:
    if status not in APPLY_STATUSES:
        raise ValueError(f"invalid apply status: {status}")
    meta = store.load_cart_meta(cart_id)
    if not meta:
        raise ValueError("Cart not found")
    items = list(meta.get("items") or [])
    found = None
    for i, item in enumerate(items):
        if item.get("item_id") != item_id:
            continue
        apply = _ensure_apply(item)
        now = store.utcnow()
        timeline = list(apply.get("timeline") or [])
        timeline.append({"status": status, "at": now, "error": error})
        apply.update(
            {
                "status": status,
                "error": error,
                "updated_at": now,
                "timeline": timeline[-40:],
            }
        )
        for key in clear_keys or []:
            apply.pop(key, None)
        if extra:
            for k, v in extra.items():
                if v is not None:
                    apply[k] = v
        item["apply"] = apply
        items[i] = item
        found = item
        break
    if not found:
        raise ValueError("Item not found")
    meta["items"] = items
    meta["updated_at"] = store.utcnow()
    store.save_cart_meta(cart_id, meta)
    return found


def start_apply_batch(
    *,
    cart_id: str,
    user_id: str,
    item_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Queue apply tasks for eligible cart items. Phase 1: status → queued only."""
    meta = store.load_cart_meta(cart_id)
    if not meta:
        raise ValueError("Cart not found")
    if str(meta.get("user_id") or "") != str(user_id):
        raise ValueError("Cart user mismatch")

    wanted = {str(x).strip() for x in (item_ids or []) if str(x).strip()} or None
    queued: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for item in list(meta.get("items") or []):
        item_id = str(item.get("item_id") or "")
        if not item_id:
            continue
        if wanted is not None and item_id not in wanted:
            continue

        status = str(item.get("status") or "")
        apply = _ensure_apply(item)
        if status not in _APPLY_ELIGIBLE or not item.get("ok"):
            skipped.append(
                {
                    "item_id": item_id,
                    "reason": f"item status must be ready_md/confirmed (got {status or 'empty'})",
                }
            )
            continue
        if apply.get("status") in {
            "queued",
            "navigating",
            "on_ats",
            "applying",
            "registered",
            "filled",
            "ready_to_submit",
        }:
            skipped.append(
                {"item_id": item_id, "reason": f"already in progress ({apply.get('status')})"}
            )
            continue
        if apply.get("status") == "submitted":
            skipped.append({"item_id": item_id, "reason": "already submitted"})
            continue

        # Allow re-run from failed (clear prior error / phase flags and re-enter queue)
        was_failed = apply.get("status") == "failed"
        updated = set_apply_status(
            cart_id=cart_id,
            item_id=item_id,
            status="queued",
            error=None,
            clear_keys=(
                [
                    "phase3_done",
                    "phase4_done",
                    "phase5_done",
                    "autofill_clicked",
                    "apply_clicked",
                    "resume_attached",
                    "auth_mode",
                    "email_existed",
                    "fill_snapshot_path",
                    "filled_fields",
                    "profile_checklist",
                    "fill_plan",
                    "dry_run",
                    "form_url",
                    "storage_state_path",
                    "screenshot_path",
                    "needs_manual_register",
                    "manual_register_reason",
                    "manual_register_opened",
                    "register_storage_state_path",
                ]
                if was_failed
                else None
            ),
            extra={
                "jobright_url": jobright_url_for(str(item.get("intern_job_id") or "")),
                "note": "Queued — resolving ATS URL (Jobright Original Job Post / scrape)",
            },
        )
        queued.append(
            {
                "item_id": item_id,
                "intern_job_id": updated.get("intern_job_id"),
                "apply": updated.get("apply"),
            }
        )

    # Refresh meta after updates
    meta = store.load_cart_meta(cart_id) or meta
    apply_summary = summarize_apply(meta)
    meta["apply_summary"] = apply_summary
    meta["updated_at"] = store.utcnow()
    store.save_cart_meta(cart_id, meta)

    return {
        "cart_id": cart_id,
        "queued_count": len(queued),
        "skipped": skipped,
        "queued": queued,
        "apply_summary": apply_summary,
        "phase": 1,
        "message": "Apply tasks queued.",
    }


def summarize_apply(meta: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = dict.fromkeys(APPLY_STATUSES, 0)
    for item in meta.get("items") or []:
        apply = item.get("apply") if isinstance(item.get("apply"), dict) else {}
        st = str(apply.get("status") or "idle")
        if st not in counts:
            counts[st] = 0
        counts[st] += 1
    return {
        "counts": counts,
        "queued": counts.get("queued", 0),
        "navigating": counts.get("navigating", 0),
        "on_ats": counts.get("on_ats", 0),
        "applying": counts.get("applying", 0),
        "registered": counts.get("registered", 0),
        "filled": counts.get("filled", 0),
        "ready_to_submit": counts.get("ready_to_submit", 0),
        "failed": counts.get("failed", 0),
        "submitted": counts.get("submitted", 0),
    }


def enrich_cart_for_response(meta: dict[str, Any]) -> dict[str, Any]:
    """Ensure every item has an apply block before returning to clients."""
    items = []
    for item in meta.get("items") or []:
        row = dict(item)
        _ensure_apply(row)
        items.append(row)
    out = {**meta, "items": items}
    out["apply_summary"] = summarize_apply(out)
    return out
