"""
Core domain models using Pydantic v2.
These models define the shape of resumes, experiences, jobs, and tailored outputs.
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


# =============================================================================
# User & Profile
# =============================================================================

class UserBase(BaseModel):
    email: str
    full_name: str
    preferred_name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[HttpUrl] = None
    portfolio_url: Optional[HttpUrl] = None


class User(UserBase):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserPreferenceProfile(BaseModel):
    """Dynamic user preferences learned from feedback."""
    verbosity: Literal["concise", "medium", "detailed"] = "medium"
    tone: Literal["casual", "professional", "formal"] = "professional"
    metric_emphasis: bool = True
    preferred_action_verbs: list[str] = Field(default_factory=lambda: ["Led", "Built", "Designed"])
    target_roles: list[str] = Field(default_factory=list)
    avoided_phrases: list[str] = Field(default_factory=list)


# =============================================================================
# Resume & Experience
# =============================================================================

class ExperienceBullet(BaseModel):
    text: str
    mentioned_skills: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)  # e.g., ["40%", "$50K"]


class Experience(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    company: str
    title: str
    location: Optional[str] = None
    date_range: str  # e.g., "2021-03 — 2024-06"
    summary: Optional[str] = None
    bullets: list[ExperienceBullet] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str
    degree: str
    field: Optional[str] = None
    date_range: Optional[str] = None
    gpa: Optional[str] = None


class Project(BaseModel):
    name: str
    description: str
    url: Optional[HttpUrl] = None
    skills: list[str] = Field(default_factory=list)


class Resume(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    title: str = "My Resume"
    summary: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Job Description
# =============================================================================

class ParsedJobDescription(BaseModel):
    """Structured output from JD parsing."""
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    years_experience: Optional[int] = None
    key_responsibilities: list[str] = Field(default_factory=list)
    company_values: list[str] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
    salary_range: Optional[str] = None
    raw_text: str


class Job(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    source_url: Optional[HttpUrl] = None
    source_platform: Optional[str] = None  # e.g., "adzuna", "linkedin"
    parsed: ParsedJobDescription
    match_score: Optional[float] = None  # 0-100
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Tailored Resume Output
# =============================================================================

class TailoredBullet(BaseModel):
    text: str
    evidence_from: UUID  # Points to original Experience.id
    is_modified: bool = True
    original_text: Optional[str] = None


class TailoredExperience(BaseModel):
    original_id: UUID
    company: str
    title: str
    date_range: str
    bullets: list[TailoredBullet]
    skills_highlighted: list[str]


class TailoredResume(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    original_resume_id: UUID
    job_id: Optional[UUID] = None
    user_id: UUID
    summary: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    experiences: list[TailoredExperience] = Field(default_factory=list)
    ats_score_estimate: Optional[float] = None
    tailoring_summary: str = ""  # Human-readable summary of changes
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Conversation & Chat
# =============================================================================

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict] = None  # e.g., {"node": "tailor", "state": "presenting"}


class ConversationSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    messages: list[ChatMessage] = Field(default_factory=list)
    current_state: str = "idle"  # Maps to AgentState
    context: dict = Field(default_factory=dict)  # Arbitrary context for the session
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
