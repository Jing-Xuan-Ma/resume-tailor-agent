# Resume Agent — Default Agent Mission

This file is loaded automatically. **Do not ask the user to paste a prompt.**

## Ordinary work vs long iteration

- **Default:** answer the user’s actual request. Do **not** start `ITERATION_PLAN.md`.
- **Long autonomous iteration:** only when the user says `go` / `继续` / `start`.

Saving time on “Run / Always allow” prompts is a **Cursor Run Mode** setting, not this mission loop.

## Mission (only after go)

Execute `ITERATION_PLAN.md` from the latest `checkpoint/iter-*-pass` (or `checkpoint/baseline` / `main`).

Keep going until **Iter-8 passes**, or `artifacts/AUTONOMOUS_PAUSE` exists, or `artifacts/AUTONOMOUS_DONE` exists, or the user presses Stop.

## Behavior (only after go)

- Follow `.cursor/rules/autonomous-execution.mdc` and `.cursor/rules/data-safety.mdc`.
- Do **not** ask clarifying questions. Use defaults in `ITERATION_PLAN.md`.
- Never end with "Should I…?" — continue the next unfinished iteration item.
- Write progress to `artifacts/iter-N-report.md` and screenshots under `artifacts/ui/iter-N/`.
- Cold email sending is frozen. Auto-apply stops at `paused_before_submit`.
- Master resume is read-only: `d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx`.
- Resume generation MUST obey `RESUME_CONSTITUTION.md`.

## Control files

| File | Meaning |
|------|---------|
| `artifacts/AUTONOMOUS_RUN` | Auto-continue armed (created when you say go) |
| `artifacts/AUTONOMOUS_PAUSE` | Stop auto-continue |
| `artifacts/AUTONOMOUS_DONE` | Planned iters finished |
