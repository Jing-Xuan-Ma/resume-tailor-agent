"""
Resume Tailor Service — orchestrates the LangGraph agent.
"""

from uuid import UUID

from app.core.models import ParsedJobDescription, Resume, TailoredResume
from app.memory.experience_embedder import ExperienceEmbedder
from app.memory.long_term import LongTermMemoryStore
from app.modules.resume_tailor.agent import tailor_agent
from app.modules.resume_tailor.nodes.file_parser import parse_resume_file
from app.modules.resume_tailor.nodes.parse_jd import JDParsingNode
from app.modules.resume_tailor.nodes.text_export import TextExportNode


class ResumeTailorService:
    """
    High-level service for resume tailoring operations.
    """

    def __init__(self):
        self.jd_parser = JDParsingNode()
        self.embedder = ExperienceEmbedder()
        self.memory_store = LongTermMemoryStore()
        self.text_exporter = TextExportNode()

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

    async def upload_resume(
        self, user_id: UUID, resume: Optional[Resume] = None, resume_text: Optional[str] = None
    ) -> dict:
        """
        Upload and embed a user's resume into the vector store.
        Supports structured Resume object or plain text.
        Returns the number of documents embedded.
        """
        if resume:
            count = await self.embedder.embed_resume(str(user_id), resume)
        elif resume_text:
            # Plain text mode: split into chunks and store directly
            count = await self._embed_plain_text(str(user_id), resume_text)
        else:
            return {"success": False, "embedded_count": 0, "message": "No resume content provided."}

        return {
            "success": True,
            "embedded_count": count,
            "message": f"Resume uploaded and {count} chunks embedded.",
        }

    async def upload_resume_file(self, user_id: UUID, filename: str, file_bytes: bytes) -> dict:
        """
        Upload a resume file (.docx / .pdf / .txt), parse to text, and embed.
        """
        try:
            text = parse_resume_file(filename, file_bytes)
        except Exception as e:
            return {"success": False, "embedded_count": 0, "message": f"Failed to parse file: {e}"}

        count = await self._embed_plain_text(str(user_id), text)
        return {
            "success": True,
            "embedded_count": count,
            "message": f"File '{filename}' parsed and {count} chunks embedded.",
        }

    async def _embed_plain_text(self, user_id: str, text: str) -> int:
        """Split plain text into chunks and store in Chroma."""
        # Simple chunking: split by blank lines, then by sentences if too long
        raw_chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
        documents = []
        for idx, chunk in enumerate(raw_chunks):
            # If chunk is too long (>500 chars), split by sentences
            if len(chunk) > 500:
                sentences = chunk.replace(". ", ".\n").split("\n")
                for s_idx, sentence in enumerate(sentences):
                    s = sentence.strip()
                    if s:
                        documents.append({
                            "text": s,
                            "metadata": {
                                "chunk_type": "text",
                                "paragraph_index": idx,
                                "sentence_index": s_idx,
                                "source": "user_upload",
                            },
                        })
            else:
                documents.append({
                    "text": chunk,
                    "metadata": {
                        "chunk_type": "text",
                        "paragraph_index": idx,
                        "source": "user_upload",
                    },
                })

        if not documents:
            return 0

        await self.embedder.store.add_experiences(user_id, documents)
        return len(documents)

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

    def export_text(self, tailored_resume: dict) -> str:
        """
        Export tailored resume as plain text.
        """
        return self.text_exporter.render(tailored_resume)
