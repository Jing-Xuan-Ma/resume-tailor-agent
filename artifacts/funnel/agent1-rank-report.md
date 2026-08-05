# Agent 1 — Rank & Discover Report

**Status: PASS**

## Scores (honest, anti-inflation)

- thin/labeling: **1.4** (skill_hit=0.0)
- rich DA: **84.4**
- title-as-query empty resume: **0.0** (must not be flat 35)
- live stuck@35 share: **0.0** · unique rounded: **23**

## Freshness snapshot

- active: **161**
- median age: **14.9h**
- under 72h: **0.64**
- skillful: **0.776**
- preferred sources (remotive/himalayas/jobicy/jobspy): **0.994**
- closed_thin: **0**

## Checks

- PASS: `thin_lt_35` 1.4
- PASS: `rich_gt_60` 84.4
- PASS: `rich_beats_thin` 84.4>1.4
- PASS: `thin_skill_hit_not_one` 0.0
- PASS: `no_flat_35_title_query` 0.0
- PASS: `live_scores_not_all_35` share=0.0
- PASS: `live_score_spread` unique=23
- PASS: `active_gt_0` 161
- PASS: `skillful_share_ge_35` 0.78
- PASS: `preferred_source_ge_40` 0.99
- PASS: `median_age_lt_14d` 14.9h
- PASS: `under72h_gt_0` 0.64
- PASS: `ui_source_column` source=True
- PASS: `ui_posted_age` age=True
- PASS: `ui_job_detail` http://127.0.0.1:3000/jobs/4c49922c-0c87-434b-b570-329124da1bea

## UI artifacts

- `artifacts/funnel/agent1/01-jobs-source-age.png`
- `artifacts/funnel/agent1/02-job-detail.png`

Evidence JSON: `artifacts/funnel/agent1/report.json`

READY_FOR_MAIN_AGENT
