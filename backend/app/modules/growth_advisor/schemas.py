from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class GrowthAnalyzeRequest(BaseModel):
    user_id: UUID
    job_id: Optional[UUID] = None
    target_role: Optional[str] = None


class GrowthPlanResponse(BaseModel):
    id: str
    user_id: str
    job_id: Optional[str] = None
    target_role: str
    gaps: list[dict] = Field(default_factory=list)
    recommendations: list[dict] = Field(default_factory=list)
    roadmap: list[dict] = Field(default_factory=list)
    created_at: str


class GrowthPlanListResponse(BaseModel):
    plans: list[GrowthPlanResponse]
