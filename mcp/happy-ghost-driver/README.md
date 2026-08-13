# Ghost-Driver-MCP: 真实浏览器自动化与旁路采集底座

为通用 AI Agent（如 Cursor、Claude Desktop）提供在**真实 Chrome、真实登录态**下的浏览器操作与数据采集能力，用途是替代自己账号上的重复劳动。

## 1. 背景与核心理念

**核心设计理念：**
1.  **真实浏览器，持久登录态**：不启动 Headless 无头浏览器，而是通过 CDP 附着一个可见的真实 Chrome。profile 常驻 `~/.ghost-driver/chrome-profile`，登录态跨重启保留。
2.  **物理与认知分离**：AI Agent 作为“大脑”感知页面结构（A11y/视觉），MCP Server 控制“幽灵之手”按坐标操作键鼠，交互层**不接受任何 CSS Selector / XPath**。
3.  **零侵入旁路采集**：不解析 HTML，而是在 BrowserContext 级监听原生网络响应（JSON）并落库，覆盖所有标签页。
4.  **行为水位由底座强制**：动作配额、夜间守卫、提交闸门、前台校验都在 Server 内实现（见 §5）。写在提示词里的约束是建议，写在这里的才是上限。

### 1.1 能力边界（务必先读）

本项目降低的是**“行为看起来像机器”**的风险，不是**“对抗专业反爬”**的能力。请按这个前提使用：

*   **无法隐藏 CDP 被驱动这一事实。** Playwright 的 `connectOverCDP` 会 enable `Runtime` domain，而 A11y 树、文本提取都依赖 `page.evaluate`。这是架构属性，注入脚本掩盖不了。要彻底规避需换掉整个感知层。
*   **不做指纹伪造。** 不改 Canvas / WebGL / Audio / 时区 / 硬件并发。真机真环境本来就自洽，伪造只会制造矛盾特征。`stealth` 默认关闭，原因见 `src/physical/stealth.ts` 顶部注释。
*   **不做代理 / IP 池。** 在自己家网络操作自己账号，突然切 IP 本身才是异常信号。
*   **`physical_*` 不是操作系统级输入。** 它是通过 CDP 注入的输入事件，只是带了拟人的轨迹与节奏；不移动系统光标。

因此：**适合只读浏览、采集、整理，以及低频的自有账号写操作。不适合高频互动或多账号运营。**

## 2. 技术栈选型

*   **开发语言**：`TypeScript / Node.js` (生态最强，官方支持度高)
*   **浏览器控制层**：`playwright-core` 
    *   *注：特意选择 `-core` 版本，因为它不自带任何浏览器内核，专门用于通过 CDP 连接现存的本地浏览器。*
*   **物理操作引擎**：`ghost-cursor`
    *   *注：专门针对 Playwright 封装的贝塞尔拟人鼠标轨迹库，自带重力、防过冲算法。*
*   **本地存储**：`better-sqlite3` (高性能同步 SQLite 库，适合单机高频入库)
*   **AI 接口协议**：`@modelcontextprotocol/sdk` (MCP 官方 Node.js SDK)

## 3. 部署形态与物理架构

系统运行时，包含三个完全解耦的独立进程：

```mermaid
graph TD
    A[进程1: 真人现存 Chrome] -- CDP ws://localhost:9222 --> B(进程2: 常驻 MCP Server)
    B -- MCP Protocol (Stdio) --> C[进程3: AI Agent 客户端]
    
    subgraph 幽灵底座 (Node.js)
        B1[旁路嗅探模块] --> SQLite[(本地数据库)]
        B2[A11y 感知模块]
        B3[Ghost Cursor 物理模块]
    end
    B1 -.监听网络.-> A
    B2 -.获取树结构.-> A
    B3 -.下发鼠标轨迹.-> A
    
    C -- 调用 Tool: 提取数据 --> B
    C -- 调用 Tool: 模拟滑动 --> B
```

1.  **宿主浏览器 (真身)**：由 `scripts/launch-chrome.sh` 启动的可见 Chrome，带 `--remote-debugging-port=9222` 和常驻 profile，保有真实登录态与硬件环境。
2.  **MCP Server (幽灵底座)**：Node.js 常驻后台进程。连接 9222 端口，监听网络，对外暴露标准 MCP Tools。
3.  **AI Agent (大脑)**：如 Cursor AI 或 Claude Desktop。通过自然语言调用 MCP 工具实现自动化。

### 3.1 关于 profile：为什么不是日常 Chrome

**Chrome 136 起，`--remote-debugging-port` 在指向默认 Chrome 数据目录时会被忽略**（官方安全变更，防止 infostealer 通过调试端口窃取 cookie）。所以无法直接附着你日常那个 Chrome，必须用独立 `--user-data-dir`。

这带来一个后果：独立 profile 在站点看来是**一台新设备**。因此：

