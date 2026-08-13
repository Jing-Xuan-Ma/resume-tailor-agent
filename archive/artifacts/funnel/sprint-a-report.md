# Sprint A Report — Honest rank + funnel spine

**Date:** 2026-08-03  
**Status:** PASS (with known friction)  
**Artifacts:** `artifacts/funnel/sprint-a/`

## Time estimate (reaffirmed)

| Scope | Estimate |
|-------|----------|
| Sprint A–C usable funnel | **2–4 days** |
| + Apply browser depth | **+3–5 days** |
| + HM / cold outreach semi-auto | **+5–10 days** |
| True Jobright parity | **3–6+ weeks** continuous |

Plan: `artifacts/funnel/JOBRIGHT_FULL_FUNNEL_PLAN.md`

## Done this sprint

1. **Score v2** — weights `query 25 + resume 20 + skills 35 + ATS keywords 20`; title-as-query guard; soft title mismatch penalty  
2. **Honest UI labels** — Detail: “ATS keywords” / “Skill coverage” (no fake Semantic); list subtitle explains heuristic  
3. **ApplyModePanel wired** after Tailor preview; visible once a version exists; unlock after Confirm  
4. **meta.json** — `confirmed_at`, `apply_status`, `outreach_status`, `job_id`, `session_id`, `source_url`, `user_id`

## Self-test (human click + screenshot)

| Shot | File | OK |
|------|------|----|
| Jobs list | `01-jobs-list.png` | yes |
| Job detail | `02-job-detail.png` | yes |
| Tailor | `03-tailor.png` | yes |
| Apply panel | `04/05-apply-panel*.png` | yes (`apply_panel_visible=True`) |

**Scores:** unique finals ≈ 61–66 (not flat 35%). Sample in `score-sample.json`.

## UX score: **3.5 / 5**

| Dimension | Score | Note |
|-----------|-------|------|
| Clarity | 4 | Match vs ATS/Skill labels clearer |
| Speed | 3 | Tailor + Word PDF still slow |
| Trust | 4 | No more fake identical 35% |
| Dead-ends | 3 | Confirm gate can block apply unlock; Auto still dry-run |

## Friction → next sprint

1. Thin JDs can still inflate ATS/skill to ~100% (e.g. labeling roles) → tighten ATS term extraction + body-length gate in score  
2. Confirm → Apply path needs one-click when evidence passes  
3. Sprint B: profile autofill checklist + Greenhouse/Lever dry-run field map in UI  

## Next

Start **Sprint B** (apply dry-run feel) unless `artifacts/AUTONOMOUS_PAUSE` exists.
