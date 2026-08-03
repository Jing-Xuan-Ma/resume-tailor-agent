# Resume Agent — Default Agent Mission

This file is loaded automatically. **Do not ask the user to paste a prompt.**

## Mission

Execute `ITERATION_PLAN.md` autonomously from the latest `checkpoint/iter-*-pass` (or `checkpoint/baseline` / `main`).

Keep going until **Iter-8 passes**, or a hard safety stop, or `artifacts/AUTONOMOUS_PAUSE` exists, or `artifacts/AUTONOMOUS_DONE` exists.

## Behavior

- Follow `.cursor/rules/autonomous-execution.mdc` and `.cursor/rules/data-safety.mdc`.
- Do **not** ask clarifying questions. Use defaults in `ITERATION_PLAN.md`.
- Never end with "Should I…?" — continue the next unfinished iteration item.
- Write progress to `artifacts/iter-N-report.md` and screenshots under `artifacts/ui/iter-N/`.
- Cold email sending is frozen. Auto-apply stops at `paused_before_submit`.
- Master resume is read-only: `d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx`.
- Resume generation MUST obey `RESUME_CONSTITUTION.md` (highest policy for tailor/export).

## Control files

| File | Meaning |
|------|---------|
| `artifacts/AUTONOMOUS_RUN` | Auto-continue enabled (default present) |
| `artifacts/AUTONOMOUS_PAUSE` | Stop auto-continue immediately |
| `artifacts/AUTONOMOUS_DONE` | All planned iters finished; stop auto-continue |

If the user only says "go" / "继续" / "start", treat that as: run the mission above.
