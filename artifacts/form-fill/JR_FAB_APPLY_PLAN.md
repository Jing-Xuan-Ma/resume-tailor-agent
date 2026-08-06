# Jobright FAB → ATS Apply 迭代计划

目标：模拟真人点击 Jobright 上 **Open Tailor / Open Apply / Open Outreach**，各自打开正确页面；Apply 链路进入 ATS 自动填表，**停在 Submit 前**（`paused_before_submit`）。全程截图 + 失败自修。

## 验收门禁

| ID | 门禁 | 通过标准 |
|----|------|----------|
| G1 | Jobright 职位页可见三按钮 | `data-testid=ra-fab-tailor/apply/outreach` 可见 |
| G2 | Open Tailor | 打开含 `view=resume&step=tailor`（或等价 Tailor UI） |
| G3 | Open Apply | 打开含 `step=apply` 的 Apply workspace |
| G4 | Open Outreach | 打开 `/outreach?jobId=` |
| G5 | ATS auto-fill | 从 Apply 打开的 ATS（或夹具）完成字段填充 |
| G6 | 停在 Submit 前 | 无真实 Submit；stage=`awaiting_human_review` / `pause_for_human` |

## 迭代顺序

1. **Iter-A** 扩展加载 + Mock Jobright FAB 出现并截图  
2. **Iter-B** 真人节奏点击三按钮，断言 URL/UI，截图  
3. **Iter-C** Apply → ATS（本地 Workday iframe 夹具）填表至 pause  
4. **Iter-D** 若真实 jobright.ai 可访问则加一轮；否则 Mock 视为主路径  
5. **Iter-E** 修复失败点直至 G1–G6 全绿，写 `artifacts/ui/jr-fab-e2e/report.md`

## 约束

- 禁止真实 Submit（data-safety）  
- 优先 `extensions/jobright-bridge`（官方扩展目录）  
- 后端 `:8000` + 前端 `:3000` 必须在线  
