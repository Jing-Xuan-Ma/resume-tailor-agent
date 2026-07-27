from pathlib import Path
from uuid import uuid4
from datetime import UTC, datetime

from app import db
from app.modules.resume_workspace.schemas import KeywordMatchItem
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor


_RESUME_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "data" / "templates"
_RESUME_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


MOCK_RESUME = {
    "candidate_name": "ZHANG WEI",
    "contact_line": "zhangwei@email.com | +86 138-0000-0000 | linkedin.com/in/zhangwei",
    "summary": "Senior software engineer with 6+ years of experience building scalable distributed systems. Proficient in Python, Go, and cloud-native architectures.",
    "education": [
        {
            "institution": "Tsinghua University",
            "degree": "B.S. in Computer Science",
            "field": "Computer Science",
            "location": "Beijing",
            "date_range": "September 2016 - June 2020",
        }
    ],
    "experiences": [
        {
            "company": "TechCorp Inc.",
            "title": "Senior Software Engineer",
            "location": "Shanghai",
            "date_range": "July 2022 - Present",
            "bullets": [
                {"text": "Designed and implemented a high-throughput message queue processing pipeline handling 50K+ events/sec using Kafka and Go"},
                {"text": "Reduced API latency by 40% through query optimization and caching strategy redesign"},
                {"text": "Led a team of 4 engineers to deliver a real-time analytics platform serving 10+ internal teams"},
            ],
        },
        {
            "company": "DataStream Ltd.",
            "title": "Software Engineer",
            "location": "Beijing",
            "date_range": "August 2020 - June 2022",
            "bullets": [
                {"text": "Built RESTful microservices with Python/FastAPI and PostgreSQL, serving 1M+ daily requests"},
                {"text": "Implemented CI/CD pipelines with GitHub Actions, reducing deployment time by 60%"},
                {"text": "Developed ETL jobs processing 200GB+ daily data using Apache Spark"},
            ],
        },
    ],
    "projects": [
        {
            "name": "Distributed Task Scheduler",
            "tools": ["Go", "Redis", "Docker", "Kubernetes"],
            "context": "Independent Project",
            "date_range": "Jan 2024 - Mar 2024",
            "bullets": [
                {"text": "Built a distributed task scheduler supporting cron-based and event-driven scheduling across 20+ worker nodes"},
            ],
        }
    ],
    "skills_certifications": "Python, Go, FastAPI, Kafka, PostgreSQL, Redis, Docker, Kubernetes, AWS, Spark, TensorFlow",
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

    async def rewrite(
        self, user_id: str, session_id: str, instruction: str,
        base_version_id: str | None = None
    ) -> dict:
        if base_version_id:
            base = db.get_resume_version(base_version_id, user_id)
            resume = base["full_resume"] if base else MOCK_RESUME
        else:
            resume = MOCK_RESUME

        tailored = dict(resume)
        tailored["summary"] = (
            "Senior backend infrastructure engineer with 6+ years of experience "
            "designing and building scalable distributed systems. Proficient in Python, "
            "Go, and cloud-native technologies including Kafka, Kubernetes, and Docker."
        )

        version_index = db.get_latest_version_index(session_id, user_id) + 1
        if version_index > 5:
            db.delete_oldest_version(session_id, user_id)
            version_index = 5

        markdown = ResumeTemplateEditor._render_markdown(tailored)

        # Try template-based editing if a template exists
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

        # Generate preview PDF
        pdf_bytes: bytes | None = None
        try:
            if template_docx:
                pdf_bytes = ResumeTemplateEditor.generate_pdf_from_resume(tailored)
        except Exception:
            pdf_bytes = None

        version_id = db.create_resume_version(
            session_id=session_id,
            user_id=user_id,
            version_index=version_index,
            content_delta={
                "instruction": instruction,
                "changed_fields": ["summary"],
                "template_replacements": template_replacements,
            },
            full_resume=tailored,
            markdown=markdown,
        )

        # Store generated files
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

    def confirm_version(self, version_id: str, user_id: str) -> bool:
        return db.confirm_resume_version(version_id, user_id)

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
            try:
                return ResumeTemplateEditor.generate_preview_pdf(
                    version["full_resume"]
                )
            except Exception:
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
