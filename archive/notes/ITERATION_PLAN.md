# Resume Agent — Autonomous Iteration Plan

> Cursor agents: follow `.cursor/rules/autonomous-execution.mdc`.  
> Do not ask the user questions. Use defaults below. Keep iterating.

## Global goals (priority order)

1. Resume quality: fixed template, content-only edits, evidence-backed, one page
2. Clear JobRight-like UI: ranked jobs → detail (score + keyword colors) → tailor → confirm
3. Job discovery: broad, fast, low token (optimize continuously)
4. Auto-apply: fill with user profile, **pause before submit**
5. Cold email: **FROZEN** — do not expand

## Defaults (no asking)

| Topic | Default |
|-------|---------|
| Category chips | Static visual labels OK; real filtering via score/source/location/work model |
| Master resume | `d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx` |
| Final resume folder | `data/final_resumes/{Company}_{Position}/` (slugify) |
| Version history | Keep last 3 old versions + current confirmed |
| Target roles | Data Analyst / Analytics first |
| Auto-apply | `paused_before_submit` only |
| Commits | Create git tags `checkpoint/iter-N-pass` when pass; commit if working tree needs a checkpoint |

## Protocol each iteration

```
branch from last checkpoint
→ implement ONLY this iter scope
→ test (API / unit / Playwright screenshots under artifacts/ui/iter-N/)
→ write artifacts/iter-N-report.md (pass/fail + evidence)
→ PASS: tag checkpoint/iter-N-pass, start next iter
→ FAIL: fix up to 2 rounds; still fail → reset --hard to previous checkpoint, log FAILURE, continue with unblocked work or next viable iter
```

## Iterations

### Iter-0 — Baseline freeze
- Boot frontend + backend; smoke critical APIs
- Tag `checkpoint/baseline` if missing
- **Pass**: app starts; smoke OK

### Iter-1 — Ranked job list UI
- Table of ranked jobs; filters that already have data; click row → detail route
- Playwright: list → open first job
- **Pass**: path works + screenshots saved

### Iter-2 — Job detail: score + keyword colors
- Match score; keyword pills (matched vs not); CTA to customize resume
- **Pass**: keywords from backend; colors visible in screenshot

### Iter-3 — Resume tailor loop (core)
- Fixed DOCX template; content-only; diff highlight; confirm gate; last 3 versions; save under `data/final_resumes/...`
- **Pass**: format intact, evidence guard OK, versions OK, file on disk

### Iter-4 — Resume quality gate
- Enforce one-page, verb/impact bullets, JD-based show/hide of experiences, skills subset reorder
- Run ≥3 sample JDs regression if available under `data/` or tests
- **Pass**: checks green; no fabrication

### Iter-5 — Apply mode split UI
- After confirm: Manual vs Auto-apply
- Auto path ends at `paused_before_submit`
- **Pass**: both entries clear; screenshot proves no submit

### Iter-6 — Auto-apply dry run
- Use profile data; fill ATS form; stop before submit; audit log + screenshot
- **Pass**: fields filled; hard stop before submit

### Iter-7 — Discovery optimization
- Dedupe, cache, fewer LLM calls, faster list
- **Pass**: document latency/token before vs after in report; no UI regression

### Iter-8 — Full-path polish
- E2E Playwright main path; empty/error states; update `AGENT_CONTEXT.md`
- **Pass**: E2E green; docs match checkpoints

## Out of scope forever (until user changes rules)

- Sending cold emails / LinkedIn messages
- Real Submit on job applications
- Deleting files outside this repository
---

## How to start

**Two different things:**

1. **少点 Run 批准** → Cursor Settings → Agents → Approvals & Execution → 选 **Run Everything**（已尽量用 `~/.cursor/permissions.json` + settings 辅助）
2. **长任务 ITERATION_PLAN** → 在一个 Agent 里发 `go` / `继续`（平时普通任务不要发 go）

| Control | Action |
|---------|--------|
| Start long iteration | say `go` / `继续` / `start` |
| Pause auto-continue | create `artifacts/AUTONOMOUS_PAUSE` or press Stop |
| Finished | `AUTONOMOUS_DONE` (auto after Iter-8) |

Note: Cursor must be open with an Agent session; hooks cannot start work if the app is closed or offline.
