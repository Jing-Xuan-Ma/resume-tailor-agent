import httpx

from app.modules.job_discovery.providers.base_provider import BaseJobProvider, RawJobLead


class RemotiveProvider(BaseJobProvider):
    name = "remotive"

    BASE_URL = "https://remotive.com/api/remote-jobs"

    async def discover(
        self,
        *,
        query: str,
        location: str | None = None,
        limit: int = 10,
    ) -> list[RawJobLead]:
        try:
            params = {"search": query, "limit": min(limit * 2, 100)}
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        results = []
        for item in (data.get("jobs") or [])[:limit]:
            loc = item.get("candidate_required_location") or location or ""
            results.append(RawJobLead(
                title=item.get("title") or "Untitled",
                company=item.get("company_name"),
                location=loc,
                source_url=item.get("url"),
                source_platform=f"remotive",
                description=item.get("description") or "",
                metadata={
                    "job_type": item.get("job_type"),
                    "category": item.get("category"),
                    "salary": item.get("salary"),
                    "tags": item.get("tags", []),
                    "publication_date": item.get("publication_date"),
                },
            ))
        return results
