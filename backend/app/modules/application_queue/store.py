"""Application queue: multi-job fill → pause → per-item user confirm Submit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app import db
from app.modules.safety.audit_log import audit

QUEUE_DIR = Path(__file__).resolve().parents[4] / "data" / "application_queue"
QUEUE_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _row_path(item_id: str) -> Path:
    return QUEUE_DIR / f"{item_id}.json"


def enqueue(
    *,
    user_id: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enqueue one or more jobs. Does not start fill until process_item."""
    created: list[dict[str, Any]] = []
    for raw in items:
        job_id = str(raw.get("job_id") or "").strip() or None
        version_id = str(raw.get("version_id") or "").strip() or None
        source_url = str(raw.get("source_url") or "").strip() or None
        company = str(raw.get("company") or "").strip() or None
        position = str(raw.get("position") or "").strip() or None
        item_id = str(uuid4())
        payload = {
            "id": item_id,
            "user_id": user_id,
            "job_id": job_id,
            "version_id": version_id,
            "source_url": source_url,
            "company": company,
            "position": position,
            "fill_status": "queued",
            "awaiting_confirm": False,
            "apply_id": None,
            "submitted_at": None,
            "skipped_at": None,
            "error": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        _row_path(item_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        db.upsert_application_queue_item(payload)
        created.append(payload)
    try:
        audit(user_id, "queue_enqueue", {"count": len(created), "ids": [c["id"] for c in created]})
    except Exception:
        pass
    return created


def get_item(item_id: str) -> dict[str, Any] | None:
    path = _row_path(item_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return db.get_application_queue_item(item_id)


def list_items(user_id: str) -> list[dict[str, Any]]:
    rows = db.list_application_queue(user_id)
    if rows:
        return rows
    # Fallback: scan files
    out: list[dict[str, Any]] = []
    for path in sorted(QUEUE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(data.get("user_id")) == str(user_id):
            out.append(data)
    return out


def _save(payload: dict[str, Any]) -> dict[str, Any]:
    payload["updated_at"] = _now()
    _row_path(payload["id"]).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    db.upsert_application_queue_item(payload)
    return payload


def process_item(*, item_id: str, user_id: str) -> dict[str, Any]:
    """Run auto apply fill-pause for one queue row. Never clicks Submit."""
    item = get_item(item_id)
    if not item:
        raise ValueError("Queue item not found")
    if str(item.get("user_id")) != str(user_id):
        raise ValueError("Queue item does not belong to this user")
    if item.get("fill_status") in {"awaiting_confirm", "submitted", "skipped"}:
        return item
    version_id = item.get("version_id")
    if not version_id:
        raise ValueError("version_id required before process — tailor & confirm first")

    from app.modules.resume_workspace.apply_flow import start_apply

    item["fill_status"] = "filling"
    _save(item)

    try:
        apply_payload = start_apply(
            user_id=user_id,
            version_id=version_id,
            mode="auto",
            company=item.get("company"),
            position=item.get("position"),
            job_id=item.get("job_id"),
            source_url=item.get("source_url"),
        )
        item["apply_id"] = apply_payload.get("id") or apply_payload.get("apply_id")
        item["source_url"] = apply_payload.get("source_url") or item.get("source_url")
        status = apply_payload.get("status")
        if status == "paused_before_submit" or apply_payload.get("paused_before_submit"):
            item["fill_status"] = "awaiting_confirm"
            item["awaiting_confirm"] = True
            item["error"] = None
        else:
            item["fill_status"] = str(status or "filled")
            item["awaiting_confirm"] = bool(apply_payload.get("paused_before_submit"))
            item["error"] = None
        item["apply_snapshot"] = {
            "status": apply_payload.get("status"),
            "paused_before_submit": apply_payload.get("paused_before_submit"),
            "submitted": apply_payload.get("submitted"),
            "message": apply_payload.get("message"),
            "ats_type": apply_payload.get("ats_type"),
        }
    except Exception as exc:
        item["fill_status"] = "failed"
        item["awaiting_confirm"] = False
        item["error"] = str(exc)

    _save(item)
    try:
        audit(user_id, "queue_process", {"id": item_id, "fill_status": item["fill_status"]})
    except Exception:
        pass
    return item


def confirm_item(*, item_id: str, user_id: str, acknowledge: bool = False) -> dict[str, Any]:
    """Per-job explicit confirm Submit (audit). Does not click live Submit."""
    item = get_item(item_id)
    if not item:
        raise ValueError("Queue item not found")
    if str(item.get("user_id")) != str(user_id):
        raise ValueError("Queue item does not belong to this user")
    if not item.get("awaiting_confirm") and item.get("fill_status") != "awaiting_confirm":
        raise ValueError("Queue item is not awaiting confirm")
    if not acknowledge:
        raise ValueError("acknowledge=true is required")
    apply_id = item.get("apply_id")
    if not apply_id:
        raise ValueError("No apply session linked to this queue item")

    from app.modules.resume_workspace.apply_flow import confirm_submit

    confirm_submit(apply_id=apply_id, user_id=user_id, acknowledge=True)
    item["fill_status"] = "submitted"
    item["awaiting_confirm"] = False
    item["submitted_at"] = _now()
    _save(item)
    try:
        audit(user_id, "queue_confirm_submit", {"id": item_id, "apply_id": apply_id})
    except Exception:
        pass
    return item


def skip_item(*, item_id: str, user_id: str) -> dict[str, Any]:
    item = get_item(item_id)
    if not item:
        raise ValueError("Queue item not found")
    if str(item.get("user_id")) != str(user_id):
        raise ValueError("Queue item does not belong to this user")
    item["fill_status"] = "skipped"
    item["awaiting_confirm"] = False
    item["skipped_at"] = _now()
    _save(item)
    try:
        audit(user_id, "queue_skip", {"id": item_id})
    except Exception:
        pass
    return item
