# 流水线可靠性报告（5×3）

**Run:** `artifacts/pipeline_reliability/runs/20260811_084940/`  
**方式:** headed Chromium 模拟人类点击（Jobs → Cart → Refine → 投递 → 查看表单）  
**结果:** 5/5 轮全部门禁通过，0 error；每轮 3/3 到达官方 ATS `ready_to_submit`（Submit 未点击）

## 平均耗时

| 环节 | 平均 | 说明 |
|------|------|------|
| 选职进购物车 | **17s** | Jobs 打开 + 组装 cart |
| 批量 Refine（生成简历） | **7.5 min** | 瓶颈；波动 3.1–12.1 min |
| 投递 Phase2–5 | **68s** | 到官方 Greenhouse 填表暂停 |
| 查看表单 | **27s** | 官网重填并停在 Submit 前 |
| 校验 | **0.2s** | API/截图核对 |

**单轮合计约 9–13 min；5 轮总墙钟约 47 min。**

## 每轮

| 轮次 | Refine | Apply | Open form | ready_to_submit | 错误 |
|------|--------|-------|-----------|-----------------|------|
| 1 | 500s | 63s | 26s | 3/3 | 无 |
| 2 | 424s | 75s | 27s | 3/3 | 无 |
| 3 | 429s | 72s | 27s | 3/3 | 无 |
| 4 | 187s | 63s | 27s | 3/3 | 无 |
| 5 | 723s | 66s | 26s | 3/3 | 无 |

## 迭代中发现并已修

1. **Jobright 常落到 Crunchbase/X** → 拒绝非 ATS 域名；接入公司 ATS 缓存 + Greenhouse/Ashby 标题解析  
2. **投递要已确认 PDF** → apply 前自动 confirm 渲染 `resume.pdf`  
3. **查看表单仅恢复 cookie 表单仍空** → 官网重填后停在 Submit  
4. **检测脚本** → `scripts/pipeline_reliability_soak.py` + 计划 `artifacts/pipeline_reliability/PLAN.md`

## 仍慢 / 局限

- Refine（LLM）占 >80% 时间，是卡顿主因；非网页打不开  
- Intern-list 中可解析官方 ATS 的职位仍偏少（本 run 用 Scale AI / Cloudflare / Postman 等已映射公司循环）  
- 需继续扩充 `data/ats_company_map.json` 才能覆盖更多公司

## 验收结论

整条链路在「有官方 ATS 映射」的职位上：**可靠停在官网 Submit 页前**，无漏开网页、无 Sync-API 报错、无自动 Submit。下一步优化重点是 **Refine 耗时** 与 **ATS 公司覆盖率**。
