"""Map scanned ATS fields → canonical profile values with confidence."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.modules.ats_connectors.canonical_profile import CANONICAL_KEYS

log = logging.getLogger(__name__)

CONF_AUTO = 0.85
CONF_REVIEW = 0.5


def _blob(field: dict[str, Any]) -> str:
    parts = [
        field.get("label"),
        field.get("aria_label"),
        field.get("placeholder"),
        field.get("name"),
        field.get("id"),
        field.get("autocomplete"),
        field.get("type"),
    ]
    return " ".join(str(p or "") for p in parts).lower()


def _rules_map_one(field: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any] | None:
    blob = _blob(field)
    ftype = str(field.get("type") or "").lower()
    fid = str(field.get("field_id") or "")

    def hit(key: str, conf: float, *needles: str) -> dict[str, Any] | None:
        if any(n in blob for n in needles):
            val = str(profile.get(key) or "")
            if not val and key != "resume_path":
                return {
                    "field_id": fid,
                    "profile_key": key,
                    "value": "",
                    "confidence": conf * 0.5,
                    "needs_review": True,
                    "action": "leave_empty",
                    "reason": f"matched {key} but profile empty",
                }
            action = "upload" if key in {"resume_path", "cover_letter_path"} or ftype == "file" else "fill"
            if key in {"resume_path", "cover_letter_path"}:
                action = "upload"
            return {
                "field_id": fid,
                "profile_key": key,
                "value": val,
                "confidence": conf,
                "needs_review": conf < CONF_AUTO,
                "action": action if val else "leave_empty",
                "reason": f"rules:{needles[0]}",
            }
        return None

    if ftype == "file" or "resume" in blob or "cv" in blob:
        return hit("resume_path", 0.9, "resume", "cv", "attach")
    if "cover" in blob and "letter" in blob:
        return hit("cover_letter_path", 0.8, "cover")

    ordered: list[tuple[str, float, tuple[str, ...]]] = [
        ("first_name", 0.95, ("first name", "first_name", "given name", "firstname")),
        ("last_name", 0.95, ("last name", "last_name", "surname", "family name", "lastname")),
        ("email", 0.95, ("email", "e-mail")),
        ("phone", 0.92, ("phone", "mobile", "tel")),
        ("linkedin", 0.9, ("linkedin",)),
        ("github", 0.88, ("github",)),
        ("portfolio", 0.85, ("portfolio", "website", "personal site")),
        ("location", 0.85, ("location", "city", "current location")),
        ("work_authorized", 0.75, ("authorized to work", "work authorization", "legally authorized")),
        ("needs_sponsorship", 0.75, ("sponsor", "sponsorship", "visa sponsorship")),
        ("full_name", 0.9, ("full name", "your name", "candidate name")),
        ("full_name", 0.7, (" name",)),  # weaker: bare "name"
    ]
    # Prefer specific over bare "name"
    for key, conf, needles in ordered:
        if key == "full_name" and needles == (" name",):
            if any(x in blob for x in ("first", "last", "user", "company", "file")):
                continue
            if re.search(r"\bname\b", blob) and "first" not in blob and "last" not in blob:
                row = hit(key, conf, "name")
                if row:
                    return row
            continue
        row = hit(key, conf, *needles)
        if row:
            return row
    return None


def map_fields_rules(fields: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    used_keys: set[str] = set()
    for field in fields:
        row = _rules_map_one(field, profile)
        if not row:
            mappings.append(
                {
                    "field_id": field.get("field_id"),
                    "profile_key": None,
                    "value": "",
                    "confidence": 0.0,
                    "needs_review": True,
                    "action": "leave_empty",
                    "reason": "unmapped",
                    "label": field.get("label") or field.get("name") or field.get("id"),
                    "selector": field.get("selector"),
                    "frame_index": field.get("frame_index", 0),
                    "type": field.get("type"),
                }
            )
            continue
        # Avoid double-binding exclusive keys when possible
        pk = row.get("profile_key")
        if pk in used_keys and pk in {"email", "phone", "first_name", "last_name", "resume_path"}:
            row = {
                **row,
                "confidence": min(float(row.get("confidence") or 0), 0.4),
                "needs_review": True,
                "action": "leave_empty",
                "reason": "duplicate_key",
                "value": "",
            }
        else:
            if pk:
                used_keys.add(str(pk))
        mappings.append(
            {
                **row,
                "label": field.get("label") or field.get("name") or field.get("id"),
                "selector": field.get("selector"),
                "frame_index": field.get("frame_index", 0),
                "type": field.get("type"),
            }
        )
    return mappings


async def map_fields_llm(fields: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]] | None:
    try:
        from app.core.llm_client import get_chat_openai
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        log.debug("llm unavailable: %s", exc)
        return None

    slim_fields = [
        {
            "field_id": f.get("field_id"),
            "type": f.get("type"),
            "label": f.get("label"),
            "aria_label": f.get("aria_label"),
            "placeholder": f.get("placeholder"),
            "name": f.get("name"),
            "id": f.get("id"),
            "required": f.get("required"),
        }
        for f in fields[:60]
    ]
    # Values only for keys that are non-empty (resume_path shown as bool presence)
    profile_view = {}
    for k in CANONICAL_KEYS:
        v = profile.get(k)
        if k == "resume_path":
            profile_view[k] = bool(v)
        elif v not in (None, ""):
            profile_view[k] = v

    system = (
        "You map ATS application form fields to a candidate profile. "
        "Return ONLY a JSON array of objects with keys: "
        "field_id, profile_key (one of the allowed keys or null), confidence (0-1), "
        "needs_review (bool), reason (short). "
        "Do not invent career history. If unsure, profile_key=null and confidence<=0.4. "
        f"Allowed profile_key values: {list(CANONICAL_KEYS)}."
    )
    try:
        llm = get_chat_openai(temperature=0.1)
        resp = await llm.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(
                    content=json.dumps(
                        {"fields": slim_fields, "profile_keys_present": profile_view},
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        raw = str(getattr(resp, "content", "") or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, list):
            return None
    except Exception as exc:
        log.warning("LLM field map failed: %s", exc)
        return None

    by_id = {str(f.get("field_id")): f for f in fields}
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("field_id") or "")
        field = by_id.get(fid) or {}
        pk = item.get("profile_key")
        if pk is not None:
            pk = str(pk)
            if pk not in CANONICAL_KEYS:
                pk = None
        conf = float(item.get("confidence") or 0)
        conf = max(0.0, min(1.0, conf))
        val = str(profile.get(pk) or "") if pk else ""
        ftype = str(field.get("type") or "")
        action = "leave_empty"
        if pk and val and conf >= CONF_REVIEW:
            action = "upload" if pk in {"resume_path", "cover_letter_path"} or ftype == "file" else "fill"
        elif pk and not val:
            action = "leave_empty"
            conf = min(conf, 0.45)
        out.append(
            {
                "field_id": fid,
                "profile_key": pk,
                "value": val if action != "leave_empty" else "",
                "confidence": conf,
                "needs_review": bool(item.get("needs_review")) or conf < CONF_AUTO,
                "action": action,
                "reason": str(item.get("reason") or "llm"),
                "label": field.get("label") or field.get("name") or field.get("id"),
                "selector": field.get("selector"),
                "frame_index": field.get("frame_index", 0),
                "type": field.get("type"),
            }
        )
    # Ensure every scanned field appears
    seen = {m["field_id"] for m in out}
    for f in fields:
        fid = str(f.get("field_id"))
        if fid in seen:
            continue
        out.append(
            {
                "field_id": fid,
                "profile_key": None,
                "value": "",
                "confidence": 0.0,
                "needs_review": True,
                "action": "leave_empty",
                "reason": "llm_omitted",
                "label": f.get("label") or f.get("name") or f.get("id"),
                "selector": f.get("selector"),
                "frame_index": f.get("frame_index", 0),
                "type": f.get("type"),
            }
        )
    return out


async def map_fields(
    fields: list[dict[str, Any]],
    profile: dict[str, Any],
    *,
    prefer_llm: bool = True,
) -> dict[str, Any]:
    provider = "rules"
    mappings: list[dict[str, Any]] | None = None
    if prefer_llm:
        mappings = await map_fields_llm(fields, profile)
        if mappings:
            provider = "llm"
    if mappings is None:
        mappings = map_fields_rules(fields, profile)
        provider = "rules"
    # Tier buckets for UI
    for m in mappings:
        conf = float(m.get("confidence") or 0)
        action = m.get("action")
        if action == "leave_empty" and not m.get("profile_key"):
            m["tier"] = "empty"
        elif conf >= CONF_AUTO and action in {"fill", "upload"}:
            m["tier"] = "auto"
        elif conf >= CONF_REVIEW and action in {"fill", "upload"}:
            m["tier"] = "review"
        else:
            m["tier"] = "empty"
            if action != "upload":
                m["action"] = "leave_empty"
                if conf < CONF_REVIEW:
                    m["value"] = ""
    return {"mappings": mappings, "provider": provider, "profile_keys": list(CANONICAL_KEYS)}
