from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ApplicationPlanRequest(BaseModel):
    user_id: UUID
    job_id: UUID
    tailored_resume_id: Optional[UUID] = None
    auto_submit: bool = False
    submit_mode: Literal["manual_review", "auto_submit"] = "manual_review"
    user_profile: dict = Field(default_factory=dict)


class ApplicationPlanResponse(BaseModel):
    application_run_id: str
    status: str
    plan: dict
    answers: list[dict]


class ApplicationRunListResponse(BaseModel):
    runs: list[dict]


class ManualSubmitConfirmRequest(BaseModel):
    user_id: UUID
    confirmation_note: Optional[str] = None


class AutoSubmitRequest(BaseModel):
    user_id: UUID
    confirm_auto_submit: bool = True


class ApplicationSubmitResponse(BaseModel):
    application_run_id: str
    status: str
    submission_result: dict
