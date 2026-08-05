# Live Greenhouse — one-job manual acceptance

**Prerequisite:** `artifacts/funnel/auto-apply-v2/report.md` shows fixture gate **PASS**.

## Flags

| Env / setting | Default | Live value |
|---------------|---------|------------|
| `ENABLE_BROWSER_FILL_PAUSE` | `true` | `true` |
| `ALLOW_LIVE_BROWSER_FILL` | `false` | `true` (only for this check) |
| `ENABLE_BROWSER_AUTOMATION` | `false` | leave false unless debugging |

Set in `.env` (project-local) or process env, then restart the API.

## Steps

1. Confirm a tailored resume version (Apply workspace → Confirm).
2. Open a **single** real Greenhouse job URL (boards.greenhouse.io/…).
3. Run **Auto apply (safe)** — agent opens the live form (or JD → Apply), DOM-scans, maps (LLM with rules fallback), fills high-confidence fields, uploads resume if `resume_path` exists.
4. Review Apply page tiers: green / amber / red.
5. Check **「我已检查」**, then **打开官网亲手 Submit**.
6. **You** click Submit on the employer site. The agent never does.

## Pass criteria

- `submitted` / browser payload remains `false` from the agent
- Audit log shows `apply_auto_paused_before_submit` (or equivalent)
- Unknown screening questions left empty (red / leave_empty)
- Resume file attached when a real DOCX/PDF path exists under `final_path`

## After the check

Set `ALLOW_LIVE_BROWSER_FILL=false` again so daily runs stay on fixtures.

## Status this PR

- Fixture gate: **PASS** (see `report.md`)
- Live Greenhouse: **not_run** in automation (optional manual step above)
