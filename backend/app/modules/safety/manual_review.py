from app.config import settings


def review_requirements(*, auto_submit: bool = False, submit_mode: str = "manual_review") -> dict:
    auto_allowed = submit_mode == "auto_submit" and auto_submit and settings.ENABLE_AUTO_SUBMIT
    return {
        "manual_review_required": not auto_allowed,
        "auto_submit_allowed": auto_allowed,
        "requested_auto_submit": auto_submit,
        "submit_mode": "auto_submit" if auto_allowed else "manual_review",
        "reason": (
            "Auto-submit enabled by explicit request and server policy."
            if auto_allowed
            else "Manual review mode: user must review and confirm submission."
        ),
    }
