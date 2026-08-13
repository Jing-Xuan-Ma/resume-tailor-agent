# captcha-solve 参考（字段）

主流程见 [SKILL.md](SKILL.md)。**站点实战**在 [references/](references/README.md)，不写在本文件。

## 选用顺序

1. URL ∈ `references/sites.json` → 读站点 `*.md`，预锁带 `--url`
2. 否则 → 仅通用 A11y Confirm
3. `actions` 永远只有谜题目标；Confirm 不在 solve JSON

## advice（节选）

```json
{
  "controls": {
    "confirm": {
      "required": true,
      "in_this_json": false,
      "preferred": "a11y --confirm-x/y",
      "site_packs": "references/sites.json + --url",
      "optional_fallback": "--fallback footer_primary（无站点包时的显式退路）"
    }
  },
  "agent_contract": {
    "actions_scope": "puzzle_targets_only",
    "burst_order": ["actions_by_order", "confirm_prelocked"],
    "post_solve_forbidden": [
      "get_page_accessibility_tree",
      "take_screenshot",
      "color_locate_confirm",
      "read_annotate_before_click"
    ]
  }
}
```

## captcha_type

| 类型 | 期望 |
|------|------|
| `same_shape_click` | 2+ puzzle click；Confirm 预锁 |
| `icon_click` / `grid_select` | 有序 click ± Confirm |
| `slider` | 1 `drag` |
| `text_input` | `type` |
| `other` | 看 `actions` + `confirm.required` |

## 预锁

```bash
uv run .agents/skills/captcha-solve/scripts/prelock_controls.py --list-sites
```

| 模式 | 条件 |
|------|------|
| 通用 | `--confirm-x/y` |
| 站点包 | `--url` 命中或 `--site <id>`（见 references） |
| 裸启发式 | `--fallback footer_primary`（无包时显式） |

## vs screen-locate

多点验证码用本 skill burst；单点普通 UI 用同目录 [screen-locate](../screen-locate/SKILL.md)。

## 裁图基建

`capture_puzzle.mjs` 秒退、勿 `browser.close()`。调试日志 stderr `!7LOG!`。
