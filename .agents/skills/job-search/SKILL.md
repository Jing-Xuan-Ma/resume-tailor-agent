---
name: job-search
description: >-
  查询 intern-list 职位库，分页返回（默认每页 20 条），并可取单岗 JD。
  Use when the user asks to 查岗位/搜职位/list jobs/ intern-list 选岗，
  或改简历前需要 job_id / jd_text。
---

# 职位查询（调 Web API）

本 skill **只编排 HTTP**。默认 API：`http://127.0.0.1:8000`。数据来自已抓取的 intern-list，不现场爬网。

## 列表

```
GET /api/v1/intern-list/jobs?q=&slug=&page=1&page_size=20
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `page` | `1` | 从 1 起 |
| `page_size` | **20** | 1–100 |
| `q` | 空 | 匹配 title / company / location |
| `slug` | 空 | 类别，可用别名：`da` `swe` `aiml` `pm` `af` `ba` |

响应：`{ page, page_size, total, total_pages, items[] }`。`items` 已按 `job_id` 去重。

流程：

```
- [ ] 1. 用户给关键词或类别；缺则先不带 q 拉第 1 页
- [ ] 2. GET .../jobs?page=1&page_size=20（可加 q / slug）
- [ ] 3. 用表格回报：job_id / title / company / location / work_model
- [ ] 4. 用户要下一页：page += 1，直到 page > total_pages
```

## 详情（改简历用）

```
GET /api/v1/intern-list/jobs/{job_id}
```

取 `jd_text`（或 `job_summary`）交给 `resume-tailor`。`detail_url` 是 Jobright 页，投递走 `jobright-apply`。

## 输出（必须回报）

- `total` / `page` / `total_pages`
- 本页岗位：`job_id`、公司、职位、地点
- 选中一岗时：`job_id` + `jd_text` 是否已取到

## 红线

- 不把整页 `items` 在对话里逐条展开成长文；先表后问选哪条。
- 库空：告诉用户先跑抓取 `python -m app.modules.intern_list_scraper`（cwd=`backend/`）。
- Web 没起来：先 `./scripts/start.sh`。
