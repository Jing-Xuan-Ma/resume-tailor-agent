# Auto Apply v2 gate report

**Result:** PASS · fixture **5/5** · UI human-click **5/5**

## Fixture gate

`backend/venv/Scripts/python.exe scripts/auto_apply_v2_selftest.py`

Greenhouse + Lever: scan → map → fill → `submitted=false`, unknown left empty, resume upload OK.

## UI human-click gate

Evidence: [`ui-gate/`](./ui-gate/) (`report.json` PASS · 5.0/5)

- Confirm → Auto → green / amber / red「即将提交的信息清单」
- 「我已检查」先锁后开「打开官网亲手 Submit」
- Browser: `filled_paused_before_submit` · agent `submitted=false` · sandbox
- Audit: `submitted_by_user_confirm`

### Fixes from this self-acceptance

1. Playwright Sync API inside FastAPI asyncio → 500 `Failed to fetch` — `asyncio.to_thread` for scan + fill
2. Browser-off path still emits confidence `fill_plan` for review UI
3. Error state no longer shows empty review steppers as success
4. UI gate seeds demo-owned version + `finalPath` for resume path

## Live Greenhouse

**Status:** `not_run` — see [`LIVE_GREENHOUSE.md`](./LIVE_GREENHOUSE.md)

## API

`POST /api/v1/resume-workspace/ats/map-fields`
