from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app import db
from app.modules.resume_workspace.apply_flow import (
    confirm_submit,
    get_apply,
    start_apply,
    start_apply_async,
)
from app.modules.resume_workspace.constitution import constitution_api_payload
from app.modules.resume_workspace.schemas import (
    ActivateTemplateResponse,
    AgentTurnRequest,
    AgentTurnResponse,
    AnalyzeResponse,
    ConfirmResponse,
    ConfirmSectionMappingRequest,
    ConfirmSectionMappingResponse,
    ConfirmSubmitRequest,
    ConfirmSubmitResponse,
    CreateJdSessionRequest,
    CreateJdSessionResponse,
    GetVersionResponse,
    KeywordMatchItem,
    ListTemplatesResponse,
    ListVersionsResponse,
    RewriteRequest,
    RewriteResponse,
    StartApplyRequest,
    StartApplyResponse,
    SuggestProjectRequest,
    SuggestProjectResponse,
    TemplateVersionItem,
    UnmappedSection,
    UploadTemplateResponse,
    VersionItem,
)
from app.modules.resume_workspace.service import ResumeWorkspaceService
from app.modules.resume_workspace.tech_evidence import run_tech_evidence_scan

router = APIRouter()
workspace_service = ResumeWorkspaceService()


@router.get("/constitution")
async def get_resume_constitution():
    """Resume rules for Tailor UI + clients (RESUME_CONSTITUTION.md)."""
    return constitution_api_payload()


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
    matches = await workspace_service.analyze(session_id)
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
        content_delta=result.get("content_delta") or {},
    )


@router.post("/jd-session/{session_id}/agent", response_model=AgentTurnResponse)
async def agent_turn(session_id: str, request: AgentTurnRequest):
    """Chat normally or rewrite the master-template resume when the user asks for edits."""
    result = await workspace_service.agent_turn(
        user_id=request.user_id,
        session_id=session_id,
        message=request.message,
        base_version_id=request.base_version_id,
        chat_history=request.chat_history,
    )
    return AgentTurnResponse(
        session_id=result["session_id"],
        agent_message=result["agent_message"],
        intent=result["intent"],
        did_rewrite=result["did_rewrite"],
        new_version_id=result.get("new_version_id"),
        version_index=result.get("version_index"),
        full_resume=result.get("full_resume"),
        keyword_matches=[KeywordMatchItem(**m) for m in (result.get("keyword_matches") or [])],
        content_delta=result.get("content_delta") or {},
        llm_provider=result.get("llm_provider"),
        llm_model=result.get("llm_model"),
        profile_updated=bool(result.get("profile_updated")),
        changed_apply=list(result.get("changed_apply") or []),
        changed_inventory=list(result.get("changed_inventory") or []),
    )


