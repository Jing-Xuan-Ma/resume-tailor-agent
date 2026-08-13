# Iter-5 Report — Apply Mode Split UI

**Status:** PASS  
**Date:** 2026-08-03

## Scope

After resume confirm: Manual vs Auto-apply; auto ends at `paused_before_submit`.

## Implemented

- Backend `apply_flow.py` + `POST .../start-apply` + `GET .../apply/{id}`
- Frontend `ApplyModePanel` on confirmed versions
- Auto path always `submitted=false`, `paused_before_submit=true`
- Smoke: `scripts/iter5_apply_mode_test.py`

## Evidence

| Check | Result |
|-------|--------|
| manual status | `ready_for_manual_apply` |
| auto status | `paused_before_submit` |
| auto submitted | false |
| frontend build | success |

## Checkpoint

- Tag: `checkpoint/iter-5-pass`
