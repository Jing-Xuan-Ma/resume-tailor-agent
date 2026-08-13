# 站点实战包（references）

存放**已验证站点**的验证码经验。通用流程见上级 [SKILL.md](../SKILL.md)。

## 选用规则（Agent 必守）

```
1. 看当前页 URL
2. 若命中 sites.json 某条目的 url_includes → 读对应 *.md，预锁时带 --url 或 --site <id>
3. 未命中 → 只走通用（A11y Confirm）；禁止套用任一站点包
```

**有站点包：优先用该包的 Confirm 缺失策略 / 题型提示。**  
**无站点包：绝不猜测，只 A11y + 通用 solve。**

## 目录

| 文件 | 用途 |
|------|------|
| `sites.json` | 机器可读：URL 匹配、fallback、inset、doc |
| `*.md` | 人读实战：题型、预锁、踩坑 |
| `README.md` | 本说明 |

## 新增站点

1. 写 `references/<site_id>.md`（题型、A11y 特征、Confirm 缺失时怎么办、实测备注）
2. 在 `sites.json` 加条目：`url_includes` / `fallback` / `inset` / `doc` / `assumption`
3. 用真实 URL 跑一遍 `prelock_controls.py --url …` 确认 `matched_site` 正确

不要把站点像素常量写进 SKILL 通用铁律。
