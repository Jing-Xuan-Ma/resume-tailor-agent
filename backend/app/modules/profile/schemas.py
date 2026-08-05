from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProfileResponse(BaseModel):
    user_id: UUID
    profile: dict


class FeedbackRequest(BaseModel):
    user_id: UUID
    feedback: dict


class CandidateLibraryResponse(BaseModel):
    user_id: str
    inventory: dict[str, Any]
    apply: dict[str, Any]
    updated_at: str


class CandidateLibraryUpdateRequest(BaseModel):
    inventory: Optional[dict[str, Any]] = None
    apply: Optional[dict[str, Any]] = Field(default=None, alias="apply")
    # allow frontend to send apply_profile as well
    apply_profile: Optional[dict[str, Any]] = None

    model_config = {"populate_by_name": True}