*   profile 必须**持久**且**长期只用这一个**（默认 `~/.ghost-driver/chrome-profile`，绝不放临时目录）。
*   首次创建后请**手动登录**，并先只读浏览几天再让 Agent 做写操作。预算守卫会在养号期自动压低配额（§5）。
*   **务必备份**：`bash scripts/backup-profile.sh`。profile 丢失 = 重新登录 = 又一次“新设备”。

## 4. 核心模块与 MCP 工具定义

共 **14 个** MCP 工具，不绑定任何特定网站。

### 4.1 导航与环境类
> 附着无需显式调用：首个浏览器类工具被调用时懒连接，Chrome 未启动会自动拉起，CDP 断开后下次调用自动重连。

*   **`browser_navigate(url: string, new_tab?: boolean)`**
    *   描述：默认在当前活动标签页打开 URL，`new_tab=true` 时新开标签。导航后按页面内容长度停留一段时间（模拟阅读），并清除上一页遗留的写意图。
*   **`list_tabs()` / `select_tab(index)` / `close_tab(index)`**
    *   描述：列出所有内容标签页、切换活动标签、关闭指定标签（例如任务完成后的清理、点击链接后被动新开的背景标签）。
      三者都基于 `list_tabs` 返回的 `index` 操作；`close_tab` 关掉当前活动页时，下一次取页会
      按 `list_tabs` 同样的规则自动挑一个新的活动页。`close_tab` 带最后一页保护：目标是浏览器
      仅剩的存活页面时拒绝关闭并返回 `last_tab` 错误（关掉它会连带关闭整个浏览器，破坏常驻）。

### 4.2 感知类 (Perception)
*   **`get_page_accessibility_tree()`**
    *   描述：获取当前页面的纯净无障碍语义树（A11y Tree）。
    *   返回值：包含元素的 `role`, `name` (文本内容), 以及在屏幕上的 `[x, y, width, height]` 坐标区域。
    *   *用途：让大模型“看懂”屏幕，且无视 CSS 类名混淆。*
*   **`take_screenshot(full_page?, max_bytes?)`**
    *   描述：对当前页面截图，把图片作为 MCP `image` 内容块**直接回传给 agent**，由 agent 自带的多模态视觉模型识别。
    *   本工具只截图、**不调用任何视觉定位、无 cooldown**，坐标由 agent 自己看图判断；需要精确视觉定位坐标时，把截图存盘后交给项目内 `.cursor/skills/screen-locate`（UI-TARS）定位。视觉定位能力刻意**不内置在 MCP Server 里**，降级路径只依赖同仓库 skill。
    *   返回：一个 `image` 块（base64 图片）+ 一个 `text` 块（JSON 元数据）。元数据含 `url`、`title`、`viewport_css`（CSS 像素视口尺寸）、`image_px`（图片真实像素尺寸）、`device_scale_factor`、`truncated`。
    *   **坐标换算规则**：agent 从图片上读到的像素坐标，需 `÷ device_scale_factor` 得到 CSS 像素坐标，再传给 `physical_click`（Retina 屏通常 `device_scale_factor = 2`）。
    *   *用途：让 Cursor 自带视觉直接看页面，配合 skill 实现自动验收/点击；不返回 selector，只返回图片与坐标元数据。geo-qa 等长文本采集应优先用下方 extract_* 工具，截图仅作完整性抽检兜底。*
*   **`extract_assistant_reply(user_message?, max_chars?)`**
    *   描述：AI 聊天页专用——程序滚动主消息容器、合并 innerText，提取最新 assistant 回答全文（无 A11y 200 字 cap）。
    *   只读感知，无 cooldown。
*   **`extract_text_at(x, y, max_chars?)`**
    *   描述：读取视口坐标处元素及其祖先的完整 innerText。只读感知。
*   **`read_clipboard()`**
    *   描述：读取系统剪贴板纯文本（配合平台「复制」按钮或 `physical_keypress`）。只读感知。
*   **`write_clipboard(text: string)`**
    *   描述：写入系统剪贴板纯文本。长文注入主路径：`write_clipboard` → 聚焦编辑区 → `physical_keypress(Meta+v)`。

### 4.3 物理交互类 (Execution)
除 `set_input_files` 外，参数只接受物理参数（坐标、方向、键位），严禁传入 CSS Selector。
*   **`physical_click(x: number, y: number)`**
    *   描述：调用 `ghost-cursor`，生成一条起始点到 `(x, y)` 的贝塞尔随机轨迹，移动到位后触发底层 `MouseDown -> MouseUp`。
*   **`physical_type(text: string, replace?: boolean)`**
    *   描述：模拟真人逐字敲击键盘输入，包含随机的字母输入间隔（如 50ms - 200ms）。`replace=true` 时先全选再输入，用于覆盖搜索框等已有内容。上限 8000 字；长文请用 `write_clipboard` + 粘贴。
