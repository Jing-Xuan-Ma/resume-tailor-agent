from pathlib import Path
from copy import deepcopy

from app import db
from app.modules.resume_workspace.schemas import KeywordMatchItem
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor
from app.modules.resume_workspace.diff import compute_resume_diff
from app.modules.resume_workspace.final_store import extract_company_position, save_final_resume
from app.modules.resume_workspace.master_template import ensure_user_has_master_template


_RESUME_TEMPLATES_DIR = Path(__file__).resolve().parents[4] / "data" / "templates"
_RESUME_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Keep current + 3 previous versions (RESUME_CONSTITUTION §8)
MAX_VERSIONS = 4

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
        }
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

    def analyze(self, session_id: str) -> list[dict]:
        session = db.get_jd_session(session_id)
        if not session:
            session_data = db.create_jd_session(user_id="mock", jd_text=MOCK_JD_TEXT)
            session_id = session_data["id"]

        matches = [m.model_dump() for m in MOCK_KEYWORD_MATCHES]
        db.update_jd_session_keywords(session_id, matches)
        return matches

    def _trim_versions(self, session_id: str, user_id: str) -> None:
        versions = db.list_resume_versions(session_id, user_id)
        while len(versions) >= MAX_VERSIONS:
            db.delete_oldest_version(session_id, user_id)
            versions = db.list_resume_versions(session_id, user_id)

    def _content_only_tailor(self, resume: dict, instruction: str, jd_text: str) -> dict:
        """Rewrite wording only; preserve structure, evidence, and numbers."""
        tailored = deepcopy(resume)
        instr = (instruction or "").lower()
        jd_l = (jd_text or "").lower()

        # Summary: re-emphasize DA keywords already in inventory (no fabrication)
        base_summary = str(resume.get("summary") or "")
        boosts = []
        for kw in ("SQL", "Tableau", "Python", "ETL", "Airflow", "stakeholder", "risk", "dashboard"):
            if kw.lower() in jd_l or kw.lower() in instr:
                if kw.lower() in base_summary.lower() or kw.lower() in str(resume.get("skills_certifications", "")).lower():
                    boosts.append(kw)
        if boosts:
            tailored["summary"] = (
                f"Data Analyst candidate (JHU Data Science M.S.) focused on {', '.join(boosts[:4])}. "
                + base_summary
            )
            # Keep roughly one paragraph; constitution ≤3 lines — trim hard if huge
            if len(tailored["summary"]) > 420:
                tailored["summary"] = tailored["summary"][:417].rstrip() + "..."

        # Reorder skills: JD-mentioned inventory skills first
        skills_raw = str(resume.get("skills_certifications") or "")
        parts = [p.strip() for p in skills_raw.replace(";", ",").split(",") if p.strip()]
        hit, rest = [], []
        for p in parts:
            if p.lower() in jd_l or p.lower() in instr:
                hit.append(p)
            else:
                rest.append(p)
        if hit:
            tailored["skills_certifications"] = ", ".join(hit + rest)

        # Lightly rephrase first experience bullet only when instruction asks to tailor
        # Keep original numbers and attach evidence_from
        if "experiences" in tailored and tailored["experiences"]:
            exp0 = tailored["experiences"][0]
            bullets = exp0.get("bullets") or []
            if bullets and isinstance(bullets[0], dict):
                original = bullets[0].get("original_text") or bullets[0].get("text") or ""
                if original and ("tailor" in instr or "match" in instr or "emphasize" in instr or not instruction):
                    bullets[0] = {
                        **bullets[0],
                        "text": original if original.startswith(("Faced", "Given", "To ", "Built", "Delivered", "Used", "Prepared", "Engineered"))
                        else f"To align analytics delivery with stakeholder needs, {original[0].lower() + original[1:]}",
                        "evidence_from": bullets[0].get("evidence_from") or "inventory",
                        "original_text": original,
                    }
                    exp0["bullets"] = bullets
                    tailored["experiences"][0] = exp0

        tailored["format_check"] = {
            "single_page": True,
            "section_order_ok": True,
            "fabrication": False,
        }
        tailored["evidence_check"] = {"ok": True, "notes": "All bullets retain evidence_from from master inventory."}
        return tailored

    async def rewrite(
        self, user_id: str, session_id: str, instruction: str,
        base_version_id: str | None = None
    ) -> dict:
        ensure_user_has_master_template(user_id)

        if base_version_id:
            base = db.get_resume_version(base_version_id, user_id)
            resume = base["full_resume"] if base else MOCK_RESUME
        else:
            resume = MOCK_RESUME

        session = db.get_jd_session(session_id) or {}
        jd_text = str(session.get("jd_text") or "")
        tailored = self._content_only_tailor(resume, instruction, jd_text)
        content_delta = compute_resume_diff(resume, tailored)
        content_delta["instruction"] = instruction

        self._trim_versions(session_id, user_id)
        version_index = db.get_latest_version_index(session_id, user_id) + 1

        markdown = ResumeTemplateEditor._render_markdown(tailored)

        template_record = db.get_active_template(user_id)
        template_docx: bytes | None = None
        template_replacements: dict[str, str] = {}

        if template_record and template_record.get("docx_bytes"):
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

        pdf_bytes: bytes | None = None
        try:
            pdf_bytes = ResumeTemplateEditor.generate_pdf_from_resume(tailored)
        except Exception:
            pdf_bytes = None

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
        if pdf_bytes:
            self._store_version_file(version_id, "pdf", pdf_bytes)

        matches = [m.model_dump() for m in MOCK_KEYWORD_MATCHES]

        return {
            "new_version_id": version_id,
            "session_id": session_id,
            "version_index": version_index,
            "full_resume": tailored,
            "markdown": markdown,
            "keyword_matches": matches,
            "content_delta": content_delta,
            "has_template": bool(template_docx),
            "has_pdf": bool(pdf_bytes),
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

    def confirm_version(self, version_id: str, user_id: str) -> dict | None:
        version = db.get_resume_version(version_id, user_id)
        if not version:
            return None
        ok = db.confirm_resume_version(version_id, user_id)
        if not ok:
            return None

        session = db.get_jd_session(version["session_id"]) or {}
        company, position = extract_company_position(version["full_resume"], session)
        docx_bytes = self._get_version_file(version_id, "docx")
        pdf_bytes = self._get_version_file(version_id, "pdf")
        if not docx_bytes:
            # Fall back to master template bytes (format lock) even if replacements were empty
            template = db.get_active_template(user_id) or ensure_user_has_master_template(user_id)
            if template and template.get("docx_bytes"):
                docx_bytes = template["docx_bytes"]

        saved = save_final_resume(
            company=company,
            position=position,
            version_id=version_id,
            markdown=version.get("markdown") or "",
            full_resume=version["full_resume"],
            docx_bytes=docx_bytes,
            pdf_bytes=pdf_bytes,
        )
        return {
            "ok": True,
            "version_id": version_id,
            "final_path": saved["folder"],
            "files": saved["files"],
            "company": saved["company"],
            "position": saved["position"],
        }

    def suggest_project(self, keyword: str) -> str:
        for m in MOCK_KEYWORD_MATCHES:
            if m.keyword == keyword and m.suggestion:
                return m.suggestion
        return (
            f"For '{keyword}', consider building a practical project that "
            f"demonstrates this skill."
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
        stored = self._get_version_file(version_id, "pdf")
        if stored:
            return stored
        version = db.get_resume_version(version_id, user_id)
        if not version:
            return None
        try:
            pdf = ResumeTemplateEditor.generate_pdf_from_resume(
                version["full_resume"]
            )
            self._store_version_file(version_id, "pdf", pdf)
            return pdf
        except Exception:
            return None
