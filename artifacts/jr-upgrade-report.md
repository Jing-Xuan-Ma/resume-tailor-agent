# JR Upgrade — Final acceptance (JR-1 … JR-6)

**Status: PASS** (scoped Jobright *mechanisms*, not marketplace scale)

| 环节 | Jobright 标准（本计划） | 结果 | 证据 |
|------|-------------------------|------|------|
| 发现 | 本地索引 + 定时/手动写入；discover 默认读库 | PASS | `artifacts/jr-1-report.md`, `jr-1-bench.json` |
| 去重 | ATS id → URL → title+company；过期 soft-close | PASS | `artifacts/jr-2-report.md`, `jr-2-bench.json` |
| 打分 | JD 正文 + 技能命中 + breakdown 0–100 | PASS | `artifacts/jr-3-report.md`, `jr-score-bench.json` |
| 过滤 | work_model / platform / max_age / min_score 服务端生效 | PASS | `artifacts/jr-4-report.md`, `jr-4-bench.json` |
| 体验 | 真实岗 summary 关键词 → tailor session | PASS | `artifacts/jr-5-report.md`, `jr-5-bench.json` |
| 总验收 | 上表全绿；不做内推/真提交/全网爬虫 | PASS | 本文件 |

## How to operate

```powershell
# Populate index (write path)
backend\venv\Scripts\python.exe scripts\jr1_ingest_jobs.py --query "data analyst" --location Remote

# Re-verify batches
backend\venv\Scripts\python.exe scripts\jr1_verify.py
backend\venv\Scripts\python.exe scripts\jr2_verify.py
backend\venv\Scripts\python.exe scripts\jr3_score_bench.py
backend\venv\Scripts\python.exe scripts\jr4_filter_bench.py
backend\venv\Scripts\python.exe scripts\jr5_path_bench.py
```

Discover defaults: `live=false` (read index). Opt-in live fan-out: `"live": true`.

Scheduler: enabled with `JOB_INDEX_INGEST_INTERVAL_MINUTES` (default 10).

## Explicitly not done (by design)

- Vector DB / embedding retrieval (optional JR-3b)
- Insider referral graph
- Real application Submit
- Competing on millions of listings / LinkedIn-scale crawling
