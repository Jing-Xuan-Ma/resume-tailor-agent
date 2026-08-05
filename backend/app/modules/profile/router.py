from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.memory.long_term import LongTermMemoryStore
from app.memory.user_profile import UserProfileManager
from app.modules.profile import library_service
from app.modules.profile.schemas import (
    CandidateLibraryResponse,
    CandidateLibraryUpdateRequest,
    FeedbackRequest,
    ProfileResponse,
)


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


@router.get("/{user_id}/library", response_model=CandidateLibraryResponse)
async def get_candidate_library(user_id: str):
    """Master Inventory + Apply Profile used by Tailor and auto-apply."""
    lib = library_service.get_or_seed_library(user_id)
    return CandidateLibraryResponse(
        user_id=lib["user_id"],
        inventory=lib["inventory"],
        apply=lib["apply"],
        updated_at=lib["updated_at"],
    )


@router.put("/{user_id}/library", response_model=CandidateLibraryResponse)
async def update_candidate_library(user_id: str, request: CandidateLibraryUpdateRequest):
    try:
        apply_payload = request.apply if request.apply is not None else request.apply_profile
        lib = library_service.update_library(
            user_id,
            inventory=request.inventory,
            apply_profile=apply_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CandidateLibraryResponse(
        user_id=lib["user_id"],
        inventory=lib["inventory"],
        apply=lib["apply"],
        updated_at=lib["updated_at"],
    )


@router.post("/{user_id}/library/reset", response_model=CandidateLibraryResponse)
async def reset_candidate_library(user_id: str):
    lib = library_service.reset_library_to_default(user_id)
    return CandidateLibraryResponse(
        user_id=lib["user_id"],
        inventory=lib["inventory"],
        apply=lib["apply"],
        updated_at=lib["updated_at"],
    )
