import httpx

from app.modules.job_discovery.providers.base_provider import BaseJobProvider, RawJobLead


class JobicyProvider(BaseJobProvider):
    name = "jobicy"

    BASE_URL = "https://jobicy.com/api/v2/remote-jobs"

    async def discover(
        self,
        *,
        query: str,
        location: str | None = None,
        limit: int = 10,
    ) -> list[RawJobLead]:
        try:
            params = {
                "count": min(limit * 2, 50),
                "keyword": query,
                "industry": "",
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        jobs = data.get("jobs") or []
        results = []
        for item in jobs[:limit]:
            loc = ", ".join(
                str(v) for v in [
                    item.get("jobCity"),
                    item.get("jobCountry"),
                ] if v
            ) or location or "Remote"
            results.append(RawJobLead(
                title=item.get("jobTitle") or "Untitled",
                company=item.get("companyName"),
                location=loc,
                source_url=item.get("url") or item.get("applyUrl"),
                source_platform="jobicy",
                description=(item.get("jobDescription") or ""),
                metadata={
                    "salary": item.get("salary"),
                    "salaryCurrency": item.get("salaryCurrency"),
                    "jobIndustry": item.get("jobIndustry"),
                    "jobType": item.get("jobType"),
                    "technologies": item.get("technologies", []),
                },
            ))
        return results
