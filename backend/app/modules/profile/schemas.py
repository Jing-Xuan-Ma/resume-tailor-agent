from uuid import UUID

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    user_id: UUID
    profile: dict


class FeedbackRequest(BaseModel):
    user_id: UUID
    feedback: dict
