# Agent 4 Report — Outreach / HM CRM

**Status: PASS**  
**Gate:** `artifacts/funnel/agent4/report.json` (`passed: true`)  
**READY_FOR_MAIN_AGENT**

## Scope
Post-apply semi-auto outreach only: LinkedIn HM search playbook + contact CRM + coffee/cold email drafts. User always sends — no mass mail.

## Done
1. **CRM API** — `GET/POST /api/v1/outreach/contacts` wired to `crm_store.py` (upsert/list: name, role, linkedin, email, coffee_availability).
2. **Draft → CRM** — `POST /draft` with `save_to_crm` upserts contact and stores `crm_contact_id` in metadata; status stays `draft` + `safety: draft_only_user_sends`.
3. **UI** (`outreach-step-panel.tsx`) — Save contact, CRM list + Load, coffee availability, ≥2 draft templates, ≥2 LinkedIn search links; `?forceOutreach=1` for demo/screenshots.
4. **api.ts** — `upsertOutreachContact` / `listOutreachContacts` (+ coffee_availability on draft).
5. **Workspace** — pass company/position from jobLabel when confirm meta missing (mount props only).

## Pass criteria
| Criterion | Result |
|-----------|--------|
| CRM upsert/list contacts | PASS |
| UI save contact + ≥2 draft templates | PASS |
| LinkedIn search links ≥2 | PASS (3) |
| Draft only, no auto mass send | PASS |
| Screenshots under `artifacts/funnel/agent4/` | PASS |
| Report md + json | PASS |

## Screenshots
- `artifacts/funnel/agent4/01-hm-playbook.png`
- `artifacts/funnel/agent4/02-crm-saved.png`
- `artifacts/funnel/agent4/03-drafts.png`

## Runtime data
- CRM files: `data/outreach_crm/{user_id}.json`

## Not touched
job_discovery, ats_connectors, application_engine, apply_flow, apply-mode-panel, scoring/ATS.

## Rollback
Not required — gate passed.
