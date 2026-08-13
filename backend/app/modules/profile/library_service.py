"""Candidate library: Master Inventory + Apply Profile (RESUME_CONSTITUTION §4)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app import db
from app.modules.resume_workspace.yiling_experience import RESUME_TAILOR_GITHUB, YILING_COMPANY


def _default_apply_from_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    contact = str(inventory.get("contact_line") or "")
    parts = [p.strip() for p in contact.split("|") if p.strip()]
    phone = next((p for p in parts if p.startswith("+") or (p[:1].isdigit() and "@" not in p)), "")
    email = next((p for p in parts if "@" in p), "")
    github = str(inventory.get("github_url") or RESUME_TAILOR_GITHUB)
    return {
        "full_name": inventory.get("candidate_name") or "",
        "preferred_name": "",
        "email": email,
        "phone": phone,
        "location": "",
        "linkedin_url": "",
        "portfolio_url": "",
        "github_url": github,
        "resume_tailor_github": RESUME_TAILOR_GITHUB,
        "twitter_url": "",
        "source": "LinkedIn",
        "work_authorized": True,
        "needs_sponsorship": True,
        "visa_status": "",
        "willing_to_relocate": True,
        "earliest_start": "",
        "salary_expectation": "",
        "gender": "",
        "race_ethnicity": "",
        "veteran_status": "",
        "disability_status": "",
        "custom_fields": {},
        "answers": {
            "why_this_role": "",
            "additional_info": "",
        },
    }


def _ensure_evidence_links(inventory: dict[str, Any]) -> dict[str, Any]:
    """Attach resume-tailor GitHub to inventory + Yiling experience for JD agents."""
    inv = deepcopy(inventory)
    inv["github_url"] = inv.get("github_url") or RESUME_TAILOR_GITHUB
    links = list(inv.get("evidence_links") or [])
    if not any(
        str(x.get("url") or "") == RESUME_TAILOR_GITHUB for x in links if isinstance(x, dict)
    ):
        links.insert(
            0,
            {
                "label": "resume-tailor-agent",
                "url": RESUME_TAILOR_GITHUB,
                "maps_to_company": YILING_COMPANY,
                "maps_to_title": "AI Agent Intern",
                "topics": [
                    "ai-agent",
                    "fastapi",
                    "nextjs",
                    "ooxml",
                    "jd-matching",
                    "resume-tailor",
                    "quality-gate",
                    "prompt-engineering",
                ],
                "note": (
                    "Primary public evidence for the Yiling AI Agent intern product. "
                    "For software/agent/automation JDs, prefer projecting this experience and "
                    "pulling stack/facts from inventory bullets tied to this repo."
                ),
            },
        )
    inv["evidence_links"] = links

    experiences = list(inv.get("experiences") or [])
    for i, exp in enumerate(experiences):
        if not isinstance(exp, dict):
            continue
        company = str(exp.get("company") or "")
        if "Yiling" in company or "依零" in company:
            exp = {**exp, "github_url": exp.get("github_url") or RESUME_TAILOR_GITHUB}
            exp["evidence_url"] = exp.get("evidence_url") or RESUME_TAILOR_GITHUB
            tags = list(exp.get("tags") or [])
            if "github" not in [t.lower() for t in tags]:
                tags.append("github")
            exp["tags"] = tags
            experiences[i] = exp
    inv["experiences"] = experiences
    return inv


def default_inventory() -> dict[str, Any]:
    # Lazy import avoids circular import at module load
    from app.modules.resume_workspace.service import MOCK_RESUME

    return _ensure_evidence_links(deepcopy(MOCK_RESUME))


def get_or_seed_library(user_id: str) -> dict[str, Any]:
    existing = db.get_candidate_library(user_id)
    if existing:
        inv = _ensure_evidence_links(existing.get("inventory") or {})
        apply_profile = dict(existing.get("apply") or {})
        if not apply_profile.get("github_url"):
            apply_profile["github_url"] = RESUME_TAILOR_GITHUB
        if not apply_profile.get("resume_tailor_github"):
            apply_profile["resume_tailor_github"] = RESUME_TAILOR_GITHUB
        # Persist soft upgrades so Profile UI and agents see the link
        if inv != existing.get("inventory") or apply_profile != existing.get("apply"):
            return db.save_candidate_library(user_id, inv, apply_profile)
        return {**existing, "inventory": inv, "apply": apply_profile}

    inventory = default_inventory()
    apply_profile = _default_apply_from_inventory(inventory)
    return db.save_candidate_library(user_id, inventory, apply_profile)


def get_master_inventory(user_id: str) -> dict[str, Any]:
    lib = get_or_seed_library(user_id)
    inv = lib.get("inventory") or {}
    return inv if isinstance(inv, dict) and inv else default_inventory()


def get_apply_profile(user_id: str) -> dict[str, Any]:
    lib = get_or_seed_library(user_id)
    apply_profile = lib.get("apply") or {}
    if not isinstance(apply_profile, dict) or not apply_profile:
        return _default_apply_from_inventory(get_master_inventory(user_id))
    return apply_profile


def evidence_context_for_jd(user_id: str, jd_text: str = "") -> dict[str, Any]:
    """Compact evidence map for agents: which GitHub/inventory blocks match this JD."""
    inv = get_master_inventory(user_id)
    apply_profile = get_apply_profile(user_id)
    jd = (jd_text or "").lower()
    links = [x for x in (inv.get("evidence_links") or []) if isinstance(x, dict)]
    matched = []
    for link in links:
        topics = [str(t).lower() for t in (link.get("topics") or [])]
        hit = any(t in jd for t in topics) if jd else True
        if hit or not jd:
            matched.append(
                {
                    "label": link.get("label"),
                    "url": link.get("url"),
                    "maps_to_company": link.get("maps_to_company"),
                    "topics": link.get("topics") or [],
                    "note": link.get("note") or "",
                }
            )
    return {
        "github_url": apply_profile.get("github_url")
        or inv.get("github_url")
        or RESUME_TAILOR_GITHUB,
        "resume_tailor_github": RESUME_TAILOR_GITHUB,
        "evidence_links": matched or links[:3],
    }


def update_library(
    user_id: str,
    *,
    inventory: dict[str, Any] | None = None,
    apply_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = get_or_seed_library(user_id)
    next_inventory = inventory if inventory is not None else current["inventory"]
    next_apply = apply_profile if apply_profile is not None else current["apply"]
    if not isinstance(next_inventory, dict):
        raise ValueError("inventory must be an object")
    if not isinstance(next_apply, dict):
        raise ValueError("apply must be an object")
    next_inventory = _ensure_evidence_links(next_inventory)
    if not next_apply.get("github_url"):
        next_apply = {**next_apply, "github_url": RESUME_TAILOR_GITHUB}
    next_apply = {
        **next_apply,
        "resume_tailor_github": next_apply.get("resume_tailor_github") or RESUME_TAILOR_GITHUB,
    }
    # Keep contact_line / name in sync when apply fields change
    if apply_profile is not None:
        name = str(
            next_apply.get("full_name") or next_inventory.get("candidate_name") or ""
        ).strip()
        phone = str(next_apply.get("phone") or "").strip()
        email = str(next_apply.get("email") or "").strip()
        linked = "LinkedIn" if next_apply.get("linkedin_url") else ""
        portfolio = "Portfolio" if next_apply.get("portfolio_url") else ""
        bits = [b for b in (phone, email, linked or None, portfolio or None) if b]
        if name:
            next_inventory = {**next_inventory, "candidate_name": name}
        if bits:
            next_inventory = {**next_inventory, "contact_line": " | ".join(bits)}
    return db.save_candidate_library(user_id, next_inventory, next_apply)


_APPLY_SCALAR_KEYS = {
    "full_name",
    "preferred_name",
    "email",
    "phone",
    "location",
    "country",
    "linkedin_url",
    "portfolio_url",
    "github_url",
    "resume_tailor_github",
    "twitter_url",
    "source",
    "visa_status",
    "earliest_start",
    "salary_expectation",
    "work_authorized",
    "needs_sponsorship",
    "willing_to_relocate",
    "gender",
    "race_ethnicity",
    "veteran_status",
    "disability_status",
}

_INVENTORY_SCALAR_KEYS = {
    "candidate_name",
    "contact_line",
    "summary",
    "skills_certifications",
    "github_url",
}


def _deep_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def patch_library(
    user_id: str,
    *,
    apply_patch: dict[str, Any] | None = None,
    inventory_patch: dict[str, Any] | None = None,
    append_education: list[dict[str, Any]] | None = None,
    append_experiences: list[dict[str, Any]] | None = None,
    append_projects: list[dict[str, Any]] | None = None,
    append_competitions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Deep-merge personal info into Candidate Library (chat → Profile).

    Scalar patches merge; education/experiences/projects/competitions append rows only
    (RESUME_CONSTITUTION §4 — no fabrication).
    """
    current = get_or_seed_library(user_id)
    next_apply = dict(current.get("apply") or {})
    next_inventory = dict(current.get("inventory") or {})

    changed_apply: list[str] = []
    changed_inventory: list[str] = []

    if apply_patch:
        clean: dict[str, Any] = {}
        for key, value in apply_patch.items():
            if key == "answers" and isinstance(value, dict):
                next_apply["answers"] = _deep_merge_dict(
                    dict(next_apply.get("answers") or {}),
                    value,
                )
                changed_apply.append("answers")
                continue
            if key == "custom_fields" and isinstance(value, dict):
                next_apply["custom_fields"] = _deep_merge_dict(
                    dict(next_apply.get("custom_fields") or {}),
                    {str(k): v for k, v in value.items() if v is not None and v != ""},
                )
                changed_apply.append("custom_fields")
                continue
            if key in _APPLY_SCALAR_KEYS and value is not None and value != "":
                clean[key] = value
                changed_apply.append(key)
        next_apply = {**next_apply, **clean}

    if inventory_patch:
        for key, value in inventory_patch.items():
            if key in _INVENTORY_SCALAR_KEYS and value is not None and value != "":
                next_inventory[key] = value
                changed_inventory.append(key)

    def _append_rows(bucket: str, rows: list[dict[str, Any]] | None) -> None:
        if not rows:
            return
        existing = list(next_inventory.get(bucket) or [])
        for row in rows:
            if not isinstance(row, dict) or not row:
                continue
            existing.append(row)
            changed_inventory.append(f"{bucket}+")
        next_inventory[bucket] = existing

    _append_rows("education", append_education)
    _append_rows("experiences", append_experiences)
    _append_rows("projects", append_projects)
    _append_rows("competitions", append_competitions)

    if not changed_apply and not changed_inventory:
        return {
            **current,
            "changed_apply": [],
            "changed_inventory": [],
        }

    saved = update_library(
        user_id,
        inventory=next_inventory,
        apply_profile=next_apply if changed_apply else None,
    )
    return {
        **saved,
        "changed_apply": sorted(set(changed_apply)),
        "changed_inventory": sorted(set(changed_inventory)),
    }


def reset_library_to_default(user_id: str) -> dict[str, Any]:
    inventory = default_inventory()
    apply_profile = _default_apply_from_inventory(inventory)
    return db.save_candidate_library(user_id, inventory, apply_profile)
