# MAIN AGENT AUTONOMOUS WATCH

status: watching
started: 2026-08-03
mode: unattended continuous
can_message_subagents: false
monitor: disk artifacts only

## Protocol
1. Poll artifacts/funnel/agent{1,2,3,4}-*-report.md and report.json
2. READY_FOR_MAIN_AGENT or passed:true → mark module done
3. Missing/stale >45min or FAIL → main agent takes over that module
4. When 2+ modules ready → start integration E2E
5. Loop: screenshot → score UX → fix → retest
6. Stop only if artifacts/AUTONOMOUS_PAUSE exists

## Subagent ownership (do not steal while active <45min)
- agent1: job_discovery, ranked-jobs-table
- agent2: resume_workspace (not apply_flow), tailor preview
- agent3: ats_connectors, apply_flow, apply-mode-panel
- agent4: cold_outreach, outreach-step-panel
