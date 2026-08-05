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


def _resolve_job(job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    listing = db.get_job_listing(job_id)
    if listing:
        return {
            "id": listing["id"],
            "title": listing.get("title"),
            "company": listing.get("company"),
            "source_url": listing.get("source_url"),
            "raw_text": listing.get("raw_text"),
        }
    return db.get_job(job_id)


def _ats_field_map(source_url: str | None, profile_by_field: dict[str, str]) -> list[dict[str, Any]]:
    """Static ATS connector field map (Greenhouse/Lever/Ashby/…) — dry-run only."""
    try:
        from app.modules.ats_connectors.registry import connector_for

        connector = connector_for(source_url)
        ats_type = getattr(connector, "ats_type", None) or "generic"
        mapped: list[dict[str, Any]] = []
        for field in connector.fields() or []:
            name = str(field.get("name") or "")
            if not name:
                continue
            aliases = [a.lower() for a in (field.get("aliases") or [])]
            value = ""
            # Map common ATS names onto profile checklist
            key_hints = [name.lower(), *[a for a in aliases]]
            for hint in key_hints:
                if "first" in hint and "name" in hint:
                    full = profile_by_field.get("full_name", "")
                    value = full.split(" ", 1)[0] if full else ""
                    break
                if "last" in hint and "name" in hint:
                    full = profile_by_field.get("full_name", "")
                    value = full.split(" ", 1)[1] if " " in full else ""
                    break
                if hint in ("full_name", "name") or hint.endswith("_name") and "first" not in hint and "last" not in hint:
                    value = profile_by_field.get("full_name", "")
                    break
                if "email" in hint:
                    value = profile_by_field.get("email", "")
                    break
                if "phone" in hint:
                    value = profile_by_field.get("phone", "")
                    break
                if "linkedin" in hint:
                    value = profile_by_field.get("linkedin", "")
                    break
                if hint in ("website", "portfolio", "url"):
                    value = profile_by_field.get("portfolio", "") or profile_by_field.get("github", "")
                    break
                if "github" in hint:
                    value = profile_by_field.get("github", "")
                    break
                if "location" in hint or "city" in hint:
                    value = profile_by_field.get("location", "")
                    break
                if "authoriz" in hint or "work_auth" in hint:
                    value = profile_by_field.get("work_authorization", "")
                    break
                if "sponsor" in hint:
                    value = profile_by_field.get("needs_sponsorship", "")
                    break
                if "resume" in hint or "cv" in hint:
                    value = profile_by_field.get("resume_upload", "")
                    break
                if "cover" in hint:
                    value = "(optional — not auto-generated in dry-run)"
                    break
            mapped.append(
                {
                    "field": name,
                    "value": value or "(empty — review)",
                    "required": bool(field.get("required")),
                    "type": field.get("type") or "text",
                    "ats_type": ats_type,
                    "note": "ats_template_map",
                }
            )
        return mapped
    except Exception as exc:
        return [{"field": "_ats_map_error", "value": str(exc), "note": "failed"}]


def start_apply(
    *,
    user_id: str,
    version_id: str,
    mode: Literal["manual", "auto"],
    company: str | None = None,
    position: str | None = None,
    final_path: str | None = None,
    job_id: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    version = db.get_resume_version(version_id, user_id)
    if not version:
        raise ValueError("Version not found")
    if not version.get("is_confirmed"):
        raise ValueError("Version must be confirmed before apply")

    job = _resolve_job(job_id)
    if job and not source_url:
        source_url = job.get("source_url")
    if job and not company:
        company = job.get("company")
    if job and not position:
        position = job.get("title")

    apply_id = str(uuid4())
    if mode == "manual":
        status = "ready_for_manual_apply"
        message = (
            "Manual mode: open the original posting and submit yourself. "
            f"{'Posting: ' + source_url if source_url else 'No live posting URL on file.'}"
        )
        filled: list[dict[str, Any]] = []
        ats_fields: list[dict[str, Any]] = []
        ats_type = None
        browser_fill: dict[str, Any] | None = None
    else:
        status = "paused_before_submit"
        message = (
            "Auto-apply dry run mapped profile + ATS fields, then stopped before Submit "
            "(safety boundary — nothing was sent)."
        )
        resume = version.get("full_resume") or {}
        try:
            from app.modules.profile.library_service import get_apply_profile

            apply_profile = get_apply_profile(user_id)
        except Exception:
            apply_profile = {}
        contact = str(resume.get("contact_line") or "")
        phone = apply_profile.get("phone")
        if not phone:
            for part in contact.split("|"):
                part = part.strip()
                if part.startswith("+") or part[:1].isdigit():
                    phone = part
                    break
        email = (
            apply_profile.get("email")
            or _email_from_contact(contact)
            or "jma107@jh.edu"
        )
        filled = [
            {"field": "full_name", "value": apply_profile.get("full_name") or resume.get("candidate_name") or "Jingxuan Ma"},
            {"field": "email", "value": email},
            {"field": "phone", "value": phone or "+1 (410) 240-4366"},
            {"field": "linkedin", "value": apply_profile.get("linkedin_url") or "LinkedIn"},
            {"field": "portfolio", "value": apply_profile.get("portfolio_url") or ""},
            {
                "field": "github",
                "value": apply_profile.get("github_url")
                or apply_profile.get("resume_tailor_github")
                or "",
            },
            {"field": "location", "value": apply_profile.get("location") or ""},
            {
                "field": "work_authorization",
                "value": "Yes" if apply_profile.get("work_authorized", True) else "No",
            },
            {
                "field": "needs_sponsorship",
                "value": "Yes" if apply_profile.get("needs_sponsorship", True) else "No",
            },
            {"field": "resume_upload", "value": final_path or f"confirmed:{version_id}"},
            {"field": "submit_button", "value": "NOT_CLICKED", "note": "hard stop — pause before submit"},
        ]
        profile_by_field = {str(item["field"]): str(item.get("value") or "") for item in filled}
        ats_fields = _ats_field_map(source_url, profile_by_field)
        ats_type = ats_fields[0].get("ats_type") if ats_fields else "generic"
        # Merge unique ATS fields into checklist view (keep profile list separate in payload)
        filled = filled + [
            {**f, "field": f"ats:{f['field']}"}
            for f in ats_fields
            if f.get("field") and not str(f["field"]).startswith("_")
        ]

        browser_fill: dict[str, Any] = {"status": "skipped", "submitted": False, "paused_before_submit": True}
        try:
            from app.config import settings
            from app.modules.application_engine.browser_session import BrowserSession
            from app.modules.ats_connectors.registry import connector_for
            from app.modules.ats_connectors.sandbox import resolve_browser_fill_url

            if settings.ENABLE_BROWSER_FILL_PAUSE or settings.ENABLE_BROWSER_AUTOMATION:
                # Default sandbox; live boards only when ALLOW_LIVE_BROWSER_FILL=true
                prefer_sandbox = not bool(getattr(settings, "ALLOW_LIVE_BROWSER_FILL", False))
                target = resolve_browser_fill_url(
                    source_url,
                    prefer_sandbox=prefer_sandbox,
                    allow_live=bool(getattr(settings, "ALLOW_LIVE_BROWSER_FILL", False)),
                )
                connector = connector_for(source_url)
                if target.get("ats_type") and target["ats_type"] != "generic":
                    ats_type = target["ats_type"]
                answers = []
                for row in ats_fields:
                    name = str(row.get("field") or "")
                    if not name or name.startswith("_"):
                        continue
                    answers.append(
                        {
                            "field": name,
                            "field_name": name,
                            "question": name.replace("_", " "),
                            "answer": row.get("value") or "",
                            "type": row.get("type") or "text",
                            "aliases": [name.replace("_", " ")],
                        }
                    )
                # Prefer first/last for greenhouse / workday fixtures
                full = profile_by_field.get("full_name") or ""
                if " " in full and not any(a.get("field_name") == "first_name" for a in answers):
                    answers.insert(
                        0,
                        {
                            "field_name": "first_name",
                            "field": "first_name",
                            "question": "First name",
                            "answer": full.split(" ", 1)[0],
                            "aliases": ["first name"],
                        },
                    )
                    answers.insert(
                        1,
                        {
                            "field_name": "last_name",
                            "field": "last_name",
                            "question": "Last name",
                            "answer": full.split(" ", 1)[1],
                            "aliases": ["last name"],
                        },
                    )
                shot = str(
                    Path(__file__).resolve().parents[4]
                    / "artifacts"
                    / "funnel"
                    / "agent3"
                    / f"browser-fill-{ats_type or 'generic'}-{apply_id[:8]}.png"
                )
                fill_url = target.get("url") or ""
                if fill_url:
                    browser_fill = BrowserSession().fill_and_pause(
                        url=fill_url,
                        answers=answers,
                        field_selectors=connector.field_selectors(),
                        screenshot_path=shot,
                        ats_type=ats_type,
                        sandbox=bool(target.get("sandbox")),
                    )
                    browser_fill["original_url"] = source_url
                    browser_fill["fill_url"] = fill_url
                else:
                    browser_fill = {
                        "submitted": False,
                        "status": "missing_url",
                        "paused_before_submit": True,
                        "message": "No sandbox fixture or source URL for browser fill.",
                        "ats_type": ats_type,
                        "sandbox": False,
                    }
        except Exception as exc:
            browser_fill = {
                "submitted": False,
                "status": "browser_fill_error",
                "message": str(exc),
                "paused_before_submit": True,
            }

    payload = {
        "id": apply_id,
        "user_id": user_id,
        "version_id": version_id,
        "job_id": job_id,
        "source_url": source_url,
        "ats_type": ats_type if mode == "auto" else None,
        "mode": mode,
        "status": status,
        "company": company,
        "position": position,
        "final_path": final_path,
        "filled_fields": filled,
        "ats_fields": ats_fields if mode == "auto" else [],
        "browser_fill": browser_fill if mode == "auto" else None,
        "submitted": False,
        "paused_before_submit": mode == "auto",
        "message": message,
        "created_at": _now(),
    }
    path = APPLY_DIR / f"{apply_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        from app.modules.safety.audit_log import audit

        audit(
            user_id,
            f"apply_{mode}_{status}",
            {
                "apply_id": apply_id,
                "mode": mode,
                "status": status,
                "version_id": version_id,
                "ats_type": payload.get("ats_type"),
                "field_count": len(filled),
            },
        )
    except Exception:
        pass

    # Touch final meta.json apply_status when possible
    if final_path:
        try:
            meta_path = Path(final_path) / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["apply_status"] = status
                meta["apply_id"] = apply_id
                meta["ats_type"] = payload.get("ats_type")
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
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
