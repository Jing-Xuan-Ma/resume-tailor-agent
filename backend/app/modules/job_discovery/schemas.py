from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class JobDiscoverRequest(BaseModel):
    user_id: UUID
    query: str = Field(min_length=1)
    location: Optional[str] = None
    limit: int = Field(default=5, ge=1, le=20)
    sites: list[str] = Field(default_factory=lambda: ["indeed", "linkedin", "zip_recruiter", "google"])
    provider: str = "jobspy"
    hours_old: Optional[int] = None
    country_indeed: str = "USA"


class JobIngestRequest(BaseModel):
    user_id: UUID
    raw_text: str = Field(min_length=1)
    source_url: Optional[str] = None
    source_platform: str = "manual"


class JobResponse(BaseModel):
    id: str
    user_id: str
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    source_url: Optional[str] = None
    source_platform: str
    raw_text: str
    parsed: dict
    match_score: Optional[float] = None
    created_at: str


class JobListResponse(BaseModel):
    jobs: list[JobResponse]


class JobBookmarkRequest(BaseModel):
    user_id: UUID
    job_id: UUID
    notes: Optional[str] = None


class JobBookmarkResponse(BaseModel):
    bookmark: dict


class JobPrepareApplicationRequest(BaseModel):
    user_id: UUID
    resume_id: UUID
    include_cover_letter: bool = True
    include_application_plan: bool = True
    auto_submit: bool = False
    submit_mode: Literal["manual_review", "auto_submit"] = "manual_review"
    user_profile: dict = Field(default_factory=dict)


class JobPrepareApplicationResponse(BaseModel):
    job: JobResponse
    tailored: dict
    cover_letter: Optional[dict] = None
    application_plan: Optional[dict] = None
