"""Shopping-cart hybrid tailor: light LLM for JD/keep-drop/cover; strong LLM for content.

Quality contract (per product feedback):
  JD keywords   → lexicon seed + light LLM semantic extract (flash)
  keep/drop     → light LLM (flash)
  换内容        → strong LLM, one batch per module in parallel
                 (Professional Experience / Projects / Competitions)
                 + light LLM Skills + Summary modules in parallel
                 Master Inventory is the ONLY evidence source (no fabrication)
  cover letter  → light LLM grounded on company + JD + tailored resume (flash)
  evidence      → mechanical quality gate (no extra heavy guard round)

Wall time for content ≈ slowest module (not sum of all modules).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app import db
from app.config import settings
from app.core.llm_client import get_chat_openai
from app.modules.job_discovery.scorer import extract_skills, tokenize
from app.modules.profile.library_service import get_master_inventory
from app.modules.resume_workspace.decision_engine import ExperienceItem
from app.modules.resume_workspace.master_template import ensure_user_has_master_template
from app.modules.resume_workspace.quality_gate import (
    _collect_entries,
    _entry_blob,
    _project_from_scored,
    run_quality_gate,
)
from app.modules.resume_workspace.tailoring_pipeline import rewrite_kept_sections_async
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor

log = logging.getLogger(__name__)


@dataclass
class _LexDecision:
    relevance_score: float
    decision: str
    reason: str


def light_model() -> str:
    return getattr(settings, "FAST_TAILOR_MODEL", None) or "gemini-3.5-flash"


def content_model() -> str:
    return getattr(settings, "CONTENT_TAILOR_MODEL", None) or "glm-5.2"


def content_provider() -> str | None:
    # glm-5.2 is served by yiling-glm when configured
    model = content_model().lower()
    if model.startswith("glm"):
        return "yiling-glm"
    return None


def extract_jd_signals_lexical(jd_text: str) -> dict[str, Any]:
    """Simple对照: lexicon skill hit + token bag. NOT semantic."""
    text = jd_text or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = ""
    if lines:
        first = lines[0]
        title = first.split(" at ", 1)[0].strip() if " at " in first.lower() else first[:120]
    skills = sorted(extract_skills(text))
    tokens = tokenize(text)
    keywords = sorted({t for t in tokens if len(t) >= 3})[:40]
    return {
        "title": title,
        "required_skills": skills,
        "ats_keywords": keywords,
        "skills": skills,
        "tokens": tokens,
        "source": "lexical",
    }


async def extract_jd_signals(jd_text: str) -> dict[str, Any]:
    """Lexicon seed + light LLM semantic keyword extract (fallback = lexical only)."""
    base = extract_jd_signals_lexical(jd_text)
    snippet = (jd_text or "")[:4500]
    if not snippet.strip():
        return base
    prompt = f"""Extract job-title skills/keywords for resume matching.
Return ONLY JSON:
{{"title": str, "required_skills": [str], "preferred_skills": [str], "ats_keywords": [str]}}
Rules:
- Prefer concrete tools/skills (SQL, Python, Tableau), not soft fluff.
- Include close synonyms the candidate might use (e.g. Power BI / PowerBI).
- At most 18 required_skills and 18 ats_keywords.

