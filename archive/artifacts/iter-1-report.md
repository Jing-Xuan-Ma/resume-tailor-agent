# Iter-1 Report — Ranked Job List UI

**Status:** PASS  
**Date:** 2026-08-03

## Scope

JobRight-style ranked jobs table with real filters; row click → detail route; Playwright path + screenshots.

## Implemented

- `frontend/app/jobs/page.tsx` + `components/ranked-jobs-table.tsx`
- `frontend/app/jobs/[id]/page.tsx` detail route
- Backend enrich: `location`, `workModel`, `salary` on mock jobs
- `GET /api/v1/jobs/{id}/detail`
- `scripts/iter1_ui_smoke.py` (Playwright via system Chrome channel)
- Workspace nav link: **Ranked** → `/jobs`

## Evidence

| Check | Result |
|-------|--------|
| API list sorted by score | top = Staff Engineer Marketplace 0.92, On Site, SF |
| `npm run build` | includes `/jobs` and `/jobs/[id]` |
| Playwright list → click first row | PASS title=`Staff Engineer - Marketplace` |
| Screenshots | `artifacts/ui/iter-1/jobs-list.png`, `job-detail.png` |

## UI checklist

1. Ranked jobs obvious on first screen — yes  
2. Score sort visible — yes  
3. Filters usable (source/threshold/search) — yes  
4. Row opens detail URL — yes  
5. Work model color tags — yes  

## Checkpoint

- Tag: `checkpoint/iter-1-pass`
