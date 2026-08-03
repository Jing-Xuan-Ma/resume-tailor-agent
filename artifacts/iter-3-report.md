# Iter-3 Report — Resume Tailor Loop

**Status:** PASS  
**Date:** 2026-08-03

## Scope

Fixed template content-only edits; diff highlight; confirm gate; last 3 old versions (+ current); save to `data/final_resumes/{Company}_{Position}/`; evidence guard enforced.

## Implemented

- Master DOCX bootstrap → `data/templates/master/` + slot replacement on rewrite
- Content-only rewrite retaining `evidence_from` / `original_text`
- Real `EvidenceGuardNode.verify()` wired into `ResumeWorkspaceService.rewrite()`
- Confirm blocked with HTTP 409 when evidence/format gate fails
- UI disables Confirm when `requires_fix` / evidence fails (`version-tabs`)
- Structured diff (`diff.py`) + `ResumeDiff` panel
- Version cap = 4 (current + 3 previous)
- Confirm → `data/final_resumes/{Company}_{Position}/` (txt/json/meta/+docx/pdf)
- Export gated on confirmed versions
- Stop hook: skip Ask/Edit; abort auto-writes `AUTONOMOUS_PAUSE` (Stop = pause)

## Evidence

| Check | Result |
|-------|--------|
| `pytest tests/test_iter3_resume_workspace.py` | 2 passed |
| rewrite returns content_delta + evidence_check | yes |
| evidence_from on bullets | yes |
| versions after 5 rewrites | ≤4 |
| confirm when guard passes → final_path on disk | yes |
| confirm when guard fails | 409 `blocked_by_evidence_guard` |

## Checkpoint

- Tag: `checkpoint/iter-3-pass`
