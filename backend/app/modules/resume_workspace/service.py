from pathlib import Path
from copy import deepcopy
import json
import re

from app import db
from app.config import settings
from app.core.llm_client import get_chat_openai
from app.modules.resume_tailor.nodes.evidence_guard import EvidenceGuardNode
from app.modules.resume_workspace.schemas import KeywordMatchItem
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor
from app.modules.resume_workspace.diff import compute_resume_diff
from app.modules.resume_workspace.final_store import extract_company_position, save_final_resume
from app.modules.resume_workspace.master_template import ensure_user_has_master_template, ensure_master_template_bytes
from app.modules.resume_workspace.master_inject import inject_content
from app.modules.resume_workspace.quality_gate import project_for_jd, run_quality_gate
from app.modules.resume_workspace.format_lock import fingerprint_docx, compare_fingerprints
from app.modules.resume_workspace.constitution import (
    MASTER_TEMPLATE_LABEL,
    constitution_system_block,
)


_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_RESUME_TEMPLATES_DIR = Path(__file__).resolve().parents[4] / "data" / "templates"
_RESUME_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _extract_json(text: str) -> dict:
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("\n", 1)[0]
    return json.loads(text)

# Keep current + 3 previous versions (RESUME_CONSTITUTION §8)
MAX_VERSIONS = 4

_REWRITE_HINTS = re.compile(
    r"\b(emphasize|highlight|shorten|rewrite|tailor|update|change|revise|focus|"
    r"make\s+the|add\s+|remove|bullet|summary|skills?|tableau|sql|one[\s-]?page|"
    r"da-focused|more\s+|less\s+|cut\s+|trim|project|experience|keyword)\b|"
    r"(改|强调|缩短|突出|聚焦|改写|删|加|摘要|技能)",
    re.I,
)
_CHAT_HINTS = re.compile(
    r"^(hi|hello|hey|thanks|thank you|ok|okay|how are you|what can you|"
    r"who are you|help|你好|谢谢|在吗|怎么样)[\s!.?1]*$",
    re.I,
)

