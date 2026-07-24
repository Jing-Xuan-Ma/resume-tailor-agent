"""
Request/Response schemas for Resume Tailor module.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.models import ParsedJobDescription, Resume, TailoredResume


class UploadResumeRequest(BaseModel):
    user_id: UUID
    resume: Optional[Resume] = None
    resume_text: Optional[str] = None  # Plain text fallback for MVP


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
    tailored_resume_id: Optional[str] = None
    draft_id: Optional[str] = None
    revision_id: Optional[str] = None
    markdown: Optional[str] = None
    key_map: list[dict] = Field(default_factory=list)


class JDParseRequest(BaseModel):
    jd_text: str


class JDParseResponse(BaseModel):
    parsed: ParsedJobDescription


class ExportTextRequest(BaseModel):
    tailored_resume: dict


class ExportTextResponse(BaseModel):
    text: str


class ModifyDraftRequest(BaseModel):
    user_id: UUID
    draft_id: str
    instruction: str


class ModifyDraftResponse(BaseModel):
    success: bool
    draft_id: str
    revision_id: Optional[str] = None
    tailored_resume: Optional[dict] = None
    markdown: Optional[str] = None
    key_map: list[dict] = Field(default_factory=list)
    message: str = ""
