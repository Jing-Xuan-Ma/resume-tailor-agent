# Macro roadmap implementation report

## Phase 1 — Auto-apply (PASS)
- Confirm-submit API + Apply/Tailor UI (`confirm-submit-btn`)
- Sandbox dry-run Greenhouse / Lever / Ashby → `artifacts/ui/apply-pass/`
- Tests: `test_iter6_auto_apply.py` (pause + confirm)

## Phase 2 — Jobright plugin main entry
- Extension v0.1.5 FAB: Tailor / Apply / Outreach deep links
- Reinject + demote processed cards
- `/jobs` demoted to Archive inventory banner

## Phase 3 — Outreach
- mailto «Open in email» + Mark sent CRM
- `mail_sender.py` gated by `ENABLE_GMAIL_SEND=false`

## Phase 4 — Batch queue
- `/api/v1/queue/*` enqueue · process · per-job confirm · skip
- UI: `/queue` + `ApplicationQueuePanel`
- No one-click submit-all

## Phase 5 — Commercial scaffolding
- `STORAGE_BACKEND` (sqlite default) + `db_postgres.py`
- Docker `api` service + product boundaries at `/api/v1/commercial/boundaries`
- Multi-tenant / billing / Gmail send off by default
