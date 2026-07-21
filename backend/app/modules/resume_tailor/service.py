"""
Resume Tailor Service — orchestrates the LangGraph agent.
"""

from uuid import UUID

from app.core.models import ParsedJobDescription, Resume, TailoredResume
from app.memory.experience_embedder import ExperienceEmbedder
from app.memory.long_term import LongTermMemoryStore
from app.modules.resume_tailor.agent import tailor_agent
from app.modules.resume_tailor.nodes.parse_jd import JDParsingNode


class ResumeTailorService:
    """
    High-level service for resume tailoring operations.
    """

    def __init__(self):
        self.jd_parser = JDParsingNode()
        self.embedder = ExperienceEmbedder()
        self.memory_store = LongTermMemoryStore()

    def _rebuild_resume_data(self, user_id: str) -> dict:
        """Rebuild resume_data dict from Chroma experience documents."""
        docs = self.memory_store.get_all_experiences(user_id)
        if not docs:
            return {}

        experiences: dict[str, dict] = {}
        for doc in docs:
            meta = doc.get("metadata", {})
            exp_id = meta.get("experience_id")
            if not exp_id:
                continue
            if exp_id not in experiences:
                experiences[exp_id] = {
                    "id": exp_id,
                    "company": meta.get("company", ""),
                    "title": meta.get("title", ""),
                    "date_range": meta.get("date_range", ""),
                    "summary": "",
                    "bullets": [],
                    "skills": meta.get("skills", []),
                }
            chunk_type = meta.get("chunk_type")
            if chunk_type == "summary":
                experiences[exp_id]["summary"] = doc.get("text", "")
            elif chunk_type == "bullet":
                experiences[exp_id]["bullets"].append(doc.get("text", ""))

        return {"experiences": list(experiences.values())}

    async def upload_resume(self, user_id: UUID, resume: Resume) -> dict:
        """
        Upload and embed a user's resume into the vector store.
        Returns the number of documents embedded.
        """
        count = await self.embedder.embed_resume(str(user_id), resume)
        return {
            "success": True,
            "embedded_count": count,
            "message": f"Resume uploaded and {count} experience chunks embedded.",
        }

    async def tailor(
        self,
        user_id: UUID,
        resume_id: UUID,
        jd_text: str,
        job_id: Optional[UUID] = None,
    ) -> dict:
        """
        Run the full tailoring pipeline.
        """
        # Load resume data from vector store
        resume_data = self._rebuild_resume_data(str(user_id))

        # Prepare initial state for LangGraph
        initial_state = {
            "user_id": str(user_id),
            "resume_id": str(resume_id),
            "user_input": jd_text,
            "resume_data": resume_data,
            "jd_text": jd_text,
            "jd_parsed": None,
            "matched_experiences": None,
            "tailored_resume": None,
            "evidence_check": None,
            "agent_response": "",
            "requires_clarification": False,
            "memory_context": {},
        }

        # Execute the agent graph
        result = await tailor_agent.ainvoke(initial_state)

        # TODO: Save tailored resume to DB
        # TODO: Emit ResumeTailoredEvent

        return {
            "success": not result.get("requires_clarification", False),
            "tailored_resume": result.get("tailored_resume"),
            "message": result.get("agent_response", ""),
            "clarification_needed": result.get("requires_clarification", False),
            "clarification_question": result.get("agent_response") if result.get("requires_clarification") else None,
            "ats_score_estimate": result.get("tailored_resume", {}).get("ats_score_estimate") if result.get("tailored_resume") else None,
        }

    async def parse_jd(self, jd_text: str) -> ParsedJobDescription:
        """
        Standalone JD parsing utility.
        """
        return await self.jd_parser.parse(jd_text)
