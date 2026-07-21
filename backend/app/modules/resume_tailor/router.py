"""
Resume Tailor API Routes
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from app.modules.resume_tailor.schemas import (
    TailorRequest,
    TailorResponse,
    JDParseRequest,
    JDParseResponse,
    UploadResumeRequest,
    UploadResumeResponse,
    ExportTextRequest,
    ExportTextResponse,
)
from app.modules.resume_tailor.service import ResumeTailorService

router = APIRouter()
tailor_service = ResumeTailorService()


@router.post("/upload-resume", response_model=UploadResumeResponse)
async def upload_resume(request: UploadResumeRequest):
    """
    Upload a user's resume and embed experiences into the vector store.
    Accepts either a structured Resume object or plain text.
    """
    try:
        result = await tailor_service.upload_resume(
            user_id=request.user_id,
            resume=request.resume,
            resume_text=request.resume_text,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-resume-file", response_model=UploadResumeResponse)
async def upload_resume_file(
    user_id: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Upload a resume file (.docx, .pdf, .txt) and embed into the vector store.
    """
    try:
        contents = await file.read()
        result = await tailor_service.upload_resume_file(
            user_id=UUID(user_id),
            filename=file.filename or "resume",
            file_bytes=contents,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/export-text", response_model=ExportTextResponse)
async def export_text(request: ExportTextRequest):
    """
    Export a tailored resume as plain text for easy copy-paste editing.
    """
    try:
        text = tailor_service.export_text(request.tailored_resume)
        return ExportTextResponse(text=text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tailored/{tailored_resume_id}")
async def get_tailored_resume(tailored_resume_id: UUID):
    """Retrieve a previously generated tailored resume."""
    # TODO: Implement retrieval from DB
    return {"tailored_resume_id": str(tailored_resume_id), "status": "not_yet_implemented"}
