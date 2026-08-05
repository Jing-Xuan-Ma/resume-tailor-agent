"""Workspace chat agent tools — Profile read/write, JD match, resume project.

Tools are the only mutation surface for the tool-calling agent loop.
Format lock + evidence rules stay in rewrite / quality_gate (RESUME_CONSTITUTION).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from app import db
from app.modules.profile import library_service
from app.modules.resume_workspace.quality_gate import project_for_jd


def _compact(obj: Any, max_chars: int = 6000) -> str:
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "…[truncated]"


def _score_entry(entry: dict[str, Any], jd_tokens: set[str]) -> float:
    blob = " ".join(
        [
            str(entry.get("title") or ""),
            str(entry.get("company") or ""),
            str(entry.get("name") or ""),
            " ".join(str(t) for t in (entry.get("tools") or [])),
            " ".join(str(t) for t in (entry.get("tags") or [])),
            " ".join(
                str(b.get("text") if isinstance(b, dict) else b)
                for b in (entry.get("bullets") or [])
            ),
        ]
    ).lower()
    if not jd_tokens:
        return 0.0
    hits = sum(1 for t in jd_tokens if t in blob)
    return hits / max(len(jd_tokens), 1)


def match_inventory_to_jd(inventory: dict[str, Any], jd_text: str) -> dict[str, Any]:
    """Deterministic Profile↔JD overlap for agent tool + UI."""
    jd = (jd_text or "").lower()
    tokens = set(re.findall(r"[a-zA-Z+]{3,}", jd))
    experiences = [e for e in (inventory.get("experiences") or []) if isinstance(e, dict)]
    projects = [e for e in (inventory.get("projects") or []) if isinstance(e, dict)]
    skills = str(inventory.get("skills_certifications") or "")

    scored_exp = sorted(
        (
            {
                "kind": "experience",
                "key": f"{e.get('company')}|{e.get('title')}",
                "company": e.get("company"),
                "title": e.get("title"),
                "score": round(_score_entry(e, tokens), 4),
            }
            for e in experiences
        ),
        key=lambda x: x["score"],
        reverse=True,
    )
    scored_proj = sorted(
        (
            {
                "kind": "project",
                "key": str(e.get("name") or ""),
                "name": e.get("name"),
                "score": round(_score_entry(e, tokens), 4),
            }
            for e in projects
        ),
        key=lambda x: x["score"],
        reverse=True,
    )

    skill_hits = []
    for part in re.split(r"[,|;/]", skills):
        s = part.strip()
        if len(s) >= 2 and s.lower() in jd:
            skill_hits.append(s)

    projected = project_for_jd(inventory, jd_text)
    hidden = list(projected.get("hidden_entries") or [])

    # Gaps: common DA tokens in JD not present in inventory blob
    inv_blob = json.dumps(inventory, ensure_ascii=False).lower()
    gap_candidates = sorted(tokens, key=len, reverse=True)[:40]
    gaps = [t for t in gap_candidates if t not in inv_blob][:12]

    return {
        "has_jd": bool(jd_text.strip()),
        "top_experiences": scored_exp[:5],
        "top_projects": scored_proj[:5],
        "skill_hits_in_jd": skill_hits[:20],
        "recommended_show": {
            "experiences": [
                f"{e.get('company')}|{e.get('title')}" for e in (projected.get("experiences") or [])
            ],
            "projects": [str(p.get("name") or "") for p in (projected.get("projects") or [])],
        },
        "hidden_entries": hidden,
        "honest_gaps": gaps,
        "note": (
            "Use project_resume to apply this projection onto the locked master template. "
            "Do not invent skills listed in honest_gaps."
        ),
    }


@dataclass
class AgentRunState:
    intent: str = "chat"
    profile_updated: bool = False
    changed_apply: list[str] = field(default_factory=list)
    changed_inventory: list[str] = field(default_factory=list)
    did_rewrite: bool = False
    new_version_id: str | None = None
    version_index: int | None = None
    full_resume: dict | None = None
    keyword_matches: list = field(default_factory=list)
    content_delta: dict = field(default_factory=dict)
    tool_trace: list[str] = field(default_factory=list)


class AgentToolContext:
    """Bound tools for one agent_turn."""

    def __init__(
        self,
        *,
        user_id: str,
        session_id: str,
        workspace: Any,
        base_version_id: str | None = None,
    ):
        self.user_id = user_id
        self.session_id = session_id
        self.workspace = workspace
        self.base_version_id = base_version_id
        self.state = AgentRunState()

    def get_profile(self) -> str:
        lib = library_service.get_or_seed_library(self.user_id)
        payload = {
            "apply": lib.get("apply") or {},
            "inventory": {
                k: (lib.get("inventory") or {}).get(k)
                for k in (
                    "candidate_name",
                    "contact_line",
                    "summary",
                    "skills_certifications",
                    "github_url",
                    "education",
                    "experiences",
                    "projects",
                    "competitions",
                    "evidence_links",
                )
            },
            "updated_at": lib.get("updated_at"),
            "apply_keys": sorted((lib.get("apply") or {}).keys()),
            "custom_fields": (lib.get("apply") or {}).get("custom_fields") or {},
        }
        self.state.tool_trace.append("get_profile")
        return _compact(payload)

    def get_jd(self) -> str:
        session = db.get_jd_session(self.session_id) or {}
        jd = str(session.get("jd_text") or "")
        self.state.tool_trace.append("get_jd")
        return _compact(
            {
                "session_id": self.session_id,
                "job_id": session.get("job_id"),
                "jd_text": jd[:8000],
                "jd_chars": len(jd),
            }
        )

    def update_profile_fields(
        self,
        apply_fields: dict[str, Any] | None = None,
        inventory_fields: dict[str, Any] | None = None,
        custom_fields: dict[str, Any] | None = None,
    ) -> str:
        apply_patch = dict(apply_fields or {})
        if custom_fields:
            apply_patch["custom_fields"] = custom_fields
        result = library_service.patch_library(
            self.user_id,
            apply_patch=apply_patch or None,
            inventory_patch=inventory_fields or None,
        )
        changed_a = result.get("changed_apply") or []
        changed_i = result.get("changed_inventory") or []
        if changed_a or changed_i:
            self.state.profile_updated = True
            self.state.intent = "update_profile"
            self.state.changed_apply = sorted(set(self.state.changed_apply + list(changed_a)))
            self.state.changed_inventory = sorted(set(self.state.changed_inventory + list(changed_i)))
        self.state.tool_trace.append("update_profile_fields")
        return _compact(
            {
                "ok": bool(changed_a or changed_i),
                "changed_apply": changed_a,
                "changed_inventory": changed_i,
                "hint": "Open Profile tab to review. Location maps to apply.location.",
            }
        )

    def add_inventory_item(self, kind: str, item: dict[str, Any]) -> str:
        kind_l = (kind or "").strip().lower()
        bucket_map = {
            "experience": "experiences",
            "experiences": "experiences",
            "education": "education",
            "project": "projects",
            "projects": "projects",
            "competition": "competitions",
            "competitions": "competitions",
        }
        bucket = bucket_map.get(kind_l)
        if not bucket:
            return _compact({"ok": False, "error": f"Unknown kind={kind}. Use experience|education|project|competition"})
        if not isinstance(item, dict) or not item:
            return _compact({"ok": False, "error": "item must be a non-empty object"})

        kwargs: dict[str, Any] = {}
        if bucket == "experiences":
            kwargs["append_experiences"] = [item]
        elif bucket == "education":
            kwargs["append_education"] = [item]
        elif bucket == "projects":
            kwargs["append_projects"] = [item]
        else:
            kwargs["append_competitions"] = [item]

        result = library_service.patch_library(self.user_id, **kwargs)
        changed_i = result.get("changed_inventory") or []
        if changed_i:
            self.state.profile_updated = True
            self.state.intent = "update_profile"
            self.state.changed_inventory = sorted(set(self.state.changed_inventory + list(changed_i)))
        self.state.tool_trace.append("add_inventory_item")
        return _compact({"ok": bool(changed_i), "bucket": bucket, "changed_inventory": changed_i})

    def match_profile_to_jd(self) -> str:
        session = db.get_jd_session(self.session_id) or {}
        jd = str(session.get("jd_text") or "")
        inv = library_service.get_master_inventory(self.user_id)
        self.state.tool_trace.append("match_profile_to_jd")
        if self.state.intent == "chat":
            self.state.intent = "chat"
        return _compact(match_inventory_to_jd(inv, jd))

    async def project_resume(self, instruction: str) -> str:
        instr = (instruction or "").strip() or (
            "Project the Master Inventory onto the locked master template for this JD: "
            "show the most relevant experiences/projects, keep one page, no fabrication."
        )
        result = await self.workspace.rewrite(
            user_id=self.user_id,
            session_id=self.session_id,
            instruction=instr,
            base_version_id=self.base_version_id,
        )
        self.state.did_rewrite = True
        self.state.intent = "rewrite"
        self.state.new_version_id = result.get("new_version_id")
        self.state.version_index = result.get("version_index")
        self.state.full_resume = result.get("full_resume")
        self.state.keyword_matches = result.get("keyword_matches") or []
        self.state.content_delta = result.get("content_delta") or {}
        self.base_version_id = self.state.new_version_id
        self.state.tool_trace.append("project_resume")
        return _compact(
            {
                "ok": True,
                "version_index": result.get("version_index"),
                "new_version_id": result.get("new_version_id"),
                "content_delta_keys": list((result.get("content_delta") or {}).keys()),
                "hidden_entries": (result.get("full_resume") or {}).get("hidden_entries") or [],
                "hint": "Tell the user to check the PDF preview on the right.",
            }
        )

    def get_resume_preview(self) -> str:
        versions = db.list_resume_versions(self.session_id, self.user_id)
        latest = versions[-1] if versions else None
        self.state.tool_trace.append("get_resume_preview")
        if not latest:
            return _compact({"ok": False, "message": "No resume version yet for this session."})

        full = latest.get("full_resume") or {}
        return _compact(
            {
                "ok": True,
                "version_id": latest.get("id"),
                "version_index": latest.get("version_index"),
                "summary": full.get("summary"),
                "experience_titles": [
                    f"{e.get('title')} | {e.get('company')}"
                    for e in (full.get("experiences") or [])
                    if isinstance(e, dict)
                ],
                "project_names": [
                    p.get("name") for p in (full.get("projects") or []) if isinstance(p, dict)
                ],
                "hidden_entries": full.get("hidden_entries") or [],
                "skills": full.get("skills_certifications"),
            }
        )


def build_langchain_tools(ctx: AgentToolContext) -> list[Any]:
    """Create LangChain StructuredTools bound to this turn's context."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    class EmptyArgs(BaseModel):
        pass

    class UpdateProfileArgs(BaseModel):
        apply_fields: dict[str, Any] = Field(
            default_factory=dict,
            description=(
                "Apply Profile scalars: full_name, email, phone, location, linkedin_url, "
                "portfolio_url, github_url, visa_status, earliest_start, salary_expectation, "
                "preferred_name, work_authorized, needs_sponsorship, willing_to_relocate. "
                "Map address/住址 to location."
            ),
        )
        inventory_fields: dict[str, Any] = Field(
            default_factory=dict,
            description="Inventory scalars: candidate_name, contact_line, summary, skills_certifications, github_url",
        )
        custom_fields: dict[str, Any] = Field(
            default_factory=dict,
            description="Extra key/value facts for Apply (e.g. mailing_address_line2, pronouns).",
        )

    class AddItemArgs(BaseModel):
        kind: str = Field(description="experience | education | project | competition")
        item: dict[str, Any] = Field(description="Row object with user-stated facts only")

    class ProjectArgs(BaseModel):
        instruction: str = Field(
            description="How to tailor the one-page projection for this JD (content only)."
        )

    tools = [
        StructuredTool.from_function(
            name="get_profile",
            description="Read the user's Profile (Apply + Master Inventory). Call before updating or matching.",
            func=ctx.get_profile,
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            name="get_jd",
            description="Read the current JD text for this tailor session.",
            func=ctx.get_jd,
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            name="update_profile_fields",
            description=(
                "Save personal facts the user stated into Profile. "
                "Use location for address/住址. Use custom_fields for extra keys not in the default schema."
            ),
            func=ctx.update_profile_fields,
            args_schema=UpdateProfileArgs,
        ),
        StructuredTool.from_function(
            name="add_inventory_item",
            description="Append a new experience, education, project, or competition row (user-stated facts only).",
            func=ctx.add_inventory_item,
            args_schema=AddItemArgs,
        ),
        StructuredTool.from_function(
            name="match_profile_to_jd",
            description="Score Profile experiences/projects against the JD; list honest gaps. Does not rewrite resume.",
            func=ctx.match_profile_to_jd,
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            name="get_resume_preview",
            description="Summarize the latest resume version in this session (titles, hidden entries).",
            func=ctx.get_resume_preview,
            args_schema=EmptyArgs,
        ),
        StructuredTool.from_function(
            name="project_resume",
            description=(
                "Rewrite/project the resume onto the locked master DOCX for this JD "
                "(show/hide + wording). Call after match_profile_to_jd when user wants the resume updated."
            ),
            coroutine=ctx.project_resume,
            args_schema=ProjectArgs,
        ),
    ]
    return tools


ToolHandler = Callable[..., str | Awaitable[str]]


def dispatch_tool(ctx: AgentToolContext, name: str, args: dict[str, Any]) -> Any:
    """Sync/async dispatch by tool name (JSON fallback path)."""
    args = args or {}
    if name == "get_profile":
        return ctx.get_profile()
    if name == "get_jd":
        return ctx.get_jd()
    if name == "update_profile_fields":
        return ctx.update_profile_fields(
            apply_fields=args.get("apply_fields"),
            inventory_fields=args.get("inventory_fields"),
            custom_fields=args.get("custom_fields"),
        )
    if name == "add_inventory_item":
        return ctx.add_inventory_item(str(args.get("kind") or ""), dict(args.get("item") or {}))
    if name == "match_profile_to_jd":
        return ctx.match_profile_to_jd()
    if name == "get_resume_preview":
        return ctx.get_resume_preview()
    if name == "project_resume":
        return ctx.project_resume(str(args.get("instruction") or ""))
    return _compact({"ok": False, "error": f"Unknown tool: {name}"})
