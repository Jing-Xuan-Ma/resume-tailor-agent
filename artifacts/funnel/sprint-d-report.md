# Sprint D Report — Browser fill (gated)

**Status: PASS**  
**Gate:** `artifacts/funnel/sprint-d/report.json`

## Done
- `BrowserSession.fill_and_pause()` — Playwright fill, screenshot, **never Submit**
- Flag `ENABLE_BROWSER_FILL_PAUSE` (default false; gated)
- Sandbox fixture `fixture_ats.html` (Greenhouse-style fields)
- Wired into auto `start_apply` when flag/automation enabled; `browser_fill` on response
- Audit event `sprint_d_browser_fill_pause`

## Evidence
- Screenshot: `artifacts/funnel/sprint-d/01-filled-paused.png`
- 5/5 fields filled; `submitted: false`; status `filled_paused_before_submit`

## Pass criteria
| Criterion | Result |
|-----------|--------|
| Happy-path fill (sandbox) | PASS |
| Screenshot filled form | PASS |
| Stop before submit | PASS |
| Audit log | PASS |

## Safety
- Live ATS fill remains off unless `ENABLE_BROWSER_FILL_PAUSE` or `ENABLE_BROWSER_AUTOMATION`
- Submit path still blocked by policy / fill_and_pause never clicks Submit

## Next
Sprint E — ingest freshness (parallel track).
