import httpx

from app.modules.job_discovery.providers.base_provider import BaseJobProvider, RawJobLead


class HimalayasProvider(BaseJobProvider):
    name = "himalayas"

    BASE_URL = "https://himalayas.app/jobs/api"

    async def discover(
        self,
        *,
        query: str,
        location: str | None = None,
        limit: int = 10,
    ) -> list[RawJobLead]:
        try:
            params = {"query": query, "limit": min(limit, 50)}
            if location:
                params["location"] = location
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        results = []
        for item in (data.get("jobs") or [])[:limit]:
            results.append(RawJobLead(
                title=item.get("title") or "Untitled",
                company=item.get("company", {}).get("name") if isinstance(item.get("company"), dict) else item.get("company"),
                location=item.get("location") or item.get("city") or location or "",
                source_url=item.get("url") or item.get("applyUrl"),
                source_platform="himalayas",
                description=item.get("description") or "",
                metadata={
                    "salary": item.get("salary"),
                    "currency": item.get("currency"),
                    "type": item.get("type"),
                    "category": item.get("category"),
                    "company_data": item.get("company"),
                },
            ))
        return results
