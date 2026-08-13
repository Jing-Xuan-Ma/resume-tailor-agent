---
name: jobright-original-apply
description: >-
  从 Jobright 职位页点击 Original Job Post，切到雇主站新标签，用 ghost-driver-mcp
  拟人填写申请表并提交。Use when the user asks to 投递/申请/apply、点击 Original Job Post、
  填写 job application form，或走 Jobright → 雇主原帖 → Submit 闭环。
---

# Jobright Original Job Post 投递

用本仓库 **ghost-driver-mcp**（`mcp/happy-ghost-driver/`）走完整投递：Jobright 详情 → **Original Job Post**（新标签）→ 雇主申请表 → 填表 → Submit。Chrome 须前台可见。

资料和简历只从本仓库取，不要用 Desktop MCP 目录或 `.debug/dummy-resume.pdf`。

## 铁律（实战踩过，必须遵守）

1. **投递时关掉 pacing。** 仓库根 `.cursor/mcp.json` 里 `PACING_ENABLED` 必须是 `"0"` 或 `"false"`。为 `"1"` 时，几十次动作后会强制休息 60–300s；Cursor 会把当次 `physical_type` 判超时，页面还可能被冲掉。发现仍为 `1`：先改成 `0`，请用户把 `ghost-driver-mcp` 关开一次，**再开始填表**。
2. **物理动作严禁并行。** 尤其禁止 `physical_type` 与 `set_input_files` / `physical_click` / `physical_scroll` 同一轮发出。等上一个 MCP 调用返回再发下一个。
3. **type 若报 timeout / -32001：立刻停。** 不要补发 click/upload。先 `list_tabs` + 截图看页是否还在雇主申请 URL。
4. **点表单前避开顶栏。** sticky nav 会占 a11y。目标控件中心必须明显低于顶栏底边；过近则先滚到视口中部再点。点完立刻核对 URL，若离开 careers/apply 页 → 停，`browser_navigate` 回雇主原帖，表单当空表重填。
5. **`set_input_files` 会武装写意图。** 上传后下一次 click/Enter 走提交闸门（停 5–20s）。因此：短字段全部填完 → 再上传简历 → 再填最后一个长文本 → **下一次 click 必须是 Submit**。

## 能力分工

| 能力 | 谁 |
|------|-----|
| 开 Jobright 详情 | `browser_navigate` |
| 点 Original Job Post / 切标签 | `physical_click` → `list_tabs` → `select_tab` |
| 感知表单 | **优先** `get_page_accessibility_tree` → 不够再 `take_screenshot` / `.agents/skills/screen-locate` |
| 填文本 | `physical_click` 聚焦 → `physical_type` |
| 上传简历 | `set_input_files`（已 Confirm 的 PDF **绝对路径**） |
| 下拉/勾选/提交 | `physical_click` / `physical_type` / `physical_keypress` |
| 验证码 | `.agents/skills/captcha-solve` |
| MCP/Chrome 排错 | `.agents/skills/debug-dev-env` |

禁止用 CSS selector / XPath 点控件（`set_input_files` 是唯一例外）。禁止 `browser.close()`。

## 前置

1. `ghost-driver-mcp` 已启用（`.cursor/mcp.json` → `mcp/happy-ghost-driver/scripts/run-mcp-stdio.sh`）；Chrome 前台；**`PACING_ENABLED=0`**。
2. 申请人资料只从本机 Web 档案取：

```
GET http://127.0.0.1:8000/api/v1/profile/{user_id}/library
→ apply.full_name / email / phone / location / linkedin_url
```

缺字段就问用户或停，**不要用测试假数据当真投**。
3. 简历必须是已 Confirm 的 PDF 绝对路径，且文件存在：
   - `resume-tailor` 的 `data/final_resumes/{Company}_{Position}/resume.pdf`
   - 或购物车 `data/shopping_cart/.../resume.pdf`（`resume_pdf_path`）
   不要用手改文件名，不要用 Desktop MCP 仓库里的 dummy PDF。

