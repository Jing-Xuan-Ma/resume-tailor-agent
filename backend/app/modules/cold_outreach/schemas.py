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
