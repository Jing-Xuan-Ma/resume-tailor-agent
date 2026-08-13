# lifeattiktok（TikTok Careers）

**仅当** URL 含 `lifeattiktok.com` 时采用本包。其它站点禁止套用。

机器配置见 [sites.json](sites.json) 键 `lifeattiktok`。

## 场景

- 注册页：`https://lifeattiktok.com/create-account`
- 点 Create 后弹出同形点选：`Select 2 objects that are the same shape`
- 题型：`same_shape_click`（3D 物体，点两个同形 → Confirm）

## A11y 特征

| 节点 | 说明 |
|------|------|
| `dialog` | 题干 + Refresh / Report / Confirm 文案常在 name 里 |
| `image`（webp/jpg 名） | puzzle 图，用中心+宽高算 origin |
| `Refresh` | 通常有 button/link |
| `Confirm` | **禁用时常不进树**；启用后可能出现 |

Confirm 名：`Confirm`。Refresh 名：`Refresh`。

## Confirm 预锁策略（本站）

1. A11y 有 Confirm → 用中心点（通用）
2. 无 Confirm → 允许本站包：`--site lifeattiktok` 或 `--url <当前URL>`  
   → `footer_primary`：`(dialog.right - 50, Refresh.y)`
3. 禁止：solve 后色值扫按钮、把某次分辨率下的像素当常量

## 预锁示例

```bash
uv run .agents/skills/captcha-solve/scripts/prelock_controls.py \
  --url "https://lifeattiktok.com/create-account" \
  --puzzle-x <cx> --puzzle-y <cy> --puzzle-w 340 --puzzle-h 212 \
  --refresh-x <cx> --refresh-y <cy> \
  --dialog-x <cx> --dialog-y <cy> --dialog-w 380 --dialog-h 372
# URL 命中后自动套用本包；若 A11y 已有 Confirm，仍优先 --confirm-x/y
```

## 实战备注

- MCP 验证码会话建议 `COOLDOWN_MIN_MS=200` / `MAX=600` / `PACING_ENABLED=0`
- 单次 `physical_click`≈1.3–2.5s；solve 后禁止再探，立刻 burst
- 失败变新题 → 整题重来，勿复用 puzzle 坐标（控件预锁可保留若弹层未关）
