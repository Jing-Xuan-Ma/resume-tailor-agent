"""Job category taxonomy for Jingxuan's target roles (Jobright-style chips)."""

from __future__ import annotations

import re
from typing import Any


# slug → display label (UI chips, stable order)
CATEGORY_LABELS: dict[str, str] = {
    "data_analysis": "Data Analysis",
    "business_analyst": "Business Analyst",
    "ml_ai": "Machine Learning and AI",
    "ai_agent": "AI Agent",
    "software_engineering": "Software Engineering",
    "risk_analytics": "Risk / Insurance Analytics",
}

CATEGORY_ORDER: list[str] = list(CATEGORY_LABELS.keys())

# Ingest queries per category (write path). Primary roles get more coverage.
CATEGORY_INGEST_QUERIES: dict[str, list[str]] = {
    "data_analysis": [
        "data analyst",
        "analytics",
        "business intelligence analyst",
    ],
    "business_analyst": [
        "business analyst",
        "analytics associate",
    ],
    "ml_ai": [
        "data scientist",
        "machine learning analyst",
        "ML engineer",
    ],
    "ai_agent": [
        "AI agent",
        "LLM engineer",
        "AI automation",
    ],
    "software_engineering": [
        "software engineer",
        "backend engineer python",
        "full stack engineer",
    ],
    "risk_analytics": [
        "risk analyst",
        "insurance analyst",
        "actuarial analyst",
    ],
}

# Scoring weights for rule hits (higher = preferred primary when tied)
_CATEGORY_RULES: list[tuple[str, list[re.Pattern[str]], int]] = [
    (
        "ai_agent",
        [
            re.compile(r"\bai[\s-]?agent\b", re.I),
            re.compile(r"\bagentic\b", re.I),
            re.compile(r"\bllm\b", re.I),
            re.compile(r"\bcopilot\b", re.I),
            re.compile(r"\bprompt\s+engineer\b", re.I),
            re.compile(r"\blangchain\b", re.I),
            re.compile(r"\bmulti[\s-]?agent\b", re.I),
        ],
        100,
    ),
    (
        "risk_analytics",
        [
            re.compile(r"\brisk\s+analyst\b", re.I),
            re.compile(r"\binsurance\s+analyst\b", re.I),
            re.compile(r"\bactuar\w*\b", re.I),
            re.compile(r"\bunderwriting\b", re.I),
            re.compile(r"\binsurance\s+analytics\b", re.I),
        ],
        90,
    ),
    (
        "data_analysis",
        [
            re.compile(r"\bdata\s+analyst\b", re.I),
            re.compile(r"\banalytics\s+analyst\b", re.I),
            re.compile(r"\bbi\s+analyst\b", re.I),
            re.compile(r"\bbusiness\s+intelligence\b", re.I),
            re.compile(r"\btableau\b", re.I),
            re.compile(r"\bpower\s*bi\b", re.I),
        ],
        85,
    ),
    (
        "business_analyst",
        [
            re.compile(r"\bbusiness\s+analyst\b", re.I),
            re.compile(r"\bproduct\s+analyst\b", re.I),
            re.compile(r"\boperations\s+analyst\b", re.I),
        ],
        80,
    ),
    (
        "ml_ai",
        [
            re.compile(r"\bmachine\s+learning\b", re.I),
            re.compile(r"\bdata\s+scientist\b", re.I),
            re.compile(r"\bml\s+engineer\b", re.I),
            re.compile(r"\bdeep\s+learning\b", re.I),
            re.compile(r"\bneural\s+network\b", re.I),
        ],
        75,
    ),
    (
        "software_engineering",
        [
            re.compile(r"\bsoftware\s+engineer\b", re.I),
            re.compile(r"\bbackend\s+engineer\b", re.I),
            re.compile(r"\bfrontend\s+engineer\b", re.I),
            re.compile(r"\bfull[\s-]?stack\b", re.I),
            re.compile(r"\bsde\b", re.I),
            re.compile(r"\bsoftware\s+developer\b", re.I),
        ],
        60,
    ),
]


def label_for(slug: str) -> str:
    return CATEGORY_LABELS.get(slug, slug.replace("_", " ").title())


def slug_for_label(label: str) -> str | None:
    needle = (label or "").strip().lower()
    for slug, lab in CATEGORY_LABELS.items():
        if lab.lower() == needle or slug == needle:
            return slug
    # aliases
    aliases = {
        "data analyst": "data_analysis",
        "software engineer": "software_engineering",
        "swe": "software_engineering",
        "ml": "ml_ai",
        "ai": "ml_ai",
        "risk": "risk_analytics",
        "insurance": "risk_analytics",
        "finance": "risk_analytics",
    }
    return aliases.get(needle)


def all_ingest_queries(*, primary_extra: bool = True) -> list[str]:
    """Flatten unique ingest queries; DA/BA first."""
    ordered_slugs = [
        "data_analysis",
        "business_analyst",
        "ml_ai",
        "ai_agent",
        "risk_analytics",
        "software_engineering",
    ]
    seen: set[str] = set()
    out: list[str] = []
    for slug in ordered_slugs:
        for q in CATEGORY_INGEST_QUERIES.get(slug, []):
            key = q.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(q.strip())
    return out


def classify_job(
    *,
    title: str = "",
    raw_text: str = "",
    source_category: str | None = None,
) -> dict[str, Any]:
    """Rule-based primary category + secondary tags."""
    blob = f"{title}\n{raw_text[:3000]}"
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}

    for slug, patterns, weight in _CATEGORY_RULES:
        hits = [p.pattern for p in patterns if p.search(blob)]
        if hits:
            scores[slug] = scores.get(slug, 0) + weight + len(hits)
            matched[slug] = hits

    # Light boost from provider category strings
    src = (source_category or "").lower()
    if src:
        if any(x in src for x in ("data", "analyst", "analytics", "bi")):
            scores["data_analysis"] = scores.get("data_analysis", 0) + 15
        if "software" in src or "engineering" in src or "dev" in src:
            scores["software_engineering"] = scores.get("software_engineering", 0) + 10
        if "machine learning" in src or src.strip() in {"ai", "ml"}:
            scores["ml_ai"] = scores.get("ml_ai", 0) + 15

    if not scores:
        return {
            "category": "other",
            "categories": [],
            "category_label": "Other",
            "category_scores": {},
        }

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], CATEGORY_ORDER.index(kv[0]) if kv[0] in CATEGORY_ORDER else 99))
    primary = ranked[0][0]
    secondaries = [s for s, _ in ranked[1:] if _ >= 60][:3]
    return {
        "category": primary,
        "categories": [primary, *secondaries],
        "category_label": label_for(primary),
        "category_scores": scores,
    }


def ui_categories() -> list[dict[str, str]]:
    return [{"slug": s, "label": CATEGORY_LABELS[s]} for s in CATEGORY_ORDER]
