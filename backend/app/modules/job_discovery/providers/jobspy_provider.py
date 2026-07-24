"""JobSpy integration with a deterministic fallback.

`python-jobspy` is an optional runtime dependency. When it is not installed, or
when a job board blocks the request, this provider returns an empty list so the
router can fall back to local synthetic leads and keep the product usable.
"""

from typing import Any


class JobSpyProvider:
    name = "jobspy"

    def discover(
        self,
        *,
        query: str,
        location: str | None,
        limit: int,
        sites: list[str] | None = None,
        hours_old: int | None = None,
        country_indeed: str = "USA",
    ) -> list[dict[str, Any]]:
        try:
            from jobspy import scrape_jobs
        except Exception:
            return []

        site_name = sites or ["indeed", "linkedin", "zip_recruiter", "google"]
        try:
            frame = scrape_jobs(
                site_name=site_name,
                search_term=query,
                google_search_term=f"{query} jobs {location or ''}".strip(),
                location=location,
                results_wanted=limit,
                hours_old=hours_old,
                country_indeed=country_indeed,
                verbose=0,
                description_format="markdown",
            )
        except Exception:
            return []

        records = frame.to_dict("records") if hasattr(frame, "to_dict") else []
        jobs = []
        for item in records[:limit]:
            title = item.get("title") or item.get("TITLE") or "Untitled Job"
            company = item.get("company") or item.get("COMPANY")
            city = item.get("city") or item.get("CITY")
            state = item.get("state") or item.get("STATE")
            country = item.get("country") or item.get("COUNTRY")
            job_location = ", ".join(str(v) for v in [city, state, country] if v) or location
            description = item.get("description") or item.get("DESCRIPTION") or ""
            job_url = item.get("job_url") or item.get("JOB_URL")
            site = item.get("site") or item.get("SITE") or "jobspy"
            raw_text = f"""{title}
Company: {company or ''}
Location: {job_location or ''}
Source: {site}
URL: {job_url or ''}

{description}
""".strip()
            jobs.append({
                "title": str(title),
                "company": str(company) if company else None,
                "location": str(job_location) if job_location else None,
                "source_url": str(job_url) if job_url else None,
                "source_platform": f"jobspy:{site}",
                "raw_text": raw_text,
                "metadata": item,
            })
        return jobs
