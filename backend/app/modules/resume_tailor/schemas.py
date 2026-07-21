"""
Request/Response schemas for Resume Tailor module.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.core.models import ParsedJobDescription, Resume, TailoredResume


class UploadResumeRequest(BaseModel):
    user_id: UUID
    resume: Resume


class UploadResumeResponse(BaseModel):
    success: bool
    embedded_count: int
    message: str


class TailorRequest(BaseModel):
    user_id: UUID
    resume_id: UUID
    jd_text: str
    job_id: Optional[UUID] = None
    preferences: Optional[dict] = None  # Override user preferences for this run


class TailorResponse(BaseModel):
    success: bool
    tailored_resume: Optional[dict] = None  # Relaxed for MVP; will be TailoredResume in production
    message: str = ""
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    ats_score_estimate: Optional[float] = None


class JDParseRequest(BaseModel):
    jd_text: str


class JDParseResponse(BaseModel):
    parsed: ParsedJobDescription


class ExportTextRequest(BaseModel):
    tailored_resume: dict


class ExportTextResponse(BaseModel):
    text: str
