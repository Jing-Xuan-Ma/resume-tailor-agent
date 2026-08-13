# Cold Outreach Pipeline — Step 6 Redesign Report

**Date:** 2026-08-05  
**Status:** PASS (backend + schema self-test)

## Goal

Replace the flat “search + template + form” screen with a 4-step pipeline:

1. Search candidates (+ JD URL ingest)  
2. Rank & select (rule-based fit scores)  
3. Enrich contact (email lookup / LinkedIn / manual)  
4. Draft templates (filtered by channel)

Decision-making stays with the user; product automates search hints, scoring, and verification presentation.

## What shipped

### Backend
| Piece | Path |
|-------|------|
| Candidate scorer (title 35% / team 25% / activity 15% / seniority 15% / size 10%) | `backend/app/modules/cold_outreach/candidate_scorer.py` |
| Email finder (Hunter optional + format inference; user-click only) | `backend/app/modules/cold_outreach/email_finder.py` |
| JD URL ingest (Greenhouse / Lever / LinkedIn Jobs) | `backend/app/modules/cold_outreach/jd_ingest.py` |
| APIs | `POST /rank-candidates`, `/find-email`, `/jd-ingest` + `linkedin_connect` draft template |
| Config | `HUNTER_API_KEY` (optional) |
| SQLite migrate | add `unsubscribe_token` / delivery columns on existing DBs |

### Frontend
| Piece | Path |
|-------|------|
| 4-step left vertical stepper UI | `frontend/components/outreach-step-panel.tsx` |
| API clients | `frontend/lib/api.ts` |
| Wider page shell | `frontend/app/outreach/page.tsx` |

### Safety (unchanged)
- Never auto-send email / LinkedIn  
- Email lookup is single-person, rate-limited  
- No SMTP blast / batch enumeration  
- Expectancy copy: “70%+ no public email is normal → LinkedIn”

## Self-test

```text
pytest tests/test_outreach_pipeline.py tests/test_basic_api.py::test_cold_outreach_draft_and_mark_sent
→ 9 passed
```

Covered:
- HM scores above generic TA  
- Rank sorts descending  
- Domain inference + Greenhouse/LinkedIn URL parse  
- Format-inference email candidates without Hunter  
- API rank / find-email / linkedin_connect draft / JD ingest  
- Legacy draft + mark-sent still works after schema migrate  

## How to try in UI

1. Open `/outreach?forceOutreach=1&company=Acme&position=Data%20Analyst`  
2. Step 1: open LinkedIn presets; optionally paste a JD URL  
3. Step 2: paste 2–3 people (name + title), Score & sort, select 1–3  
4. Step 3: 查邮箱 / LinkedIn / 手动填  
5. Step 4: templates auto-filter by channel → Draft → Copy / mailto / Mark sent  

Optional: set `HUNTER_API_KEY` in `.env` for live Hunter enrichment (free tier).

## Follow-ups (P2+)
- Second email source (RocketReach) after measuring Hunter hit rate  
- Persist ranked candidate batches per job_id  
- Playwright UI screenshot gate for the stepper  
