"""
Resume Tailor API Routes
"""

from uuid import UUID

from io import BytesIO

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse

from app.config import settings
from app.core.rate_limit import rate_limiter
from app.modules.resume_tailor.schemas import (
    TailorRequest,
    TailorResponse,
    JDParseRequest,
    JDParseResponse,
    UploadResumeRequest,
    UploadResumeResponse,
    ResumeRecordResponse,
    ExportTextRequest,
    ExportTextResponse,
    ModifyDraftRequest,
    ModifyDraftResponse,
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


@router.get("/resumes/latest", response_model=ResumeRecordResponse)
async def get_latest_resume(user_id: UUID = Query(...)):
    """Return the user's latest uploaded source resume."""
    record = tailor_service.get_latest_resume(user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Resume not found")
    return record


@router.post("/tailor", response_model=TailorResponse)
async def tailor_resume(request: TailorRequest):
    """
    Core endpoint: tailor a user's resume for a specific job description.
    """
    try:
        rate_limiter.check(str(request.user_id), "tailor", settings.MAX_DAILY_APPLICATIONS)
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


@router.post("/drafts/modify", response_model=ModifyDraftResponse)
async def modify_draft(request: ModifyDraftRequest):
    """
    Revise the active tailored resume draft based on a chat instruction.
    """
    try:
        return await tailor_service.modify_draft(
            user_id=request.user_id,
            draft_id=request.draft_id,
            instruction=request.instruction,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str, user_id: UUID = Query(...)):
    """Retrieve the current draft state for the workspace."""
    draft = tailor_service.get_draft(user_id=user_id, draft_id=draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.get("/drafts/{draft_id}/export")
async def export_draft(draft_id: str, user_id: UUID = Query(...), format: str = Query("pdf")):
    """Export the current draft as PDF or Word (.docx)."""
    draft = tailor_service.get_draft(user_id=user_id, draft_id=draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    fmt = format.lower()
    if fmt == "docx":
        data = tailor_service.export_draft_docx(draft)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = "tailored-resume.docx"
    elif fmt == "pdf":
        data = tailor_service.export_draft_pdf(draft)
        media_type = "application/pdf"
        filename = "tailored-resume.pdf"
    else:
        raise HTTPException(status_code=400, detail="format must be 'pdf' or 'docx'")

    return StreamingResponse(
        BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tailored/{tailored_resume_id}")
async def get_tailored_resume(tailored_resume_id: UUID, user_id: UUID | None = Query(None)):
    """Retrieve a previously generated tailored resume."""
    record = tailor_service.get_tailored_resume(tailored_resume_id, user_id=user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Tailored resume not found")
    return record
