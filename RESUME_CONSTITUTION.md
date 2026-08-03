# Resume Constitution（简历宪法）v1

> 本文件是简历生成/改写的最高规则。  
> 与本文件冲突时，以本文件为准（高于临时 prompt、对话偏好、模型自由发挥）。  
> 主投方向默认：**Data Analyst / Analytics**；保险/风险关键词为次级加权。

---

## 0. 绝对原则（不可违反）

1. **不编造**：禁止发明公司、职位、时间、学位、工具、项目、指标、成果、证书。
2. **证据链**：每条 bullet 必须能追溯到 Master Inventory（主经历库）或用户书面确认的事实。
3. **只改内容，不改版式**：字体、字号、边距、标题样式、栏位、section 顺序、联系方式布局均锁定。
4. **一页硬约束**：投递版必须单页。放不下就删减/隐藏，禁止靠缩边距、缩字号“硬塞”。
5. **诚实缺口**：没有的技能不写；可用相邻经历表达迁移能力，但不得声称直接经验。
6. **用户确认后才定稿**：未确认前不得写入 `data/final_resumes/` 定稿目录。

---

## 1. 母版与文件边界

| 角色 | 路径 | 权限 |
|------|------|------|
| 视觉母版（Master Template） | `d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx` | **只读**；禁止覆盖/删除 |
| 参考 PDF | `d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.pdf` | 只读 |
| 仓库内工作副本 | `backend/` / `data/` 下由系统复制的模板 | 可写 |
| 主经历库 | 结构化 JSON（Master Inventory） | 可追加事实；不等于每次投递全文 |
| 投递投影版 | 按 JD 裁剪后的一页简历 | 可写 |
| 定稿目录 | `data/final_resumes/{Company}_{Position}/` | 仅用户确认后写入 |
| 历史版本 | 同一任务保留最近 **3** 个 old version + 当前稿 | 自动轮转 |

命名规则：`Company`、`Position` 做 filesystem-safe slug（去非法字符、空格转 `_`、过长截断）。

---

## 2. 固定版式（Format Lock）

### 2.1 结构顺序（不可重排）

```
[Name 居中加粗]
[Phone | Email | LinkedIn | Portfolio]   ← 单行，用 | 分隔
[Summary]                               ← 无小标题，紧贴联系方式，≤3 行

EDUCATION
PROFESSIONAL EXPERIENCE
PROJECTS
COMPETITIONS                            ← 可整段省略（投递版）
SKILLS & CERTIFICATIONS                 ← 单行关键词，禁止 bullet
```

空 section 可省略；**禁止**新增 section，**禁止**调换顺序。

### 2.2 条目标题格式

- Education：`学校(加粗左)` …… `日期(右)`；下一行 `学位/专业` …… `地点(右)`；可选 `• Coursework: A | B | C`
- Experience：`Title | Company` …… `Location | Dates`
- Project：`Name | Tools` …… `Independent Project`（或给定 context）
- Competition：`Name | Role` …… `Location | Date`

### 2.3 版式禁令

- 禁止：多栏、表格排主内容、文本框、图标栏、页眉页脚放关键信息、花哨符号 bullet
- 导出：优先 DOCX（由母版 run 级替换生成）；PDF 必须为文字型，非截图

### 2.4 格式保持实现契约

1. LLM **只输出结构化 JSON 字段**（summary、bullets、skills 等），禁止直接“重写整份 Word”。
2. 导出时用 **母版 run/段落槽位替换**（或复制已有样式块再填字），保留 bold/size/段落样式。
3. 导出后自检：页数=1、section 标题集合合法、无新增 section、Evidence Guard 通过。

---

## 3. 写作标准（Content Quality）

### 3.1 Bullet 结构

优先 **Situation → Action → Result**（与母版一致）：

- 可用开头：`Faced with…` / `Given…` / `To…`，随后接强动词动作
- 强动词示例：Built, Designed, Engineered, Led, Delivered, Applied, Conducted, Optimized
- 有证据才写量化结果；**无数字不得编百分比/时长/金额**
- 每条尽量 1–2 行；成就优先于职责罗列

### 3.2 默认条数与弹性

- Master Inventory 中，Experience/Project 条目默认维护 **3** 条 bullets
- **投递投影版**允许：
  - 整段经历 **上架 / 下架**
  - 单段从 3 条压到 2 条（为保一页或降噪）
  - Competitions 整段隐藏
- 未经用户明确要求，不得把一段扩到 >3 条

### 3.3 Summary

- 无标题；2–3 句；视觉上 ≤3 行
- 点明身份 + 与 JD 最相关的 3–5 个关键词（必须已真实具备）
- 按岗位簇调整侧重点（见 §5）

### 3.4 Skills

- 单行，逗号/分号分隔；**不是** bullet 列表
- 投递版做 **子集 + 重排**，不要永远全量粘贴（防一页溢出与噪音）
- 技能分层见 §5；只写能在经历/项目中举证或用户确认会的项

---

## 4. 主经历库 vs 投递投影（Show / Hide）

### 4.1 Master Inventory（真相源）

新经历先写入主库，字段最低要求：

- title, organization, location, date_range
- bullets_raw（≥2 条事实：做了什么、用了什么工具）
- metrics（可选；没有则禁止量化）
- tags（如：etl, tableau, credit-risk, reporting, performance）

### 4.2 投递投影选择算法（默认）

