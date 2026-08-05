import httpx

from app.config import settings
from app.modules.job_discovery.providers.base_provider import BaseJobProvider, RawJobLead


class AdzunaProvider(BaseJobProvider):
    name = "adzuna"

    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self) -> None:
        self.last_error: str | None = None

    async def discover(
        self,
        *,
        query: str,
        location: str | None = None,
        limit: int = 10,
    ) -> list[RawJobLead]:
        self.last_error = None
        app_id = settings.ADZUNA_APP_ID or ""
        app_key = settings.ADZUNA_API_KEY or ""
        if not app_id or not app_key:
            self.last_error = "missing_credentials"
            return []

        country = "us"
        page = 1
        try:
            params: dict = {
                "app_id": app_id,
                "app_key": app_key,
                "what": query,
                "results_per_page": min(limit, 50),
            }
            # Empty where can confuse Adzuna; only send when provided.
            if location and location.strip() and location.strip().lower() != "remote":
                params["where"] = location.strip()
            url = f"{self.BASE_URL}/{country}/search/{page}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                if resp.status_code >= 400:
                    self.last_error = f"http_{resp.status_code}: {resp.text[:200]}"
                    return []
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"request_failed: {exc}"
            return []

        results = []
        for item in (data.get("results") or [])[:limit]:
            loc_data = item.get("location", {}) or {}
            area = loc_data.get("area")
            if isinstance(area, list):
                area_txt = ", ".join(str(a) for a in area if a)
            else:
                area_txt = str(area) if area else ""
            loc_parts = [
                loc_data.get("city") or area_txt,
                loc_data.get("region"),
                loc_data.get("country", {}).get("label")
                if isinstance(loc_data.get("country"), dict)
                else loc_data.get("country"),
            ]
            loc = ", ".join(str(v) for v in loc_parts if v) or location or ""
            company = item.get("company")
            company_name = (
                company.get("display_name") if isinstance(company, dict) else company
            )
            results.append(
                RawJobLead(
                    title=item.get("title") or "Untitled",
                    company=company_name,
                    location=loc,
                    source_url=item.get("redirect_url"),
                    source_platform="adzuna",
                    description=item.get("description") or "",
                    metadata={
                        "salary_min": item.get("salary_min"),
                        "salary_max": item.get("salary_max"),
                        "salary_currency": (
                            item.get("salary_currency", {}).get("code")
                            if isinstance(item.get("salary_currency"), dict)
                            else item.get("salary_currency")
                        ),
                        "category": (
                            item.get("category", {}).get("label")
                            if isinstance(item.get("category"), dict)
                            else item.get("category")
                        ),
                        "contract_type": item.get("contract_type"),
                        "created": item.get("created"),
                    },
                )
            )
        if not results:
            self.last_error = "empty_result"
        return results
