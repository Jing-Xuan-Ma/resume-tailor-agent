from typing import Optional
from pydantic import BaseModel, Field


class CreateJdSessionRequest(BaseModel):
    user_id: str
    job_id: Optional[str] = None
    jd_text: str


class CreateJdSessionResponse(BaseModel):
    session_id: str
    jd_text: str
    job_id: Optional[str] = None
    created_at: str


class KeywordMatchItem(BaseModel):
    keyword: str
    status: str
    source_span_in_jd: list[int] = Field(default_factory=lambda: [0, 0])
    suggestion: Optional[str] = None


class AnalyzeResponse(BaseModel):
    session_id: str
    keyword_matches: list[KeywordMatchItem]


class RewriteRequest(BaseModel):
    user_id: str
    session_id: str
    instruction: str
    base_version_id: Optional[str] = None


class RewriteResponse(BaseModel):
    new_version_id: str
    session_id: str
    version_index: int
    full_resume: dict
    markdown: str
    keyword_matches: list[KeywordMatchItem]


class ConfirmResponse(BaseModel):
    ok: bool
    version_id: str


class SuggestProjectRequest(BaseModel):
    user_id: str
    keyword: str


class SuggestProjectResponse(BaseModel):
    suggestion: str


class VersionItem(BaseModel):
    id: str
    version_index: int
    is_confirmed: bool
    created_at: str
    confirmed_at: Optional[str] = None


class ListVersionsResponse(BaseModel):
    versions: list[VersionItem]


class GetVersionResponse(BaseModel):
    id: str
    session_id: str
    version_index: int
    content_delta: dict
    full_resume: dict
    markdown: str
    is_confirmed: bool
    created_at: str
    confirmed_at: Optional[str] = None
