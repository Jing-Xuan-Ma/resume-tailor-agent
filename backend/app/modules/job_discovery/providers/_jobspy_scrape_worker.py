"""Child-process worker for JobSpy scrapes (keeps parent API process stable)."""

from __future__ import annotations

import json
import sys
from typing import Any


def _scrape(payload: dict[str, Any]) -> list[dict[str, Any]]:
    from jobspy import scrape_jobs

    query = payload.get("query") or ""
    location = payload.get("location")
    limit = int(payload.get("limit") or 10)
    sites = payload.get("sites") or ["indeed"]
    hours_old = payload.get("hours_old")
    country_indeed = payload.get("country_indeed") or "USA"

    frame = scrape_jobs(
        site_name=sites,
        search_term=query,
        google_search_term=f"{query} jobs {location or ''}".strip(),
        location=location,
        results_wanted=limit,
        hours_old=hours_old,
        country_indeed=country_indeed,
        verbose=0,
        description_format="markdown",
    )
    records = frame.to_dict("records") if hasattr(frame, "to_dict") else []
    jobs: list[dict[str, Any]] = []
    for item in records[:limit]:
        title = item.get("title") or item.get("TITLE") or "Untitled Job"
        company = item.get("company") or item.get("COMPANY")
        city = item.get("city") or item.get("CITY")
        state = item.get("state") or item.get("STATE")
        country = item.get("country") or item.get("COUNTRY")
        job_location = ", ".join(str(v) for v in [city, state, country] if v) or location
        description = item.get("description") or item.get("DESCRIPTION") or ""
        job_url = item.get("job_url") or item.get("JOB_URL")
        job_url_direct = item.get("job_url_direct") or item.get("JOB_URL_DIRECT")
        site = item.get("site") or item.get("SITE") or "jobspy"
        board_url = str(job_url).strip() if job_url else None
        direct_url = str(job_url_direct).strip() if job_url_direct else None

        def _usable_direct(u: str | None) -> bool:
            if not u or not u.lower().startswith(("http://", "https://")):
                return False
            low = u.lower()
            # Workday career roots like ...myworkdayjobs.com/FRS often fail to open.
            if "myworkdayjobs.com" in low:
                return "/job/" in low or low.count("/") >= 5
            return True

        # Prefer company/ATS apply link; keep Indeed/etc. as board_url.
        if _usable_direct(direct_url):
            source_url = direct_url
        else:
            source_url = board_url
        # metadata may contain non-JSON types; keep a small safe subset
        safe_meta = {
            "site": site,
            "date_posted": str(item.get("date_posted") or item.get("DATE_POSTED") or ""),
            "board_url": board_url,
            "job_url_direct": direct_url,
            "apply_url": direct_url if _usable_direct(direct_url) else None,
            "has_external_apply": bool(_usable_direct(direct_url)),
        }
        raw_text = f"""{title}
Company: {company or ''}
Location: {job_location or ''}
Source: {site}
URL: {source_url or board_url or ''}

{description}
""".strip()
        jobs.append(
            {
                "title": str(title),
                "company": str(company) if company else None,
                "location": str(job_location) if job_location else None,
                "source_url": source_url,
                "source_platform": f"jobspy:{site}",
                "raw_text": raw_text,
                "metadata": safe_meta,
            }
        )
    return jobs


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: _jobspy_scrape_worker.py <in.json> <out.json>", file=sys.stderr)
        return 2
    in_path, out_path = sys.argv[1], sys.argv[2]
    try:
        payload = json.loads(open(in_path, encoding="utf-8-sig").read())
        jobs = _scrape(payload)
        open(out_path, "w", encoding="utf-8").write(json.dumps({"jobs": jobs}))
        return 0
    except Exception as exc:  # noqa: BLE001
        open(out_path, "w", encoding="utf-8").write(json.dumps({"error": str(exc), "jobs": []}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
