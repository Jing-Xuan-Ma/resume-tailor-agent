# Job freshness check (2026-08-03)

## Verdict

UI looked ~10 days old mainly because **default score-sort promoted hardcoded mock jobs** (Jul 23–27, scores 60–95) above real index rows (scores ~35). Real catalog ingest times were mostly **today**; LinkedIn/Indeed path is **off** (`python-jobspy` not installed). Remotive’s own `publication_date` for DA roles is often **5–10 days old** — that source is slower than Jobright.

## Evidence

| Check | Result |
|-------|--------|
| `jobspy` in venv | **False** (pip install hung / network) |
| Active listings | 44 (remotive 25, seed 14, himalayas 3, remoteok 1, greenhouse 1) |
| `scraped_at` ages | ~42 under 24h; 2 over 7d |
| `list_jobs` score sort (before fix) | Top 8 = **mocks**, ages **7–10.8 days** |
| `list_jobs` after fix | **44 jobs, 0 mocks** |
| Remotive live `publication_date` | e.g. 2026-07-23 … 07-28 (truly multi-day old) |
| Discover cache on ingest | Was serving stale provider payloads (5 min TTL) — **ingest now skip_cache** |

## Fixes applied

1. `job_list_service.py` — mocks only when catalog empty; relative mock ages if used
2. `posted_at.py` — prefer provider post time for UI `scrapedAt`
3. Remotive / Himalayas — store publication / pubDate in metadata
4. `discover_all(..., skip_cache=True)` for ingest write path
5. `pyproject.toml` optional extra `jobspy`

## Still needed for Jobright-like hours

1. Successfully `pip install python-jobspy` (network blocked this session)
2. Default ingest `hours_old=24|72` once JobSpy works
3. Optional: filter Remotive by `publication_date` age, not only `scraped_at`
4. Reduce reliance on `seed` fixtures in the live index
