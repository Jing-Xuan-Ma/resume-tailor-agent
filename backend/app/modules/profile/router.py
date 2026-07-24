from uuid import UUID

from fastapi import APIRouter

from app.memory.long_term import LongTermMemoryStore
from app.memory.user_profile import UserProfileManager
from app.modules.profile.schemas import FeedbackRequest, ProfileResponse


router = APIRouter()
manager = UserProfileManager(LongTermMemoryStore())


@router.get("/{user_id}", response_model=ProfileResponse)
async def get_profile(user_id: UUID):
    profile = await manager.get_profile(str(user_id))
    return ProfileResponse(user_id=user_id, profile=profile.model_dump())


@router.post("/feedback", response_model=ProfileResponse)
async def update_profile_from_feedback(request: FeedbackRequest):
    profile = await manager.update_from_feedback(str(request.user_id), request.feedback)
    return ProfileResponse(user_id=request.user_id, profile=profile.model_dump())
