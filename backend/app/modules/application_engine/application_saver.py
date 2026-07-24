from app import db
from app.modules.safety.audit_log import audit


def save_application_plan(*, user_id: str, job_id: str, tailored_resume_id: str | None, ats_type: str, plan: dict, answers: list[dict], submit_mode: str = "manual_review") -> str:
    run_id = db.save_application_run(
        user_id=user_id,
        job_id=job_id,
        tailored_resume_id=tailored_resume_id,
        status="prepared_pending_manual_review",
        ats_type=ats_type,
        plan=plan,
        answers=answers,
        submit_mode=submit_mode,
    )
    audit(user_id, "application_plan_created", {"job_id": job_id, "ats_type": ats_type}, application_run_id=run_id)
    return run_id
