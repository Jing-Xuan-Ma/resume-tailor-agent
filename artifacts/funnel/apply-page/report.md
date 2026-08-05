# Apply workspace — iteration report

**Status: PASS** (`artifacts/funnel/apply-page/report.json`)  
**Date:** 2026-08-04  
**UX self-score: 4.2 / 5**

## What shipped

1. **Confirm is findable**
   - Apply workspace page: big **Confirm this resume** CTA when unlocked versions need it
   - Tailor Step 5 panel: **Confirm this resume → unlock Apply** (no more hunting the header only)
   - Manual/Auto stay **locked** until confirmed (clear amber hint)

2. **Apply is a separate page**
   - Route: `/apply?versionId=…&jobId=…&company=…&position=…`
   - Tailor Step 5: **Open Apply workspace →**
   - Deeplink `?step=apply` opens the Apply tab (same pattern as Outreach)

3. **Manual / Auto**
   - Manual: opens official posting when URL exists + download DOCX/PDF
   - Auto: profile + ATS checklist, **paused_before_submit**, never Submit
   - Review steps with **Previous / Next**: Profile → ATS → Resume → Pause

## Screenshots

| # | File | What |
|---|------|------|
| 01 | `01-apply-workspace.png` | Dedicated Apply page |
| 02 | `02-confirmed.png` | Confirmed unlocks Manual/Auto |
| 03 | `03-manual.png` | Manual path |
| 04 | `04-auto-review.png` | Auto + review checklist |
| 05 | `05-review-pause.png` | Pause step / NOT_CLICKED |
| 06 | `06-tailor-apply-panel.png` | Step 5 on Tailor |
| 07 | `07-need-confirm.png` | Confirm CTA when locked |

## UX scorecard

| Dimension | Score | Note |
|-----------|-------|------|
| Clarity | 4.5 | Confirm gate obvious; safety copy visible |
| Speed | 4 | Page loads fast; auto dry-run quick |
| Trust | 4.5 | paused_before_submit + NOT_CLICKED explicit |
| Dead-ends | 3.5 | Without live posting URL, Manual can’t open Greenhouse; browser fill often sandbox/skipped |

## Remaining (honest)

- Live Greenhouse multi-page fill + **resume file upload** still needs `ENABLE_BROWSER_FILL_PAUSE` + `ALLOW_LIVE_BROWSER_FILL` and stronger Greenhouse attach selectors
- Empty Tailor (no job) still shows Step 5 as `waiting_version` — expected
- Profile fields come from library / defaults — fill Profile if any look wrong

## How to use (靖萱)

1. Tailor a job → header **Confirm** *or* Step 5 **Confirm this resume**
2. Click **Open Apply workspace →**
3. Choose Manual (official site) or Auto (review checklist, you submit)
4. On Auto: flip Profile / ATS / Resume / Pause, then open the official form yourself

Gate: `artifacts/funnel/apply-page/_gate.py` → all checks PASS.
