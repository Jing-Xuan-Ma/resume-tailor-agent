import httpx

from app.config import settings
from app.modules.job_discovery.providers.base_provider import BaseJobProvider, RawJobLead


class AdzunaProvider(BaseJobProvider):
    name = "adzuna"

    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    async def discover(
        self,
        *,
        query: str,
        location: str | None = None,
        limit: int = 10,
    ) -> list[RawJobLead]:
        app_id = settings.ADZUNA_APP_ID or ""
        app_key = settings.ADZUNA_API_KEY or ""
        if not app_id or not app_key:
            return []

        country = "us"
        page = 1
        try:
            params: dict = {
                "app_id": app_id,
                "app_key": app_key,
                "what": query,
                "where": location or "",
                "results_per_page": min(limit, 50),
                "content_type": "application/json",
            }
            url = f"{self.BASE_URL}/{country}/search/{page}"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        results = []
        for item in (data.get("results") or [])[:limit]:
            loc_data = item.get("location", {}) or {}
            loc_parts = [
                loc_data.get("city") or loc_data.get("area"),
                loc_data.get("region"),
                loc_data.get("country", {}).get("label") if isinstance(loc_data.get("country"), dict) else loc_data.get("country"),
            ]
            loc = ", ".join(str(v) for v in loc_parts if v) or location or ""
            results.append(RawJobLead(
                title=item.get("title") or "Untitled",
                company=item.get("company", {}).get("display_name") if isinstance(item.get("company"), dict) else item.get("company"),
                location=loc,
                source_url=item.get("redirect_url"),
                source_platform="adzuna",
                description=item.get("description") or "",
                metadata={
                    "salary_min": item.get("salary_min"),
                    "salary_max": item.get("salary_max"),
                    "salary_currency": item.get("salary_currency", {}).get("code") if isinstance(item.get("salary_currency"), dict) else item.get("salary_currency"),
                    "category": item.get("category", {}).get("label") if isinstance(item.get("category"), dict) else item.get("category"),
                    "contract_type": item.get("contract_type"),
                    "created": item.get("created"),
                },
            ))
        return results