@router.post("/resume-version/{version_id}/confirm", response_model=ConfirmResponse)
async def confirm_version(version_id: str, user_id: str = Query(...)):
    result = workspace_service.confirm_version(version_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Version not found")
    if result.get("blocked"):
        raise HTTPException(
            status_code=409,
            detail={
                "status": "blocked_by_evidence_guard",
                "reason": result.get("reason"),
                "issues": result.get("issues") or [],
                "evidence_check": result.get("evidence_check") or {},
                "format_check": result.get("format_check") or {},
            },
        )
    return ConfirmResponse(
        ok=True,
        version_id=version_id,
        final_path=result.get("final_path"),
        files=result.get("files") or {},
        company=result.get("company"),
        position=result.get("position"),
    )


@router.post("/resume-version/{version_id}/start-apply", response_model=StartApplyResponse)
async def start_apply_endpoint(version_id: str, request: StartApplyRequest):
    mode = (request.mode or "").lower().strip()
    if mode not in {"manual", "auto"}:
        raise HTTPException(status_code=400, detail="mode must be manual or auto")
    try:
        if mode == "auto":
            payload = await start_apply_async(
                user_id=request.user_id,
                version_id=version_id,
                mode=mode,  # type: ignore[arg-type]
                company=request.company,
                position=request.position,
                final_path=request.final_path,
                job_id=request.job_id,
                source_url=request.source_url,
            )
        else:
            payload = start_apply(
                user_id=request.user_id,
                version_id=version_id,
                mode=mode,  # type: ignore[arg-type]
                company=request.company,
                position=request.position,
                final_path=request.final_path,
                job_id=request.job_id,
                source_url=request.source_url,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartApplyResponse(
        apply_id=payload["id"],
        mode=payload["mode"],
        status=payload["status"],
        submitted=bool(payload.get("submitted")),
        paused_before_submit=bool(payload.get("paused_before_submit")),
        message=payload["message"],
        filled_fields=payload.get("filled_fields") or [],
        ats_fields=payload.get("ats_fields") or [],
        ats_type=payload.get("ats_type"),
        source_url=payload.get("source_url"),
        board_url=payload.get("board_url"),
        apply_resolve=payload.get("apply_resolve"),
        browser_fill=payload.get("browser_fill"),
        final_path=payload.get("final_path"),
        confirmed_submit_at=payload.get("confirmed_submit_at"),
        fill_plan=payload.get("fill_plan") or [],
        map_provider=payload.get("map_provider"),
        requires_human_review=bool(payload.get("requires_human_review")),
    )


@router.post("/ats/map-fields", response_model=dict)
async def map_ats_fields_endpoint(body: dict):
    """Reusable DOM-field → profile mapping for Playwright and future extensions."""
    from app.modules.ats_connectors.canonical_profile import canonical_apply_profile
    from app.modules.ats_connectors.dom_scan import normalize_client_fields
    from app.modules.ats_connectors.field_mapper import map_fields

    user_id = str(body.get("user_id") or "")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    fields = normalize_client_fields(list(body.get("fields") or []))
    profile = canonical_apply_profile(
        user_id,
        final_path=body.get("final_path"),
        version_id=body.get("version_id"),
    )
    prefer_llm = bool(body.get("prefer_llm", True))
    result = await map_fields(fields, profile, prefer_llm=prefer_llm)
    return result


@router.get("/apply/{apply_id}", response_model=StartApplyResponse)
async def get_apply_endpoint(apply_id: str):
    payload = get_apply(apply_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Apply session not found")
    return StartApplyResponse(
        apply_id=payload["id"],
        mode=payload["mode"],
        status=payload["status"],
        submitted=bool(payload.get("submitted")),
        paused_before_submit=bool(payload.get("paused_before_submit")),
        message=payload["message"],
        filled_fields=payload.get("filled_fields") or [],
        ats_fields=payload.get("ats_fields") or [],
        ats_type=payload.get("ats_type"),
        source_url=payload.get("source_url"),
        board_url=payload.get("board_url"),
        apply_resolve=payload.get("apply_resolve"),
        browser_fill=payload.get("browser_fill"),
        final_path=payload.get("final_path"),
        confirmed_submit_at=payload.get("confirmed_submit_at"),
        fill_plan=payload.get("fill_plan") or [],
        map_provider=payload.get("map_provider"),
        requires_human_review=bool(payload.get("requires_human_review")),
    )


@router.post("/apply/{apply_id}/confirm-submit", response_model=ConfirmSubmitResponse)
async def confirm_submit_endpoint(apply_id: str, request: ConfirmSubmitRequest):
    """User explicitly confirms after pause-before-submit (audit; does not click live Submit)."""
    try:
        payload = confirm_submit(
            apply_id=apply_id,
            user_id=request.user_id,
            acknowledge=bool(request.acknowledge),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ConfirmSubmitResponse(
        apply_id=payload["id"],
        status=payload["status"],
        submitted=bool(payload.get("submitted")),
        paused_before_submit=bool(payload.get("paused_before_submit")),
        message=payload["message"],
        confirmed_submit_at=payload.get("confirmed_submit_at"),
        source_url=payload.get("source_url"),
    )


@router.post("/resume-version/{version_id}/suggest-project", response_model=SuggestProjectResponse)
async def suggest_project(version_id: str, request: SuggestProjectRequest):
    suggestion = await workspace_service.suggest_project(request.keyword)
    return SuggestProjectResponse(suggestion=suggestion)


@router.get("/jd-session/{session_id}/versions", response_model=ListVersionsResponse)
async def list_versions(session_id: str, user_id: str = Query(...)):
    versions = workspace_service.list_versions(session_id, user_id)
    return ListVersionsResponse(
        versions=[
            VersionItem(
                id=v["id"],
                version_index=v["version_index"],
                is_confirmed=bool(v["is_confirmed"]),
                created_at=v["created_at"],
                confirmed_at=v.get("confirmed_at"),
            )
            for v in versions
        ]
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
        headers={
            "Content-Disposition": (
                f'attachment; filename="resume-v{version["version_index"]}.{fmt}"'
            )
        },
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


@router.post("/template/upload", response_model=UploadTemplateResponse)
async def upload_template(
    user_id: str = Form(...),
    file: UploadFile = File(...),  # noqa: B008 - standard FastAPI upload dependency pattern
):
    filename = file.filename or "resume.docx"
    if not filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Only .docx files are accepted "
                "(run-level XML editing requires Word's native structure)."
            ),
        )
    contents = await file.read()
    result = workspace_service.upload_template(
        user_id=user_id,
        filename=filename,
        docx_bytes=contents,
    )
    return UploadTemplateResponse(**result)


@router.get("/template/active")
async def get_active_template(user_id: str = Query(...)):
    template = workspace_service.get_active_template(user_id)
    if not template:
        raise HTTPException(status_code=404, detail="No template uploaded")
    return {
        "template_id": template["id"],
        "filename": template["filename"],
        "block_count": len(template["parsed_blocks"]),
        "resume_structure": template.get("parsed_structure") or {},
        "unmapped_sections": template.get("unmapped_sections") or [],
        "created_at": template["created_at"],
    }


@router.get("/templates", response_model=ListTemplatesResponse)
async def list_templates(user_id: str = Query(...)):
    """Full upload history for a user — most recent first. Lets the UI offer
    'view/roll back to a previous version' instead of only ever seeing latest."""
    versions = workspace_service.list_template_versions(user_id)
    return ListTemplatesResponse(
        templates=[
            TemplateVersionItem(
                id=v["id"],
                filename=v["filename"],
                is_active=bool(v["is_active"]),
                resume_structure=v.get("parsed_structure") or {},
                unmapped_sections=[
                    UnmappedSection(**s) for s in (v.get("unmapped_sections") or [])
                ],
                created_at=v["created_at"],
                updated_at=v["updated_at"],
            )
            for v in versions
        ]
    )


@router.post("/template/{template_id}/activate", response_model=ActivateTemplateResponse)
async def activate_template(template_id: str, user_id: str = Query(...)):
    """Roll back / switch to a previously uploaded resume version."""
    result = workspace_service.activate_template_version(template_id, user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Template version not found")
    return ActivateTemplateResponse(**result)


@router.post("/template/section-mapping", response_model=ConfirmSectionMappingResponse)
async def confirm_section_mapping(request: ConfirmSectionMappingRequest):
    """User confirms what an unrecognized section heading (e.g. a custom title)
    actually maps to. Saved for reuse so future uploads with the same heading
    don't need re-confirming, and re-parses the active template immediately."""
    try:
        result = workspace_service.confirm_section_mapping(
            request.user_id, request.raw_title, request.section_type
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ConfirmSectionMappingResponse(**result)


# ---------------------------------------------------------------------------
# Tech Evidence (Phase 2-pre) — scan a repo, stage candidates as 'pending',
# only persist to the confirmed evidence base after explicit user review.
# ---------------------------------------------------------------------------


class ScanRepoRequest(BaseModel):
    user_id: str
    repo_path: str


class TechEvidenceDecision(BaseModel):
    id: str
    action: str  # "confirm" | "reject"
    skill: str | None = None
    evidence_description: str | None = None


class ConfirmTechEvidenceRequest(BaseModel):
    user_id: str
    decisions: list[TechEvidenceDecision]


@router.post("/tech-evidence/scan")
async def scan_tech_evidence(request: ScanRepoRequest):
    """Run Phase 2-pre extraction. Nothing here is 'confirmed' yet — every
    result lands as pending/auto_rejected, awaiting explicit user review."""
    repo_path = Path(request.repo_path).expanduser().resolve()
    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail=f"repo_path not found: {repo_path}")
    entries = run_tech_evidence_scan(repo_path)
    payload = [
        {
            "skill": e.skill,
            "evidence_file": e.evidence_file,
            "evidence_description": e.evidence_description,
            "verified": e.verified,
            "reject_reason": e.reject_reason,
        }
        for e in entries
    ]
    ids = db.save_tech_evidence_batch(
        user_id=request.user_id,
        source_repo=str(repo_path),
        entries=payload,
    )
    for row_id, item in zip(ids, payload, strict=True):
        item["id"] = row_id
    return {
        "total": len(payload),
        "verified": sum(1 for p in payload if p["verified"]),
        "auto_rejected": sum(1 for p in payload if not p["verified"]),
        "entries": payload,
    }


@router.get("/tech-evidence")
async def list_tech_evidence(user_id: str = Query(...), status: str | None = Query(None)):
    return {"entries": db.list_tech_evidence(user_id, status=status)}


@router.post("/tech-evidence/confirm")
async def confirm_tech_evidence(request: ConfirmTechEvidenceRequest):
    """The human-review gate: only entries the user explicitly confirms (with
    optional edits) become part of the evidence base Phase 2a can read."""
    results = []
    for decision in request.decisions:
        if decision.action not in {"confirm", "reject"}:
            raise HTTPException(status_code=400, detail=f"invalid action: {decision.action}")
        status = "confirmed" if decision.action == "confirm" else "rejected"
        ok = db.set_tech_evidence_status(
            evidence_id=decision.id,
            user_id=request.user_id,
            status=status,
            skill=decision.skill,
            evidence_description=decision.evidence_description,
        )
        results.append({"id": decision.id, "status": status, "applied": ok})
    return {"results": results}
