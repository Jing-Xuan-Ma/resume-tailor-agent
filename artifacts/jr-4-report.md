# JR-4 Report — Hard filters

**Status: PASS**

## Goal

Server-side filters that actually change result sets:

- `work_model` (remote / hybrid / onsite)
- `source_platform`
- `hours_old` / max age
- `min_score_100` (0–100)

## What shipped

- `work_model` column on `job_listings` + `infer_work_model()`
- Filters on `search_job_listings` / `search_index` / `POST /discover`
- Discover request fields: `work_model`, `source_platform`, `min_score_100`

## Pass criteria

All PASS — see `artifacts/jr-4-bench.json`