MOCK_RESUME = {
    "candidate_name": "Jingxuan Ma",
    "contact_line": "+1 (410) 240-4366 | jma107@jh.edu | LinkedIn | Portfolio",
    "summary": (
        "Data Science M.S. student at Johns Hopkins with a background in Applied Statistics "
        "and data analytics. Skilled in R, advanced SQL, Python ETL pipelines using Apache Airflow, "
        "Tableau dashboard development, operations automation, stakeholder collaboration, and AI "
        "prompt engineering to accelerate data analysis."
    ),
    "education": [
        {
            "institution": "Johns Hopkins University",
            "degree": "Master of Science in Data Science",
            "field": "Data Science",
            "location": "Baltimore, US",
            "date_range": "August 2025 - June 2027",
            "coursework": ["Database Systems", "Introduction to Algorithms", "Nonlinear Optimization", "Human-Computer Interaction"],
        },
        {
            "institution": "University College Cork",
            "degree": "Bachelor of Science in Actuarial Sciences",
            "field": "Actuarial Sciences",
            "location": "Cork, Ireland | Beijing, China",
            "date_range": "September 2021 - June 2025",
            "coursework": ["Probability & Statistics", "Actuarial Mathematics", "Financial Mathematics", "Regression Analysis", "Statistical Computing"],
        },
    ],
    "experiences": [
        {
            "company": "Beijing Yiling Network Technology Co., Ltd.",
            "title": "AI Agent Intern",
            "location": "Beijing, China",
            "date_range": "June 2026 - Present",
            "github_url": "https://github.com/Jing-Xuan-Ma/resume-tailor-agent",
            "evidence_url": "https://github.com/Jing-Xuan-Ma/resume-tailor-agent",
            "tags": [
                "ai-agent", "python", "fastapi", "nextjs", "ooxml", "resume",
                "jd-matching", "quality-gate", "prompt-engineering", "github",
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
        },
        {
            "company": "Shenwan Hongyuan Securities Co., Ltd.",
            "title": "Data Analyst Intern",
            "location": "Beijing, China",
            "date_range": "June 2024 - August 2024",
            "bullets": [
                {
                    "text": "Faced with the need to evaluate whether a pricing model library could meet both runtime and maintainability requirements, conducted a structured feasibility analysis across Python, pure & optimized C++, Eigen vectorization, OpenMP, and ctypes-based Python/C++ integration",
                    "evidence_from": "shenwan_exp_1",
                    "original_text": "Faced with the need to evaluate whether a pricing model library could meet both runtime and maintainability requirements, conducted a structured feasibility analysis across Python, pure & optimized C++, Eigen vectorization, OpenMP, and ctypes-based Python/C++ integration",
                },
                {
                    "text": "Built and benchmarked a 100,000-path Monte Carlo pricing simulation, applying compiler optimization, vectorized matrix operations, and multithreaded random-path generation to isolate major bottlenecks in computation-intensive pricing workflows",
                    "evidence_from": "shenwan_exp_2",
                    "original_text": "Built and benchmarked a 100,000-path Monte Carlo pricing simulation, applying compiler optimization, vectorized matrix operations, and multithreaded random-path generation to isolate major bottlenecks in computation-intensive pricing workflows",
                },
                {
                    "text": "Delivered a hybrid architecture recommendation that assigned heavy simulation and statistical computation to C++ while keeping configuration, preprocessing, and visualization in Python; reduced runtime from approx. 33.4s to approx. 1.4s with OpenMP optimization",
                    "evidence_from": "shenwan_exp_3",
                    "original_text": "Delivered a hybrid architecture recommendation that assigned heavy simulation and statistical computation to C++ while keeping configuration, preprocessing, and visualization in Python; reduced runtime from approx. 33.4s to approx. 1.4s with OpenMP optimization",
                },
            ],
        },
        {
            "company": "Yinhua Fund Management Co., Ltd.",
            "title": "Data Analyst Intern",
            "location": "Beijing, China",
            "date_range": "June 2023 - August 2023",
            "bullets": [
                {
                    "text": "Given the need to support campaign review and market reporting, collected, organized, and cleaned market and customer data from multiple business materials, creating structured datasets for trend analysis and management communication",
                    "evidence_from": "yinhua_exp_1",
                    "original_text": "Given the need to support campaign review and market reporting, collected, organized, and cleaned market and customer data from multiple business materials, creating structured datasets for trend analysis and management communication",
                },
                {
                    "text": "Used Python, Excel, and visualization techniques to analyze market patterns, prepare charts and analytical materials, and convert raw performance data into insights that could support investment-product marketing decisions",
                    "evidence_from": "yinhua_exp_2",
                    "original_text": "Used Python, Excel, and visualization techniques to analyze market patterns, prepare charts and analytical materials, and convert raw performance data into insights that could support investment-product marketing decisions",
                },
                {
                    "text": "Prepared concise reporting assets for internal stakeholders by translating quantitative findings into business narratives, improving clarity around customer behavior, campaign performance, and market trends",
                    "evidence_from": "yinhua_exp_3",
                    "original_text": "Prepared concise reporting assets for internal stakeholders by translating quantitative findings into business narratives, improving clarity around customer behavior, campaign performance, and market trends",
                },
            ],
        },
    ],
    "projects": [
        {
            "name": "Credit Risk Prediction Model",
            "tools": ["Python", "SQL", "scikit-learn", "XGBoost", "R"],
            "context": "Independent Project",
            "date_range": "",
            "bullets": [
                {
                    "text": "To build and adapt algorithms for complex risk use cases, designed an end-to-end predictive pipeline integrating SQL-style extraction, missing-value treatment, feature engineering, and statistical modeling to estimate expected claim costs and credit default behavior",
                    "evidence_from": "credit_proj_1",
                    "original_text": "To build and adapt algorithms for complex risk use cases, designed an end-to-end predictive pipeline integrating SQL-style extraction, missing-value treatment, feature engineering, and statistical modeling to estimate expected claim costs and credit default behavior",
                },
                {
                    "text": "Applied advanced statistics and machine learning libraries (scikit-learn, XGBoost) to train, evaluate, and benchmark regression and tree-based models, leveraging ROC-AUC, F1-score, and cost drivers to balance predictive accuracy with business interpretability.",
                    "evidence_from": "credit_proj_2",
                    "original_text": "Applied advanced statistics and machine learning libraries (scikit-learn, XGBoost) to train, evaluate, and benchmark regression and tree-based models, leveraging ROC-AUC, F1-score, and cost drivers to balance predictive accuracy with business interpretability.",
                },
                {
                    "text": "Extended the framework with stochastic modeling via Monte Carlo simulations to analyze skewed loss distributions, interpreting error patterns to translate quantitative outputs into risk-monitoring thresholds and optimized decision-making insights.",
                    "evidence_from": "credit_proj_3",
                    "original_text": "Extended the framework with stochastic modeling via Monte Carlo simulations to analyze skewed loss distributions, interpreting error patterns to translate quantitative outputs into risk-monitoring thresholds and optimized decision-making insights.",
                },
            ],
        },
        {
            "name": "Insurance Claims Severity Modeling",
            "tools": ["Python", "R", "pandas", "scikit-learn", "Monte Carlo Simulation"],
            "context": "Independent Project",
            "date_range": "",
            "bullets": [
                {
                    "text": "To estimate claim severity across heterogeneous policy segments, collected and cleaned historical claims data and engineered exposure- and policy-level features to support distributional analysis of loss costs",
                    "evidence_from": "claims_proj_1",
                    "original_text": "To estimate claim severity across heterogeneous policy segments, collected and cleaned historical claims data and engineered exposure- and policy-level features to support distributional analysis of loss costs",
                },
                {
                    "text": "Analyzed skewed loss distributions, outliers, and cost drivers; compared regression and tree-based approaches to evaluate trade-offs among predictive accuracy, robustness, and business interpretability for underwriting and reserving use cases",
                    "evidence_from": "claims_proj_2",
                    "original_text": "Analyzed skewed loss distributions, outliers, and cost drivers; compared regression and tree-based approaches to evaluate trade-offs among predictive accuracy, robustness, and business interpretability for underwriting and reserving use cases",
                },
                {
                    "text": "Extended the modeling framework with Monte Carlo simulation and performance-benchmarking concepts to evaluate scalable pricing workflows, translating model outputs into risk segmentation, pricing review, and portfolio-level reporting insights",
                    "evidence_from": "claims_proj_3",
                    "original_text": "Extended the modeling framework with Monte Carlo simulation and performance-benchmarking concepts to evaluate scalable pricing workflows, translating model outputs into risk segmentation, pricing review, and portfolio-level reporting insights",
                },
            ],
        },
        {
            "name": "Tesla Vehicle Quality & Risk Analytics Pipeline",
            "tools": ["Python", "Apache Airflow", "SQL", "Tableau", "NHTSA API"],
            "context": "Independent Project",
            "date_range": "",
            "bullets": [
                {
                    "text": "Built an end-to-end ETL pipeline extracting 11,349 NHTSA complaints and 60 recall actions across Tesla Models 3/S/X/Y (2015–2024); engineered dynamic model-name discovery and ID-based deduplication to reduce 30,777 raw records to 11,349 verified distinct complaints",
                    "evidence_from": "tesla_proj_1",
                    "original_text": "Built an end-to-end ETL pipeline extracting 11,349 NHTSA complaints and 60 recall actions across Tesla Models 3/S/X/Y (2015–2024); engineered dynamic model-name discovery and ID-based deduplication to reduce 30,777 raw records to 11,349 verified distinct complaints",
                },
                {
                    "text": "Engineered frequency- and severity-based risk indicators (crash/fire/injury-weighted scores by model-year and component) in SQL, applying an actuarial-style frequency × severity loss framework to quantify and rank vehicle quality risk across product lines",
                    "evidence_from": "tesla_proj_2",
                    "original_text": "Engineered frequency- and severity-based risk indicators (crash/fire/injury-weighted scores by model-year and component) in SQL, applying an actuarial-style frequency × severity loss framework to quantify and rank vehicle quality risk across product lines",
                },
                {
                    "text": "Built and published an interactive Tableau dashboard visualizing component-level risk rankings and recall-lag trends (first complaint to official recall), translating 11,349 complaint records into decision-ready risk insights for quality and safety stakeholders.",
                    "evidence_from": "tesla_proj_3",
                    "original_text": "Built and published an interactive Tableau dashboard visualizing component-level risk rankings and recall-lag trends (first complaint to official recall), translating 11,349 complaint records into decision-ready risk insights for quality and safety stakeholders.",
                },
            ],
        },
    ],
    "skills_certifications": (
        "Python, R, SQL, Tableau, Apache Airflow, data cleaning, feature engineering, "
        "exploratory analysis, Pandas, NumPy, scikit-learn, XGBoost, Monte Carlo Simulation, "
        "Credit Risk, Claims Modeling, stakeholder reporting"
    ),
}

MOCK_JD_TEXT = """
Software Engineer - Backend Infrastructure

About the role:
We are looking for a talented backend infrastructure engineer to join our growing team. You will design and build scalable systems that power our core platform.

Requirements:
• 5+ years of experience in backend development
• Strong proficiency in Python or Go
• Experience with distributed systems and microservice architecture
• Hands-on experience with Kafka or similar message queue systems
• Deep understanding of SQL and NoSQL databases (PostgreSQL, Redis)
• Experience with Kubernetes and Docker containerization
• Strong problem-solving and communication skills

Preferred:
• Experience with real-time data processing
• Knowledge of CI/CD pipelines and infrastructure as code
• Experience leading technical projects
• Familiarity with machine learning pipelines

Responsibilities:
• Design and implement scalable backend services
• Optimize system performance and reliability
• Collaborate with cross-functional teams to deliver product features
• Mentor junior engineers and conduct code reviews
"""

MOCK_KEYWORD_MATCHES = [
    KeywordMatchItem(keyword="Python", status="covered", source_span_in_jd=[180, 186], suggestion=None),
    KeywordMatchItem(keyword="Go", status="covered", source_span_in_jd=[191, 193], suggestion=None),
    KeywordMatchItem(keyword="Kafka", status="covered", source_span_in_jd=[459, 464], suggestion=None),
    KeywordMatchItem(keyword="PostgreSQL", status="covered", source_span_in_jd=[552, 562], suggestion=None),
    KeywordMatchItem(keyword="Redis", status="covered", source_span_in_jd=[564, 569], suggestion=None),
    KeywordMatchItem(keyword="Kubernetes", status="covered", source_span_in_jd=[614, 624], suggestion=None),
    KeywordMatchItem(keyword="Docker", status="covered", source_span_in_jd=[619, 625], suggestion=None),
    KeywordMatchItem(keyword="distributed systems", status="covered", source_span_in_jd=[274, 294], suggestion=None),
    KeywordMatchItem(keyword="real-time data processing", status="missing", source_span_in_jd=[701, 726], suggestion="Consider building a real-time dashboard project using Kafka Streams or Flink to process live data."),
    KeywordMatchItem(keyword="CI/CD pipelines", status="covered", source_span_in_jd=[751, 766], suggestion=None),
    KeywordMatchItem(keyword="infrastructure as code", status="missing", source_span_in_jd=[791, 814], suggestion="Learn Terraform or Pulumi and create a sample infrastructure repo."),
    KeywordMatchItem(keyword="machine learning pipelines", status="missing", source_span_in_jd=[872, 898], suggestion="Take an existing ML project and wrap it with MLflow for experiment tracking."),
    KeywordMatchItem(keyword="microservice architecture", status="covered", source_span_in_jd=[298, 321], suggestion=None),
    KeywordMatchItem(keyword="team leadership", status="covered", source_span_in_jd=[723, 739], suggestion=None),
]


class ResumeWorkspaceService:

    def __init__(self):
        self.template_editor = ResumeTemplateEditor()
        self.evidence_guard = EvidenceGuardNode()

    def create_session(self, user_id: str, jd_text: str, job_id: str | None = None) -> dict:
        return db.create_jd_session(user_id=user_id, job_id=job_id, jd_text=jd_text)

    def upload_template(self, user_id: str, filename: str, docx_bytes: bytes) -> dict:
        blocks = self.template_editor.load_template(docx_bytes)
        template_id = db.save_template(
            user_id=user_id,
            filename=filename,
            docx_bytes=docx_bytes,
            parsed_blocks=blocks["blocks"],
        )
        return {
            "template_id": template_id,
            "block_count": blocks["block_count"],
            "filename": filename,
        }

    def get_active_template(self, user_id: str) -> dict | None:
        return db.get_active_template(user_id)

    async def analyze(self, session_id: str) -> list[dict]:
        session = db.get_jd_session(session_id)
        if not session:
            session_data = db.create_jd_session(user_id="mock", jd_text=MOCK_JD_TEXT)
            session_id = session_data["id"]
            session = session_data

        jd_text = str((session or {}).get("jd_text") or "")
        user_id = str((session or {}).get("user_id") or "")
        matches: list[dict] = []

        # Prefer LLM keyword analysis when prompts + API are available.
        prompt_path = _PROMPTS_DIR / "keyword_analysis.txt"
        if prompt_path.exists() and jd_text.strip():
            resume_text = ""
            if user_id and user_id != "mock":
                latest = db.get_latest_resume(user_id)
                if latest:
                    resume_text = json.dumps(latest.get("parsed", latest), ensure_ascii=False)
            try:
                llm = get_chat_openai(
                    model=settings.DEFAULT_PARSER_MODEL,
                    temperature=0.1,
                    max_tokens=2048,
                )
                human_prompt = f"JD:\n{jd_text}"
                if resume_text:
                    human_prompt += f"\n\nResume:\n{resume_text}"
                response = await llm.ainvoke([
                    ("system", _load_prompt("keyword_analysis.txt")),
                    ("human", human_prompt),
                ])
                result = _extract_json(response.content)
                matches = result.get("keyword_matches", []) or []
            except Exception:
                matches = []

        if not matches:
            matches = self._keyword_matches_for_jd(jd_text)
        db.update_jd_session_keywords(session_id, matches)
        return matches

    def _keyword_matches_for_jd(self, jd_text: str) -> list[dict]:
        """Derive skill tags from JD text against DA skill lexicon (not static mock list)."""
        from app.modules.job_discovery.scorer import SKILL_LEXICON, tokenize
        from app.modules.resume_workspace.schemas import KeywordMatchItem

        jd = jd_text or ""
        jd_l = jd.lower()
        tokens = tokenize(jd)
        # Multi-word phrases from lexicon that appear in JD
        phrases = sorted(SKILL_LEXICON, key=len, reverse=True)
        found: list[str] = []
        for phrase in phrases:
            if " " in phrase or "-" in phrase:
                if phrase.lower() in jd_l:
                    found.append(phrase)
            elif phrase.lower() in tokens or phrase.lower() in jd_l:
                found.append(phrase)
        # Always surface common DA stack if present in JD wording variants
        aliases = {
            "power bi": "Power BI",
            "powerbi": "Power BI",
            "a/b": "A/B testing",
            "machine learning": "machine learning",
        }
        for alias, label in aliases.items():
            if alias in jd_l and label not in found:
                found.append(label)

        # Dedupe case-insensitively, cap tags
        seen: set[str] = set()
        keywords: list[str] = []
        for kw in found:
            key = kw.lower()
            if key in seen:
                continue
            seen.add(key)
            keywords.append(kw if len(kw) > 2 else kw.upper())
            if len(keywords) >= 16:
                break

        if not keywords:
            # Fallback DA defaults only when JD is empty/unparseable
            keywords = ["SQL", "Python", "Tableau", "Excel", "statistics"]

        # Heuristic coverage vs inventory keywords commonly on Jingxuan's resume
        inventory = {
            "sql", "python", "tableau", "excel", "statistics", "pandas", "numpy",
            "power bi", "powerbi", "r", "etl", "dashboard", "dashboards", "a/b",
            "experimentation", "postgresql", "mysql", "aws", "dbt",
        }
        matches: list[dict] = []
        for kw in keywords:
            covered = kw.lower() in inventory or any(
                tok in inventory for tok in kw.lower().replace("/", " ").split()
            )
            start = jd_l.find(kw.lower())
            span = [start, start + len(kw)] if start >= 0 else [0, 0]
            matches.append(
                KeywordMatchItem(
                    keyword=kw.title() if kw.islower() else kw,
                    status="covered" if covered else "missing",
                    source_span_in_jd=span,
                    suggestion=(
                        None
                        if covered
                        else f"Only claim {kw} if it exists in Master Inventory — do not fabricate."
                    ),
                ).model_dump()
            )
        return matches

    def _trim_versions(self, session_id: str, user_id: str) -> None:
        versions = db.list_resume_versions(session_id, user_id)
        while len(versions) >= MAX_VERSIONS:
            db.delete_oldest_version(session_id, user_id)
            versions = db.list_resume_versions(session_id, user_id)

    def _content_only_tailor(self, resume: dict, instruction: str, jd_text: str) -> dict:
        """Rewrite wording only; preserve structure, evidence, numbers, and one-page budget."""
        tailored = deepcopy(resume)
        instr = (instruction or "").lower()
        jd_l = (jd_text or "").lower()

        # NEVER lengthen summary — one-page lock. Keep master summary unless shortening.
        base_summary = str(resume.get("summary") or "")
        tailored["summary"] = base_summary

        # Reorder skills only; keep token count, do not append new tokens
        skills_raw = str(resume.get("skills_certifications") or "")
        parts = [p.strip() for p in skills_raw.replace(";", ",").split(",") if p.strip()]
        hit, rest = [], []
        for p in parts:
            if p.lower() in jd_l or p.lower() in instr:
                hit.append(p)
            else:
                rest.append(p)
        if hit:
            reordered = ", ".join(hit + rest)
            # Prefer not longer than original skills line
            if len(reordered) <= len(skills_raw) + 5:
                tailored["skills_certifications"] = reordered

        # Do not rewrite bullets by default (length risk). Keep evidence fields intact.
        tailored["format_check"] = {
            "single_page": True,
            "section_order_ok": True,
            "fabrication": False,
        }
        tailored["evidence_check"] = {
            "ok": True,
            "notes": "Inventory preserved; summary not lengthened for one-page lock.",
        }
        return tailored

    async def rewrite(
        self, user_id: str, session_id: str, instruction: str,
        base_version_id: str | None = None
    ) -> dict:
        ensure_user_has_master_template(user_id)

        session = db.get_jd_session(session_id) or {}
        jd_text = str(session.get("jd_text") or "")
        # Master Inventory is the truth source (Profile library); fallback to built-in seed.
        from app.modules.profile.library_service import get_master_inventory

        source_master = get_master_inventory(user_id) or MOCK_RESUME
        if base_version_id:
            base = db.get_resume_version(base_version_id, user_id)
            # Still project from inventory for show/hide; version is only a content hint
            _ = base
        projected = project_for_jd(source_master, jd_text)
        tailored = self._content_only_tailor(projected, instruction, jd_text)
        tailored["experiences"] = projected.get("experiences") or []
        tailored["projects"] = projected.get("projects") or []
        tailored["competitions"] = projected.get("competitions") or []
        tailored["hidden_entries"] = projected.get("hidden_entries") or []
        tailored["skills_certifications"] = (
            projected.get("skills_certifications") or tailored.get("skills_certifications")
        )
        gate = run_quality_gate(tailored, jd_text)
        evidence = await self.evidence_guard.verify(source_master, tailored)
        issues = list(evidence.get("issues") or [])
        hard_issues = [i for i in issues if "weak textual support" not in i]
        evidence_hard_ok = len(hard_issues) == 0
        tailored["format_check"] = {
            "single_page": "content likely exceeds one page" not in gate["errors"],
            "section_order_ok": True,
            "fabrication": any("fabricated" in e for e in gate["errors"]),
            "quality_gate": gate,
        }
        tailored["evidence_check"] = {
            "ok": evidence_hard_ok,
            "passed": evidence_hard_ok,
            "issues": issues,
            "hard_issues": hard_issues,
            "confidence": evidence.get("confidence"),
            "notes": (
                "; ".join(issues[:3])
                if issues
                else "ok"
            ),
        }
        if not gate["ok"] or not evidence_hard_ok:
            tailored["requires_fix"] = True
        if issues and evidence_hard_ok:
            tailored["evidence_warnings"] = issues
        content_delta = compute_resume_diff(source_master, tailored)
        content_delta["instruction"] = instruction
        content_delta["quality_gate"] = gate
        content_delta["evidence_check"] = tailored["evidence_check"]

        self._trim_versions(session_id, user_id)
        version_index = db.get_latest_version_index(session_id, user_id) + 1

        markdown = ResumeTemplateEditor._render_markdown(tailored)

        template_record = db.get_active_template(user_id)
        template_docx: bytes | None = None
        template_replacements: dict[str, str] = {}

        # Prefer master DOCX content-only injection (format lock)
        master_bytes = ensure_master_template_bytes()
        if master_bytes:
            try:
                template_docx = inject_content(master_bytes, tailored, source_master)
                fp_m = fingerprint_docx(master_bytes)
                fp_g = fingerprint_docx(template_docx)
                fmt_cmp = compare_fingerprints(fp_m, fp_g)
                content_delta["format_lock"] = fmt_cmp
            except Exception as exc:
                content_delta["format_lock_error"] = str(exc)
                template_docx = None

        if template_docx is None and template_record and template_record.get("docx_bytes"):
            template_docx = template_record["docx_bytes"]
            try:
                self.template_editor.load_template(template_docx)
                template_replacements = self.template_editor.build_replacement_map(
                    resume, tailored, template_docx
                )
            except Exception:
                template_replacements = {}

            if template_replacements:
                try:
                    template_docx = self.template_editor.apply_text_replacements(
                        template_docx, template_replacements
                    )
                except Exception:
                    pass
            content_delta["template_replacements"] = template_replacements

        # Skip sync Word PDF so rewrite returns for HTML first-paint.
        # Preview endpoint builds master PDF on first request via _ensure_word_pdf.
        content_delta["pdf_async"] = True

        version_id = db.create_resume_version(
            session_id=session_id,
            user_id=user_id,
            version_index=version_index,
            content_delta=content_delta,
            full_resume=tailored,
            markdown=markdown,
        )

        if template_docx:
            self._store_version_file(version_id, "docx", template_docx)

        matches = self._keyword_matches_for_jd(jd_text)

        return {
            "new_version_id": version_id,
            "session_id": session_id,
            "version_index": version_index,
            "full_resume": tailored,
            "markdown": markdown,
            "keyword_matches": matches,
            "content_delta": content_delta,
            "has_template": bool(template_docx),
            "has_pdf": False,
            "pdf_pending": True,
        }

    def _classify_intent(self, message: str) -> str:
        text = (message or "").strip()
        if not text:
            return "chat"
        if _CHAT_HINTS.search(text) and not _REWRITE_HINTS.search(text):
            return "chat"
        if _REWRITE_HINTS.search(text):
            return "rewrite"
        # Ambiguous medium-length instruction → prefer rewrite for tailor workspace
        if len(text) >= 24 and any(w in text.lower() for w in ("resume", "jd", "bullet", "page", "简历")):
            return "rewrite"
        return "chat"

    async def _llm_chat_reply(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        context: dict | None = None,
    ) -> str:
        history = []
        for item in (chat_history or [])[-8:]:
            role = str(item.get("role") or "")
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                history.append({"role": role, "content": content})
        messages = [
            {
                "role": "system",
                "content": (
                    constitution_system_block()
                    + "\nYou are Resume Agent for Jingxuan Ma (Data Analyst / Analytics). "
                    "You can chat normally and also rewrite the resume on the locked master DOCX template "
                    f"({MASTER_TEMPLATE_LABEL}, content-only injection). "
                    "Be concise and helpful. Do not claim you changed the resume unless a rewrite just ran. "
                    "Never invent employers, metrics, or skills."
                ),
            },
            *history,
            {"role": "user", "content": message},
        ]
        if context:
            messages.insert(
                1,
                {"role": "system", "content": f"Workspace context: {json.dumps(context, ensure_ascii=False)[:1200]}"},
            )
        llm = get_chat_openai(
            model=settings.DEFAULT_PARSER_MODEL or settings.DEFAULT_TAILOR_MODEL,
            temperature=0.4,
            max_tokens=700,
        )
        response = await llm.ainvoke(messages)
        content = str(response.content or "").strip()
        return content or "I can chat about this JD or update the resume preview when you give an edit instruction."

    async def _llm_rewrite_ack(self, instruction: str, version_index: int, content_delta: dict) -> str:
        changed = []
        if isinstance(content_delta, dict):
            for key in ("summary", "skills_certifications", "experiences", "projects", "hidden_entries"):
                if content_delta.get(key):
                    changed.append(key)
        hint = ", ".join(changed) if changed else "JD-based projection on the locked master template"
        try:
            llm = get_chat_openai(
                model=settings.DEFAULT_PARSER_MODEL or settings.DEFAULT_TAILOR_MODEL,
                temperature=0.2,
                max_tokens=120,
            )
            response = await llm.ainvoke(
                [
                    {
                        "role": "system",
                        "content": (
                            constitution_system_block()
                            + "Confirm a resume rewrite in at most 2 short sentences. "
                            "Mention checking the PDF preview on the right. "
                            "Do NOT invent bullet text, employers, metrics, or before/after examples."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"User instruction: {instruction}\n"
                            f"Created version: v{version_index}\n"
                            f"Touched areas (labels only): {hint}"
                        ),
                    },
                ]
            )
            content = str(response.content or "").strip()
            if content and "old version" not in content.lower() and "**" not in content:
                return content
        except Exception:
            pass
        return (
            f"Updated to v{version_index} on your locked master template ({hint}). "
            "Check the PDF preview on the right — tell me if you want another tweak."
        )

    async def agent_turn(
        self,
        user_id: str,
        session_id: str,
        message: str,
        base_version_id: str | None = None,
        chat_history: list[dict] | None = None,
    ) -> dict:
        provider = (settings.LLM_PROVIDER or "openai").strip().lower()
        model = settings.DEFAULT_PARSER_MODEL or settings.DEFAULT_TAILOR_MODEL
        intent = self._classify_intent(message)
        session = db.get_jd_session(session_id) or {}
        jd_text = str(session.get("jd_text") or "")
        try:
            from app.modules.profile.library_service import evidence_context_for_jd

            evidence = evidence_context_for_jd(user_id, jd_text)
        except Exception:
            evidence = {"resume_tailor_github": "https://github.com/Jing-Xuan-Ma/resume-tailor-agent"}
        context = {
            "has_jd": bool(jd_text),
            "job_id": session.get("job_id"),
            "master_template": "Jingxuan_Resume_Data Analyst.docx",
            "intent_guess": intent,
            "evidence": evidence,
            "guidance": (
                "When the JD involves agents, FastAPI, Next.js, OOXML, JD matching, or resume tooling, "
                "prefer Yiling AI Agent Intern facts and cite evidence from resume_tailor_github. "
                "Do not invent repo features beyond inventory bullets."
            ),
        }

        if intent == "rewrite":
            result = await self.rewrite(
                user_id=user_id,
                session_id=session_id,
                instruction=message,
                base_version_id=base_version_id,
            )
            try:
                agent_message = await self._llm_rewrite_ack(
                    message, result["version_index"], result.get("content_delta") or {}
                )
            except Exception:
                agent_message = (
                    f"Updated to v{result['version_index']}. "
                    "Check the resume preview on the right."
                )
            return {
                "session_id": session_id,
                "agent_message": agent_message,
                "intent": "rewrite",
                "did_rewrite": True,
                "new_version_id": result["new_version_id"],
                "version_index": result["version_index"],
                "full_resume": result["full_resume"],
                "keyword_matches": result.get("keyword_matches") or [],
                "content_delta": result.get("content_delta") or {},
                "llm_provider": provider,
                "llm_model": model,
            }

        try:
            agent_message = await self._llm_chat_reply(message, chat_history, context)
        except Exception as exc:
            agent_message = (
                "I can help chat about this role or rewrite the resume on your locked master template. "
                f"(LLM temporarily unavailable: {exc})"
            )
        return {
            "session_id": session_id,
            "agent_message": agent_message,
            "intent": "chat",
            "did_rewrite": False,
            "new_version_id": None,
            "version_index": None,
            "full_resume": None,
            "keyword_matches": [],
            "content_delta": {},
            "llm_provider": provider,
            "llm_model": model,
        }

    def _store_version_file(self, version_id: str, ext: str, data: bytes) -> Path:
        version_dir = _RESUME_TEMPLATES_DIR / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        file_path = version_dir / f"resume.{ext}"
        file_path.write_bytes(data)
        return file_path

    def _get_version_file(self, version_id: str, ext: str) -> bytes | None:
        file_path = _RESUME_TEMPLATES_DIR / version_id / f"resume.{ext}"
        if file_path.exists():
            return file_path.read_bytes()
        return None

    def _ensure_master_docx(self, version_id: str, user_id: str, full_resume: dict) -> bytes | None:
        """Return OOXML DOCX for this version (stored or re-injected from master)."""
        docx_bytes = self._get_version_file(version_id, "docx")
        if docx_bytes:
            return docx_bytes
        master_bytes = ensure_master_template_bytes()
        if master_bytes:
            try:
                from app.modules.profile.library_service import get_master_inventory

                source_master = get_master_inventory(user_id) or MOCK_RESUME
            except Exception:
                source_master = deepcopy(MOCK_RESUME)
            try:
                docx_bytes = inject_content(master_bytes, full_resume, source_master)
                self._store_version_file(version_id, "docx", docx_bytes)
                return docx_bytes
            except Exception:
                pass
        template = db.get_active_template(user_id) or ensure_user_has_master_template(user_id)
        if template and template.get("docx_bytes"):
            docx_bytes = template["docx_bytes"]
            self._store_version_file(version_id, "docx", docx_bytes)
            return docx_bytes
        return None

    def _ensure_word_pdf(self, version_id: str, docx_bytes: bytes | None, full_resume: dict) -> bytes | None:
        """Prefer Word COM PDF from master DOCX; never archive Markdown-marker PDFs."""
        pdf_bytes = self._get_version_file(version_id, "pdf")
        # Tiny Helvetica dumps (<12KB) may bake Markdown; Word PDFs are large and may
        # coincidentally contain b'##' / b'**' in compressed streams — do not reject those.
        if pdf_bytes and len(pdf_bytes) < 12000:
            if b"##" in pdf_bytes or b"**" in pdf_bytes or b"# " in pdf_bytes:
                pdf_bytes = None
            else:
                # Still prefer rebuilding from DOCX when available
                if docx_bytes:
                    pdf_bytes = None
        if pdf_bytes and len(pdf_bytes) >= 12000:
            return pdf_bytes
        if docx_bytes:
            try:
                pdf_bytes = ResumeTemplateEditor.convert_docx_to_pdf_via_word(
                    docx_bytes, label=version_id[:8]
                )
                self._store_version_file(version_id, "pdf", pdf_bytes)
                return pdf_bytes
            except Exception:
                try:
                    pdf_bytes = ResumeTemplateEditor.convert_to_pdf_via_libreoffice(docx_bytes)
                    self._store_version_file(version_id, "pdf", pdf_bytes)
                    return pdf_bytes
                except Exception:
                    pass
        try:
            pdf_bytes = ResumeTemplateEditor.generate_pdf_from_resume(full_resume)
            if pdf_bytes and (b"##" in pdf_bytes or b"**" in pdf_bytes):
                return None
            if pdf_bytes:
                self._store_version_file(version_id, "pdf", pdf_bytes)
            return pdf_bytes
        except Exception:
            return None

    def confirm_version(self, version_id: str, user_id: str) -> dict | None:
        version = db.get_resume_version(version_id, user_id)
        if not version:
            return None

        full_resume = version.get("full_resume") or {}
        evidence = full_resume.get("evidence_check") or {}
        format_check = full_resume.get("format_check") or {}
        issues = list(evidence.get("issues") or [])
        hard_issues = evidence.get("hard_issues")
        if hard_issues is None:
            # Wording-overlap alone is not a confirm blocker (JD inventory variants).
            hard_issues = [i for i in issues if "weak textual support" not in i]
        if hard_issues or format_check.get("fabrication") is True:
            return {
                "ok": False,
                "blocked": True,
                "version_id": version_id,
                "reason": "evidence_or_format_gate",
                "issues": hard_issues or issues,
                "evidence_check": evidence,
                "format_check": format_check,
            }

        session = db.get_jd_session(version["session_id"]) or {}
        company, position = extract_company_position(full_resume, session)
        docx_bytes = self._ensure_master_docx(version_id, user_id, full_resume)
        pdf_bytes = self._ensure_word_pdf(version_id, docx_bytes, full_resume)
        if not docx_bytes or not pdf_bytes:
            return {
                "ok": False,
                "blocked": True,
                "version_id": version_id,
                "reason": "missing_master_docx_or_pdf",
                "issues": [
                    "Confirm requires OOXML DOCX + Word-level PDF (no Markdown preview).",
                    f"docx={'ok' if docx_bytes else 'missing'}",
                    f"pdf={'ok' if pdf_bytes else 'missing'}",
                ],
                "evidence_check": evidence,
                "format_check": format_check,
            }

        ok = db.confirm_resume_version(version_id, user_id)
        if not ok:
            return None

        saved = save_final_resume(
            company=company,
            position=position,
            version_id=version_id,
            markdown=version.get("markdown") or "",
            full_resume=full_resume,
            docx_bytes=docx_bytes,
            pdf_bytes=pdf_bytes,
            extra_meta={
                "job_id": session.get("job_id") or session.get("listing_id"),
                "session_id": version.get("session_id"),
                "source_url": session.get("source_url") or session.get("original_url"),
                "match_score": full_resume.get("match_score") or session.get("match_score"),
                "user_id": user_id,
                "preview_engine": "ooxml_word_pdf",
            },
        )
        return {
            "ok": True,
            "version_id": version_id,
            "final_path": saved["folder"],
            "files": saved["files"],
            "company": saved["company"],
            "position": saved["position"],
            "meta": saved.get("meta"),
        }

    async def suggest_project(self, keyword: str) -> str:
        prompt_path = _PROMPTS_DIR / "suggest_project.txt"
        if prompt_path.exists():
            try:
                llm = get_chat_openai(
                    model=settings.DEFAULT_PARSER_MODEL,
                    temperature=0.5,
                    max_tokens=512,
                )
                response = await llm.ainvoke([
                    ("system", _load_prompt("suggest_project.txt")),
                    ("human", f"Missing keyword/skill: {keyword}"),
                ])
                result = _extract_json(response.content)
                suggestion = (result.get("suggestion") or "").strip()
                if suggestion:
                    return suggestion
            except Exception:
                pass
        return (
            f"For '{keyword}', only add a project if it already exists in Master Inventory "
            f"or you confirm new facts in writing — never fabricate a portfolio piece."
        )

    def list_versions(self, session_id: str, user_id: str) -> list[dict]:
        return db.list_resume_versions(session_id, user_id)

    def get_version(self, version_id: str, user_id: str) -> dict | None:
        return db.get_resume_version(version_id, user_id)

    def export_version(self, version_id: str, user_id: str, fmt: str) -> bytes | None:
        version = db.get_resume_version(version_id, user_id)
        if not version:
            return None
        if not version["is_confirmed"]:
            return None

        # Try stored file first
        stored = self._get_version_file(version_id, fmt)
        if stored:
            return stored

        # Generate on the fly
        if fmt == "text":
            return ResumeTemplateEditor._render_markdown(
                version["full_resume"]
            ).encode("utf-8")

        if fmt == "pdf":
            try:
                return ResumeTemplateEditor.generate_pdf_from_resume(
                    version["full_resume"]
                )
            except Exception:
                return ResumeTemplateEditor._render_markdown(
                    version["full_resume"]
                ).encode("utf-8")

        if fmt == "docx":
            stored_docx = self._get_version_file(version_id, "docx")
            if stored_docx:
                return stored_docx
            template = db.get_active_template(user_id) or ensure_user_has_master_template(user_id)
            if template and template.get("docx_bytes"):
                return template["docx_bytes"]
            return ResumeTemplateEditor._render_markdown(
                version["full_resume"]
            ).encode("utf-8")

        return None

    def get_version_pdf(self, version_id: str, user_id: str) -> bytes | None:
        version = db.get_resume_version(version_id, user_id)
        if not version:
            return None
        full_resume = version.get("full_resume") or {}
        docx = self._ensure_master_docx(version_id, user_id, full_resume)
        return self._ensure_word_pdf(version_id, docx, full_resume)
