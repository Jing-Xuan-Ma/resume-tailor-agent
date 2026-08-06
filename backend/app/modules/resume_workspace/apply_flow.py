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
        from app.modules.job_discovery.apply_url import listing_board_url, resolve_listing_apply_url

        return {
            "id": listing["id"],
            "title": listing.get("title"),
            "company": listing.get("company"),
            "source_url": resolve_listing_apply_url(listing),
            "board_url": listing_board_url(listing),
            "raw_text": listing.get("raw_text"),
            "metadata": listing.get("metadata") if isinstance(listing.get("metadata"), dict) else {},
            "apply_resolve": (
                (listing.get("metadata") or {}).get("apply_resolve")
                if isinstance(listing.get("metadata"), dict)
                else None
            ),
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
    prefer_llm: bool = False,
) -> dict[str, Any]:
    """Sync entry — auto mode uses DOM scan + rules map (LLM via start_apply_async)."""
    return _start_apply_impl(
        user_id=user_id,
        version_id=version_id,
        mode=mode,
        company=company,
        position=position,
        final_path=final_path,
        job_id=job_id,
        source_url=source_url,
        prefer_llm=prefer_llm,
        mapped_override=None,
    )


async def start_apply_async(
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
    """Async entry — auto mode uses one browser session (scan+fill), rules-first mapping.

    Previously: scan_fields() launch + fill_and_pause() launch (+ optional LLM).
    Now: single scan_and_fill_pause() inside _start_apply_impl; LLM only if configured.
    """
    import asyncio

    from app.config import settings

    prefer_llm = bool(getattr(settings, "APPLY_FIELD_MAP_PREFER_LLM", False))
    return await asyncio.to_thread(
        lambda: _start_apply_impl(
            user_id=user_id,
            version_id=version_id,
            mode=mode,
            company=company,
            position=position,
            final_path=final_path,
            job_id=job_id,
            source_url=source_url,
            prefer_llm=prefer_llm,
            mapped_override=None,
            pre_target=None,
        )
    )


def _start_apply_impl(
    *,
    user_id: str,
    version_id: str,
    mode: Literal["manual", "auto"],
    company: str | None = None,
    position: str | None = None,
    final_path: str | None = None,
    job_id: str | None = None,
    source_url: str | None = None,
    prefer_llm: bool = False,
    mapped_override: dict[str, Any] | None = None,
    pre_target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    version = db.get_resume_version(version_id, user_id)
    if not version:
        raise ValueError("Version not found")
    if not version.get("is_confirmed"):
        raise ValueError("Version must be confirmed before apply")

    job = _resolve_job(job_id)
    from app.modules.job_discovery.apply_url import (
        is_aggregator_url,
        normalize_apply_url,
        prefer_official_apply_url,
    )

    board_url = normalize_apply_url((job or {}).get("board_url"))
    # Always prefer company/ATS apply URL over Indeed/LinkedIn board links —
    # but skip unusable Workday career roots (see is_usable_job_apply_url).
    source_url = prefer_official_apply_url(
        normalize_apply_url(source_url),
        normalize_apply_url((job or {}).get("source_url")),
        board_fallback=board_url
        or normalize_apply_url(source_url)
        or normalize_apply_url((job or {}).get("source_url")),
    )
    if not board_url and source_url and is_aggregator_url(source_url):
        board_url = source_url
    # If we opened a board link because ATS was unusable, keep board_url populated.
    if source_url and is_aggregator_url(source_url) and not board_url:
        board_url = source_url
    if job and not company:
        company = job.get("company")
    if job and not position:
        position = job.get("title")

    apply_id = str(uuid4())
    fill_plan_ui: list[dict[str, Any]] = []
    map_provider = None
    if mode == "manual":
        status = "ready_for_manual_apply"
        if source_url and is_aggregator_url(source_url):
            message = (
                "Manual mode: company ATS link was missing or unusable "
                "(e.g. Workday career root). Opening the job-board listing instead — "
                f"{source_url}"
            )
        else:
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
            "Auto-apply scanned the form, mapped fields to your profile, filled what it could, "
            "then stopped before Submit — review the confidence tiers, then you click Submit."
        )
        resume = version.get("full_resume") or {}
        from app.modules.ats_connectors.canonical_profile import canonical_apply_profile
        from app.modules.ats_connectors.field_mapper import map_fields_rules

        profile = canonical_apply_profile(
            user_id,
            final_path=final_path,
            version_id=version_id,
            resume_overrides=resume if isinstance(resume, dict) else {},
        )
        filled = [
            {"field": "full_name", "value": profile.get("full_name") or "", "tier": "auto"},
            {"field": "email", "value": profile.get("email") or "", "tier": "auto"},
            {"field": "phone", "value": profile.get("phone") or "", "tier": "auto"},
            {"field": "linkedin", "value": profile.get("linkedin") or "", "tier": "review"},
            {"field": "portfolio", "value": profile.get("portfolio") or "", "tier": "review"},
            {"field": "github", "value": profile.get("github") or "", "tier": "review"},
            {"field": "location", "value": profile.get("location") or "", "tier": "review"},
            {"field": "work_authorization", "value": profile.get("work_authorized") or "", "tier": "review"},
            {"field": "needs_sponsorship", "value": profile.get("needs_sponsorship") or "", "tier": "review"},
            {
                "field": "resume_upload",
                "value": profile.get("resume_path") or final_path or f"confirmed:{version_id}",
                "tier": "auto" if profile.get("resume_path") else "empty",
                "note": None if profile.get("resume_path") else "no real resume file path — upload skipped",
            },
            {"field": "submit_button", "value": "NOT_CLICKED", "note": "hard stop — pause before submit", "tier": "empty"},
        ]
        profile_by_field = {
            "full_name": profile.get("full_name") or "",
            "email": profile.get("email") or "",
            "phone": profile.get("phone") or "",
            "linkedin": profile.get("linkedin") or "",
            "portfolio": profile.get("portfolio") or "",
            "github": profile.get("github") or "",
            "location": profile.get("location") or "",
            "work_authorization": profile.get("work_authorized") or "",
            "needs_sponsorship": profile.get("needs_sponsorship") or "",
            "resume_upload": profile.get("resume_path") or "",
        }
        ats_fields = _ats_field_map(source_url, profile_by_field)
        ats_type = ats_fields[0].get("ats_type") if ats_fields else "generic"

        browser_fill = {"status": "skipped", "submitted": False, "paused_before_submit": True}
        try:
            from app.config import settings
            from app.modules.application_engine.browser_session import BrowserSession
            from app.modules.ats_connectors.registry import connector_for
            from app.modules.ats_connectors.sandbox import resolve_browser_fill_url

            def _synthetic_fields_from_ats() -> list[dict[str, Any]]:
                """When browser is off, still produce mappable field descriptors for UI tiers."""
                synth: list[dict[str, Any]] = []
                for i, f in enumerate(ats_fields):
                    name = str(f.get("field") or "")
                    if not name or name.startswith("_"):
                        continue
                    synth.append(
                        {
                            "field_id": f"static-{i}",
                            "tag": "input",
                            "type": f.get("type") or "text",
                            "name": name,
                            "id": name,
                            "label": name.replace("_", " "),
                            "aria_label": "",
                            "placeholder": "",
                            "selector": f"#{name}",
                            "frame_index": 0,
                        }
                    )
                return synth

            def _attach_plan(plan: list[dict[str, Any]], provider: str) -> None:
                nonlocal fill_plan_ui, map_provider, filled
                fill_plan_ui = list(plan)
                map_provider = provider
                filled = filled + [
                    {
                        "field": f"ats:{m.get('label') or m.get('profile_key') or m.get('field_id')}",
                        "value": m.get("value") or "",
                        "tier": m.get("tier") or "empty",
                        "confidence": m.get("confidence"),
                        "needs_review": m.get("needs_review"),
                        "note": m.get("reason"),
                        "profile_key": m.get("profile_key"),
                        "action": m.get("action"),
                    }
                    for m in fill_plan_ui
                ]

            if settings.ENABLE_BROWSER_FILL_PAUSE or settings.ENABLE_BROWSER_AUTOMATION:
                prefer_sandbox = not bool(getattr(settings, "ALLOW_LIVE_BROWSER_FILL", False))
                target = pre_target or resolve_browser_fill_url(
                    source_url,
                    prefer_sandbox=prefer_sandbox,
                    allow_live=bool(getattr(settings, "ALLOW_LIVE_BROWSER_FILL", False)),
                )
                connector = connector_for(source_url)
                if target.get("ats_type") and target["ats_type"] != "generic":
                    ats_type = target["ats_type"]
                fill_url = target.get("url") or ""
                shot = str(
                    Path(__file__).resolve().parents[4]
                    / "artifacts"
                    / "funnel"
                    / "auto-apply-v2"
                    / f"browser-fill-{ats_type or 'generic'}-{apply_id[:8]}.png"
                )
                if fill_url:
                    def _tier_mappings(mapped: list[dict[str, Any]]) -> list[dict[str, Any]]:
                        for m in mapped:
                            conf = float(m.get("confidence") or 0)
                            action = m.get("action")
                            if action == "leave_empty" and not m.get("profile_key"):
                                m["tier"] = "empty"
                            elif conf >= 0.85 and action in {"fill", "upload"}:
                                m["tier"] = "auto"
                            elif conf >= 0.5 and action in {"fill", "upload"}:
                                m["tier"] = "review"
                            else:
                                m["tier"] = "empty"
                        return mapped

                    prebuilt = (
                        list(mapped_override["mappings"])
                        if mapped_override and mapped_override.get("mappings")
                        else None
                    )
                    map_provider = (
                        mapped_override.get("provider")
                        if prebuilt is not None and mapped_override
                        else "rules"
                    )

                    def _build_plan(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
                        nonlocal map_provider
                        if prefer_llm:
                            try:
                                import asyncio

                                from app.modules.ats_connectors.field_mapper import map_fields

                                packed = asyncio.run(map_fields(fields, profile, prefer_llm=True))
                                map_provider = packed.get("provider") or "rules"
                                return _tier_mappings(list(packed.get("mappings") or []))
                            except Exception:
                                map_provider = "rules"
                        return _tier_mappings(map_fields_rules(fields, profile))

                    # One Chromium launch: scan DOM → map → fill → screenshot (never Submit).
                    browser_fill = BrowserSession().scan_and_fill_pause(
                        url=fill_url,
                        fill_plan=_tier_mappings(prebuilt) if prebuilt is not None else None,
                        build_plan=None if prebuilt is not None else _build_plan,
                        field_selectors=connector.field_selectors(),
                        screenshot_path=shot,
                        ats_type=ats_type,
                        sandbox=bool(target.get("sandbox")),
                        click_apply_first=True,
                        answers=[],
                    )
                    fill_plan_ui = list(browser_fill.get("fill_plan") or prebuilt or [])
                    browser_fill["original_url"] = source_url
                    browser_fill["fill_url"] = fill_url
                    browser_fill["map_provider"] = map_provider
                    browser_fill["fill_plan"] = fill_plan_ui
                    filled = [
                        {"field": "full_name", "value": profile.get("full_name") or "", "tier": "auto"},
                        {"field": "email", "value": profile.get("email") or "", "tier": "auto"},
                        {"field": "phone", "value": profile.get("phone") or "", "tier": "auto"},
                        {"field": "linkedin", "value": profile.get("linkedin") or "", "tier": "review"},
                        {"field": "portfolio", "value": profile.get("portfolio") or "", "tier": "review"},
                        {"field": "github", "value": profile.get("github") or "", "tier": "review"},
                        {"field": "location", "value": profile.get("location") or "", "tier": "review"},
                        {"field": "work_authorization", "value": profile.get("work_authorized") or "", "tier": "review"},
                        {"field": "needs_sponsorship", "value": profile.get("needs_sponsorship") or "", "tier": "review"},
                        {
                            "field": "resume_upload",
                            "value": profile.get("resume_path") or final_path or f"confirmed:{version_id}",
                            "tier": "auto" if profile.get("resume_path") else "empty",
                            "note": None if profile.get("resume_path") else "no real resume file path — upload skipped",
                        },
                        {"field": "submit_button", "value": "NOT_CLICKED", "note": "hard stop — pause before submit", "tier": "empty"},
                    ] + [
                        {
                            "field": f"ats:{m.get('label') or m.get('profile_key') or m.get('field_id')}",
                            "value": m.get("value") or "",
                            "tier": m.get("tier") or "empty",
                            "confidence": m.get("confidence"),
                            "needs_review": m.get("needs_review"),
                            "note": m.get("reason"),
                            "profile_key": m.get("profile_key"),
                            "action": m.get("action"),
                        }
                        for m in fill_plan_ui
                    ]
                else:
                    browser_fill = {
                        "submitted": False,
                        "status": "missing_url",
                        "paused_before_submit": True,
                        "message": "No sandbox fixture or source URL for browser fill.",
                        "ats_type": ats_type,
                        "sandbox": False,
                    }
                    plan = map_fields_rules(_synthetic_fields_from_ats(), profile)
                    for m in plan:
                        conf = float(m.get("confidence") or 0)
                        action = m.get("action")
                        if action == "leave_empty" and not m.get("profile_key"):
                            m["tier"] = "empty"
                        elif conf >= 0.85 and action in {"fill", "upload"}:
                            m["tier"] = "auto"
                        elif conf >= 0.5 and action in {"fill", "upload"}:
                            m["tier"] = "review"
                        else:
                            m["tier"] = "empty"
                    fill_plan_ui = plan
                    map_provider = "rules"
                    filled = filled + [
                        {
                            "field": f"ats:{m.get('label') or m.get('profile_key') or m.get('field_id')}",
                            "value": m.get("value") or "",
                            "tier": m.get("tier") or "empty",
                            "confidence": m.get("confidence"),
                            "needs_review": m.get("needs_review"),
                            "note": m.get("reason"),
                            "profile_key": m.get("profile_key"),
                            "action": m.get("action"),
                        }
                        for m in fill_plan_ui
                    ]
            else:
                # Browser disabled — still emit confidence tiers for Apply review UI
                plan = map_fields_rules(_synthetic_fields_from_ats(), profile)
                for m in plan:
                    conf = float(m.get("confidence") or 0)
                    action = m.get("action")
                    if action == "leave_empty" and not m.get("profile_key"):
                        m["tier"] = "empty"
                    elif conf >= 0.85 and action in {"fill", "upload"}:
                        m["tier"] = "auto"
                    elif conf >= 0.5 and action in {"fill", "upload"}:
                        m["tier"] = "review"
                    else:
                        m["tier"] = "empty"
                fill_plan_ui = plan
                map_provider = "rules"
                browser_fill = {
                    "submitted": False,
                    "status": "browser_fill_disabled",
                    "paused_before_submit": True,
                    "message": "Browser fill-pause disabled — checklist tiers from ATS template map only.",
                    "ats_type": ats_type,
                }
                filled = filled + [
                    {
                        "field": f"ats:{m.get('label') or m.get('profile_key') or m.get('field_id')}",
                        "value": m.get("value") or "",
                        "tier": m.get("tier") or "empty",
                        "confidence": m.get("confidence"),
                        "needs_review": m.get("needs_review"),
                        "note": m.get("reason"),
                        "profile_key": m.get("profile_key"),
                        "action": m.get("action"),
                    }
                    for m in fill_plan_ui
                ]
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
        "board_url": board_url,
        "apply_resolve": (job or {}).get("apply_resolve"),
        "ats_type": ats_type if mode == "auto" else None,
        "mode": mode,
        "status": status,
        "company": company,
        "position": position,
        "final_path": final_path,
        "filled_fields": filled,
        "ats_fields": ats_fields if mode == "auto" else [],
        "fill_plan": fill_plan_ui if mode == "auto" else [],
        "map_provider": map_provider if mode == "auto" else None,
        "browser_fill": browser_fill if mode == "auto" else None,
        "submitted": False,
        "paused_before_submit": mode == "auto",
        "message": message,
        "created_at": _now(),
        "requires_human_review": mode == "auto",
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
                "map_provider": map_provider,
            },
        )
    except Exception:
        pass

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


