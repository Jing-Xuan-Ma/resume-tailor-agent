from app.modules.safety.manual_review import review_requirements


def submission_policy(auto_submit: bool = False, submit_mode: str = "manual_review") -> dict:
    return review_requirements(auto_submit=auto_submit, submit_mode=submit_mode)
