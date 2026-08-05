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
    content_delta: dict = Field(default_factory=dict)


class AgentTurnRequest(BaseModel):
    user_id: str
    message: str
    base_version_id: Optional[str] = None
    chat_history: list[dict] = Field(default_factory=list)


class AgentTurnResponse(BaseModel):
    session_id: str
    agent_message: str
    intent: str  # chat | rewrite | update_profile
    did_rewrite: bool = False
    new_version_id: Optional[str] = None
    version_index: Optional[int] = None
    full_resume: Optional[dict] = None
    keyword_matches: list[KeywordMatchItem] = Field(default_factory=list)
    content_delta: dict = Field(default_factory=dict)
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    profile_updated: bool = False
    changed_apply: list[str] = Field(default_factory=list)
    changed_inventory: list[str] = Field(default_factory=list)


class ConfirmResponse(BaseModel):
    ok: bool
    version_id: str
    final_path: Optional[str] = None
    files: dict = Field(default_factory=dict)
    company: Optional[str] = None
    position: Optional[str] = None


class StartApplyRequest(BaseModel):
    user_id: str
    mode: str  # manual | auto
    company: Optional[str] = None
    position: Optional[str] = None
    final_path: Optional[str] = None
    job_id: Optional[str] = None
    source_url: Optional[str] = None


class StartApplyResponse(BaseModel):
    apply_id: str
    mode: str
    status: str
    submitted: bool
    paused_before_submit: bool
    message: str
    filled_fields: list[dict] = Field(default_factory=list)
    ats_fields: list[dict] = Field(default_factory=list)
    ats_type: Optional[str] = None
    source_url: Optional[str] = None
    board_url: Optional[str] = None
    apply_resolve: Optional[dict] = None
    browser_fill: Optional[dict] = None
    final_path: Optional[str] = None
    confirmed_submit_at: Optional[str] = None
    fill_plan: list[dict] = Field(default_factory=list)
    map_provider: Optional[str] = None
    requires_human_review: bool = False


class ConfirmSubmitRequest(BaseModel):
    user_id: str
    acknowledge: bool = False


class ConfirmSubmitResponse(BaseModel):
    apply_id: str
    status: str
    submitted: bool
    paused_before_submit: bool
    message: str
    confirmed_submit_at: Optional[str] = None
    source_url: Optional[str] = None


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
