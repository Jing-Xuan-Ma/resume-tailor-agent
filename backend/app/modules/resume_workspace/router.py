from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import Response

from app.modules.resume_workspace.schemas import (
    CreateJdSessionRequest,
    CreateJdSessionResponse,
    AnalyzeResponse,
    KeywordMatchItem,
    RewriteRequest,
    RewriteResponse,
    ConfirmResponse,
    SuggestProjectRequest,
    SuggestProjectResponse,
    ListVersionsResponse,
    VersionItem,
    GetVersionResponse,
)
from app.modules.resume_workspace.service import ResumeWorkspaceService

router = APIRouter()
workspace_service = ResumeWorkspaceService()


@router.post("/jd-session", response_model=CreateJdSessionResponse)
async def create_jd_session(request: CreateJdSessionRequest):
    session = workspace_service.create_session(
        user_id=request.user_id,
        jd_text=request.jd_text,
        job_id=request.job_id,
    )
    return CreateJdSessionResponse(
        session_id=session["id"],
        jd_text=session["jd_text"],
        job_id=session.get("job_id"),
        created_at=session["created_at"],
    )


@router.post("/jd-session/{session_id}/analyze", response_model=AnalyzeResponse)
async def analyze_jd(session_id: str):
    matches = workspace_service.analyze(session_id)
    return AnalyzeResponse(
        session_id=session_id,
        keyword_matches=[KeywordMatchItem(**m) for m in matches],
    )


@router.post("/jd-session/{session_id}/rewrite", response_model=RewriteResponse)
async def rewrite_resume(session_id: str, request: RewriteRequest):
    result = await workspace_service.rewrite(
        user_id=request.user_id,
        session_id=session_id,
        instruction=request.instruction,
        base_version_id=request.base_version_id,
    )
    return RewriteResponse(
        new_version_id=result["new_version_id"],
        session_id=result["session_id"],
        version_index=result["version_index"],
        full_resume=result["full_resume"],
        markdown=result["markdown"],
        keyword_matches=[KeywordMatchItem(**m) for m in result["keyword_matches"]],
    )


@router.post("/resume-version/{version_id}/confirm", response_model=ConfirmResponse)
async def confirm_version(version_id: str, user_id: str = Query(...)):
    ok = workspace_service.confirm_version(version_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Version not found")
    return ConfirmResponse(ok=True, version_id=version_id)


@router.post("/resume-version/{version_id}/suggest-project", response_model=SuggestProjectResponse)
async def suggest_project(version_id: str, request: SuggestProjectRequest):
    suggestion = workspace_service.suggest_project(request.keyword)
    return SuggestProjectResponse(suggestion=suggestion)


@router.get("/jd-session/{session_id}/versions", response_model=ListVersionsResponse)
async def list_versions(session_id: str, user_id: str = Query(...)):
    versions = workspace_service.list_versions(session_id, user_id)
    return ListVersionsResponse(
        versions=[VersionItem(
            id=v["id"],
            version_index=v["version_index"],
            is_confirmed=bool(v["is_confirmed"]),
            created_at=v["created_at"],
            confirmed_at=v.get("confirmed_at"),
        ) for v in versions]
    )


@router.get("/resume-version/{version_id}", response_model=GetVersionResponse)
async def get_version(version_id: str, user_id: str = Query(...)):
    version = workspace_service.get_version(version_id, user_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return GetVersionResponse(
        id=version["id"],
        session_id=version["session_id"],
        version_index=version["version_index"],
        content_delta=version["content_delta"],
        full_resume=version["full_resume"],
        markdown=version["markdown"],
        is_confirmed=bool(version["is_confirmed"]),
        created_at=version["created_at"],
        confirmed_at=version.get("confirmed_at"),
    )


@router.get("/resume-version/{version_id}/export")
async def export_version(version_id: str, user_id: str = Query(...), format: str = Query("pdf")):
    version = workspace_service.get_version(version_id, user_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    if not version["is_confirmed"]:
        raise HTTPException(status_code=400, detail="Only confirmed versions can be exported")

    fmt = format.lower()
    data = workspace_service.export_version(version_id, user_id, fmt)
    if not data:
        raise HTTPException(status_code=500, detail="Export failed")

    media_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text": "text/plain",
    }
    return Response(
        content=data,
        media_type=media_types.get(fmt, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="resume-v{version["version_index"]}.{fmt}"'},
    )


@router.get("/resume-version/{version_id}/preview")
async def preview_version_pdf(version_id: str, user_id: str = Query(...)):
    """Get the PDF preview bytes for a version (even if not confirmed)."""
    pdf = workspace_service.get_version_pdf(version_id, user_id)
    if not pdf:
        version = workspace_service.get_version(version_id, user_id)
        if not version:
            raise HTTPException(status_code=404, detail="Version not found")
        raise HTTPException(status_code=500, detail="PDF generation failed")
    return Response(content=pdf, media_type="application/pdf")


@router.post("/template/upload")
async def upload_template(
    user_id: str = Form(...),
    file: UploadFile = File(...),
):
    contents = await file.read()
    result = workspace_service.upload_template(
        user_id=user_id,
        filename=file.filename or "resume.docx",
        docx_bytes=contents,
    )
    return result


@router.get("/template/active")
async def get_active_template(user_id: str = Query(...)):
    template = workspace_service.get_active_template(user_id)
    if not template:
        raise HTTPException(status_code=404, detail="No template uploaded")
    return {
        "template_id": template["id"],
        "filename": template["filename"],
        "block_count": len(template["parsed_blocks"]),
        "created_at": template["created_at"],
    }
