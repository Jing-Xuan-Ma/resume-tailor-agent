"""Beijing Yiling (依零) AI Agent intern — inventory facts + JD-conditioned bullet variants.

Facts only from the resume-agent product work (FastAPI, Next.js, OOXML format lock,
JD projection, Word PDF one-page gate, evidence-linked bullets). No fabricated metrics.
"""

from __future__ import annotations

from typing import Any

YILING_COMPANY = "Beijing Yiling Network Technology Co., Ltd."
YILING_COMPANY_ZH = "北京依零网络科技有限公司"
YILING_TITLE = "AI Agent Development Intern"
YILING_LOCATION = "Beijing, China"
YILING_DATES = "June 2026 - August 2026"
YILING_DONOR = "Shenwan"  # OOXML carve donor heading substring
# Public evidence repo for this internship product (resume tailor agent)
RESUME_TAILOR_GITHUB = "https://github.com/Jing-Xuan-Ma/resume-tailor-agent"

# Canonical inventory entry (default bullets = general DA / agent framing)
YILING_EXPERIENCE: dict[str, Any] = {
    "company": YILING_COMPANY,
    "company_zh": YILING_COMPANY_ZH,
    "title": YILING_TITLE,
    "location": YILING_LOCATION,
    "date_range": YILING_DATES,
    "github_url": RESUME_TAILOR_GITHUB,
    "evidence_url": RESUME_TAILOR_GITHUB,
    "tags": [
        "ai-agent",
        "python",
        "fastapi",
        "nextjs",
        "langgraph",
        "rag",
        "chroma",
        "evidence-guard",
        "ats",
        "greenhouse",
        "lever",
        "playwright",
    ],
    "bullets": [
        {
            "text": (
                "Built an AI job-application agent (FastAPI, LangGraph, Next.js) that tailors "
                "resumes via RAG over user experience embeddings in Chroma, with an independent "
                "Evidence Guard module rejecting unsupported claims"
            ),
            "evidence_from": "yiling_exp_1",
            "original_text": (
                "Built an AI job-application agent (FastAPI, LangGraph, Next.js) that tailors "
                "resumes via RAG over user experience embeddings in Chroma, with an independent "
                "Evidence Guard module rejecting unsupported claims"
            ),
        },
        {
            "text": (
                "Designed a multi-stage pipeline (JD parsing, semantic match, rewrite-only "
                "generation, fact-check) and a safety-first application flow with manual confirm "
                "by default and optional Playwright ATS auto-submit behind feature flags"
            ),
            "evidence_from": "yiling_exp_2",
            "original_text": (
                "Designed a multi-stage pipeline (JD parsing, semantic match, rewrite-only "
                "generation, fact-check) and a safety-first application flow with manual confirm "
                "by default and optional Playwright ATS auto-submit behind feature flags"
            ),
        },
        {
            "text": (
                "Integrated multi-source job discovery and scoring with ATS-aware application "
                "package generation, including cover letters, form answers, and Greenhouse/Lever "
                "connectors"
            ),
            "evidence_from": "yiling_exp_3",
            "original_text": (
                "Integrated multi-source job discovery and scoring with ATS-aware application "
                "package generation, including cover letters, form answers, and Greenhouse/Lever "
                "connectors"
            ),
        },
    ],
}

# Deliberately no more `yiling_entry_for_jd` / `swap_project_for_yiling` here.
# Both were hardcoded, per-company special cases in the old projection logic
# (quality_gate.project_for_jd used to import and call them, and ooxml_inject
# used to force-hide a project whenever Yiling appeared). That logic is now
# fully general: project_for_jd scores every experience/project the same way
# regardless of company name (decision_engine.py), and ooxml_inject only acts
# on whatever project_for_jd's hidden_entries actually decided. Removed
# 2026-08-10 once both call sites were gone — see git history for the prior
# per-JD-cluster bullet-variant approach and why it was replaced.
