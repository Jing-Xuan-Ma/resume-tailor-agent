# Iter-6 Report — Auto-apply Dry Run

**Status:** PASS  
**Date:** 2026-08-03

## Scope

Use profile data; fill ATS form fields; stop before submit; audit log + evidence artifact.

## Evidence

| Check | Result |
|-------|--------|
| `scripts/iter6_auto_apply_dry_run.py` | PASS |
| `pytest tests/test_iter6_auto_apply.py` | 2 passed |
| status | `paused_before_submit` |
| submitted | false |
| submit_button | `NOT_CLICKED` |
| filled | full_name, email, phone, linkedin, resume_upload |
| artifact | `artifacts/ui/iter-6/auto-apply-dry-run.json` |

## Safety

- Auto path never clicks real Submit
- Audit event `apply_auto_paused_before_submit` recorded when audit module available

## Checkpoint

- Tag: `checkpoint/iter-6-pass`
