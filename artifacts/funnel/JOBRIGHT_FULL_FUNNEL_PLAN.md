# Jobright Full-Funnel Iteration Plan

> Owner: agent (靖萱 / Data Analyst track)  
> Started: 2026-08-03  
> User override: cold outreach is **IN SCOPE** (supersedes old `ITERATION_PLAN.md` “frozen forever” for email/LinkedIn).  
> Real job-board **Submit** stays gated (`paused_before_submit` default) until dry-run self-tests are green.

## Time estimate (honest)

| Scope | Calendar (focused agent days) | What “done” means |
|-------|-------------------------------|-------------------|
| **Sprint A–C (usable funnel)** | **2–4 days** | Rank honest → tailor → confirm → apply dry-run wired → outreach draft UI; human-click screenshots pass |
| **Sprint D–E (apply depth)** | **+3–5 days** | Greenhouse/Lever/Ashby fill reliably; Workday partial; audit + pause-before-submit proven |
| **Sprint F–G (hiring manager)** | **+5–10 days** | Contact discovery playbook + LinkedIn-assisted find (semi-auto) + coffee/cold email templates + CRM-like store |
| **True Jobright parity** | **3–6+ weeks** | Multi-source freshness, semantic ATS, full auto-submit opt-in, scale outreach — continuous, not one shot |

**This session:** write plan → start Sprint A → self-test → report → loop.  
Pause file: `artifacts/AUTONOMOUS_PAUSE`. Sprint reports: `artifacts/funnel/sprint-*-report.md`.

---

## Current baseline (audit)

| Stage | Maturity | Notes |
|-------|----------|--------|
| Ingest | Partial | Multi-provider + quality gate; LinkedIn/Indeed fragile; Adzuna teaser risk |
| Rank / score | Partial | Fixed flat-35% bug; still heuristic; `atsScore`/`semanticScore` cosmetic |
| Tailor + store | Strong | Constitution, master DOCX, versions, `data/final_resumes/{Company}_{Position}/` |
| Apply | Partial | Engine + ATS connectors exist; UI unwired; browser off by default |
| Outreach | Stub | Draft API only; no HM find, no UI, no send |

---

## Product logic (Jobright-aligned)

```
Discover → Rank (resume+JD+ATS keywords) → Tailor (1 job : 1 folder)
  → Confirm → Apply (auto-fill, pause before submit)
  → Find owner (HM / recruiter / team lead)
  → Coffee chat / cold email → Track reply
```

### Ranking formula (target, iterate)

Current:
`100 × (0.35·query + 0.25·resume_token + 0.40·skill_hit)`

Target v2 (Sprint A):
`100 × (0.25·query + 0.20·resume_token + 0.35·skill_hit + 0.20·ats_keyword)`  
+ soft penalties: missing must-have skills, title mismatch, stale posting  
+ hard filters (optional): location / work model / years if parseable  
Label UI honestly: **Match** = heuristic; add **ATS keyword coverage** separately — do not fake “semantic” until embeddings exist.

### Resume storage (per job)

```
data/final_resumes/{Company}_{Position}/
  resume.docx | resume.pdf | meta.json   # confirmed
data/templates/{version_id}/
  resume.docx | resume.pdf               # drafts
SQLite: resume_versions, applications, outreach_messages
```

`meta.json` must link: `job_id`, `source_url`, `match_score`, `confirmed_at`, `apply_status`, `outreach_status`.

### Apply policy

- Manual: open original URL + show filled field checklist  
- Auto: Playwright fill known ATS → **always pause before submit** until user opts in  
- Never invent profile fields; use Profile Library only  

### Outreach policy

- Discover contacts: title heuristics (Hiring Manager, Recruiter, Head of Data, Team Lead) + company  
- Prefer public sources / user-pasted LinkedIn URL first; no credential stuffing  
- Draft coffee-chat + cold email; user sends (or gated send later)  
- Rate limits + audit log  

---

## Sprint backlog

### Sprint A — Honest rank + funnel spine (Day 1)
**Do**
1. Score v2: ATS keyword coverage from JD required skills vs resume; honest labels in UI  
2. Wire `ApplyModePanel` after Confirm; call `startApply` / plan APIs  
3. Per-job `meta.json` enrichment on confirm  
4. Human path screenshots: Jobs → Detail → Tailor → Confirm → Apply panel  

**Pass**
- Scores not flat; breakdown visible  
- Apply panel reachable without console errors  
- Screenshots under `artifacts/funnel/sprint-a/` + report  

### Sprint B — Apply dry-run feel (Day 1–2)
**Do**
1. Profile autofill checklist from library  
2. Greenhouse/Lever/Ashby: dry-run field map from live URL when possible  
3. UX: one scroll path, clear Manual vs Auto, no dead buttons  

**Pass**
- Dry-run JSON + UI show mapped fields; pause-before-submit explicit  

### Sprint C — Outreach UI + drafts (Day 2–3)
**Do**
1. Step after Apply: “Find people / Cold outreach”  
2. Contact slots (role, name, LinkedIn URL, email if known)  
3. Templates: coffee chat, post-apply thank-you, recruiter ping  
4. Persist drafts in `outreach_messages`  

**Pass**
- User can create ≥2 draft types from a confirmed job; screenshot + copy quality review  

### Sprint D — Browser fill (gated) (Day 3–5)
**Do**
1. Enable browser automation in dev with safety flag  
2. One happy-path ATS fill (sandbox or known Greenhouse)  
3. Screenshot filled form; stop before submit  

**Pass**
- Video/screenshot evidence; audit log row  

### Sprint E — Ingest freshness (parallel)
**Do**
1. Prefer Remotive/Himalayas/Jobicy + JobSpy 3.12 worker  
2. Close thin/ad listings; surface source + age in UI  

**Pass**
- Median age / skillful share report better than baseline  

### Sprint F — Hiring-manager playbook (semi-auto)
**Do**
1. Suggest search queries for LinkedIn (“Company” + “Data Analytics Manager”)  
2. Optional: open search URLs; user confirms person → agent drafts message  
3. Coffee-chat scheduler fields (availability note only)  

**Pass**
- Guided flow feels human; no silent mass messaging  

### Sprint G — Polish loop
E2E Playwright, empty states, latency, copy, remove duplicate tailor stacks from UX.

---

## Self-test protocol (every sprint)

1. Boot FE + BE  
2. Act as 靖萱: click like a human (no API-only “pass”)  
3. Screenshot critical screens → `artifacts/funnel/sprint-X/`  
4. Score UX 1–5: clarity / speed / trust / dead-ends  
5. Fix top friction → re-shot until ≥4/5 or document blocker  
6. Write `artifacts/funnel/sprint-X-report.md`  

---

## Immediate next actions

1. ✅ This plan  
2. → Sprint A implementation + screenshots  
3. → Sprint A report; continue B without waiting unless `AUTONOMOUS_PAUSE`
