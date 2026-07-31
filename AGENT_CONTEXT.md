# AGENT_CONTEXT — Resume Tailor Agent 项目上下文

> **这是本项目的"记忆胶囊"。**
> 如果你（开发者）在一个全新的AI对话窗口中继续本项目，**请先将此文件的前80行粘贴给AI**，AI将立即恢复全部上下文，无需重新解释。

---

## 1. 项目定位（一句话）

**"一个以真实经历为底线、以AI定制为引擎、以人工确认为安全阀的智能求职副驾驶。它不会替你撒谎，但会帮你说服。"**

- **核心功能**：针对用户真实经历 + 目标JD，生成不编造、高匹配、ATS友好的定制简历。
- **差异化**：强调 "Evidence Guard（证据链）" —— 任何定制内容必须能在用户原始经历中找到出处，LLM不得 hallucinate。
- **模式**：核心简历定制为必选；自动投递、冷邮件外联、成长建议等后续为可选插件。

---

## 2. 目标用户

美国/国际市场求职者，尤其是：
- 技术岗（Software Engineer, Data Scientist, PM等）
- 需要大量定制化投递的求职者
- 非技术背景用户（因此UI必须极度友好，对话式交互）

---

## 3. 技术栈总览

| 层级 | 技术 |
|------|------|
| **前端** | Next.js 14 (App Router) + Tailwind CSS |
| **后端API** | FastAPI (Python 3.11+) |
| **Agent编排** | LangGraph (状态机、工具调用、人机循环) |
| **LLM** | 统一 `LLM_PROVIDER`：OpenAI-compatible / Gemini / 智谱 GLM |
| **Embedding** | 本地 hash embedding fallback + 可选 OpenAI embeddings |
| **向量DB** | Chroma (本地持久化) |
| **关系DB** | SQLite（本地）/ PostgreSQL（`DATABASE_URL=postgresql://…` + Alembic） |
| **缓存/限流** | Redis（可选）+ 内存 fallback |
| **职位发现** | JobSpy 抓取 + Remotive/RemoteOK/Himalayas/Jobicy/Adzuna API |
| **ATS 深挖** | Greenhouse + Lever（核心字段）；Workday/iCIMS 为薄层 fallback |
| **文档处理** | python-docx, pdfplumber |
| **浏览器自动化** | 可选 Playwright（默认关闭） |

---

## 4. 架构核心决策（Architecture Decisions）

### ADR-001: 模块化事件驱动架构
- 模块间不直接调用，通过 `EventBus` 发布/订阅事件通信。
- 好处：后续加入 `auto_apply`, `cold_outreach`, `growth_advisor` 模块时，现有代码零改动。

### ADR-002: 三层记忆系统
- **事实记忆** → PostgreSQL（用户基本信息、结构化简历）
- **语义记忆** → Vector Store（经历Embedding、对话语义）
- **对话记忆** → Vector Store + 自动摘要（超过50轮自动压缩）

### ADR-003: 简历定制核心 — "Rewrite-Only, No Fabrication"
- Agent只能**改写（rephrase / restructure / quantify）**用户已有经历。
- 禁止编造项目、技能、职位、时间线。
- 通过独立的 `Evidence Guard` 节点校验每处修改的 "evidence_from" 字段。

### ADR-004: 投递安全模式
- 默认 `manual_review` 模式：Agent填表 → 用户预览 → 用户点击 Submit。
- 可选 `auto_submit` 模式：需用户全局开启，并有每日上限。

### ADR-005: 从单点切入，插件化扩展
- Phase 1 只做 `resume_tailor` 模块。
- 其他模块（`job_discovery`, `auto_apply`, `cold_outreach`, `growth_advisor`）预留接口目录，但内部暂为占位符。

---

## 5. 模块清单及开发状态

