import json
import re
from pathlib import Path
from uuid import uuid4
from datetime import UTC, datetime

from app import db
from app.config import settings
from app.modules.resume_workspace.schemas import KeywordMatchItem
from app.modules.resume_workspace.template_editor import ResumeTemplateEditor
from app.core.llm_client import get_chat_openai


_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_RESUME_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "data" / "templates"
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

    async def analyze(self, session_id: str) -> list[dict]:
        session = db.get_jd_session(session_id)
        if not session:
            return []

        jd_text = session["jd_text"]
        user_id = session.get("user_id", "")
        resume_text = ""
        if user_id:
            latest = db.get_latest_resume(user_id)
            if latest:
                resume_text = json.dumps(latest.get("parsed", latest), ensure_ascii=False)

        system_prompt = _load_prompt("keyword_analysis.txt")

        llm = get_chat_openai(
            model=settings.DEFAULT_PARSER_MODEL,
            temperature=0.1,
            max_tokens=2048,
        )
        human_prompt = f"JD:\n{jd_text}"
        if resume_text:
            human_prompt += f"\n\nResume:\n{resume_text}"

        try:
            response = await llm.ainvoke([
                ("system", system_prompt),
                ("human", human_prompt),
            ])
            result = _extract_json(response.content)
            matches = result.get("keyword_matches", [])
        except Exception:
            matches = []

        db.update_jd_session_keywords(session_id, matches)
        return matches

    async def rewrite(
        self, user_id: str, session_id: str, instruction: str,
        base_version_id: str | None = None
    ) -> dict:
        session = db.get_jd_session(session_id)
        jd_text = session["jd_text"] if session else ""

        if base_version_id:
            base = db.get_resume_version(base_version_id, user_id)
            resume = base["full_resume"] if base else None
        else:
            resume = None

        if not resume:
            latest = db.get_latest_resume(user_id)
            resume = latest["parsed"] if latest else None

        if not resume:
            resume = await self._llm_generate_initial_resume(user_id, jd_text)

        # Get keyword matches before rewrite
        keyword_matches = await self.analyze(session_id)

        # Build prompt
        system_prompt = _load_prompt("workspace_rewrite.txt")
        user_prompt = (
            f"Target JD:\n{jd_text}\n\n"
            f"Current Resume:\n{json.dumps(resume, ensure_ascii=False, indent=2)}\n\n"
            f"User instruction: {instruction}\n\n"
            f"Rewrite the resume following the format rules above. "
            f"Keep all section structure identical. Only rewrite text content."
        )

        llm = get_chat_openai(
            model=settings.DEFAULT_TAILOR_MODEL,
            temperature=0.3,
            max_tokens=4096,
        )
        try:
            response = await llm.ainvoke([
                ("system", system_prompt),
                ("human", user_prompt),
            ])
            tailored = _extract_json(response.content)
        except Exception as e:
            tailored = dict(resume)

        # Re-analyze keyword matches after rewrite
        if session_id:
            keyword_matches = await self.analyze(session_id)

        version_index = db.get_latest_version_index(session_id, user_id) + 1
        if version_index > 5:
            db.delete_oldest_version(session_id, user_id)
            version_index = 5

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
                "changed_fields": list(tailored.keys()) if tailored != resume else [],
                "template_replacements": template_replacements,
            },
            full_resume=tailored,
            markdown=markdown,
        )

        if template_docx:
            self._store_version_file(version_id, "docx", template_docx)
        if pdf_bytes:
            self._store_version_file(version_id, "pdf", pdf_bytes)

        return {
            "new_version_id": version_id,
            "session_id": session_id,
            "version_index": version_index,
            "full_resume": tailored,
            "markdown": markdown,
            "keyword_matches": keyword_matches,
            "has_template": bool(template_docx),
            "has_pdf": bool(pdf_bytes),
        }

    async def _llm_generate_initial_resume(self, user_id: str, jd_text: str) -> dict:
        system_prompt = _load_prompt("workspace_rewrite.txt")
        llm = get_chat_openai(
            model=settings.DEFAULT_TAILOR_MODEL,
            temperature=0.3,
            max_tokens=4096,
        )
        try:
            response = await llm.ainvoke([
                ("system", system_prompt),
                ("human", (
                    f"Target JD:\n{jd_text}\n\n"
                    f"No existing resume found for this user. "
                    f"Create a minimal resume structure with empty sections. "
                    f"Set candidate_name to 'Unknown', summary to a brief placeholder. "
                    f"Do NOT fabricate any experience or skills."
                )),
            ])
            return _extract_json(response.content)
        except Exception:
            return {"candidate_name": "", "contact_line": "", "summary": "", "education": [], "experiences": [], "projects": [], "skills_certifications": ""}

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

    async def suggest_project(self, keyword: str) -> str:
        system_prompt = _load_prompt("suggest_project.txt")
        llm = get_chat_openai(
            model=settings.DEFAULT_PARSER_MODEL,
            temperature=0.5,
            max_tokens=512,
        )
        try:
            response = await llm.ainvoke([
                ("system", system_prompt),
                ("human", f"Missing keyword/skill: {keyword}"),
            ])
            result = _extract_json(response.content)
            return result.get("suggestion", "")
        except Exception:
            return (
                f"For '{keyword}', consider building a practical project that "
                f"demonstrates this skill. Try searching for open-source projects "
                f"or tutorials related to {keyword}."
            )

    def list_versions(self, session_id: str, user_id: str) -> list[dict]:
        return db.list_resume_versions(session_id, user_id)

    def get_version(self, version_id: str, user_id: str) -> dict | None:
        return db.get_resume_version(version_id, user_id)

    def export_version(self, version_id: str, user_id: str, fmt: str) -> bytes | None:
        version = db.get_resume_version(version_id, user_id)
        if not version or not version["is_confirmed"]:
            return None

        stored = self._get_version_file(version_id, fmt)
        if stored:
            return stored

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
