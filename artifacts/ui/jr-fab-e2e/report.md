# Jobright FAB → ATS e2e

**Result:** PASS

## Gates

- ✅ `api_health` ok
- ✅ `frontend_mock` 200
- ✅ `upsert_lead` 0206d00f-48b5-4346-aa96-518608f14f06
- ✅ `G1_fab_three_buttons` three buttons
- ✅ `ra-fab-tailor` http://127.0.0.1:3000/?view=resume&jobId=0206d00f-48b5-4346-aa96-518608f14f06&step=tailor
- ✅ `G2_open_tailor` http://127.0.0.1:3000/?view=resume&jobId=0206d00f-48b5-4346-aa96-518608f14f06&step=tailor
- ✅ `ra-fab-apply` http://127.0.0.1:3000/?view=resume&jobId=0206d00f-48b5-4346-aa96-518608f14f06&step=apply
- ✅ `G3_open_apply` http://127.0.0.1:3000/?view=resume&jobId=0206d00f-48b5-4346-aa96-518608f14f06&step=apply
- ✅ `ra-fab-outreach` http://127.0.0.1:3000/outreach?jobId=0206d00f-48b5-4346-aa96-518608f14f06
- ✅ `G4_open_outreach` http://127.0.0.1:3000/outreach?jobId=0206d00f-48b5-4346-aa96-518608f14f06
- ✅ `ats_fill` {"first": "Jingxuan", "step2": 1, "files": 1, "linkedin": "https://linkedin.com/in/example", "status": "STEP2_VISIBLE"}
- ✅ `paused_before_submit` awaiting_human_review
- ✅ `G5_G6_ats_pause` iframe+dynamic+upload+pause

## Screenshots

- `artifacts/ui/jr-fab-e2e/01-jobright-mock.png`
- `artifacts/ui/jr-fab-e2e/02-fab-visible.png`
- `artifacts/ui/jr-fab-e2e/03-open-tailor.png`
- `artifacts/ui/jr-fab-e2e/04-open-apply.png`
- `artifacts/ui/jr-fab-e2e/05-open-outreach.png`
- `artifacts/ui/jr-fab-e2e/11-ats-shell.png`
- `artifacts/ui/jr-fab-e2e/12-ats-loop-0.png`
- `artifacts/ui/jr-fab-e2e/12-ats-loop-1.png`
- `artifacts/ui/jr-fab-e2e/13-ats-final.png`

## Iterations

- extension_loaded
- fab_missing_inject_fallback
- fab_wired_to_upsert_urls