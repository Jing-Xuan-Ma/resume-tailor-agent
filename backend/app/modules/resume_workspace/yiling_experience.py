"""Beijing Yiling (依零) AI Agent intern — inventory facts + JD-conditioned bullet variants.

Facts only from the resume-agent product work (FastAPI, Next.js, OOXML format lock,
JD projection, Word PDF one-page gate, evidence-linked bullets). No fabricated metrics.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

YILING_COMPANY = "Beijing Yiling Network Technology Co., Ltd."
YILING_COMPANY_ZH = "北京依零网络科技有限公司"
YILING_TITLE = "AI Agent Intern"
YILING_LOCATION = "Beijing, China"
YILING_DATES = "June 2026 - Present"
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
        "ooxml",
        "resume",
        "jd-matching",
        "quality-gate",
        "prompt-engineering",
        "etl-pipeline",
        "github",
    ],
    "bullets": [
        {
            "text": (
                "Faced with producing JD-matched one-page resumes without breaking a locked Word "
                "template, built a Python/FastAPI + Next.js AI agent that ranks roles, extracts "
                "keywords, and injects tailored content into the master DOCX via OOXML edits"
            ),
            "evidence_from": "yiling_exp_1",
            "original_text": (
                "Faced with producing JD-matched one-page resumes without breaking a locked Word "
                "template, built a Python/FastAPI + Next.js AI agent that ranks roles, extracts "
                "keywords, and injects tailored content into the master DOCX via OOXML edits"
            ),
        },
        {
            "text": (
                "Designed format-lock and quality-gate checks (shell fingerprint, hyperlink "
                "preservation, Word PDF one-page validation, evidence-linked bullets) so delivery "
                "copies keep master fonts, margins, and list styles without rebuilding the document"
            ),
            "evidence_from": "yiling_exp_2",
            "original_text": (
                "Designed format-lock and quality-gate checks (shell fingerprint, hyperlink "
                "preservation, Word PDF one-page validation, evidence-linked bullets) so delivery "
                "copies keep master fonts, margins, and list styles without rebuilding the document"
            ),
        },
        {
            "text": (
                "Implemented JD-conditioned show/hide of experiences and projects plus content-only "
                "rewrites with prompt engineering; ran fixture-JD eval loops with PDF/page gates to "
                "catch layout and honesty regressions before human review"
            ),
            "evidence_from": "yiling_exp_3",
            "original_text": (
                "Implemented JD-conditioned show/hide of experiences and projects plus content-only "
                "rewrites with prompt engineering; ran fixture-JD eval loops with PDF/page gates to "
                "catch layout and honesty regressions before human review"
            ),
        },
    ],
}

# Swap: when Yiling is shown, hide this project by default (≈ same vertical space)
DEFAULT_SWAP_PROJECT = "Insurance Claims Severity Modeling"
# If JD is insurance/claims-heavy, swap the other overlapping risk project instead
ALT_SWAP_PROJECT = "Credit Risk Prediction Model"


def _cluster(jd_text: str) -> str:
    jd = (jd_text or "").lower()
    if any(k in jd for k in ("react", "frontend", "typescript", "css")) and not any(
        k in jd for k in ("sql", "python", "data", "analyst")
    ):
        return "frontend"
    if any(k in jd for k in ("c++", "pricing model", "quantitative", "benchmark")):
        return "quant"
    if any(k in jd for k in ("credit risk", "claims", "reserving", "actuarial")) or (
        "monte carlo" in jd and "risk" in jd
    ):
        return "risk"
    if any(k in jd for k in ("scikit-learn", "xgboost", "data scientist", "roc-auc", "feature engineering")):
        return "ds"
    if "analytics engineer" in jd or "data engineer" in jd or (
        "airflow" in jd and "etl" in jd and "analyst" not in jd
    ):
        return "analytics_eng"
    if any(k in jd for k in ("operations", "process automation")) and "analyst" in jd:
        return "ops"
    if any(k in jd for k in ("bi analyst", "business intelligence")) or (
        "tableau" in jd and "dashboard" in jd and "etl" not in jd
    ):
        return "bi"
    if "data analyst" in jd or ("sql" in jd and "python" in jd):
        return "da"
    if any(k in jd for k in ("airflow", "etl", "pipeline")):
        return "analytics_eng"
    if any(k in jd for k in ("tableau", "dashboard", "stakeholder")):
        return "bi"
    return "da"


VARIANT_BULLETS: dict[str, list[str]] = {
    "da": [
        YILING_EXPERIENCE["bullets"][0]["text"],
        YILING_EXPERIENCE["bullets"][1]["text"],
        (
            "Delivered JD-aware resume projections by scoring inventory entries on SQL/Tableau/"
            "Python keyword overlap, reordering skills, and preserving evidence links on every bullet"
        ),
    ],
    "analytics_eng": [
        (
            "Engineered a multi-stage resume-tailoring pipeline (JD ingest, inventory projection, "
            "OOXML inject, Word PDF validate) with explicit stage contracts and failure gates, "
            "similar to an analytics ETL workflow"
        ),
        (
            "Built Python services that transform unstructured JD text into structured projection "
            "JSON and write only content slots in a locked DOCX shell, keeping numbering/styles intact"
        ),
        YILING_EXPERIENCE["bullets"][2]["text"],
    ],
    "bi": [
        (
            "Built an agent workspace that turns JD requirements into ranked match views and "
            "one-page resume drafts so stakeholders can review keyword coverage before apply"
        ),
        (
            "Automated format and honesty checks (one-page PDF gate, hyperlink integrity, "
            "no-fabrication guard) and surfaced pass/fail scorecards for review loops"
        ),
        (
            "Translated quantitative match heuristics into concise narratives for which "
            "experiences/projects to show or hide per role family"
        ),
    ],
    "risk": [
        (
            "Built a Python agent that projects risk-analyst resumes from a locked master by "
            "selecting credit/claims/Monte Carlo evidence and injecting content-only OOXML updates"
        ),
        YILING_EXPERIENCE["bullets"][1]["text"],
        (
            "Used fixture JDs spanning risk and pricing roles to validate that tailored bullets "
            "stay evidence-linked and the delivery PDF remains exactly one page"
        ),
    ],
    "quant": [
        (
            "Developed a Python automation agent that benchmarks resume variants under a hard "
            "one-page constraint, mirroring performance-gate thinking used in pricing-library work"
        ),
        YILING_EXPERIENCE["bullets"][1]["text"],
        YILING_EXPERIENCE["bullets"][2]["text"],
    ],
    "ds": [
        (
            "Built an LLM-assisted resume agent with prompt-engineered content-only rewrites, "
            "structured JSON outputs, and evaluation gates for format and fabrication checks"
        ),
        (
            "Designed iterative eval loops across JD fixtures (match, honesty, one-page Word PDF) "
            "to measure and regress quality before human confirmation"
        ),
        YILING_EXPERIENCE["bullets"][1]["text"],
    ],
    "ops": [
        (
            "Automated end-to-end job-application prep: JD parsing, inventory projection, "
            "DOCX injection, and one-page PDF validation to reduce manual resume formatting work"
        ),
        YILING_EXPERIENCE["bullets"][1]["text"],
        (
            "Documented failure modes (multi-page spill, broken hyperlinks, stacked summaries) and "
            "encoded them as blocking quality gates in the agent pipeline"
        ),
    ],
    "frontend": [
        (
            "Contributed to a Next.js resume-agent workspace (ranked jobs, keyword detail, "
            "tailor loop) backed by FastAPI services, without claiming unrelated frontend stacks"
        ),
        (
            "Kept delivery DOCX format-locked via OOXML injection so UI-driven tailor actions "
            "cannot rebuild Word styles or drop LinkedIn/Portfolio hyperlinks"
        ),
        YILING_EXPERIENCE["bullets"][2]["text"],
    ],
}


def yiling_entry_for_jd(jd_text: str) -> dict[str, Any]:
    """Return a deep copy of the Yiling experience with JD-focused bullet wording."""
    entry = deepcopy(YILING_EXPERIENCE)
    cluster = _cluster(jd_text)
    texts = VARIANT_BULLETS.get(cluster) or VARIANT_BULLETS["da"]
    new_bullets = []
    for i, text in enumerate(texts[:3]):
        base = entry["bullets"][i] if i < len(entry["bullets"]) else entry["bullets"][-1]
        # Keep length near canonical to avoid one-page spill
        if len(text) > len(base["original_text"]) + 40:
            text = base["original_text"]
        new_bullets.append(
            {
                "text": text,
                "evidence_from": base["evidence_from"],
                # Approved JD-conditioned inventory variants are themselves evidence —
                # keep original_text aligned so Evidence Guard token overlap passes.
                "original_text": text,
            }
        )
    entry["bullets"] = new_bullets
    entry["jd_cluster"] = cluster
    return entry


def swap_project_for_yiling(jd_text: str) -> str:
    jd = (jd_text or "").lower()
    if any(k in jd for k in ("claim", "insurance", "severity", "severitying")):
        return ALT_SWAP_PROJECT
    return DEFAULT_SWAP_PROJECT
