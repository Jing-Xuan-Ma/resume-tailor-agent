"""Category slugs for Jobright intern mini-sites (from Jobright frontend bundle)."""

from __future__ import annotations

# Labels shown on https://www.intern-list.com/
CATEGORY_LABELS: dict[str, str] = {
    "swe": "Software Engineering",
    "data_analysis": "Data Analysis",
    "ml_ai": "Machine Learning and AI",
    "product_management": "Product Management",
    "accounting_finance": "Accounting and Finance",
    "engineering_development": "Engineering and Development",
    "business_analyst": "Business Analyst",
    "marketing_gen": "Marketing",
    "cyber_security": "Cybersecurity",
    "consulting": "Consulting",
    "creatives_design": "Creatives and Design",
    "data_science": "Data Science",
    "management_executive": "Management and Executive",
    "public_sector": "Public Sector and Government",
    "legal_compliance": "Legal and Compliance",
    "human_resources": "Human Resources",
    "arts_entertainment": "Arts and Entertainment",
    "sales": "Sales",
    "customer_service": "Customer Service and Support",
    "education_training": "Education and Training",
    "healthcare": "Healthcare",
    "supply_chain": "Supply Chain",
    "project_manager": "Project Manager",
    "data_engineer": "Data Engineer",
}

# Official intern:us tab order from Jobright JS
INTERN_US_SLUGS: list[str] = [
    "swe",
    "data_analysis",
    "marketing_gen",
    "ml_ai",
    "business_analyst",
    "product_management",
    "creatives_design",
    "accounting_finance",
    "consulting",
    "engineering_development",
    "human_resources",
    "arts_entertainment",
    "management_executive",
    "customer_service",
    "legal_compliance",
    "sales",
    "public_sector",
    "education_training",
    "cyber_security",
    "project_manager",
    "data_engineer",
    "healthcare",
    "supply_chain",
]

INTERN_CA_SLUGS: list[str] = [
    "engineering_development",
    "accounting_finance",
    "swe",
    "management_executive",
    "sales",
    "marketing_gen",
    "data_analysis",
    "ml_ai",
    "human_resources",
]

# Short aliases used on intern-list.com (?k=…)
SLUG_ALIASES: dict[str, str] = {
    "da": "data_analysis",
    "se": "swe",
    "swe": "swe",
    "ml": "ml_ai",
    "ai": "ml_ai",
    "aiml": "ml_ai",
    "pm": "product_management",
    "af": "accounting_finance",
    "ba": "business_analyst",
    "mkt": "marketing_gen",
    "hr": "human_resources",
}

# Default six targets for this project
TARGET_K_SLUGS: list[str] = ["swe", "da", "aiml", "pm", "af", "ba"]
TARGET_SLUGS: list[str] = [
    "swe",
    "data_analysis",
    "ml_ai",
    "product_management",
    "accounting_finance",
    "business_analyst",
]

TARGET_LINKS: dict[str, str] = {
    "swe": "https://www.intern-list.com/?k=swe",
    "data_analysis": "https://www.intern-list.com/?k=da",
    "ml_ai": "https://www.intern-list.com/?k=aiml",
    "product_management": "https://www.intern-list.com/?k=pm",
    "accounting_finance": "https://www.intern-list.com/?k=af",
    "business_analyst": "https://www.intern-list.com/?k=ba",
}


def normalize_slug(slug: str) -> str:
    s = (slug or "").strip().lower().replace("-", "_")
    return SLUG_ALIASES.get(s, s)


def category_key(slug: str, *, country: str = "us", site: str = "intern") -> str:
    return f"{site}:{country}:{normalize_slug(slug)}"


def resolve_slugs(
    raw: list[str] | None,
    *,
    country: str = "us",
    all_categories: bool = False,
    targets: bool = False,
) -> list[str]:
    if all_categories:
        return list(INTERN_US_SLUGS if country == "us" else INTERN_CA_SLUGS)
    if targets or not raw:
        return list(TARGET_SLUGS)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        slug = normalize_slug(item)
        if slug not in CATEGORY_LABELS and slug not in INTERN_US_SLUGS:
            raise ValueError(f"Unknown category slug: {item!r} (normalized={slug!r})")
        if slug not in seen:
            seen.add(slug)
            out.append(slug)
    return out
