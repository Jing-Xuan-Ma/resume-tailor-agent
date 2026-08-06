# Jobright LIVE e2e (round 2)

**Result:** PARTIAL — 三按钮链路通过；真实职位详情被登录墙拦住

## 结论

匿名访问 `jobright.ai` 会进入 `onboarding-v3/signup`，**拿不到真实职位详情页 / 外部 ATS 链接**。  
在当前页注入 FAB 后，**Open Tailor / Open Apply / Open Outreach 仍能打开本机 Resume Agent 对应页面**（经 leads upsert）。

## Gates

见同目录 `report.json`。关键项：

- `live_job_open` FAIL（signup 墙）
- `G1–G4` FAB 三按钮 PASS
- `ats_opened` skipped（无外部 apply URL）

## 要完成「真职位 → 真 ATS → pause before submit」

请任选其一后再跑 `scripts/jr_live_jobright_e2e.py`：

1. Chrome 用**已登录 Jobright** 的用户目录跑（persistent profile）
2. 或你先在浏览器登录 Jobright，打开某个职位详情，把 URL 设为环境变量 `JR_JOB_URL=...`

截图目录：`artifacts/ui/jr-live-e2e/`
