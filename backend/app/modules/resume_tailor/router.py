"""
Resume Tailor API Routes
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.modules.resume_tailor.schemas import (
    TailorRequest,
    TailorResponse,
    JDParseRequest,
    JDParseResponse,
)
from app.modules.resume_tailor.service import ResumeTailorService

router = APIRouter()
tailor_service = ResumeTailorService()


@router.post("/tailor", response_model=TailorResponse)
async def tailor_resume(request: TailorRequest):
    """
    Core endpoint: tailor a user's resume for a specific job description.
    """
    try:
        result = await tailor_service.tailor(
            user_id=request.user_id,
            resume_id=request.resume_id,
            jd_text=request.jd_text,
            job_id=request.job_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/parse-jd", response_model=JDParseResponse)
async def parse_jd(request: JDParseRequest):
    """
    Utility endpoint: parse a raw job description into structured fields.
    """
    try:
        parsed = await tailor_service.parse_jd(request.jd_text)
        return JDParseResponse(parsed=parsed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tailored/{tailored_resume_id}")
async def get_tailored_resume(tailored_resume_id: UUID):
    """Retrieve a previously generated tailored resume."""
    # TODO: Implement retrieval from DB
    return {"tailored_resume_id": str(tailored_resume_id), "status": "not_yet_implemented"}
