import httpx

from app.modules.job_discovery.providers.base_provider import BaseJobProvider, RawJobLead


class RemoteOkProvider(BaseJobProvider):
    name = "remoteok"

    BASE_URL = "https://remoteok.com/api"

    async def discover(
        self,
        *,
        query: str,
        location: str | None = None,
        limit: int = 10,
    ) -> list[RawJobLead]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    self.BASE_URL,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        ql = query.lower()
        results = []
        for item in data[: limit * 3]:
            title = item.get("position") or ""
            if ql not in title.lower():
                continue
            loc = item.get("location") or "Remote"
            results.append(RawJobLead(
                title=title,
                company=item.get("company"),
                location=loc,
                source_url=item.get("url"),
                source_platform="remoteok",
                description=item.get("description") or "",
                metadata={
                    "salary_min": item.get("salary_min"),
                    "salary_max": item.get("salary_max"),
                    "currency": item.get("currency"),
                    "tags": item.get("tags", []),
                    "date": item.get("date"),
                },
            ))
            if len(results) >= limit:
                break
        return results
