from fastapi import APIRouter, HTTPException, Query

from app.modules.intern_list_scraper.query import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    get_job,
    search_jobs,
)

router = APIRouter()


@router.get("/jobs")
def list_jobs(
    q: str | None = None,
    slug: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    """Paginated intern-list search. Default 20 per page. Dedupes by job_id."""
    return search_jobs(q=q, slug=slug, page=page, page_size=page_size)


@router.get("/jobs/{job_id}")
def job_detail(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return job
