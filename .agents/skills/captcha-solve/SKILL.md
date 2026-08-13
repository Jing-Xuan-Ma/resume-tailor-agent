---
name: captcha-solve
description: >-
  用火山方舟视觉模型识别通用网页验证码并输出可执行 action 方案（多点点击/拖拽/输入 + 归一化与图片像素坐标）。
  本 skill 只负责「看图 → 出方案」，不直接操作浏览器；由上层 Agent 配合 ghost-driver-mcp 执行。
  Use when encountering CAPTCHA / 验证码 / 点选验证 / 滑动验证 / 同形选择 / 图标点选,
  or when browser automation is blocked by a visual challenge that needs click/drag coordinates.
---

# 通用验证码方案 — Captcha Solve

`solve.py`：**看图 → JSON `actions` + `advice`**。点击/Refresh/Confirm/验收由上层 Agent + `ghost-driver-mcp` 完成。

**`actions` 只含谜题目标，不含 Confirm。** Confirm 在 solve 前预锁。

## 通用 + 站点包

```
URL 命中 references/sites.json？
  ├─ 是 → 读对应 references/*.md，预锁带 --url（优先用该站经验）
  └─ 否 → 只走通用（A11y Confirm）；禁止套用其它站几何
```

| | 通用（默认） | 站点包（`references/`） |
|--|-------------|-------------------------|
| 谜题点 | 裁图 + `solve.py` | 可附题型/hint 经验 |
| Confirm | A11y `--confirm-x/y` | 仅该站 URL 命中时可启用包内 fallback |
| 索引 | — | [references/README.md](references/README.md) |

Confirm 名提示：`Confirm` / `Submit` / `Verify` / `确认` / `提交` / `验证` / `确定`。

## 配置

```bash
cp .agents/skills/captcha-solve/.env.example .agents/skills/captcha-solve/.env
# CAPTCHA_API_KEY + CAPTCHA_MODEL（方舟 ep-… 或模型 ID）
```

```bash
uv run .agents/skills/captcha-solve/scripts/solve.py \
  --image .debug/shots/captcha-puzzle.png \
  --hint "Select 2 objects that are the same shape"
```

可选：`--annotate`（仅人眼调试）、`--verbose`。Exit：`0` 有方案 / `1` 未解析 / `2` 配置或 API 错。

## 标准闭环

```
0. list_tabs / URL → 查 references/sites.json；命中则打开对应 *.md
1. a11y 一次：puzzle；Confirm/Submit…；Refresh；dialog（可选）
2. prelock_controls.py
   - 通用：--confirm-x/y + puzzle
   - 命中站点且 Confirm 缺失：加 --url <当前URL>（自动套站点包）
   - ready_for_burst=true 才继续
3. capture_puzzle.mjs（capture_cli；秒退、不杀 Chrome）
4. solve.py → actions 仅谜题目标；此后禁止再探 Confirm
5. recommend_refresh 且 Refresh<2 → 预锁 Refresh → 回 1
6. burst：actions→CSS → confirm_css（solve→第一击 < 2s）
7. 点完后再截图/URL 验收；失败整题重来
```

### 预锁示例

```bash
# 列出已登记站点包
uv run .agents/skills/captcha-solve/scripts/prelock_controls.py --list-sites

# 通用
uv run .agents/skills/captcha-solve/scripts/prelock_controls.py \
  --puzzle-x <cx> --puzzle-y <cy> --puzzle-w <w> --puzzle-h <h> \
  --confirm-x <cx> --confirm-y <cy>

# 当前页在站点包内（Confirm 常缺失时）
uv run .agents/skills/captcha-solve/scripts/prelock_controls.py \
  --url "https://lifeattiktok.com/create-account" \
  --puzzle-x … --puzzle-y … --puzzle-w … --puzzle-h … \
  --refresh-x … --refresh-y … \
  --dialog-x … --dialog-y … --dialog-w … --dialog-h …
```

### 坐标

```
css = puzzle_origin_css + image_coord / device_scale_factor
# Confirm/Refresh：只用预锁值
```

## 铁律

1. **想得久、点得快**：solve 后 2s 内第一击。
2. **控件预锁**：solve 前写死；solve 后禁止再探。
3. **站点包仅 URL 命中时用**；未命中禁止套用。
4. **禁止逐步验收**；拥挤换题 Refresh≤2。
5. **验证码会话 cooldown**：

```json
"COOLDOWN_MIN_MS": "200",
"COOLDOWN_MAX_MS": "600",
"PACING_ENABLED": "0"
```

### 陷阱

| 陷阱 | 后果 |
|------|------|
| solve 后色值找 Confirm | 题轮换 |
| 未命中站点却套 lifeattiktok 几何 | 别站必偏 |
| solve 后还 a11y/annotate | 点得慢 |

## 分工

| 谁 | 做什么 |
|----|--------|
| Agent + MCP | 弹层、预锁、裁图、burst、验收 |
| `references/` | 站点实战包（URL 命中才用） |
| `prelock_controls.py` | puzzle/Confirm/Refresh CSS |
| `solve.py` | 谜题 actions + advice |
| A11y | Confirm/Refresh 首选 |

## 失败

- 变新题 → 重裁 + solve，勿复用 puzzle 坐标。
- `prelock` exit `1` → 补 A11y Confirm，或确认 URL 是否命中站点包。
- `solve` exit `1` → `--hint` / 检查裁切。

字段见 [reference.md](reference.md)；站点包见 [references/README.md](references/README.md)。