```
modules/
├── chat/                    ✅ 对话接口
├── resume_tailor/           ✅ 简历定制 + Evidence Guard + 导出
├── resume_workspace/        ✅ Phase 6 — JD面板 / 版本 / 关键词缺口
├── memory/                  ✅ Chroma 经历记忆
├── job_discovery/           ✅ 多 provider 发现 + auto-discover + 三阶段打分 + Job List
│   └── providers/           JobSpy, Remotive, RemoteOK, Himalayas, Jobicy, Adzuna
├── application_engine/      ✅ 申请计划 + 手动确认 + auto-submit 边界 + Playwright
├── ats_connectors/          ✅ GH+Lever 深挖；Ashby/Workday/iCIMS/Generic 薄层
├── cold_outreach/           ✅ 草稿 + mark-sent + 发信骨架
├── growth_advisor/          ✅ 技能差距 + 4周路线图
├── auth/ / profile/         ✅ 注册登录 + 画像反馈
└── safety/                  ✅ 审计 / 日限额 / 人工确认策略
```

### 职位爬取 / 发现源（不是 ATS 投递站）

| Provider | 类型 | 目标站点 / API |
|----------|------|----------------|
| jobspy | 抓取（可选依赖 python-jobspy） | Indeed, LinkedIn, ZipRecruiter, Google Jobs |
| remotive | API | remotive.com/api/remote-jobs |
| remoteok | API | remoteok.com/api |
| himalayas | API | himalayas.app/jobs/api |
| jobicy | API | jobicy.com/api/v2/remote-jobs |
| adzuna | API（需 key） | api.adzuna.com |
| local_phase2 | 合成 fallback | 无外网时保证演示可用 |

### ATS 投递目标（申请表单，不是爬虫源）

Greenhouse（深）、Lever（深）、Ashby、Workday（fallback）、iCIMS（fallback）、Generic。

---

## 6. 核心数据流（简历定制场景）

```
用户输入（聊天/粘贴JD）
    │
    ▼
[Chat Node] —— 理解意图（是上传简历？粘贴JD？要求定制？）
    │
    ▼
[Retrieve Memory] —— 检索用户经历、历史对话、偏好
    │
    ▼
[Parse JD] —— GPT-4o提取结构化JD（required_skills, years_exp, keywords）
    │
    ▼
[Match Experiences] —— 向量相似度搜索，找出最相关的3-5段经历
    │
    ▼
[Tailor Resume] —— Claude 3.5生成定制简历（JSON结构化输出）
    │
    ▼
[Evidence Guard] —— 独立校验：每条声明是否有原始出处？
    │
    ├── ❌ 未通过 → 回到Tailor节点或向用户提问澄清
    │
    └── ✅ 通过 → [Render PDF] → 返回给用户
```

---

## 7. 关键Prompt摘要（不可丢失）

### System Prompt 核心约束（tailor_system.txt）
- "You are an expert resume consultant."
- "You can ONLY rephrase, restructure, and quantify existing experiences."
- "You are FORBIDDEN from inventing projects, skills, job titles, or timelines."
- "Each bullet point must start with a strong action verb and include metrics when possible."
- "Output must include an 'evidence_from' field for every claim, mapping to the user's original experience ID."

### Evidence Guard Prompt 核心约束（evidence_check.txt）
- "You are an independent fact-checker."
- "Review the tailored resume claim by claim."
- "For each claim, verify it is directly supported by the user's original experience text."
- "Flag any claim that adds new information not present in the original."

---

## 8. 数据库Schema概要

### PostgreSQL 表
- `users` — 用户基础信息
- `resumes` — 用户原始简历（JSONB）
- `experiences` — 工作经历（1:N关联resumes）
- `tailored_resumes` — 定制后的简历（关联resumes + jobs）
- `jobs` — 职位信息（JD原文 + 结构化字段）
- `conversations` — 对话历史（最近50轮）

### Chroma Collections
- `user_experiences` — 经历Embedding（按bullet切分）
- `conversation_memory` — 对话语义记忆
- `user_preferences` — 用户偏好示例

---

## 9. 风险与规避（已确认策略）

