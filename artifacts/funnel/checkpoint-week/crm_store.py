"""Lightweight outreach CRM store (contacts + coffee-chat notes)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4] / "data" / "outreach_crm"
ROOT.mkdir(parents=True, exist_ok=True)


def _path(user_id: str) -> Path:
    safe = "".join(c for c in user_id if c.isalnum() or c in "-_")
    return ROOT / f"{safe}.json"


def _load(user_id: str) -> dict[str, Any]:
    path = _path(user_id)
    if not path.exists():
        return {"contacts": [], "updated_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    data["updated_at"] = datetime.now(UTC).isoformat()
    path = _path(user_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def list_contacts(user_id: str) -> list[dict[str, Any]]:
    return list(_load(user_id).get("contacts") or [])


def upsert_contact(user_id: str, contact: dict[str, Any]) -> dict[str, Any]:
    data = _load(user_id)
    contacts: list[dict[str, Any]] = list(data.get("contacts") or [])
    cid = str(contact.get("id") or uuid4())
    prev: dict[str, Any] | None = None
    for existing in contacts:
        if existing.get("id") == cid or (
            existing.get("linkedin_url")
            and contact.get("linkedin_url")
            and existing.get("linkedin_url") == contact.get("linkedin_url")
        ):
            prev = existing
            break

    reply_status = contact.get("reply_status") or (prev or {}).get("reply_status") or "none"
    last_reply_at = contact.get("last_reply_at") or (prev or {}).get("last_reply_at") or ""
    if reply_status in {"replied", "scheduled"}:
        prev_status = (prev or {}).get("reply_status") or "none"
        if not last_reply_at or prev_status != reply_status:
            last_reply_at = datetime.now(UTC).isoformat()

    row = {
        "id": (prev or {}).get("id") or cid,
        "name": contact.get("name") if contact.get("name") is not None else (prev or {}).get("name") or "",
        "role": contact.get("role") if contact.get("role") is not None else (prev or {}).get("role") or "",
        "company": contact.get("company") if contact.get("company") is not None else (prev or {}).get("company") or "",
        "job_id": contact.get("job_id") if contact.get("job_id") is not None else (prev or {}).get("job_id"),
        "linkedin_url": contact.get("linkedin_url")
        if contact.get("linkedin_url") is not None
        else (prev or {}).get("linkedin_url")
        or "",
        "email": contact.get("email") if contact.get("email") is not None else (prev or {}).get("email") or "",
        "coffee_availability": contact.get("coffee_availability")
        if contact.get("coffee_availability") is not None
        else (prev or {}).get("coffee_availability")
        or "",
        "notes": contact.get("notes") if contact.get("notes") is not None else (prev or {}).get("notes") or "",
        "status": contact.get("status") or (prev or {}).get("status") or "identified",
        "reply_status": reply_status,
        "last_reply_at": last_reply_at,
        "coffee_slots": contact.get("coffee_slots")
        if contact.get("coffee_slots") is not None
        else (prev or {}).get("coffee_slots")
        or [],
        "updated_at": datetime.now(UTC).isoformat(),
    }
    replaced = False
    for i, existing in enumerate(contacts):
        if existing.get("id") == row["id"] or (
            existing.get("linkedin_url")
            and row["linkedin_url"]
            and existing.get("linkedin_url") == row["linkedin_url"]
        ):
            contacts[i] = {**existing, **row, "id": existing.get("id") or row["id"]}
            row = contacts[i]
            replaced = True
            break
    if not replaced:
        contacts.insert(0, row)
    data["contacts"] = contacts[:100]
    _save(user_id, data)
    return row


def export_contacts_csv(user_id: str) -> str:
    rows = list_contacts(user_id)
    lines = [
        "id,name,role,company,email,linkedin_url,status,reply_status,coffee_availability,last_reply_at,notes"
    ]
    for c in rows:
        def esc(v: Any) -> str:
            s = str(v or "").replace('"', '""')
            return f'"{s}"'

        lines.append(
            ",".join(
                [
                    esc(c.get("id")),
                    esc(c.get("name")),
                    esc(c.get("role")),
                    esc(c.get("company")),
                    esc(c.get("email")),
                    esc(c.get("linkedin_url")),
                    esc(c.get("status")),
                    esc(c.get("reply_status")),
                    esc(c.get("coffee_availability")),
                    esc(c.get("last_reply_at")),
                    esc(c.get("notes")),
                ]
            )
        )
    return "\n".join(lines) + "\n"