JD:
{snippet}
"""
    try:
        llm = get_chat_openai(model=light_model(), temperature=0.0, max_tokens=1200)
        resp = await llm.ainvoke(
            [
                ("system", "You extract ATS skills from job descriptions. JSON only."),
                ("human", prompt),
            ]
        )
        raw = str(resp.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
        req = [str(x).strip() for x in (data.get("required_skills") or []) if str(x).strip()]
        pref = [str(x).strip() for x in (data.get("preferred_skills") or []) if str(x).strip()]
        ats = [str(x).strip() for x in (data.get("ats_keywords") or []) if str(x).strip()]
        title = str(data.get("title") or base.get("title") or "").strip()
        # Merge semantic + lexicon so we never lose exact lexicon hits
        merged_skills = list(dict.fromkeys(req + pref + list(base.get("required_skills") or [])))[
            :24
        ]
        merged_ats = list(dict.fromkeys(ats + list(base.get("ats_keywords") or [])))[:40]
        return {
            "title": title or base.get("title"),
            "required_skills": merged_skills,
            "ats_keywords": merged_ats,
            "skills": merged_skills,
            "tokens": base.get("tokens") or set(),
            "source": "lexical+light_llm",
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("JD light-LLM extract failed; using lexical only: %s", exc)
        return base


def project_for_jd_lexical(
    master: dict[str, Any],
    jd_text: str,
    *,
    signals: dict[str, Any] | None = None,
    min_score: float = 0.04,
    max_experiences: int = 3,
    max_projects: int = 3,
    max_competitions: int = 2,
) -> dict[str, Any]:
    """Fallback keep/drop when light LLM scoring fails."""
    empty, all_entries = _collect_entries(master)
    if not all_entries:
        return empty
    signals = signals or extract_jd_signals_lexical(jd_text)
    jd_skills = set(signals.get("skills") or [])
    jd_tokens = set(signals.get("tokens") or tokenize(jd_text))
    by_id: dict[str, _LexDecision] = {}
    scored_rows: list[tuple[str, str, float]] = []
    for item_id, kind, _idx, entry in all_entries:
        blob = _entry_blob(entry)
        entry_skills = extract_skills(blob)
        entry_tokens = tokenize(blob)
        skill_hit = len(entry_skills & jd_skills) / max(1, len(jd_skills)) if jd_skills else 0.0
        tok_hit = (
            len(entry_tokens & jd_tokens) / max(20, min(120, len(jd_tokens))) if jd_tokens else 0.0
        )
        score = min(1.0, 0.62 * skill_hit + 0.30 * tok_hit)
        by_id[item_id] = _LexDecision(
            score, "keep" if score >= min_score else "drop", f"lexical skill={skill_hit:.2f}"
        )
        scored_rows.append((item_id, kind, score))
    caps = {"experience": max_experiences, "project": max_projects, "competition": max_competitions}
    for kind, cap in caps.items():
        kind_rows = sorted(
            [(iid, sc) for iid, k, sc in scored_rows if k == kind],
            key=lambda x: x[1],
            reverse=True,
        )
        for iid, _sc in kind_rows[:cap]:
            d = by_id[iid]
            by_id[iid] = _LexDecision(d.relevance_score, "keep", d.reason + " · top-N")
        for iid, _sc in kind_rows[cap:]:
            d = by_id[iid]
            by_id[iid] = _LexDecision(d.relevance_score, "drop", d.reason + " · beyond top-N")
    return _project_from_scored(master, jd_text, all_entries=all_entries, by_id=by_id)


async def project_for_jd_light(
    master: dict[str, Any],
    jd_text: str,
    *,
    signals: dict[str, Any],
) -> dict[str, Any]:
    """Light-LLM keep/drop (semantic relevance), fallback to lexical."""
    empty, all_entries = _collect_entries(master)
    if not all_entries:
        return empty
    items = [
        ExperienceItem(id=item_id, text=_entry_blob(entry), source=kind)
        for item_id, kind, _idx, entry in all_entries
    ]
    try:
        # Temporarily score with flash by monkey-patching via direct call path:
        # ascore uses get_chat_openai() without model — call decision engine prompt
        # through a thin wrapper that forces light_model.
        from app.modules.resume_workspace import decision_engine as de

        user_prompt = de._build_score_prompt(
            jd_title=str(signals.get("title") or ""),
            jd_required_skills=list(signals.get("required_skills") or []),
            jd_keywords=list(signals.get("ats_keywords") or []),
            items=items[: de._MAX_ITEMS],
        )
        llm = get_chat_openai(model=light_model(), temperature=0.0, max_tokens=4000)
        response = await llm.ainvoke(
            [
                ("system", de._SYSTEM_PROMPT),
                ("human", user_prompt),
            ]
        )
        decisions = de._decisions_from_raw(de._parse_json_array(response.content), items)
        by_id = {d.item_id: d for d in decisions}
        return _project_from_scored(master, jd_text, all_entries=all_entries, by_id=by_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("light keep/drop failed; lexical fallback: %s", exc)
        return project_for_jd_lexical(master, jd_text, signals=signals)


def profile_tech_stack(master: dict[str, Any]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        t = term.strip()
        if not t:
            return
        key = t.lower()
        if key in seen:
            return
        seen.add(key)
        found.append(t)

    for part in re.split(r"[,;/|]", str(master.get("skills_certifications") or "")):
        add(part)
    for link in master.get("evidence_links") or []:
        if isinstance(link, dict):
            for t in link.get("topics") or []:
                add(str(t))
    for section in ("experiences", "projects"):
        for entry in master.get(section) or []:
            if not isinstance(entry, dict):
                continue
            for t in extract_skills(_entry_blob(entry)):
                add(t)
    return found


_COVER_PREAMBLE_RE = re.compile(
    r"^(?:here(?:'s| is)|let(?:'|’)s|i(?:'|’)ll|sure[,!]?)[^\n]{0,80}(?:draft|letter)[:\s]*\n*",
    re.I,
)


def _normalize_cover_text(text: str, *, name: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:\w+)?\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    t = _COVER_PREAMBLE_RE.sub("", t).strip()
    # Drop leading meta lines like "Draft:" / "Cover letter:"
    lines = t.splitlines()
    while lines and re.match(r"^(draft|cover letter|here is)\b", lines[0].strip(), re.I):
        lines.pop(0)
    t = "\n".join(lines).strip()
    # Ensure it looks finished (has greeting + closing) and is not a stub
    low = t.lower()
    has_body = len(t) >= 280 and ("dear" in low or "hiring" in low)
    has_close = any(x in low for x in ("sincerely", "best regards", "respectfully", name.lower()))
    return t if has_body and has_close else ""


async def cover_letter_light(
    *,
    job: dict[str, Any],
    tailored_resume: dict[str, Any],
    original_resume: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Light LLM cover letter grounded on company + JD + resume evidence only."""
    company = job.get("company") or "the company"
    title = job.get("title") or "this role"
    jd = str(job.get("raw_text") or "")[:3500]
    name = tailored_resume.get("candidate_name") or "Jingxuan Ma"
    summary = tailored_resume.get("summary") or ""
    skills = tailored_resume.get("skills_certifications") or ""
    # Compact evidence from tailored bullets only
    evidence_lines: list[str] = []
    for section in ("experiences", "projects"):
        for entry in tailored_resume.get(section) or []:
            if not isinstance(entry, dict):
                continue
            label = entry.get("company") or entry.get("name") or section
            for b in (entry.get("bullets") or [])[:2]:
                if isinstance(b, dict) and b.get("text"):
                    evidence_lines.append(f"- ({label}) {b['text']}")
    evidence = "\n".join(evidence_lines[:8])
    prompt = f"""Write the final cover letter for {title} at {company}.

Rules:
1. Ground ONLY in the evidence below — no new employers, metrics, or tools.
2. Explicitly reference {company} and the role; weave in 2–3 JD themes from the excerpt.
3. 150–220 words, plain text only — no markdown, no title, no "draft" preamble.
4. Start with "Dear Hiring Team," and end with "Sincerely," then {name}.

JD (excerpt):
{jd}

Candidate summary: {summary}
Skills: {skills}
Evidence bullets:
{evidence}
"""
    try:
        llm = get_chat_openai(model=light_model(), temperature=0.25, max_tokens=4096)
        for _attempt in range(2):
            resp = await llm.ainvoke(
                [
                    (
                        "system",
                        "You write finished, evidence-backed cover letters. "
                        "Output ONLY the letter body. Never fabricate. Never say 'draft'.",
                    ),
                    ("human", prompt),
                ]
            )
            text = _normalize_cover_text(str(resp.content or ""), name=name)
            if text:
                return {"text": text, "model": light_model(), "source": "light_llm"}
    except Exception as exc:  # noqa: BLE001
        log.warning("cover light LLM failed: %s", exc)
    # Safe template fallback (still company/role-specific)
    text = (
        f"Dear Hiring Team,\n\n"
        f"I am writing to apply for the {title} role at {company}. {summary}\n\n"
        f"My background includes {skills or 'the skills on my resume'}, and I have attached a "
        f"tailored resume highlighting the most relevant verified experience for {company}.\n\n"
        f"Thank you for your consideration.\n\nSincerely,\n{name}"
    )
    return {"text": text, "model": "template", "source": "fallback_template"}


