"""Generic ATS connector interfaces and URL detection."""

from urllib.parse import urlparse

from app.modules.application_engine.browser_session import BrowserSession


class BaseATSConnector:
    ats_type = "generic"

    def supports(self, url: str | None) -> bool:
        return True

    def fields(self) -> list[dict]:
        return [
            {"name": "full_name", "type": "text", "required": True, "question": "Full name", "aliases": ["name", "full name", "legal name"]},
            {"name": "email", "type": "text", "required": True, "question": "Email address", "aliases": ["email", "e-mail"]},
            {"name": "phone", "type": "text", "required": False, "question": "Phone number", "aliases": ["phone", "mobile", "telephone"]},
            {"name": "resume", "type": "file", "required": True, "question": "Upload resume", "aliases": ["resume", "cv"]},
            {"name": "cover_letter", "type": "file", "required": False, "question": "Upload cover letter", "aliases": ["cover letter"]},
            {"name": "work_authorization", "type": "select", "required": True, "question": "Are you authorized to work in this location?", "options": ["Yes", "No"], "aliases": ["authorized", "work authorization", "legally authorized"]},
        ]

    def field_selectors(self) -> dict[str, list[str]]:
        return {
            "full_name": ["input[name*='name' i]", "input[id*='name' i]"],
            "email": ["input[type='email']", "input[name*='email' i]", "input[id*='email' i]"],
            "phone": ["input[type='tel']", "input[name*='phone' i]", "input[id*='phone' i]"],
            "work_authorization": ["select[name*='authoriz' i]", "select[id*='authoriz' i]"],
            "resume": ["input[type='file'][name*='resume' i]", "input[type='file']"],
            "cover_letter": ["input[type='file'][name*='cover' i]"],
        }

    def submit_selectors(self) -> list[str]:
        return [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit')",
            "button:has-text('Apply')",
            "button:has-text('Send')",
        ]

    def plan_steps(self, url: str | None) -> list[dict]:
        return [
            {"action": "open_url", "target": url, "mode": "manual_review"},
            {"action": "detect_form", "target": self.ats_type, "mode": "dry_run"},
            {"action": "fill_supported_fields", "target": "application_form", "mode": "dry_run"},
            {"action": "submit_or_wait_for_confirmation", "target": "submit_button", "mode": "policy_controlled"},
        ]

    def submit(self, *, run: dict) -> dict:
        plan = run.get("plan") or {}
        policy = plan.get("policy") or {}
        if not policy.get("auto_submit_allowed"):
            return {
                "submitted": False,
                "status": "blocked_by_policy",
                "message": "Auto-submit is not allowed for this application run.",
            }
        if not run.get("job_id"):
            return {"submitted": False, "status": "invalid_run", "message": "Missing job_id."}
        result = BrowserSession().submit(
            url=(plan.get("browser_session") or {}).get("url"),
            answers=run.get("answers") or [],
            should_submit=True,
            field_selectors=self.field_selectors(),
            submit_selectors=self.submit_selectors(),
        )
        return {"ats_type": self.ats_type, **result}


def host(url: str | None) -> str:
    if not url:
        return ""
    return urlparse(url).netloc.lower()
