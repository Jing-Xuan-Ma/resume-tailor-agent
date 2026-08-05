# Agent 3 Report — Apply / ATS fill-pause

**Status: PASS**  
**Gate:** `artifacts/funnel/agent3/report.json`  
**submitted: false** on all suites

## Goal
Sandbox-first auto-fill dry-run for Greenhouse / Lever / Ashby / Workday. Always pause before Submit. Never real Submit.

## Done
- `ats_connectors/sandbox.py` — resolve ATS URL → local fixture (`prefer_sandbox=True`)
- Ashby sandbox fixture + richer Ashby field selectors
- Lever / Workday / Ashby `supports()` recognize fixture paths
- `BrowserSession.fill_and_pause` — chrome fallback, `#msg` submit-leak check, never clicks Submit
- `BrowserSession.submit` (Playwright path) — hard-stopped before Submit
- `apply_flow` auto mode — sandbox fill-pause, screenshots under `artifacts/funnel/agent3/`
- `ApplyModePanel` — shows `browser_fill` status / submitted / field list
- `StartApplyResponse.browser_fill` typing refined in `frontend/lib/api.ts`

## Suites (required 3 + Ashby bonus)

| ATS | Filled | submitted | Status |
|-----|--------|-----------|--------|
| Greenhouse | 5 | false | filled_paused_before_submit |
| Lever | 4 | false | filled_paused_before_submit |
| Workday | 5 | false | filled_paused_before_submit |
| Ashby (bonus) | 4 | false | filled_paused_before_submit |

## Screenshots
- `artifacts/funnel/agent3/01-greenhouse-filled-paused.png`
- `artifacts/funnel/agent3/02-lever-filled-paused.png`
- `artifacts/funnel/agent3/03-workday-filled-paused.png`
- `artifacts/funnel/agent3/04-ashby-filled-paused.png`
- `artifacts/funnel/agent3/05-ui-browser-fill-panel.png`

## Safety
- Fill path never clicks Submit; sandbox `#msg` stays empty (no SUBMITTED leak)
- Playwright `submit()` path also pauses before Submit
- Connector-boundary dry-run mark (automation off) unchanged for existing tests
- Did **not** turn on `ENABLE_AUTO_SUBMIT` in this agent’s scope (config owned by main agent)
- Live boards not hit when sandbox fixture exists for the ATS type

## Gate
```
python artifacts/funnel/agent3/_gate.py
```
33 checks PASS · `passed: true`

READY_FOR_MAIN_AGENT
