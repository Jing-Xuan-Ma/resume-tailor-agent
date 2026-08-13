# JR-1 Report — Local job index + scheduled ingest

**Status: PASS**

## Goal

Read/write separation for job discovery (Jobright-style):

- **Write path**: providers → upsert `job_listings`
- **Read path**: `/discover` defaults to local index (`live=false`)

## What shipped

| Piece | Location |
|-------|----------|
| Shared catalog table | `job_listings` in `backend/app/db.py` |
| Upsert / search / count | `upsert_job_listing`, `search_job_listings`, `count_job_listings` |
| Fingerprint + ingest + search | `backend/app/modules/job_discovery/job_index.py` |
| Background scheduler | `backend/app/modules/job_discovery/scheduler.py` (started in `main.py` lifespan) |
| Discover read path | `POST /api/v1/jobs/discover` with `live: bool = false` |
| Manual ingest API | `POST /api/v1/jobs/index/ingest`, `GET /api/v1/jobs/index/stats` |
| CLI ingest | `scripts/jr1_ingest_jobs.py` |
| Verify | `scripts/jr1_verify.py` → `artifacts/jr-1-bench.json` |

## Config (env)

- `JOB_INDEX_ENABLED` (default true)
- `JOB_INDEX_INGEST_INTERVAL_MINUTES` (default 10)
- `JOB_INDEX_INGEST_ON_STARTUP` (default false)
- `JOB_INDEX_DEFAULT_QUERIES` (default `data analyst,analytics,business intelligence`)
- `JOB_INDEX_DEFAULT_LOCATION` / `JOB_INDEX_INGEST_LIMIT`

## Pass criteria check

| Criterion | Result |
|-----------|--------|
| Search without live providers returns index jobs | PASS (`from_index_jobs=5`) |
| Repeat upsert same URL does not duplicate rows | PASS (`dup_delta=0`) |
| Index discover latency << live fan-out | PASS (`discover_from_index_ms≈567` cold TestClient; no provider fan-out) |
| Existing discover still returns jobs when index empty | PASS (synthetic fallback retained) |

Evidence: `artifacts/jr-1-bench.json`

## How to use

```powershell
# Manual write path
backend\venv\Scripts\python.exe scripts/jr1_ingest_jobs.py --query "data analyst" --location Remote

# Verify
backend\venv\Scripts\python.exe scripts/jr1_verify.py

# Discover from index (default)
# POST /api/v1/jobs/discover { "live": false, ... }

# Opt into live providers + write-through
# POST /api/v1/jobs/discover { "live": true, ... }
```

## Out of scope (later JR batches)

- JR-2: stronger ATS id merge / cross-source entity resolution
- JR-3: score breakdown + full JD semantic scoring
- JR-4: hard filters (remote/visa/age) as first-class query params
- JR-5/6: UX polish + full matrix acceptance

## Notes

- User-scoped `jobs` table unchanged (history / bookmarks still use it).
- Catalog is shared `job_listings`; discover still copies hits into per-user `jobs` for downstream tailor/apply.
