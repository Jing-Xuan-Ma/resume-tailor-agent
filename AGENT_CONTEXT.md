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
| **前端** | Next.js 14 (App Router) + Tailwind CSS + shadcn/ui |
| **后端API** | FastAPI (Python 3.11+) |
| **Agent编排** | LangGraph (状态机、工具调用、人机循环) |
| **LLM** | Claude 3.5 Sonnet (简历定制主模型) + GPT-4o (通用) |
| **Embedding** | text-embedding-3-large |
| **向量DB** | Chroma (本地) / Pineapple (生产) |
| **关系DB** | PostgreSQL |
| **缓存/消息** | Redis |
| **PDF生成** | Playwright print-to-PDF / WeasyPrint |
| **文档处理** | python-docx, pdfplumber |
| **部署** | Vercel(前端) + Railway/Render/Fly.io(后端) |

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
├── chat/                    ✅ Phase 1 — 对话接口
├── resume_tailor/           ✅ Phase 1 — 核心：简历定制（当前主战场）
│   ├── nodes/
│   │   ├── parse_jd.py      # JD解析（Structured Output）
│   │   ├── match_skills.py  # 经历匹配（向量相似度）
│   │   ├── tailor_resume.py # LLM定制（Claude 3.5）
│   │   ├── evidence_guard.py# 证据校验（独立LLM调用）
│   │   └── render_pdf.py    # PDF渲染
│   └── prompts/
│       ├── tailor_system.txt
│       └── evidence_check.txt
├── memory/                  ✅ Phase 1 — 记忆系统
│   ├── long_term.py         # Chroma向量操作
│   ├── conversation.py      # 对话历史管理
│   └── user_profile.py      # 动态偏好画像
├── job_discovery/           ⏳ Phase 2 — 职位发现（接口预留）
├── auto_apply/              ⏳ Phase 3 — 自动投递（接口预留，依赖JobApplyAgent的ATS fill引擎）
├── cold_outreach/           ⏳ Phase 4 — 冷邮件外联（接口预留，依赖Gmail API + LinkedIn）
└── growth_advisor/          ⏳ Phase 5 — 成长建议（接口预留）
```

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
| LinkedIn封号 | 抓取作为可选数据源，主推Adzuna/RemoteOK/RSS API |
| 平台ToS违规（自动投递） | 默认人工确认模式；全自动为可选高级功能 |
| 简历同质化 | 基于真实独特经历定制 + LLM Temperature > 0 |
| 用户数据隐私 | 本地Chroma优先；生产环境自托管；简历数据加密存储 |

---

## 10. 当前开发进度（每次更新此字段）

**最后更新**: 2026-07-21
**当前阶段**: Phase 1 — 简历定制引擎MVP（LLM 已激活）
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

**待完成**:
- [ ] 前端简历上传 UI（支持粘贴/上传简历文件）
- [ ] 解析 LLM 返回的结构化 JSON（目前当作纯文本展示）
- [x] ~~PDF 渲染节点~~ → 改为文本导出（已支持 Copy as Text）
- [ ] 用户认证和数据库集成

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
