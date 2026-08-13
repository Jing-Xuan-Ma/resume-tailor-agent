# Agent2 · Tailor & Store — Report

**Status: PASS**  
**READY_FOR_MAIN_AGENT**

## Scope

Locked to Tailor / Confirm / Word PDF preview / final archive. No ATS fill, no cold email.

## Deliverables

| Item | Result |
|------|--------|
| OOXML → Word PDF preview (no `##` / `**` in text) | PASS — ~321KB Word PDF, 1 page |
| Confirm → `data/final_resumes/{Company}_{Position}/` | PASS — `Agent2_Gate_Co_Data_Analyst/` |
| Files: docx + pdf + meta.json | PASS |
| meta: `job_id`, `confirmed_at`, `apply_status`, `outreach_status` | PASS |
| Screenshots `artifacts/funnel/agent2/` | PASS |
| Unit tests `test_iter3_resume_workspace.py` | PASS (2) |

## Sample archive

```
data/final_resumes/Agent2_Gate_Co_Data_Analyst/
  Agent2_Gate_Co_Data_Analyst.docx
  Agent2_Gate_Co_Data_Analyst.pdf
  Agent2_Gate_Co_Data_Analyst.json
  Agent2_Gate_Co_Data_Analyst.txt
  meta.json
```

meta excerpt:

- `job_id`: `agent2_gate_job_da_001`
- `confirmed_at`: ISO UTC
- `apply_status`: `not_started`
- `outreach_status`: `not_started`
- `preview_engine`: `ooxml_word_pdf`

## Code changes (allowed paths only)

- `final_store.py` — job listing company/title resolve; require docx+pdf on confirm; meta contract keys
- `service.py` — `_ensure_master_docx` / `_ensure_word_pdf`; confirm blocks only hard evidence issues (not JD wording overlap); Word PDF preferred
- `yiling_experience.py` — JD variant `original_text` aligned to approved inventory wording
- `resume-workspace.tsx` — Confirm banner shows docx/pdf/meta path
- tests + gate scripts under `artifacts/funnel/agent2/`

## Screenshots

- `01-preview-page.png` — rendered Word PDF page (no Markdown)
- `02-word-pdf-preview.png` — master PDF iframe
- `03-tailor-workspace.png` — tailor UI
- `04-after-confirm.png` — post-Confirm

## Gate

See `artifacts/funnel/agent2/report.json` (`passed: true`).

## Out of scope (not done)

ATS connectors, apply_flow, cold outreach panels.
