---
name: resume-tailor
description: >-
  按 RESUME_CONSTITUTION 调用本仓库 Web API，针对一份 JD 改简历并导出已确认 PDF。
  Use when the user asks to 改简历/tailor resume/生成投递简历/confirm PDF，
  或投递前需要一份证据充分的简历文件。
---

# 改简历（调 Web API，不重写引擎）

本 skill **只编排 HTTP**。LLM 改写、证据门、OOXML 注入都在 FastAPI 里。默认 API：`http://127.0.0.1:8000`。

先读仓库根目录 `RESUME_CONSTITUTION.md`（或 `GET /api/v1/resume-workspace/constitution`）。禁止编造经历、数字、职称。

## 输入

- `user_id`（Web 登录用户；缺则问）
- JD 文本，或 intern-list `job_id`（`job-search`：`GET /api/v1/intern-list/jobs/{id}` 取 `jd_text`）
- 可选：已有 `session_id` / `version_id`

## 流程

```
- [ ] 1. GET /api/v1/profile/{user_id}/library     确认档案存在
- [ ] 2. GET /api/v1/resume-workspace/constitution  对齐宪法
- [ ] 3. POST /api/v1/resume-workspace/jd-session   { user_id, jd_text, job_id? }
- [ ] 4. POST .../jd-session/{session_id}/analyze
- [ ] 5. POST .../jd-session/{session_id}/rewrite   { user_id, instruction? }
- [ ] 6. 若证据门拦住：按 issues 改档案或缩小改写，禁止捏造后重试
- [ ] 7. POST .../resume-version/{version_id}/confirm?user_id=
- [ ] 8. 把 confirm 返回的 final_path / files 里的 PDF 绝对路径交给 jobright-apply
```

购物车批量改简历（多岗）走现成接口，不必逐步 analyze：

```
POST /api/v1/shopping-cart/batch-generate
  { user_id, intern_job_ids, wait: true }

POST /api/v1/shopping-cart/{cart_id}/items/{item_id}/confirm
  { user_id }

→ item.resume_pdf_path 即投递用 PDF
```

## 输出（必须回报）

- `version_id` 或 cart `item_id`
- **PDF 绝对路径**（`final_path` 目录下的 `resume.pdf`，或 `resume_pdf_path`）
- company / position

没有绝对路径就不要进入 `jobright-apply`。

## 红线

- 不把简历正文在对话里整篇重写一遍再塞回 API。
- 不跳过 confirm。未确认版本不能用于投递。
- Web 没起来：先 `./scripts/start.sh`。
