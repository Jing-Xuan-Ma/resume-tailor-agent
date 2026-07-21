"""
Chat request/response schemas.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ChatRequest(BaseModel):
    user_id: UUID
    session_id: Optional[UUID] = None
    message: str
    context: Optional[dict] = None  # e.g., {"current_resume_id": "...", "current_job_id": "..."}


class ChatResponse(BaseModel):
    session_id: UUID
    agent_message: str
    agent_state: str  # e.g., "presenting", "clarifying", "idle"
    suggested_actions: list[str] = []  # e.g., ["Upload JD", "View tailored resume", "Export PDF"]