| 风险 | 规避策略 |
|------|---------|
| LLM编造经历 | Evidence Guard + 用户确认环节 + 绝不使用"生成式"经历 |
| LinkedIn封号 | JobSpy 中 LinkedIn 为可选抓取源；主路径用 Remotive/RemoteOK/Himalayas/Jobicy/Adzuna API |
| 平台ToS违规（自动投递） | 默认人工确认模式；全自动为可选高级功能 |
| 简历同质化 | 基于真实独特经历定制 + LLM Temperature > 0 |
| 用户数据隐私 | 本地Chroma优先；生产环境自托管；简历数据加密存储 |

---

## 10. 当前开发进度（每次更新此字段）

**最后更新**: 2026-07-31
**当前阶段**: Phase 1-7 可用；金线验收脚本已固化（简历上传 → 发现职位 → 定制 → 申请包 → 手动确认提交）
**已完成**:
- [x] 项目目录结构搭建
- [x] AGENT_CONTEXT.md + README.md
- [x] docker-compose.yml (Postgres + Chroma + Redis)
- [x] FastAPI骨架 (main.py, config.py)
- [x] 核心Pydantic模型 (models.py)
- [x] LangGraph Agent定义 (agent.py)
- [x] 记忆系统封装 (long_term.py)
- [x] Prompt模板 (tailor_system.txt, evidence_check.txt)
- [x] Next.js前端骨架
- [x] 运行后端服务并测试健康检查（/health 正常返回）
- [x] 实现ExperienceEmbedder（经历向量化存入 Chroma）
- [x] 后端兼容无 Docker 环境（本地持久化 Chroma + 容错）
- [x] 前端 ChatPanel 组件（拆分组件，连接后端 API）
- [x] 前端 ResumeWorkspace 组件（展示定制结果预览）
- [x] 端到端测试：/health ✅ /chat/send ✅ /tailor ✅ /parse-jd ✅
- [x] 项目迁移到 D:\resume-agent（C 盘空间不足）
- [x] LLM 从 Claude → GPT-5.5 迁移（自定义 provider: router.c.yiling.top）
- [x] API Key 配置完成，GPT-5.5 真实调用测试通过
- [x] Tailor 节点真实 LLM 输出验证（拒绝编造，遵守 Evidence Guard）
- [x] 实现 ExperienceEmbedder 的 API 端点（`/upload-resume`）
- [x] 带真实经历的端到端测试通过（上传简历 → 存入 Chroma → GPT-5.5 定制 → Evidence Guard 校验）
- [x] Chroma 本地记忆完整迁移到 `D:\resume-agent\data\chroma`，并移除 C 盘重复副本
- [x] 后端 Chroma 路径改为项目相对路径，避免继续写入 `C:\Users\HP\resume-agent\data\chroma`

**最新已完成**:
- [x] 前端简历上传 UI（Chat/Upload 切换模式，支持粘贴纯文本简历）
- [x] 解析 LLM 返回的结构化 JSON → 展示结构化 experiences、projects、education
- [x] ~~PDF 渲染节点~~ → 改为文本导出（已支持 Copy as Text）
- [x] 用户认证 API（register/login/me）和本地 SQLite 持久化层
- [x] 用户画像、反馈学习、对话归档、事件审计、限流
- [x] 持久化定制简历、草稿、职位、收藏、cover letter、application runs、audit logs
- [x] Phase 2 职位发现：JobSpy provider + 本地 fallback + 职位评分/收藏
- [x] Phase 2.2：job → tailored resume → cover letter → application plan 一键准备申请包
- [x] Phase 3 自动投递框架：application_engine、ats_connectors、safety 模块
- [x] ATS 识别/connector：Greenhouse、Lever、Ashby、Workday、iCIMS、Generic fallback
- [x] 手动确认提交 API：`/api/v1/applications/{id}/confirm-manual-submit`
- [x] 自动提交 API：`/api/v1/applications/{id}/auto-submit`
- [x] 可选 Playwright 浏览器执行器：`ENABLE_BROWSER_AUTOMATION=True` 时尝试真实填表/提交
- [x] Greenhouse/Workday first_name/last_name 拆分、文件 artifacts 生成、resume/cover letter 上传字段支持
- [x] 后端测试 13 passed，前端 build 通过
- [x] 前端职位发现/申请管理 UI：Jobs workspace 支持职位发现、JD 导入、职位列表、收藏、申请包生成、手动确认提交、自动提交触发
- [x] 前端登录/注册入口：AuthGate 接入 register/login/me，localStorage 持久化 token，主工作区使用真实 user_id
- [x] 原始简历持久化表/API：上传简历写入 SQLite resumes 表，返回 durable resume_id，前端通过 latest resume 恢复并用于定制/申请包
- [x] 后端测试环境恢复：backend/venv 安装 dev 依赖，完整 pytest 通过
- [x] Phase 4 冷外联 MVP：`/api/v1/outreach/draft` 生成草稿，列表查询，用户手动发送后 `mark-sent`
- [x] Phase 5 成长建议 MVP：`/api/v1/growth/analyze` 基于最新简历和目标职位输出 gap/recommendations/roadmap
- [x] 前端 Jobs workspace 接入 Outreach/Growth 操作面板
- [x] 后端测试 16 passed，前端 build 通过

