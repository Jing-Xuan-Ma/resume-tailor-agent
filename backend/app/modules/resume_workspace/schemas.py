from pydantic import BaseModel, Field


class CreateJdSessionRequest(BaseModel):
    user_id: str
    job_id: str | None = None
    jd_text: str


class CreateJdSessionResponse(BaseModel):
    session_id: str
    jd_text: str
    job_id: str | None = None
    created_at: str


class KeywordMatchItem(BaseModel):
    keyword: str
    status: str
    source_span_in_jd: list[int] = Field(default_factory=lambda: [0, 0])
    suggestion: str | None = None


class AnalyzeResponse(BaseModel):
    session_id: str
    keyword_matches: list[KeywordMatchItem]


class RewriteRequest(BaseModel):
    user_id: str
    session_id: str
    instruction: str
    base_version_id: str | None = None


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
    base_version_id: str | None = None
    chat_history: list[dict] = Field(default_factory=list)


class AgentTurnResponse(BaseModel):
    session_id: str
    agent_message: str
    intent: str  # chat | rewrite | update_profile
    did_rewrite: bool = False
    new_version_id: str | None = None
    version_index: int | None = None
    full_resume: dict | None = None
    keyword_matches: list[KeywordMatchItem] = Field(default_factory=list)
    content_delta: dict = Field(default_factory=dict)
    llm_provider: str | None = None
    llm_model: str | None = None
    profile_updated: bool = False
    changed_apply: list[str] = Field(default_factory=list)
    changed_inventory: list[str] = Field(default_factory=list)


class ConfirmResponse(BaseModel):
    ok: bool
    version_id: str
    final_path: str | None = None
    files: dict = Field(default_factory=dict)
    company: str | None = None
    position: str | None = None


class StartApplyRequest(BaseModel):
    user_id: str
    mode: str  # manual | auto
    company: str | None = None
    position: str | None = None
    final_path: str | None = None
    job_id: str | None = None
    source_url: str | None = None


class StartApplyResponse(BaseModel):
    apply_id: str
    mode: str
    status: str
    submitted: bool
    paused_before_submit: bool
    message: str
    filled_fields: list[dict] = Field(default_factory=list)
    ats_fields: list[dict] = Field(default_factory=list)
    ats_type: str | None = None
    source_url: str | None = None
    board_url: str | None = None
    apply_resolve: dict | None = None
    browser_fill: dict | None = None
    final_path: str | None = None
    confirmed_submit_at: str | None = None
    fill_plan: list[dict] = Field(default_factory=list)
    map_provider: str | None = None
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
    confirmed_submit_at: str | None = None
    source_url: str | None = None


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
    confirmed_at: str | None = None


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
    confirmed_at: str | None = None


class UnmappedSection(BaseModel):
    raw_title: str


class UploadTemplateResponse(BaseModel):
    template_id: str
    filename: str
    block_count: int
    resume_structure: dict = Field(default_factory=dict)
    unmapped_sections: list[UnmappedSection] = Field(default_factory=list)
    is_active: bool = True


class TemplateVersionItem(BaseModel):
    id: str
    filename: str
    is_active: bool
    resume_structure: dict = Field(default_factory=dict)
    unmapped_sections: list[UnmappedSection] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ListTemplatesResponse(BaseModel):
    templates: list[TemplateVersionItem]


class ActivateTemplateResponse(BaseModel):
    ok: bool
    template_id: str
    resume_structure: dict = Field(default_factory=dict)


class ConfirmSectionMappingRequest(BaseModel):
    user_id: str
    raw_title: str
    section_type: str


class ConfirmSectionMappingResponse(BaseModel):
    ok: bool
    template_id: str | None = None
    resume_structure: dict = Field(default_factory=dict)
    unmapped_sections: list[UnmappedSection] = Field(default_factory=list)
