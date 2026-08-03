"""Post-confirm apply mode split: manual vs auto (pause before submit)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4
import json

from app import db

APPLY_DIR = Path(__file__).resolve().parents[4] / "data" / "apply_sessions"
APPLY_DIR.mkdir(parents=True, exist_ok=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def start_apply(
    *,
    user_id: str,
    version_id: str,
    mode: Literal["manual", "auto"],
    company: str | None = None,
    position: str | None = None,
    final_path: str | None = None,
) -> dict[str, Any]:
    version = db.get_resume_version(version_id, user_id)
    if not version:
        raise ValueError("Version not found")
    if not version.get("is_confirmed"):
        raise ValueError("Version must be confirmed before apply")

    apply_id = str(uuid4())
    if mode == "manual":
        status = "ready_for_manual_apply"
        message = "Manual mode: open the original posting and submit yourself. Agent will not submit."
        filled = []
    else:
        status = "paused_before_submit"
        message = (
            "Auto-apply dry run filled profile fields and attached the confirmed resume, "
            "then stopped before Submit (safety boundary)."
        )
        filled = [
            {"field": "full_name", "value": (version["full_resume"] or {}).get("candidate_name")},
            {"field": "email", "value": _email_from_contact((version["full_resume"] or {}).get("contact_line"))},
            {"field": "resume_upload", "value": final_path or f"confirmed:{version_id}"},
        ]

    payload = {
        "id": apply_id,
        "user_id": user_id,
        "version_id": version_id,
        "mode": mode,
        "status": status,
        "company": company,
        "position": position,
        "final_path": final_path,
        "filled_fields": filled,
        "submitted": False,
        "paused_before_submit": mode == "auto",
        "message": message,
        "created_at": _now(),
    }
    path = APPLY_DIR / f"{apply_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    audit_payload = {
        "apply_id": apply_id,
        "mode": mode,
        "status": status,
        "version_id": version_id,
    }
    try:
        from app.modules.safety.audit_log import audit

        audit(user_id, f"apply_{mode}_{status}", audit_payload)
    except Exception:
        pass
    return payload


def _email_from_contact(contact_line: str | None) -> str | None:
    if not contact_line:
        return None
    for part in str(contact_line).split("|"):
        part = part.strip()
        if "@" in part:
            return part
    return None


def get_apply(apply_id: str) -> dict[str, Any] | None:
    path = APPLY_DIR / f"{apply_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