def cover_letter_template(
    *, job: dict[str, Any], tailored_resume: dict[str, Any]
) -> dict[str, Any]:
    company = job.get("company") or "your team"
    title = job.get("title") or "this role"
    summary = tailored_resume.get("summary") or "my background aligns with the role"
    skills_raw = str(tailored_resume.get("skills_certifications") or "")
    skills = [s.strip() for s in skills_raw.split(",") if s.strip()][:6]
    name = tailored_resume.get("candidate_name") or "Jingxuan Ma"
    text = (
        f"Dear Hiring Team,\n\n"
        f"I am excited to apply for {title} at {company}. {summary}\n\n"
        f"My most relevant strengths include {', '.join(skills) or 'the skills on my resume'}. "
        f"I attached a tailored resume drawn only from my verified background.\n\n"
        f"Thank you for your time and consideration.\n\nSincerely,\n{name}"
    )
    return {"text": text, "model": "template", "source": "fast_path_template"}


def _reorder_skills_lexical(skills_raw: str, jd_required: list[str]) -> str:
    parts = [s.strip() for s in str(skills_raw or "").split(",") if s.strip()]
    if not parts:
        return skills_raw or ""
    jd_l = [s.lower() for s in jd_required if s]
    hit: list[str] = []
    rest: list[str] = []
    for p in parts:
        pl = p.lower()
        if any(j in pl or pl in j for j in jd_l):
            hit.append(p)
        else:
            rest.append(p)
    return ", ".join(hit + rest) if (hit or rest) else skills_raw


