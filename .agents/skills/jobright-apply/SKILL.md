---
name: jobright-apply
description: >-
  从 Jobright 职位页点 Original Job Post，切到雇主 ATS，用 ghost-driver-mcp 拟人填表并
  在 Submit 前暂停。Use when the user asks to 投递/申请/apply、点击 Original Job Post、
  填写 job application form，或走 Jobright → 雇主原帖 → 填表暂停闭环。
---

# Jobright 投递（停在 Submit 前）

用 **ghost-driver-mcp** 走投递：Jobright 详情 → **Original Job Post**（新标签）→ 雇主申请表 → 填表 → **禁止点 Submit**。Chrome 须前台可见。

## 能力分工

| 能力 | 谁 |
|------|-----|
| 开 Jobright 详情 | `browser_navigate` |
| 点 Original Job Post / 切标签 | `physical_click` → `list_tabs` → `select_tab` |
| 感知表单 | **优先** `get_page_accessibility_tree` → 不够再 `take_screenshot` / `screen-locate` |
| 填文本 | `physical_click` 聚焦 → `physical_type` |
| 上传简历 | `set_input_files`（已确认 PDF 的绝对路径） |
| 下拉/勾选 | `physical_click` / `physical_type` / `physical_keypress` |
| 验证码 | `captcha-solve` |
| MCP/Chrome 排错 | `debug-dev-env` |
| 申请人资料 / 简历 PDF | Web API：`GET /api/v1/profile/{user_id}/library`；PDF 来自 `resume-tailor` skill 或购物车 confirm 返回的绝对路径 |

禁止用 CSS selector / XPath 点控件（`set_input_files` 是唯一例外）。禁止 `browser.close()`。**禁止点击任何 Submit / Submit Application / 提交申请。**

## 前置

1. `ghost-driver-mcp` 已启用；Chrome 窗口在前台。
2. 资料只从本机 Web 档案取，缺字段就问用户或停，**不要用测试假数据当真投**。
3. 简历必须是已确认 PDF 的绝对路径（`resume-tailor` 的 `final_path`/`resume.pdf`，或购物车 `resume_pdf_path`）。文件不存在则停。

```
GET http://127.0.0.1:8000/api/v1/profile/{user_id}/library
→ apply.full_name / email / phone 等
```

## 标准流程

```
- [ ] 1. 打开 Jobright 职位页
- [ ] 2. 点 Original Job Post，切到雇主新标签
- [ ] 3. 关掉 Cookie / 登录墙
- [ ] 4. 滚到申请表，a11y 列出全部可见字段
- [ ] 5. 填必填（文本 → 简历 → 勾选 → 下拉）
- [ ] 6. 停在 Submit 前：截图 + 列出已填字段，交给用户手动提交
```

### 1. 打开 Jobright

```
browser_navigate(url=<jobright jobs/info/...>)
get_page_accessibility_tree
```

定位 `name` 含 **Original Job Post** 的 `link`/`button`，记下 `x,y`。

### 2. 新标签

`physical_click` 该坐标。然后：

```
list_tabs → 选「最新、URL 不是 jobright.ai」的雇主页（通常 index 最大）
select_tab(index)
```

不要在 Jobright 页上填表。

### 3. 遮挡层

a11y 若有 Cookie / Consent：先点 **Accept**。登录墙、人机验证：按 `captcha-solve` 或请用户手动过。

### 4. 找到表单

`physical_scroll` 向下，直到 a11y 出现申请表和 `textbox`/`combobox`。每屏都重新取 a11y。字段跨多屏：填完当前屏再滚。

### 5. 填表

每个文本框：**先 click 再 type**。

| 控件 | 做法 |
|------|------|
| 文本 / textarea | click 中心 → `physical_type` |
| 覆盖旧值 | `physical_type(..., replace=true)` |
| 简历 | `set_input_files(path=<已确认 PDF 绝对路径>)` |
| 复选框 | 点 16×16 的 checkbox 节点，不要点旁边大 label |
| 下拉 combobox | **优先在框内直接 type 选项原文** |
| 未暴露的控件 | `take_screenshot` + `screen-locate` |

**写意图闸门**：一次长 `physical_type`（约 ≥25 字）会武装写意图；**之后第一次 click 或 Enter 会被当成提交**。长字段不要放在最后一次输入之后还去点别的控件。`set_input_files`、`physical_scroll`、只读 a11y/截图不消耗写意图。

配额：`budget_exceeded` → 停止并上报。`not_foreground` → `select_tab`。`night_guard` → 推迟到白天。

### 6. 暂停（铁律）

填完必填后：

1. `take_screenshot` 保存暂停页。
2. 向用户汇报：雇主 URL、已填字段（邮箱可打码）、简历是否挂上。
3. **不要** `physical_click` 任何 Submit / Submit Application / Apply（若 Apply 是进入表单的入口则可点；最终提交按钮不可点）。
4. 用户自己在前台 Chrome 点提交。

## 字段策略

只用 `library.apply` + 用户当场补充的值。必填以页面红星 `*` 和 a11y `name` 为准。

## 失败处理

| 现象 | 动作 |
|------|------|
| 点了 Original Job Post 但没新标签 | 再 `list_tabs`；或 `browser_navigate(..., new_tab=true)` |
| Cookie 挡住 | 先 Accept |
| 下拉点不开 | 聚焦 combobox 后 `physical_type` 选项文本 |
| Turnstile / 点选验证 | `captcha-solve`；过不了就停 |
| `budget_exceeded` / `night_guard` | 停止并上报 |

## 收工汇报

Jobright URL、雇主页 URL、填了哪些字段、简历是否挂上、**已暂停在 Submit 前**。不要写长篇分析。
