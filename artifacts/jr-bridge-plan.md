# Jobright Extension Workbench — Iteration Plan

> Started: 2026-08-04  
> Goal: Chrome/Edge extension as personal workbench on Jobright (Phase 1 first)

## Pass criteria (Phase 1)

1. `POST /api/v1/jobs/index/leads` upserts into `job_listings` with quality gate
2. Extension side panel: detect mock Jobright-like page → Tailor / Apply / Outreach steps
3. Deeplink `/?view=resume&jobId=…&step=…` opens Workspace and scrolls to step
4. Human-path Playwright screenshots under `artifacts/ui/jobright-bridge/`
5. Report: `artifacts/jr-bridge-report.md`

## Phases

- **P1 (this run):** API + extension shell + deeplink + selftest fixtures
- **P2 (later):** iframe embed full workbench in side panel

## Safety

- paused_before_submit only; no auto-send email