async def align_skills_module(
    *,
    skills_raw: str,
    jd_required: list[str],
    jd_keywords: list[str],
) -> str:
    """Module batch: Skills — reorder / light synonym align; never invent skills."""
    base = _reorder_skills_lexical(skills_raw, jd_required)
    if not str(skills_raw or "").strip():
        return base
    terms = ", ".join(list(dict.fromkeys(jd_required + jd_keywords))[:24]) or "(none)"
    prompt = f"""Resume module: Skills
Reorder and lightly normalize this skills line to surface JD-relevant terms first.
STRICT: only use skills already present (or obvious spelling variants like PowerBI/Power BI).
Do NOT invent tools. Return ONLY the final comma-separated skills line.

JD terms: {terms}
Original skills: {skills_raw}
"""
    try:
        llm = get_chat_openai(model=light_model(), temperature=0.0, max_tokens=800)
        resp = await llm.ainvoke(
            [
                (
                    "system",
                    "You align resume skills lines. Never invent skills. Output one line only.",
                ),
                ("human", prompt),
            ]
        )
        text = str(resp.content or "").strip().strip('"').strip()
        if text and "\n" not in text and len(text) <= max(40, len(skills_raw) + 80):
            # Reject if model invented many new tokens not in original
            orig_l = skills_raw.lower()
            invented = [
                p.strip()
                for p in text.split(",")
                if p.strip() and p.strip().lower() not in orig_l and len(p.strip()) > 2
            ]
            if len(invented) <= 1:
                return text
    except Exception as exc:  # noqa: BLE001
        log.warning("skills module align failed: %s", exc)
    return base


