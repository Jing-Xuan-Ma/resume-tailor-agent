# Pipeline reliability — 5×3 human-path soak

## Goal
Simulate human UI clicks (headed Chromium) for **5 rounds × 3 jobs**:
Jobs (Intern-list) → Shopping Cart → 批量 Refine → 投递 → 查看表单 → official ATS Submit page (never click Submit).

## Stages timed
1. `select_jobs` — pick 3 checkboxes + open Shopping Cart  
2. `refine` — 批量 Refine until items ready/failed  
3. `apply` — 投递已勾选 through Phase 2–5  
4. `open_form` — 查看表单 → official ATS re-fill pause  
5. `verify_submit_ui` — screenshot + DOM readback / Submit visible, not clicked  

## Acceptance (stop when all pass across 5 rounds)
| Gate | Pass if |
|------|---------|
| A1 UI opens | `/jobs?tab=internlist` and cart page load; no blank/crash |
| A2 Select | Exactly 3 jobs selected; cart URL has 3 `internJobIds` |
| A3 Refine | ≥2/3 items `ok` with resume content within timeout |
| A4 Apply | No Sync-API-in-asyncio; each item ends `ready_to_submit` **or** typed failure (`no_official_ats`, account, etc.) |
| A5 Official ATS | `ready_to_submit` items have greenhouse/workday/lever/… URL (not crunchbase/x/jobright) |
| A6 Open form | For each `ready_to_submit`: headed open + Submit visible + ≥1 identity field filled OR documented ATS block |
| A7 Timing | Every stage has ms recorded in report JSON |

## Iteration loop
1. Run harness round N → write `round_N.json` + screenshots  
2. Classify errors → patch code  
3. Re-run failed stages / next round  
4. Stop only when A1–A7 hold for all 5 rounds **or** remaining failures are external ATS walls documented as `blocked_external`

## Outputs
- `artifacts/pipeline_reliability/runs/<ts>/report.md`  
- `artifacts/pipeline_reliability/runs/<ts>/report.json`  
- per-round screenshots under `rounds/rN/`
