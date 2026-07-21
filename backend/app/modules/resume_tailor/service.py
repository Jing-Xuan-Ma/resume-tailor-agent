"""
Resume Tailor Service — orchestrates the LangGraph agent.
"""

from uuid import UUID

from app.core.models import ParsedJobDescription, TailoredResume
from app.modules.resume_tailor.agent import tailor_agent
from app.modules.resume_tailor.nodes.parse_jd import JDParsingNode


class ResumeTailorService:
    """
    High-level service for resume tailoring operations.
    """

    def __init__(self):
        self.jd_parser = JDParsingNode()

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
        # Prepare initial state for LangGraph
        initial_state = {
            "user_id": str(user_id),
            "resume_id": str(resume_id),
            "user_input": jd_text,
            "resume_data": {},  # TODO: Load from DB
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
