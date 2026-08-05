# JR-5 Report — Path: index discover → detail keywords → tailor handoff

**Status: PASS**

## Goal

Connect real catalog jobs (not only mocks) through:

1. `POST /discover` (index)
2. `GET /jobs/{id}/summary` with matched/missing skills
3. `to_resume_workspace` using real JD text

## What shipped

- `JobListService.get_job/get_summary/to_resume_workspace` fall back to SQLite `jobs` rows
- Summary exposes `coveredKeywords` / `missingKeywords` / `scoreBreakdown` from JR-3 fields
- Scope kept: no referral, no real Submit

## Pass criteria

All PASS — `artifacts/jr-5-bench.json`
