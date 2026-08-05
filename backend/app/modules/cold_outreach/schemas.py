from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class OutreachDraftRequest(BaseModel):
    user_id: UUID
    job_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    contact_role: Optional[str] = None
    company: Optional[str] = None
    channel: Literal["email", "linkedin", "referral"] = "email"
    tone: Literal["concise", "warm", "formal"] = "warm"
    template_type: Literal[
        "coffee_chat",
        "post_apply_thanks",
        "recruiter_ping",
        "linkedin_connect",
        "general",
    ] = "general"
    linkedin_url: Optional[str] = None
    contact_email: Optional[str] = None
    coffee_availability: Optional[str] = None
    save_to_crm: bool = True


class OutreachContactRequest(BaseModel):
    user_id: UUID
    id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    company: Optional[str] = None
    job_id: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    coffee_availability: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = "identified"
    reply_status: Optional[str] = "none"
    coffee_slots: Optional[list[str]] = None


class OutreachContactResponse(BaseModel):
    id: str
    name: str = ""
    role: str = ""
    company: str = ""
    job_id: Optional[str] = None
    linkedin_url: str = ""
    email: str = ""
    coffee_availability: str = ""
    notes: str = ""
    status: str = "identified"
    reply_status: str = "none"
    last_reply_at: str = ""
    coffee_slots: list[str] = Field(default_factory=list)
    updated_at: str = ""


class OutreachContactListResponse(BaseModel):
    contacts: list[OutreachContactResponse] = Field(default_factory=list)


class OutreachSendRequest(BaseModel):
    user_id: UUID
    """Confirmation: must be true to actually send."""
    confirm_send: bool = False
    """Override recipient email (defaults to contact_name + company inferred)."""
    to_email: Optional[str] = None


class OutreachSendResponse(BaseModel):
    id: str
    status: str
    delivery_status: Optional[str] = None
    delivery_error: Optional[str] = None
    sent_at: Optional[str] = None
    provider: str = "not_configured"
    rate_limit_remaining: Optional[int] = None


class OutreachMessageResponse(BaseModel):
    id: str
    user_id: str
    job_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_role: Optional[str] = None
    company: Optional[str] = None
    channel: str
    subject: str
    body: str
    status: str
    metadata: dict = Field(default_factory=dict)
    unsubscribe_token: Optional[str] = None
    sent_at: Optional[str] = None
    delivery_status: Optional[str] = None
    delivery_error: Optional[str] = None
    created_at: str
    updated_at: str


class OutreachListResponse(BaseModel):
    messages: list[OutreachMessageResponse]


class OutreachMarkSentRequest(BaseModel):
    user_id: UUID


class UnsubscribeResponse(BaseModel):
    status: str
    message: str


# ── Step-2 candidate ranking ──────────────────────────────────


class OutreachCandidateInput(BaseModel):
    id: Optional[str] = None
    name: str = ""
    title: str = ""
    role: Optional[str] = None
    snippet: str = ""
    headline: Optional[str] = None
    recent_activity: str = ""
    linkedin_url: str = ""
    company_size: Optional[str] = None
    status: str = "not_contacted"


class OutreachRankRequest(BaseModel):
    user_id: UUID
    candidates: list[OutreachCandidateInput] = Field(default_factory=list, max_length=25)
    jd_text: str = ""
    position: str = ""
    company: str = ""
    company_size: Optional[Literal["small", "medium", "large", "unknown"]] = "unknown"


class OutreachRankedCandidate(BaseModel):
    id: str = ""
    name: str = ""
    title: str = ""
    snippet: str = ""
    recent_activity: str = ""
    linkedin_url: str = ""
    score: int = 0
    stars: int = 1
    match_reason: str = ""
    reason_details: list[str] = Field(default_factory=list)
    components: dict = Field(default_factory=dict)
    status: str = "not_contacted"


class OutreachRankResponse(BaseModel):
    candidates: list[OutreachRankedCandidate] = Field(default_factory=list)
    jd_signals: dict = Field(default_factory=dict)


# ── Step-1 JD URL ingest ──────────────────────────────────────


class OutreachJdIngestRequest(BaseModel):
    user_id: UUID
    url: str
    jd_text_override: str = ""


class OutreachJdIngestResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    company: str = ""
    position: str = ""
    jd_text: str = ""
    platform: str = "unknown"
    source_url: str = ""
    page_title: str = ""
    fetch_status: str = ""


# ── Step-3 email finder ───────────────────────────────────────


class OutreachEmailFindRequest(BaseModel):
    user_id: UUID
    name: str
    company: str = ""
    domain: str = ""
    website: str = ""
    use_hunter: bool = True


class OutreachEmailCandidate(BaseModel):
    email: str
    source: str = ""
    source_detail: str = ""
    pattern: str = ""
    confidence: float = 0.0
    confidence_label: str = "low"
    smtp_status: str = "not_checked"
    recommendation: str = ""


class OutreachEmailFindResponse(BaseModel):
    name: str = ""
    company: str = ""
    domain: str = ""
    hunter_used: bool = False
    candidates: list[OutreachEmailCandidate] = Field(default_factory=list)
    expectancy_note: str = ""
    empty_reason: Optional[str] = None
