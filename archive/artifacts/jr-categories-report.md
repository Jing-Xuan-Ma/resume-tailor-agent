# Categories — real Jobright-style chips

**Status: PASS**

## Categories (6)

1. Data Analysis  
2. Business Analyst  
3. Machine Learning and AI  
4. AI Agent  
5. Software Engineering  
6. Risk / Insurance Analytics  

## What shipped

- `backend/app/modules/job_discovery/categories.py` — taxonomy, ingest queries, rule classify  
- `job_listings.category` column + search filter  
- Upsert classifies on write; `POST /api/v1/jobs/index/reclassify` backfills  
- `GET /api/v1/jobs/categories` + counts  
- `GET /api/v1/jobs/list?category=...` filters catalog (label or slug)  
- Ranked Jobs chips pass `category` and default to **Data Analysis**  
- Ingest defaults expand to all category queries when `JOB_INDEX_DEFAULT_QUERIES=auto`

## Verify

`artifacts/jr-categories-bench.json` — `all_pass: true`

## Next (optional)

Re-run ingest to fill non-DA categories:

```powershell
backend\venv\Scripts\python.exe scripts\jr1_ingest_jobs.py
# or POST /api/v1/jobs/index/ingest with empty queries (uses category map)
```
