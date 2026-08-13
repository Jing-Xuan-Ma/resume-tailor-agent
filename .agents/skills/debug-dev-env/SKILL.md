---
name: debug-dev-env
description: >-
  Start and stop the ghost-driver-mcp local debug stack: Chrome with CDP
  (port 9222) and the project MCP server for Cursor. Use when the user asks
  to debug, start/stop dev environment, launch Chrome for automation, enable
  MCP tools, check CDP status, tail debug logs, or troubleshoot attach failures.
---

# Ghost-Driver 本地调试环境

MCP 源码在仓库内 `mcp/happy-ghost-driver/`。下面命令都相对 **resume-tailor-agent 根目录**。

> **定位**：本 skill 只服务**本地开发调试**（起停 Chrome、看日志、排 attach 问题），
> **不是运行时依赖**。MCP 自带自愈（断连重连、Chrome 未启自动拉起、wedge 看门狗强制重启），
> 线上/发布环境不需要也不应依赖 `dev-env.sh`。

在 Cursor 里调试 ghost-driver-mcp 需要 **两个进程**：

| 进程 | 谁管理 | 作用 |
|------|--------|------|
| Chrome `:9222` | MCP 内部按需自动拉起 / 或 `mcp/happy-ghost-driver/scripts/dev-env.sh` | CDP 附着目标，带常驻独立 profile |
| MCP Server | Cursor 通过 `.cursor/mcp.json` 拉起 | stdio 暴露 14 个 Tools |

## 工具清单（14 个）

- 采集：`query_intercepted_network_data`（MCP 内置 sniffer 自动抓包，**无需**单独跑 sniffer 进程；`ENABLE_SNIFFER=0` 可关）
- 感知：`get_page_accessibility_tree`（只读，**不走 cooldown**，多步任务更快）、`take_screenshot`（截图回传给 agent；需要视觉定位坐标时配合项目内 `.agents/skills/screen-locate`，MCP 不内置视觉定位）、`extract_text_at`、`extract_assistant_reply`、`read_clipboard`
- 物理：`physical_click`、`physical_type`、`physical_scroll`、`physical_keypress`
- 导航/标签：`browser_navigate`、`list_tabs`、`select_tab`、`close_tab`

## 账号安全守卫（物理动作会被拒绝）

物理类工具经过 `mcp/happy-ghost-driver/src/guard/`，配置 `mcp/happy-ghost-driver/config/budget.json`，账本 `~/.ghost-driver/ledger.db`。可能返回的拒绝：

| 错误 | 含义 | 正确反应 |
|------|------|----------|
| `not_foreground` | 目标标签不可见，或发布时 Chrome 无系统焦点 | `select_tab` 置前台；发布类还需点进 Chrome 窗口 |
| `budget_exceeded` | 该域名该风险级配额耗尽 | **停止任务并上报**。不要重试，不要换域名绕过 |
| `night_guard` | 处于夜间写操作禁止时段（默认 01:00–07:00） | 推迟到白天 |

调试时可用 `GUARD_ENABLED=0` / `PACING_ENABLED=0` 关闭守卫与会话节奏，**但不要用于日常自动化**。

profile 常驻 `~/.ghost-driver/chrome-profile`（不是临时目录，登录态跨重启保留）。
备份：`bash mcp/happy-ghost-driver/scripts/backup-profile.sh`。

## 多标签页行为（常驻浏览器）

- `browser_navigate(url, new_tab?)`：打开 URL，目标页成为「活动页」，后续 a11y/点击/输入都作用其上。**agent 自主开页首选这个，别再用裸 CDP 开 tab**。
- `list_tabs()` → `[{index,url,title,active,visible}]`；`select_tab(index)` 切换活动页并置前台。
- 自动选页规则：优先**前台可见**页、排除非 http(s) 目标；活动页退到后台且有其它可见页时自动跟随前台。`select_tab`/`browser_navigate` 的显式选择会被保持。

## 自动连接（关键行为）

MCP **不再在启动时一次性 attach**。物理类工具首次被调用时，`PageProvider`
（`src/attach/provider.ts`）会按需：

1. 连接 `CDP_ENDPOINT`（默认 `http://127.0.0.1:9222`）
2. Chrome 没开 → **自动调用 `mcp/happy-ghost-driver/scripts/launch-chrome.sh` 拉起**并等待（`AUTO_LAUNCH_CHROME=0` 可禁用）
3. 没有打开的标签页 → **自动新建**一个；有真实标签页则优先选中（跳过 about:blank / newtab）
4. Chrome 被关后重开 → 监听 `disconnected`，下次调用**自动重连**
5. Chrome 活着但页面 wedge（连续 2 次 `browser_navigate` goto 超时）→ **看门狗强制重启**：
   先 CDP `Browser.close` 优雅关闭，不行再按 profile 标记 `pkill`，随后自动重拉 Chrome 并重试导航一次。
   仅当 Chrome 是 MCP 自己拉起时生效（`AUTO_LAUNCH_CHROME=0` 的用户自管 Chrome 不会被杀）。

