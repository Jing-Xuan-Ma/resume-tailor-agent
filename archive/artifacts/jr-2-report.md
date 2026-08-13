# JR-2 Report — ATS fingerprint + lifecycle

**Status: PASS**

## Goal

Stronger dedupe than `(title, company)`:

1. Prefer **ATS identity** (Greenhouse / Lever / Ashby)
2. Else normalized **URL**
3. Else title+company hash
4. Soft-close stale listings (`status=closed`) so search ignores them

## What shipped

- `extract_ats_identity` + upgraded `listing_fingerprint` in `job_index.py`
- Metadata stores `ats_platform` / `ats_org` / `ats_job_id`
- `db.mark_stale_job_listings(max_age_hours=...)`
- Ingest runs stale close (default 21 days) after upsert

## Pass criteria

| Check | Result |
|-------|--------|
| Greenhouse URL variants same fingerprint | PASS |
| Lever ATS parse | PASS |
| Same ATS job upserted twice → one row | PASS |
| No-URL falls back to `tc:` | PASS |
| Stale → `closed`, excluded from active search | PASS |

Evidence: `artifacts/jr-2-bench.json` (`all_pass: true`)