## 标准流程

```
- [ ] 0. 确认 PACING_ENABLED=0，否则先改 .cursor/mcp.json 并重连 MCP
- [ ] 1. 打开 Jobright 职位页
- [ ] 2. 点 Original Job Post，切到雇主新标签
- [ ] 3. 关掉 Cookie / 登录墙
- [ ] 4. 滚到申请表，a11y 列出全部可见字段（字段滚到视口中部）
- [ ] 5. 短字段 → 简历上传 → 最后一次长输入 → 点 Submit
- [ ] 6. 等到成功页或明确失败原因
```

### 1. 打开 Jobright

```
browser_navigate(url=<jobright jobs/info/...>)
get_page_accessibility_tree
```

定位 `name` 含 **Original Job Post** 的 `link`/`button`，记下 `x,y`。点之前避开顶栏重叠。

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

点某个字段前：控件中心 y 必须 **低于 sticky header 底边至少 ~40px**。点完看 URL；离开申请页 = 误点导航，按铁律 4 处理。

### 5. 填表

每个文本框：**先 click 再 type**，等返回。一次只发一个物理工具。

| 控件 | 做法 |
|------|------|
| 文本 / textarea | click 中心 → `physical_type` |
| 覆盖旧值 | `physical_type(..., replace=true)` |
| 简历 | **短字段都填完后**再 `set_input_files(path=<已确认 PDF 绝对路径>)` |
| 复选框 | 点 16×16 的 checkbox 节点，不要点旁边大 label |
| 下拉 combobox | **优先在框内直接 type 选项原文** |
| 未暴露的控件 | `take_screenshot` + `screen-locate` |

**写意图闸门：** `physical_type` ≥25 字，或 **`set_input_files`**，都会武装；之后第一次 click/Enter 当成提交。

推荐顺序：姓名 / 电话 / First / Last / 城市 / 勾选 / Location 下拉（短）→ 上传简历 → Email 或 LinkedIn（若会 ≥25 字，放最后）→ **立刻点 Submit**。

配额：`budget_exceeded` → **停止并上报**。`not_foreground` → `select_tab`。`night_guard` → 推迟到白天。

### 6. 提交与验收

1. a11y 找到 Submit（`Submit Application` / `Submit` / `Apply`），确认坐标不与顶栏重叠。
2. `physical_click`。Cloudflare Turnstile 可能自动变绿。
3. **等待**（约 5–15s）再截图。不要立刻再点 Submit。
4. 成功信号：`Application Submitted` / Thank you / we’ve received your application。
5. 仍停在表单：截图看校验红字，补完再提交一次。

`a11y_failed` / `Execution context was destroyed` = 页面导航或刷新。当作空表重填。

## 字段策略

只用 `library.apply` + 用户当场补充的值。必填以页面红星 `*` 和 a11y `name` 为准。

## 失败处理

| 现象 | 动作 |
|------|------|
| `PACING_ENABLED=1` 或 type 耗时 >30s / timeout | 停；改 pacing=0 并重连 MCP |
| 点了 Original Job Post 但没新标签 | 再 `list_tabs`；或 `browser_navigate(..., new_tab=true)` |
| Cookie 挡住 | 先 Accept |
| 点字段后 URL 变成营销页 | 顶栏误点；navigate 回申请 URL，空表重填 |
| 下拉点不开 | 聚焦 combobox 后 `physical_type` 选项文本 |
| Turnstile / 点选验证 | `.agents/skills/captcha-solve`；过不了就停 |
| `budget_exceeded` / `night_guard` | 停止并上报 |

排错命令相对 **resume-tailor-agent 根目录**：

```bash
bash mcp/happy-ghost-driver/scripts/dev-env.sh status
bash mcp/happy-ghost-driver/scripts/dev-env.sh logs
```

## 收工汇报

Jobright URL、雇主页 URL、填了哪些字段（邮箱可打码）、简历绝对路径是否挂上、是否到达成功页。不要写长篇分析。
