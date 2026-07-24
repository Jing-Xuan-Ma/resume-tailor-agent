from app import db


def audit(user_id: str, action: str, payload: dict, application_run_id: str | None = None) -> None:
    db.save_application_audit(user_id, application_run_id, action, payload)