*   **`physical_keypress(keys: string)`**
    *   描述：按下键位组合（Playwright 格式，如 `Meta+c`、`Control+a`、`Meta+v`）。请先 `physical_click` 聚焦目标区域。
*   **`physical_scroll(direction: 'up'|'down', distance_px: number)`**
    *   描述：生成一段带有动量的鼠标滚轮操作事件（Mouse Wheel Event）。
*   **`set_input_files(path: string, selector?: string)`**
    *   描述：向 `<input type="file">` 注入本地绝对路径文件（封面/插图/DOCX）。file input 对 A11y 常不可见，故允许可选 CSS selector；默认 `input[type="file"]`。

### 4.4 数据采集类 (Collection)
*   **`query_intercepted_network_data(url_pattern: string)`**
    *   描述：MCP Server 在后台使用 Playwright 的 `page.on('response', ...)` 静默监听所有流量。此工具允许 Agent 根据正则/关键词（如 `*search/notes*`）从 SQLite 提取最近拦截到的完整 JSON/文本数据。

## 5. 账号安全守卫（Server 强制，不可绕过）

所有物理动作都经过 `src/guard/`。配置见 `config/budget.json`，动作账本在 `~/.ghost-driver/ledger.db`。

### 5.1 风险分级

配额按风险分级计数，而非按动作次数：

| 级别 | 含义 | 对应动作 |
| --- | --- | --- |
| `read` | 纯消费 | `physical_scroll`、`browser_navigate` |
| `light` | 交互但不产出内容 | `physical_click`、`physical_type`、`physical_keypress` |
| `write` | 内容公开且不可撤回 | 发布、评论、私信等提交 |

### 5.2 提交闸门（写意图追踪）

MCP 只收坐标，无法从 `physical_click(x, y)` 判断点的是收藏还是发布。所以从**输入侧反推**：

```
physical_type(足够长的文本)  →  该页标记「写意图待决」
        ↓
之后首次 click 或 Enter      →  判定为提交，强制走闸门
```

发布必然先撰写，所以绕不过去。闸门包含：提交前 5–20s 停顿（模拟检查内容）、截图存档到 `.debug/submits/`、独立且更严格的配额、写入账本。

一个特例值得知道：`physical_type("正文\n")` 会被**拆成**「输入正文」+「独立的 Enter」两步，因为 `typeText` 把 `\n` 映射为 Enter，不拆开就能在一次未受控的调用里完成撰写加发布。文本**中间**的换行不受影响（多行内容需要它）。

### 5.3 其他守卫

*   **前台校验**：目标标签不在前台时拒绝动作（`not_foreground`）。真人不可能点击看不见的东西。
    *   实测结论：CDP 附着下 `document.visibilityState` **不可用**，后台标签也报 `visible`；而 Playwright 默认对每个 page 开启焦点模拟，使 `document.hasFocus()` 也恒为 `true`。因此 `PageProvider` 会主动关闭焦点模拟，守卫以 **`hasFocus()` 为权威信号**（已验证精确跟随前台标签）。
    *   仍看不到的：**窗口遮挡**。Chrome 窗口被其它应用完全盖住时，其活动标签依然报 focused。
*   **窗口焦点**：默认仅对 `write` 级要求 Chrome 拥有系统焦点（`requireWindowFocus: "write"`），强制你在内容发出的那一刻在场。`"all"` 最严（整个运行期间需保持 Chrome 在前台），`"off"` 关闭。
*   **夜间守卫**：默认 01:00–07:00 拒绝写操作。夜里读没问题，按点发帖不像人。
*   **养号期爬坡**：profile 年龄小于 `rampUpDays`（默认 14 天）时配额按比例压低，逐步放开。
*   **会话节奏**：每若干动作强制 60–300s 长休；滚动偶发反向回滚。这些补的是**宏观**节奏——1–3s 的动作级冷却只能让单次点击像人，让不了一小时像人。

配额耗尽时返回结构化错误 `budget_exceeded`，并明确告知 Agent 不要重试、不要换域名绕过。

### 5.4 常用环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `GHOST_PROFILE_DIR` | `~/.ghost-driver/chrome-profile` | Chrome 常驻 profile |
| `GUARD_ENABLED` | `1` | 关闭全部守卫（仅用于调试） |
| `PACING_ENABLED` | `1` | 关闭会话级节奏 |
| `ENABLE_STEALTH` | `0` | 注入指纹补丁（默认关，见 §1.1） |
| `SNIFF_DOMAINS` | 空 | 旁路采集域名白名单，**强烈建议设置** |
| `SNIFF_RETENTION_DAYS` | `7` | 采集数据留存天数，`0` 为永久保留 |

### 5.5 自查