因此用户**无需**手动保证「先开 Chrome 再启 MCP」的顺序，也无需每次重连 MCP。
唯一需要重连 MCP 的场景：**改了 MCP 源码并 `npm run build` 之后**（Cursor 子进程需重载新 `dist/`）。

## 内置抓包（in-process sniffer）

MCP 启动后会在每次建立 / 重建 `BrowserContext` 时，于 **context 级**挂一个
sniffer（`src/collect/sniffer.ts`），覆盖**所有标签页**（含新开的）。捕获到的
响应体写入 `DB_PATH`，由 `query_intercepted_network_data` 查询。

- 默认开启；`ENABLE_SNIFFER=0` 关闭。
- 过滤项（逗号分隔）：`CONTENT_TYPES`（默认 `application/json`）、`URL_INCLUDE`、`URL_EXCLUDE`。
- Chrome 重启 → context 重建时自动重挂；关停时打印 `final sniffer stats`。

## 快速启停（Agent 直接执行）

**仓库根目录**下运行：

```bash
# 启动 Chrome（调试必备）+ 可选 standalone MCP
bash mcp/happy-ghost-driver/scripts/dev-env.sh start

# 只看 Chrome（Cursor 自己管 MCP 时用）
bash mcp/happy-ghost-driver/scripts/dev-env.sh start --chrome-only

# 停止全部
bash mcp/happy-ghost-driver/scripts/dev-env.sh stop

# 健康检查
bash mcp/happy-ghost-driver/scripts/dev-env.sh status

# 查看最近日志
bash mcp/happy-ghost-driver/scripts/dev-env.sh logs
```

npm 快捷方式（在 `mcp/happy-ghost-driver`）：`npm run dev:env:start` / `dev:env:stop` / `dev:env:status` / `dev:env:logs`

## Cursor MCP 接入

项目已配置 `.cursor/mcp.json`，Server 名 **`ghost-driver-mcp`**。

1. Cursor → Settings → MCP → 启用 `ghost-driver-mcp`
2. 直接调用任意工具即可——Chrome 会按需自动拉起、自动 attach
3. **改了 MCP 源码后**：`npm run build` → 在 Settings → MCP 把 `ghost-driver-mcp` 关再开（或 Reload Window），让子进程载入新 `dist/`

MCP 由 Cursor 子进程启动，入口为 `mcp/happy-ghost-driver/scripts/run-mcp-stdio.sh`（stdout 走 MCP 协议，**stderr 写日志**）。

## 日志位置（观测与排错）

所有运行时日志在 **`mcp/happy-ghost-driver/.debug/logs/`**（已 gitignore）：

| 文件 | 内容 |
|------|------|
| `dev-env.log` | 启停编排、端口检测、构建触发 |
| `mcp-cursor-latest.log` | Cursor 拉起的 MCP stderr（含 `[INFO]` attach/CDP/tool 调用） |
| `mcp-standalone-latest.log` | `dev-env.sh start` 拉起的独立 MCP |
| `chrome-latest.log` | Chrome 启动脚本输出 |

**Agent 调试时务必先读日志**：

```bash
bash mcp/happy-ghost-driver/scripts/dev-env.sh logs
tail -f mcp/happy-ghost-driver/.debug/logs/mcp-cursor-latest.log
tail -f mcp/happy-ghost-driver/.debug/logs/dev-env.log
```

MCP 业务日志格式（`src/util/logger.ts`）：`[ISO8601] [LEVEL] message { meta }`

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DB_PATH` | `./data/intercepted.db` | SQLite 拦截库路径；父目录不存在时会自动创建 |
| `CDP_ENDPOINT` | `http://127.0.0.1:9222` | Chrome DevTools 地址 |
| `GHOST_PROFILE_DIR` | `~/.ghost-driver/chrome-profile` | Chrome 常驻 profile（登录态所在，勿删） |
| `GUARD_ENABLED` | `1` | 关闭账号安全守卫（仅调试） |
| `PACING_ENABLED` | `1` | 关闭会话级节奏（长休/阅读停留/回滚） |
| `ENABLE_STEALTH` | `0` | 注入指纹补丁；默认关，真实 profile 下无必要 |
| `SNIFF_DOMAINS` | 空 | 采集域名白名单，不设则抓所有站点 JSON |
| `SNIFF_RETENTION_DAYS` | `7` | 采集留存天数，`0` 为永久 |

## 闭环自检（Agent 自主跑，无需 Cursor）

