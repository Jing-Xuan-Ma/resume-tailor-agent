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
    template_type: Literal["coffee_chat", "post_apply_thanks", "recruiter_ping", "general"] = "general"
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
    created_at: str
    updated_at: str


class OutreachListResponse(BaseModel):
    messages: list[OutreachMessageResponse]


class OutreachMarkSentRequest(BaseModel):
    user_id: UUID