```bash
bash scripts/backup-profile.sh list     # 备份状态
sqlite3 ~/.ghost-driver/ledger.db \
  "SELECT date(ts/1000,'unixepoch','localtime') d, write_class, count(*)
   FROM action_ledger GROUP BY d, write_class ORDER BY d DESC;"
```

账本的用途是回答一个问题：**今天这些动作，看起来像我自己吗？**

守卫本身的端到端自检（需 CDP 在线，使用沙箱账本，不消耗真实配额）：

```bash
node test/e2e/verify-guards.mjs
```

### 5.6 从旧临时 profile 迁移

早期版本把 profile 放在 `$TMPDIR`。如果那里已有登录态，**迁移而不是重新登录**——重新登录就是一次“新设备”事件，正是要避免的：

```bash
# 必须先完全退出 Chrome：热拷贝会损坏 Cookies / Login Data 数据库
bash scripts/backup-profile.sh migrate
bash scripts/launch-chrome.sh          # 确认登录态在
bash scripts/backup-profile.sh         # 立刻备份
```

## 6. 核心代码示例 (伪代码片段)

**1. 挂载浏览器并初始化网络嗅探**

监听绑在 **BrowserContext** 而非单个 Page 上，这样已开和新开的所有标签页都被覆盖，不会因为 Agent 换了标签就漏采。实现见 `src/collect/sniffer.ts`。

```typescript
const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
const context = browser.contexts()[0];

context.on('response', async (response) => {
    // 实际实现还会按域名白名单、content-type、body 上限过滤
    if (response.url().includes('/api/v1/search')) {
        const json = await response.json();
        await store.insert({ url: response.url(), body: JSON.stringify(json), /* ... */ });
    }
});
```

**2. 物理级模拟点击**

`ghost-cursor` 的类型面向 Puppeteer，项目通过 Playwright 的 `newCDPSession` 补一层兼容再驱动它。移动与按下之间有 hover 停顿，按下与抬起之间有按压延迟——两者都是检测器会看的特征。实现见 `src/physical/cursor.ts`。

```typescript
const cursor = createCursor(page);

async function executePhysicalClick(x: number, y: number) {
    await cursor.moveTo({ x, y });          // 贝塞尔轨迹
    await sleep(gaussianInt(200, 800));     // hover 停顿
    await cursor.mouseDown();
    await sleep(gaussianInt(50, 150));      // 按压时长
    await cursor.mouseUp();
}
```

## 7. 使用建议

技术上的拟人只解决一半问题，另一半由**你怎么用**决定。

1.  **profile 只用一个，并且备份。** 反复重新登录制造的“新设备”信号，比任何鼠标轨迹都致命。
2.  **新 profile 先养。** 手动登录，只读浏览几天，再开写操作。守卫会在养号期压低配额，但别去调高它。
3.  **保持目标标签可见。** 前台校验会拒绝不可见标签上的动作；发布时还需要 Chrome 拥有系统焦点。
4.  **写操作宁少勿多。** 默认 `write` 配额刻意很小（每天 24 次，小红书 10 次）。如果撞上限，先问是不是任务设计得太激进。
5.  **不要挂机。** 会话长休和夜间守卫是底线，不是节奏建议。24 小时不停的账号无论技术特征多干净都不像人。
6.  **设置 `SNIFF_DOMAINS`。** 否则浏览器碰到的每个登录态 API 的 JSON 都会被明文落库——包括邮箱、银行、工作系统。

### 新机器上手（Cursor 一站式）

前置：Node.js ≥ 20、Google Chrome、[uv](https://docs.astral.sh/uv/)（`screen-locate` / `captcha-solve` 用）。

```bash
npm install
npm run build
cp .cursor/skills/screen-locate/.env.example .cursor/skills/screen-locate/.env
cp .cursor/skills/captcha-solve/.env.example .cursor/skills/captcha-solve/.env
# 填入 LOCATE_API_KEY、CAPTCHA_API_KEY（火山方舟）
```

用 Cursor 打开本仓库 → Settings → MCP 启用 `ghost-driver-mcp`（项目配置 `.cursor/mcp.json`，入口 `scripts/run-mcp-stdio.sh`）。Chrome 会在首次浏览器工具调用时自动拉起。

同目录 skill（`.cursor/skills/`）：

| Skill | 用途 |
| --- | --- |
| `screen-locate` | 截图 + 自然语言 → 点击坐标（UI-TARS） |
| `captcha-solve` | 验证码看图 → 可执行 click/drag 方案 |
| `xhs-wenchuang-search` | 小红书文创拟人浏览 |
| `debug-dev-env` | Chrome / MCP 启停与排错 |

### 开发与调试

```bash
npm run build
npm test                    # 单元测试（含 src/guard/ 守卫逻辑）
npm run test:integration    # MCP stdio 契约
bash scripts/launch-chrome.sh
```