`npm run test:e2e`（`test/e2e/closed-loop.mjs`）一条命令自管全生命周期：
清场 → 启 Chrome → 开 Google → spawn standalone MCP（加载当前 `dist/`）→
`get_page_accessibility_tree` 定位搜索框 → `physical_click` → `physical_type` →
校验跳转到 `google.com/search?q=...` → 拆除。

- MCP 日志实时镜像到 stdout（`[mcp]` 前缀）并存 `.debug/logs/closed-loop-<ts>.log`
- 退出码：闭环成功 0 / 失败 1
- **改完 MCP 源码先 `npm run build` 再跑**——它用的是 `dist/`，不依赖 Cursor 那个进程
- 这是 Agent 调试物理链路的首选方式（不受 Cursor MCP 进程是否重载的影响）

## 标准调试流程

```
1. cd mcp/happy-ghost-driver && npm install && npm run build
2a.（Agent 自检）npm run test:e2e
2b.（Cursor 联调）启用 ghost-driver-mcp，改过源码则先 build 再重连一次
3. 直接调用工具 → Chrome 自动拉起 + 自动 attach
4. 出问题 → bash mcp/happy-ghost-driver/scripts/dev-env.sh logs
5. 结束 → bash mcp/happy-ghost-driver/scripts/dev-env.sh stop
```

`mcp/happy-ghost-driver/scripts/dev-env.sh` 主要用于手动观测/排错；日常 Cursor 调试已不依赖它手动起 Chrome。

## 常见问题

**`cdp: UNREACHABLE`**
- 先 `bash mcp/happy-ghost-driver/scripts/dev-env.sh start --chrome-only`，等 10s 内 `cdp: OK`
- 9222 被占用：`lsof -nP -iTCP:9222 -sTCP:LISTEN`
- 读 `chrome-latest.log`

**MCP tools 报 `browser_not_attached`**
- 改了源码但没重连 MCP：Cursor 仍跑旧 `dist/` → `npm run build` 后重连一次
- `AUTO_LAUNCH_CHROME=0` 且 Chrome 没开 → 手动起 Chrome 或去掉该变量
- `CDP_ENDPOINT` 与 Chrome 端口不一致
- 看 `mcp-cursor-latest.log` 里 `PageProvider: ... connect failed` / `did not become reachable`

**Chrome 断连后 MCP 不再自动拉起（`launchAttempted` 陷阱）**
- **已缓解（当前代码）**：`clearCache` 在 disconnect / wedge / dispose 时会重置 `launchAttempted`；launch 超时未连上也会重置，下一次 tool 调用可再 auto-launch。macOS 启动改走 `open -na`，Chrome 不再随 agent shell 退出被收走。
- 若仍看到反复 `ECONNREFUSED` 且**没有** `PageProvider: auto-launching Chrome`：Cursor → Settings → MCP → **关再开** `ghost-driver-mcp`，然后直接 `browser_navigate`。
- **Agent 易犯错误**：用 Node/Playwright 脚本 `connectOverCDP` 后 `browser.close()` 做验证——这会杀死持久化 Chrome，造成「刚启动又 9222 down」的假象。不要对调试 Chrome 调 `browser.close()`。

**macOS：Chrome 启动后几秒就没了 / 9222 闪一下又 ECONNREFUSED**
- 旧 `launch-chrome.sh` 用二进制 + `&` 挂后台，会被 Cursor agent shell 收进程组时带走。
- 现已改为 `open -na "Google Chrome" --args ...`（LaunchServices 接管），并在脚本内等到 CDP 就绪再退出。
- 手动救场：`bash mcp/happy-ghost-driver/scripts/launch-chrome.sh` 或 `bash mcp/happy-ghost-driver/scripts/dev-env.sh start --chrome-only`。

**`DB_PATH is not set`**
- `.cursor/mcp.json` 已设 `data/intercepted.db`；standalone 模式检查 `dev-env.sh` 导出

**物理操作无效**
- Chrome 窗口必须前台、标签可见（README §7）
- 查 MCP 日志里的 visibility / cooldown 警告

## Agent 观测清单

每次帮用户调试后，在回复中简要汇报：

- [ ] `mcp/happy-ghost-driver/scripts/dev-env.sh status` 关键行（chrome / cdp / build）
- [ ] 若失败：贴 `dev-env.log` 或 `mcp-cursor-latest.log` 最后 10–20 行
- [ ] 建议的下一步（开标签、Reload MCP、重建 `npm run build` 等）

## Windows

Chrome 用 `mcp/happy-ghost-driver/scripts/launch-chrome.ps1`；`dev-env.sh` 仅 macOS/Linux。Windows 上手动启 Chrome 后，仍可用 Cursor + `.cursor/mcp.json` 调试 MCP。
