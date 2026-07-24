from app.config import settings
from app.core.rate_limit import rate_limiter


def check_application_limit(user_id: str) -> None:
    rate_limiter.check(user_id, "application_plan", settings.MAX_DAILY_APPLICATIONS)