def confirm_submit(
    *,
    apply_id: str,
    user_id: str,
    acknowledge: bool = False,
) -> dict[str, Any]:
    """Explicit user confirmation after pause-before-submit.

    Does NOT drive Playwright to click Submit on live boards.
    Records an audited `submitted_by_user_confirm` state so the queue / UI
    can advance. Real browser Submit remains gated by product policy.
    """
    from app.config import settings

    payload = get_apply(apply_id)
    if not payload:
        raise ValueError("Apply session not found")
    if str(payload.get("user_id") or "") != str(user_id):
        raise ValueError("Apply session does not belong to this user")
    if payload.get("submitted"):
        return payload
    if payload.get("status") not in {"paused_before_submit", "ready_for_manual_apply", "awaiting_user_submit"}:
        raise ValueError(f"Apply session is not awaiting confirm (status={payload.get('status')})")
    if not acknowledge:
        raise ValueError("acknowledge=true is required to confirm submit")
    if not bool(getattr(settings, "ENABLE_USER_CONFIRM_SUBMIT", True)):
        raise ValueError("User confirm-submit is disabled by config")

    payload["status"] = "submitted_by_user_confirm"
    payload["submitted"] = True
    payload["paused_before_submit"] = False
    payload["confirmed_submit_at"] = _now()
    payload["message"] = (
        "You confirmed submit. Recorded for audit — live board Submit still requires "
        "you to click on the official page (or a future gated browser submit)."
    )
    path = APPLY_DIR / f"{apply_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        from app.modules.safety.audit_log import audit

        audit(
            user_id,
            "apply_user_confirm_submit",
            {
                "apply_id": apply_id,
                "job_id": payload.get("job_id"),
                "version_id": payload.get("version_id"),
                "ats_type": payload.get("ats_type"),
                "source_url": payload.get("source_url"),
            },
        )
    except Exception:
        pass

    final_path = payload.get("final_path")
    if final_path:
        try:
            meta_path = Path(final_path) / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["apply_status"] = payload["status"]
                meta["submitted"] = True
                meta["confirmed_submit_at"] = payload["confirmed_submit_at"]
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    return payload