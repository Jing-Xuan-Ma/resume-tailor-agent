# Sprint B Report — Apply dry-run feel

**Status: PASS**  
**Gate:** `artifacts/funnel/sprint-bc/report.json` (`passed: true`)

## Done
- Auto apply returns profile autofill checklist + ATS field map (Greenhouse/Lever/Ashby/generic)
- UI shows both lists; `paused_before_submit` + hard-stop `submit_button`
- `job_id` / `source_url` passed into start-apply; `meta.json` apply_status updated
- Screenshots: `01-apply-panel.png`, `02-checklist.png`

## Pass criteria
| Criterion | Result |
|-----------|--------|
| Dry-run JSON + UI mapped fields | PASS |
| Pause before submit explicit | PASS |

## UX note
- Confirm must succeed (or server-flag confirmed) before Auto; handler re-syncs confirm from API.
- Thin remotive URLs map as `generic` ATS — expected without Greenhouse/Lever host.

## Next
Sprint C (same gate file — also PASS).
