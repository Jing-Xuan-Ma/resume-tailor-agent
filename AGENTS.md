# Resume Tailor Agent

Web 管数据与档案；**改简历和投递在 Agent 对话里用 skill + MCP 完成**。Cursor / Claude Code 读本文件即可开工。

## 这是什么

本地求职 copilot：从 intern-list 抓岗 → 维护个人档案 → 按宪法改简历出 PDF → 用真实 Chrome 填 ATS 表 → **停在 Submit 前交给用户**。

| 层 | 做什么 |
|----|--------|
| Web (`backend/` + `frontend/`) | 抓取清洗 intern-list、档案 CRUD、改简历 API、购物车确认 PDF |
| Skills (`.agents/skills/`) | 编排流程；不重写引擎 |
| MCP (`mcp/happy-ghost-driver/`) | 真实 Chrome 的手：导航、截图、拟人点击/输入 |

## 启动

```bash
./scripts/start.sh    # Web :3000/:8000 + Chrome CDP :9222
./scripts/stop.sh     # 停 Web 和投递用 Chrome（不动日常 Chrome）
```

MCP 由 Cursor/CC 按 `.cursor/mcp.json` / `.mcp.json` 拉起。首次 MCP：`cd mcp/happy-ghost-driver && npm install && npm run build`。

默认 API：`http://127.0.0.1:8000`。排错用 skill `debug-dev-env`。

## Skills（`.agents/skills/`）

| Skill | 何时用 |
|-------|--------|
| `job-search` | 查 intern-list 职位，分页默认 20 条，取 `job_id` / `jd_text` |
| `resume-tailor` | 按 JD 改简历、confirm、拿到 PDF 绝对路径 |
| `jobright-apply` | Jobright → Original Job Post → 填表；**禁止点 Submit** |
| `screen-locate` | 截图 + 自然语言 → 点击坐标（A11y 不够时） |
| `captcha-solve` | 图形验证码方案（不直接点浏览器） |
| `debug-dev-env` | Chrome/MCP 起停与日志 |

## 核心流程

```
- [ ] 1. Web 跑着；档案在 GET /api/v1/profile/{user_id}/library
- [ ] 2. 选岗：job-search → GET /api/v1/intern-list/jobs（默认每页 20）
- [ ] 3. resume-tailor → 已确认 PDF 绝对路径
- [ ] 4. jobright-apply + ghost-driver-mcp 填表
- [ ] 5. 停在 Submit 前，截图汇报；用户自己点提交
```

购物车批量：`POST /api/v1/shopping-cart/batch-generate` → confirm → `resume_pdf_path`。Web **不再**「开始投递」。

## 关键 API

- 档案：`GET|PUT /api/v1/profile/{user_id}/library`
- 宪法：`GET /api/v1/resume-workspace/constitution`（源文件 `RESUME_CONSTITUTION.md`）
- 改简历：`POST /api/v1/resume-workspace/jd-session` → analyze → rewrite → confirm
- Intern-list 查询：`GET /api/v1/intern-list/jobs?page=1&page_size=20`（`q`/`slug` 可选）；详情：`GET /api/v1/intern-list/jobs/{job_id}`；抓取 CLI：`python -m app.modules.intern_list_scraper`（cwd=`backend/`，config=`config/intern-list.toml`）
- 确认 PDF 落盘：`data/final_resumes/` 或购物车 item 目录下的 `resume.pdf`

## 红线

1. **不编造**经历、数字、职称。改简历必须过证据门。
2. **不点 Submit / Submit Application / 提交申请。**
3. **不删用户数据**：`.env`、档案、Chrome profile `~/.ghost-driver/chrome-profile`、`data/app.db`。
4. 投递资料只用 library + 用户当场给的值，不用测试假数据当真投。
5. 点控件用 MCP 坐标 / A11y，不用 CSS selector（`set_input_files` 除外）。

## 仓库地图

```
backend/app/modules/intern_list_scraper/   抓取清洗
backend/app/modules/profile/               档案
backend/app/modules/resume_workspace/      改简历引擎
mcp/happy-ghost-driver/                    浏览器 MCP
.agents/skills/                            对话技能
archive/                                   旧迭代产物（不用）
```