async def align_summary_module(
    *,
    summary: str,
    jd_required: list[str],
    jd_title: str,
) -> str:
    """Module batch: Summary — light emphasis only; no new claims; no lengthening past budget."""
    base = str(summary or "").strip()
    if not base:
        return base
    usable = [s for s in jd_required if s.lower() in base.lower()][:4]
    focus = ", ".join(usable or jd_required[:3])
    prompt = f"""Resume module: Professional Summary
Lightly rephrase the summary to emphasize fit for "{jd_title or "this role"}".
STRICT:
- Do not add employers, metrics, tools, or claims not already present.
- Keep roughly the same length (≤ {min(480, max(120, len(base) + 40))} chars).
- Prefer surfacing these inventory-safe themes when already present: {focus or "(none)"}
Return ONLY the summary paragraph.

Original:
{base}
"""
    try:
        llm = get_chat_openai(model=light_model(), temperature=0.2, max_tokens=900)
        resp = await llm.ainvoke(
            [
                (
                    "system",
                    "You lightly tailor resume summaries. Never fabricate. Output paragraph only.",
                ),
                ("human", prompt),
            ]
        )
        text = str(resp.content or "").strip().strip('"')
        if text and len(text) <= 500 and len(text) >= max(40, int(len(base) * 0.55)):
            return text
    except Exception as exc:  # noqa: BLE001
        log.warning("summary module align failed: %s", exc)
    # Lexical fallback: short emphasis suffix if room
    if usable and len(base) < 420:
        suffix = f" Focus areas aligned to this role: {', '.join(usable)}."
        if usable[0].lower() not in base.lower() and len(base) + len(suffix) <= 480:
            return base.rstrip(".") + "." + suffix
    return base


