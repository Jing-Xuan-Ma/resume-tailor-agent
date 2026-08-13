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
| `jobright-original-apply` | 已跑通的 Jobright → 雇主原帖 → 填表 → Submit（须 `PACING_ENABLED=0`） |
| `screen-locate` | 截图 + 自然语言 → 点击坐标（A11y 不够时） |
| `captcha-solve` | 图形验证码方案（不直接点浏览器） |
| `debug-dev-env` | Chrome/MCP 起停与日志 |

## 本地简历存储（统一约定）

所有简历相关文件只落在仓库根目录的 **`data/`**（已 gitignore）。Agent / 脚本 / Web **不得**写到 Desktop、Downloads、随意临时目录，或覆盖用户系统别处的母版。

```
data/
├── templates/
│   ├── master/
│   │   └── Jingxuan_Resume_Data_Analyst.docx   # 视觉母版工作副本（只读；禁止覆盖/删除）
│   └── {version_id}/                           # 中间导出（未 Confirm；勿当投递文件）
│       └── resume.{docx,pdf}
├── final_resumes/
│   └── {Company}_{Position}/                   # Confirm 后定稿（投递主入口）
│       ├── resume.pdf                          # ★ 投递用稳定别名（优先用这个）
│       ├── resume.docx
│       ├── meta.json                           # company / position / version_id / confirmed_at
│       └── {Company}_{Position}.{pdf,docx,txt,json}
└── shopping_cart/
    └── {item_id}/…/resume.pdf                  # 购物车 Confirm 后的投递 PDF
```

### 命名与路径规则

| 规则 | 约定 |
|------|------|
| 根目录 | 永远是 `<repo>/data/…`；对话里回报 **绝对路径** |
| 文件夹名 | `{Company}_{Position}`，filesystem-safe slug：去 `\ / : * ? " < > \|`，空白→`_`，过长截断 |
| 投递文件 | 优先 `…/resume.pdf`；同目录 `resume.docx` 备用。不要用手改文件名当正式路径 |
| 定稿时机 | **仅 Confirm 之后** 写入 `final_resumes/` 或购物车 `resume.pdf`；未确认版本不可投递 |
| 母版 | 只读 `data/templates/master/Jingxuan_Resume_Data_Analyst.docx`；版式锁定，只做内容注入 |
| 事实来源 | 经历/数字来自 Profile library（Master Inventory），不是随便改 PDF 正文 |

### Agent 操作规范

1. `resume-tailor` Confirm 后，把返回的 `final_path` 下的 **`resume.pdf` 绝对路径** 交给 `jobright-apply`。
2. 购物车批量：`batch-generate` → item `confirm` → 用 item 的 `resume_pdf_path`。
3. 需要人工核对时打开 `data/final_resumes/`；**不要**在对话里整篇重写简历再另存别处。
4. 清理：可删过期的 `final_resumes/{Company}_{Position}/` 或购物车 item 目录；**永不删除** `templates/master/`、`.env`、`data/app.db`、Chrome profile。

## 核心流程

```
- [ ] 1. Web 跑着；档案在 GET /api/v1/profile/{user_id}/library
- [ ] 2. 选岗：job-search → GET /api/v1/intern-list/jobs（默认每页 20）
- [ ] 3. resume-tailor → Confirm → data/final_resumes/…/resume.pdf（绝对路径）
- [ ] 4. jobright-apply 填表（默认停在 Submit 前）；要走已跑通的提交闭环用 jobright-original-apply
- [ ] 5. 停在 Submit 前则截图交给用户；original-apply 则等到 Application Submitted
```

购物车批量：`POST /api/v1/shopping-cart/batch-generate` → confirm → `resume_pdf_path`。Web **不再**「开始投递」。

## 关键 API

- 档案：`GET|PUT /api/v1/profile/{user_id}/library`
- 宪法：`GET /api/v1/resume-workspace/constitution`（源文件 `RESUME_CONSTITUTION.md`）
- 改简历：`POST /api/v1/resume-workspace/jd-session` → analyze → rewrite → confirm
- Intern-list 查询：`GET /api/v1/intern-list/jobs?page=1&page_size=20`（`q`/`slug` 可选）；详情：`GET /api/v1/intern-list/jobs/{job_id}`；抓取 CLI：`python -m app.modules.intern_list_scraper`（cwd=`backend/`，config=`config/intern-list.toml`）
- 定稿落盘：见上文「本地简历存储」

## 红线

1. **不编造**经历、数字、职称。改简历必须过证据门。
2. **不点 Submit / Submit Application / 提交申请。**
3. **不删用户数据**：`.env`、档案、Chrome profile `~/.ghost-driver/chrome-profile`、`data/app.db`、`data/templates/master/`。
4. 投递资料只用 library + 用户当场给的值，不用测试假数据当真投。
5. 点控件用 MCP 坐标 / A11y，不用 CSS selector（`set_input_files` 除外）。
6. 简历文件只出入 `data/` 约定目录；未 Confirm 不投递。

## 仓库地图

```
backend/app/modules/intern_list_scraper/   抓取清洗
backend/app/modules/profile/               档案（Master Inventory）
backend/app/modules/resume_workspace/      改简历引擎 + final_store
data/templates/master/                     母版 DOCX（只读）
data/final_resumes/                        Confirm 定稿
data/shopping_cart/                        购物车确认 PDF
mcp/happy-ghost-driver/                    浏览器 MCP
.agents/skills/                            对话技能
archive/                                   旧迭代产物（不用）
```
