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
