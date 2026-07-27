from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app import db
from app.modules.application_engine.application_saver import save_application_plan
from app.modules.application_engine.planner import ApplicationPlanner
from app.modules.application_engine.schemas import (
    ApplicationPlanRequest,
    ApplicationPlanResponse,
    ApplicationRunListResponse,
    ApplicationSubmitResponse,
    AutoSubmitRequest,
    ManualSubmitConfirmRequest,
)
from app.modules.ats_connectors.registry import connector_for
from app.modules.safety.audit_log import audit
from app.modules.safety.daily_limits import check_application_limit


router = APIRouter()
planner = ApplicationPlanner()


@router.post("/plan", response_model=ApplicationPlanResponse)
async def plan_application(request: ApplicationPlanRequest):
    check_application_limit(str(request.user_id))
    job = db.get_job(str(request.job_id), user_id=str(request.user_id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    user = db.get_user(str(request.user_id)) or {}
    profile = {**user, **(db.get_profile(str(request.user_id)) or {}), **request.user_profile}
    result = planner.build_plan(
        job=job,
        user_profile=profile,
        tailored_resume_id=str(request.tailored_resume_id) if request.tailored_resume_id else None,
        auto_submit=request.auto_submit,
        submit_mode=request.submit_mode,
    )
    plan = result["plan"]
    answers = result["answers"]
    run_id = save_application_plan(
        user_id=str(request.user_id),
        job_id=str(request.job_id),
        tailored_resume_id=str(request.tailored_resume_id) if request.tailored_resume_id else None,
        ats_type=plan["ats_type"],
        plan=plan,
        answers=answers,
        submit_mode=plan["mode"],
    )
    status = "prepared_for_auto_submit" if plan["mode"] == "auto_submit" else "prepared_pending_manual_review"
    db.update_application_run_status(run_id=run_id, user_id=str(request.user_id), status=status, submission_result={})
    audit(str(request.user_id), f"application_plan_{plan['mode']}", {"job_id": str(request.job_id)}, application_run_id=run_id)
    return ApplicationPlanResponse(application_run_id=run_id, status=status, plan=plan, answers=answers)


@router.get("", response_model=ApplicationRunListResponse)
async def list_application_runs(user_id: UUID = Query(...), limit: int = Query(50, ge=1, le=100)):
    return ApplicationRunListResponse(runs=db.list_application_runs(str(user_id), limit=limit))


@router.get("/{application_run_id}")
async def get_application_run(application_run_id: str, user_id: UUID = Query(...)):
    run = db.get_application_run(application_run_id, user_id=str(user_id))
    if not run:
        raise HTTPException(status_code=404, detail="Application run not found")
    return run


@router.post("/{application_run_id}/confirm-manual-submit", response_model=ApplicationSubmitResponse)
async def confirm_manual_submit(application_run_id: str, request: ManualSubmitConfirmRequest):
    run = db.get_application_run(application_run_id, user_id=str(request.user_id))
    if not run:
        raise HTTPException(status_code=404, detail="Application run not found")
    result = {
        "submitted": True,
        "status": "submitted_by_user",
        "mode": "manual_review",
        "message": "User confirmed the application was manually submitted.",
        "confirmation_note": request.confirmation_note,
    }
    updated = db.update_application_run_status(
        run_id=application_run_id,
        user_id=str(request.user_id),
        status="submitted_by_user",
        submission_result=result,
    )
    db.record_job_action(str(request.user_id), run["job_id"], "submitted_by_user",
                         {"application_run_id": application_run_id, "mode": "manual_review"})
    audit(str(request.user_id), "manual_submission_confirmed", result, application_run_id=application_run_id)
    return ApplicationSubmitResponse(application_run_id=application_run_id, status=updated["status"], submission_result=updated["submission_result"])


@router.post("/{application_run_id}/auto-submit", response_model=ApplicationSubmitResponse)
async def auto_submit(application_run_id: str, request: AutoSubmitRequest):
    if not request.confirm_auto_submit:
        raise HTTPException(status_code=400, detail="confirm_auto_submit must be true")
    check_application_limit(str(request.user_id))
    run = db.get_application_run(application_run_id, user_id=str(request.user_id))
    if not run:
        raise HTTPException(status_code=404, detail="Application run not found")
    if run.get("status") in {"submitted_by_user", "auto_submitted"}:
        raise HTTPException(status_code=409, detail="Application already submitted")

    job = db.get_job(run["job_id"], user_id=str(request.user_id))
    connector = connector_for(job.get("source_url") if job else None)
    result = connector.submit(run=run)
    status = "auto_submitted" if result.get("submitted") else "auto_submit_blocked"
    updated = db.update_application_run_status(
        run_id=application_run_id,
        user_id=str(request.user_id),
        status=status,
        submission_result=result,
    )
    db.record_job_action(str(request.user_id), run["job_id"], status,
                         {"application_run_id": application_run_id, "mode": "auto_submit"})
    audit(str(request.user_id), status, result, application_run_id=application_run_id)
    if not result.get("submitted"):
        raise HTTPException(status_code=409, detail=result)
    return ApplicationSubmitResponse(application_run_id=application_run_id, status=updated["status"], submission_result=updated["submission_result"])