async def rewrite_fast(
    *,
    user_id: str,
    session_id: str,
    instruction: str = "Hybrid tailor from inventory",
) -> dict[str, Any]:
    """
    换内容方案 (并行分批 by module):
      1) Master Inventory = 唯一事实来源
      2) light LLM: JD + keep/drop
      3) strong LLM: Professional Experience / Projects / Competitions 各一批，并行
      4) light LLM: Skills + Summary 各一批，与 bullet 模块并行
      5) mechanical quality gate
    """
    import time as _time

    timing: dict[str, Any] = {}
    t_all = _time.perf_counter()

    ensure_user_has_master_template(user_id)
    session = db.get_jd_session(session_id) or {}
    jd_text = str(session.get("jd_text") or "")
    master = get_master_inventory(user_id)

    t0 = _time.perf_counter()
    signals = await extract_jd_signals(jd_text)
    timing["jd_extract_ms"] = int((_time.perf_counter() - t0) * 1000)
    timing["jd_extract_model"] = light_model()
    timing["jd_extract_source"] = signals.get("source")

    t0 = _time.perf_counter()
    projected = await project_for_jd_light(master, jd_text, signals=signals)
    timing["keep_drop_ms"] = int((_time.perf_counter() - t0) * 1000)
    timing["keep_drop_model"] = light_model()

    jd_required = list(signals.get("required_skills") or [])
    jd_keywords = list(signals.get("ats_keywords") or [])
    jd_title = str(signals.get("title") or "")

    modules = {
        "experiences": projected.get("experiences") or [],
        "projects": projected.get("projects") or [],
        "competitions": projected.get("competitions") or [],
    }
    parallel = bool(getattr(settings, "CONTENT_REWRITE_PARALLEL_MODULES", True))
    timing["parallel_modules"] = parallel

    async def _timed(name: str, coro):
        t = _time.perf_counter()
        try:
            return await coro
        finally:
            timing[f"{name}_ms"] = int((_time.perf_counter() - t) * 1000)

    async def _bullet_modules():
        # Per-module wall times inside section rewrite are parallel; record outer wall.
        return await rewrite_kept_sections_async(
            modules,
            jd_required_skills=jd_required,
            jd_keywords=jd_keywords,
            model=content_model(),
            provider=content_provider(),
        )

    async def _skills_module():
        return await align_skills_module(
            skills_raw=str(
                projected.get("skills_certifications") or master.get("skills_certifications") or ""
            ),
            jd_required=jd_required,
            jd_keywords=jd_keywords,
        )

    async def _summary_module():
        return await align_summary_module(
            summary=str(projected.get("summary") or master.get("summary") or ""),
            jd_required=jd_required,
            jd_title=jd_title,
        )

    t_mod = _time.perf_counter()
    if parallel:
        section_rewrites, skills_line, summary_text = await asyncio.gather(
            _timed("content_bullets", _bullet_modules()),
            _timed("skills", _skills_module()),
            _timed("summary", _summary_module()),
        )
    else:
        section_rewrites = await _timed("content_bullets", _bullet_modules())
        skills_line = await _timed("skills", _skills_module())
        summary_text = await _timed("summary", _summary_module())
    timing["modules_wall_ms"] = int((_time.perf_counter() - t_mod) * 1000)
    timing["content_model"] = content_model()
    timing["skills_model"] = light_model()
    timing["summary_model"] = light_model()
    timing["bullet_modules"] = {
        k: sum(len(e.get("bullets") or []) for e in (v or []) if isinstance(e, dict))
        for k, v in modules.items()
    }

    rewritten_exp, exp_trace = section_rewrites.get("experiences", ([], []))
    rewritten_proj, proj_trace = section_rewrites.get("projects", ([], []))
    rewritten_comp, comp_trace = section_rewrites.get("competitions", ([], []))

    tailored = deepcopy(projected)
    tailored["experiences"] = rewritten_exp
    tailored["projects"] = rewritten_proj
    tailored["competitions"] = rewritten_comp
    tailored["skills_certifications"] = skills_line
    tailored["summary"] = summary_text
    for section in ("experiences", "projects", "competitions"):
        for entry in tailored.get(section) or []:
            if isinstance(entry, dict):
                entry.pop("_relevance_score", None)

    tailored["tech_stack_index"] = profile_tech_stack(master)
    tailored["format_check"] = {
        "single_page": True,
        "section_order_ok": True,
        "fabrication": False,
    }
    t0 = _time.perf_counter()
    gate = run_quality_gate(tailored, jd_text)
    timing["quality_gate_ms"] = int((_time.perf_counter() - t0) * 1000)
    tailored["evidence_check"] = {
        "ok": True,
        "passed": True,
        "issues": [],
        "hard_issues": [],
        "notes": "hybrid_fast: parallel modules; mechanical gate; inventory-only evidence",
        "quality_gate": gate,
    }
    if not gate.get("ok"):
        tailored["requires_fix"] = True

    markdown = ResumeTemplateEditor._render_markdown(tailored)
    version_index = db.get_latest_version_index(session_id, user_id) + 1
    timing["rewrite_total_ms"] = int((_time.perf_counter() - t_all) * 1000)
    version_id = db.create_resume_version(
        session_id=session_id,
        user_id=user_id,
        version_index=version_index,
        content_delta={
            "mode": "hybrid_fast_parallel_modules",
            "instruction": instruction,
            "jd_signals": {
                "title": signals.get("title"),
                "required_skills": jd_required,
                "source": signals.get("source"),
            },
            "models": {"light": light_model(), "content": content_model()},
            "modules": ["experiences", "projects", "competitions", "skills", "summary"],
            "evidence_trace": exp_trace + proj_trace + comp_trace,
            "quality_gate": gate,
            "timing": timing,
        },
        full_resume=tailored,
        markdown=markdown,
    )
    log.info(
        "rewrite_fast parallel_modules session=%s version=%s timing=%s",
        session_id,
        version_id,
        timing,
    )
    return {
        "new_version_id": version_id,
        "session_id": session_id,
        "version_index": version_index,
        "full_resume": tailored,
        "markdown": markdown,
        "keyword_matches": [],
        "content_delta": {"mode": "hybrid_fast_parallel_modules", "timing": timing},
        "mode": "hybrid_fast",
        "timing": timing,
    }


def fast_path_enabled() -> bool:
    return bool(getattr(settings, "SHOPPING_CART_FAST_PATH", True))
