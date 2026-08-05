"""Compute content-only diffs between resume versions for UI highlighting."""

from __future__ import annotations

from typing import Any


def _bullet_texts(entry: dict[str, Any]) -> list[str]:
    bullets = entry.get("bullets") or []
    out: list[str] = []
    for b in bullets:
        if isinstance(b, dict):
            out.append(str(b.get("text") or ""))
        else:
            out.append(str(b))
    return out


def _entry_key(entry: dict[str, Any], kind: str) -> str:
    if kind == "experience":
        return f"exp::{entry.get('company','')}::{entry.get('title','')}"
    if kind == "project":
        return f"proj::{entry.get('name','')}"
    return f"other::{entry.get('name', entry.get('title',''))}"


def compute_resume_diff(before: dict[str, Any] | None, after: dict[str, Any]) -> dict[str, Any]:
    """Return structured diff for frontend color highlighting."""
    before = before or {}
    changes: list[dict[str, Any]] = []
    unchanged_paths: list[str] = []

    b_contact = str(before.get("contact_line") or "")
    a_contact = str(after.get("contact_line") or "")
    if b_contact != a_contact:
        changes.append(
            {
                "path": "contact_line",
                "kind": "replace",
                "before": b_contact,
                "after": a_contact,
            }
        )
    elif a_contact:
        unchanged_paths.append("contact_line")

    b_summary = str(before.get("summary") or "")
    a_summary = str(after.get("summary") or "")
    if b_summary != a_summary:
        changes.append(
            {
                "path": "summary",
                "kind": "replace",
                "before": b_summary,
                "after": a_summary,
            }
        )
    elif a_summary:
        unchanged_paths.append("summary")

    b_skills = str(before.get("skills_certifications") or "")
    a_skills = str(after.get("skills_certifications") or "")
    if b_skills != a_skills:
        changes.append(
            {
                "path": "skills_certifications",
                "kind": "replace",
                "before": b_skills,
                "after": a_skills,
            }
        )
    elif a_skills:
        unchanged_paths.append("skills_certifications")

    for section, kind in (("experiences", "experience"), ("projects", "project")):
        b_map = {_entry_key(e, kind): e for e in (before.get(section) or []) if isinstance(e, dict)}
        a_list = [e for e in (after.get(section) or []) if isinstance(e, dict)]
        a_keys = {_entry_key(e, kind) for e in a_list}

        for key, prev in b_map.items():
            if key in a_keys:
                continue
            label = (
                f"{prev.get('company')}|{prev.get('title')}"
                if kind == "experience"
                else str(prev.get("name") or "")
            )
            changes.append(
                {
                    "path": f"{section}.hidden",
                    "kind": "hide",
                    "before": label,
                    "after": "",
                }
            )

        for idx, entry in enumerate(a_list):
            key = _entry_key(entry, kind)
            prev = b_map.get(key)
            entry_path = f"{section}[{idx}]"
            if not prev:
                changes.append(
                    {
                        "path": entry_path,
                        "kind": "add",
                        "before": "",
                        "after": key,
                    }
                )
            a_bullets = _bullet_texts(entry)
            b_bullets = _bullet_texts(prev) if prev else []
            max_len = max(len(a_bullets), len(b_bullets))
            entry_changed = not prev
            for bi in range(max_len):
                bt = b_bullets[bi] if bi < len(b_bullets) else ""
                at = a_bullets[bi] if bi < len(a_bullets) else ""
                bullet_path = f"{section}[{idx}].bullets[{bi}]"
                if bt == at:
                    if at:
                        unchanged_paths.append(bullet_path)
                    continue
                entry_changed = True
                if not bt and at:
                    changes.append(
                        {
                            "path": bullet_path,
                            "kind": "add",
                            "before": "",
                            "after": at,
                        }
                    )
                elif bt and not at:
                    changes.append(
                        {
                            "path": bullet_path,
                            "kind": "remove",
                            "before": bt,
                            "after": "",
                        }
                    )
                else:
                    changes.append(
                        {
                            "path": bullet_path,
                            "kind": "replace",
                            "before": bt,
                            "after": at,
                        }
                    )
            if prev and not entry_changed:
                unchanged_paths.append(entry_path)

    hidden = list(after.get("hidden_entries") or [])

    return {
        "changed_fields": sorted({c["path"].split("[")[0].split(".")[0] for c in changes}),
        "changes": changes,
        "change_count": len(changes),
        "unchanged_paths": unchanged_paths,
        "hidden_entries": hidden,
        "highlight": {
            "changed": "amber",
            "unchanged": "muted",
            "hidden": "rose",
        },
    }