1. 从 JD 提取关键词与权重  
2. 对每段 Experience/Project 打相关分  
3. 空间预算（Data Analyst 默认）：
   - Education：保留（两段学历可都留；Coursework 可按 JD 微调）
   - Experience：上架 **1–2** 段最高分实习/工作
   - Projects：上架 **1–2** 个最高分项目
   - Competitions：分数低或空间不够则整段隐藏
4. Skills：按 §5 重排，控制约 **8–15** 个高相关硬技能靠前  
5. 若仍超一页：先压低分项目 bullets → 再隐藏最低分整段

### 4.3 当前资产优先级（Data Analyst 默认）

| 块 | 默认优先级 | 典型映射 |
|----|------------|----------|
| Tesla ETL + Tableau 项目 | 高 | Airflow, SQL, Tableau, dashboard, ETL |
| 申万宏源实习 | 高（量化/性能岗更高） | Python, Monte Carlo, pricing, C++ |
| Credit Risk 项目 | 高（风险/ML 岗） | ML, SQL, credit risk, XGBoost |
| Claims Severity 项目 | 高（保险岗） | claims, severity, R/Python |
| 银华基金实习 | 中（偏业务 DA） | cleaning, reporting, stakeholder |
| MCM 等竞赛 | 低 | 空间不够可隐藏 |

---

## 5. Skills 三层清单（按岗显隐）

### Tier A — 通用 DA 常驻靠前

`Python, SQL, Tableau, data cleaning, exploratory analysis, feature engineering, ETL, stakeholder reporting`

### Tier B — 差异化（风险/保险/资管/量化分析时抬升）

`R, Monte Carlo Simulation, Credit Risk, Claims Modeling, Actuarial Science, Financial Modeling, scikit-learn, XGBoost, risk analytics`

### Tier C — 按 JD 显隐

`Apache Airflow, C++, OpenMP, SPSS, Pandas, NumPy, matplotlib, AI prompt engineering, performance benchmarking`

规则：JD 未要求且空间紧时，C 层可移出 Skills，改留在相关 bullet 中（若该段已上架）。

### Summary 侧重点速查

| 岗位簇 | Summary 侧重 |
|--------|----------------|
| 通用 Data Analyst | SQL + Tableau/可视化 + stakeholder + cleaning/ETL |
| 保险/风险分析 | credit/claims/Monte Carlo + statistical modeling |
| 偏 DS/ML | scikit-learn/XGBoost + feature engineering + evaluation metrics |
| 偏数据工程 | Airflow + SQL + pipeline scale numbers（仅有证据时） |

---

## 6. 针对 JD 的合法改动 / 非法改动

### 允许

- 改写措辞以贴近 JD 用语（真实经历范围内）
- 调整 bullet 顺序（强相关在前）
- 上架/下架整段经历或项目
- 压缩 bullets（3→2）
- Skills 子集与排序
- Summary 重写侧重点

### 禁止

- 改变母版视觉样式与 section 体系
- 添加未发生的经历、工具、证书、数字
- 把“参与/了解”写成“主导/精通”若原文不支持
- 为凑关键词堆砌不会的技能
- 自动定稿绕过用户确认

---

## 7. 新经历加入流程

1. **入库**：写入 Master Inventory（满足 §4.1 最低字段）  
2. **不自动全局上架**：新经历不强制出现在每一份投递版  
3. **打分上架**：与 JD 相关分足够高时，替换/挤出最低分段落以保一页  
4. **格式层**：复制母版中标准 Experience/Project 块样式再填内容；或替换槽位文字  
5. **缺数字**：只写定性事实，不生成假指标  
6. **用户可纠错**：若用户否定某条，立即从投影版移除并回写库存标注

---

## 8. 版本、Diff 与定稿

1. 每次生成投递稿：相对上一版做 **内容 diff**（新增/删改着色展示）  
2. 保留最近 **3** 个 old version + 当前草稿  
3. 用户确认后：
   - 写入 `data/final_resumes/{Company}_{Position}/`
   - 文件名包含公司与职位 slug  
4. 确认前状态不得称为 final

---

## 9. 自动质检清单（导出前必过）

- [ ] 单页  
- [ ] Section 顺序与标题合法  
- [ ] 联系方式与 Name 未被改乱  
- [ ] 每条改写有 evidence_from  
- [ ] 无无出处数字/工具  
- [ ] Skills 为单行且无不会的词  
- [ ] 上架经历与 JD 相关分解释得清（写入 tailoring_summary）  
- [ ] 未触碰母版只读路径  

任一项失败 → **不得定稿**，回到修改循环。

---

## 10. Agent 输出契约（实现层）

简历定制节点必须输出结构化对象（字段可与现有 schema 对齐），至少包含：

- `summary`
- `education[]`
- `experiences[]`（含 `bullets[{text, evidence_from, original_text}]`）
- `projects[]` / `competitions[]`（可空）
- `skills_certifications`（单行字符串）
- `hidden_entries[]`（本投递版下架的库存 ID，便于 UI 说明）
- `tailoring_summary`（改了什么、为何、如何保一页）
- `format_check` / `evidence_check` 结果

禁止只输出“漂亮的纯文本简历”而不带证据字段。

---

## 11. 修订

- 版本：v1（2026-08-03）  
- 修订本宪法需用户明确授权；Agent 不得自行降级 §0 绝对原则。
