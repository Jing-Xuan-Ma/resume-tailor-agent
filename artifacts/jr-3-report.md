# JR-3 Report — Explainable scoring

**Status: PASS**

## Goal

Match score uses **JD body + skill coverage**, not title-only tokens; expose breakdown.

## What shipped

- `score_job_detailed()` in `scorer.py` with weights: query 35% / resume 25% / skills 40%
- Skill lexicon for DA track; `matched_skills` / `missing_skills`
- Discover + index search persist breakdown on `parsed`

## Pass criteria

| Check | Result |
|-------|--------|
| Breakdown present | PASS |
| Matched/missing skills present | PASS |
| High-fit DA/BI > low-fit nurse/PM | PASS |
| Same title, SQL body beats unrelated body | PASS |

Evidence: `artifacts/jr-score-bench.json`

Note: embedding / vector retrieval deferred (JR-3b optional); lexical skill coverage is enough for current catalog size.
