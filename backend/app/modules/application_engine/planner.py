from app.modules.application_engine.browser_session import BrowserSession
from app.modules.application_engine.form_detector import detect_form
from app.modules.application_engine.question_answerer import QuestionAnswerer
from app.modules.application_engine.submission_policy import submission_policy
from app.modules.ats_connectors.registry import connector_for


class ApplicationPlanner:
    def __init__(self) -> None:
        self.answerer = QuestionAnswerer()

    def build_plan(self, *, job: dict, user_profile: dict, tailored_resume_id: str | None = None, auto_submit: bool = False, submit_mode: str = "manual_review", artifacts: dict | None = None) -> dict:
        source_url = job.get("source_url")
        connector = connector_for(source_url)
        form = detect_form(source_url)
        session = BrowserSession().open(source_url)
        answers = []
        for field in form["fields"]:
            answer = self.answerer.answer(
                question=field["question"],
                field_type=field["type"],
                options=field.get("options"),
                user_profile=user_profile,
                job=job,
                field_name=field["name"],
                artifacts=artifacts or {},
            )
            answer["field_name"] = field["name"]
            answer["field_type"] = field["type"]
            answer["aliases"] = field.get("aliases", [])
            answers.append(answer)
        policy = submission_policy(auto_submit=auto_submit, submit_mode=submit_mode)
        plan = {
            "job_id": job["id"],
            "tailored_resume_id": tailored_resume_id,
            "ats_type": connector.ats_type,
            "mode": policy["submit_mode"],
            "browser_session": session,
            "steps": connector.plan_steps(source_url),
            "fields": form["fields"],
            "artifacts": artifacts or {},
            "policy": policy,
            "can_submit": bool(policy.get("auto_submit_allowed")),
            "submit_blocked_reason": policy["reason"],
        }
        return {"plan": plan, "answers": answers}