**待完成**:
- [x] 安装 Playwright 浏览器依赖并做 Greenhouse 真实页面级实测（2026-07-29 完成）
  - 测试 URL: SpaceX + AppDirect 真实 Greenhouse 职位页
  - 结果: 核心字段 (first_name/last_name/email/phone/resume/cover_letter) 全部通过 `#id` 选择器匹配 ✅
  - LinkedIn 通过 label "LinkedIn Profile" 匹配 ✅
  - Website 字段在测试页面上不存在（部分 GH 页面无此字段）
  - work_authorization 在部分页面不存在（EEO 问题是独立的 gender/disability 等字段）
  - 表单 ID 实为 `application-form`（连字符），但选择器通过 `#first_name` 等 ID 定位，不影响现有功能
  - 建议优化: LinkedIn/Website 等自定义字段可考虑 `label[for^=question_]` 模式匹配，当前 label 回退已够用
- [x] JobSpy 超时真正生效（shutdown wait=False）+ 回归测试（2026-07-31）
- [x] 可演示金线验收：upload → auto-discover → tailor → prepare → manual confirm
  - `pytest tests/test_golden_path.py`
  - `python -m scripts.run_golden_path`
  - 顺带修 auto-discover 从简历 experiences/summary 推导 query；JD 离线 fallback 用首行作 title
- [x] Greenhouse + Lever 核心字段深挖（2026-07-31）
  - Greenhouse: first/last/email/phone/resume/cover/linkedin + apply/submit selectors
  - Lever: name/email/phone/org/urls[LinkedIn|GitHub|Portfolio] + cover textarea + template-btn-submit
  - QuestionAnswerer 补 phone/org/github/twitter；cover letter 文本/文件双路径
  - Workday / iCIMS 明确为薄层 fallback（不继续铺开）
  - `pytest tests/test_ats_core_fields.py`
- [ ] Ashby 真机 selector 验证（可选，优先级低于 GH/Lever）
- [ ] 生产级冷外联发送：OAuth/Gmail API、退订/频控/合规、逐封显式确认
- [ ] 生产部署：确认 PostgreSQL + Alembic migrations 在目标环境跑通

---

## 11. 如何在新窗口恢复上下文（给AI的指令）

如果你读到这行，说明你在继续 **Resume Tailor Agent** 项目。

**请基于以上所有信息，假设你已经完全理解项目，直接回答用户的具体问题。**

如果用户要求"继续开发"，请从 **第10节"当前开发进度"** 中标记为 `[ ]` 的第一项开始实施。

**项目代码位置**: `D:\resume-agent\`

**快速启动命令**（无 Docker 环境）:
```bash
# 终端 1 — 后端
cd D:\resume-agent\backend
.\venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
# 访问 http://localhost:8000/health 验证

# 终端 2 — 前端
cd D:\resume-agent\frontend
npm run dev
# 访问 http://localhost:3000

# 项目无须 Docker 即可运行（Chroma 使用本地持久化模式）
# 填入 .env 中的 API Key 后可激活真实 LLM 调用
```
