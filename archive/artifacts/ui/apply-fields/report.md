# Apply Profile/ATS Fields — Editable Scan List Report

**Date:** 2026-08-05  
**Status:** PASS

## Problem

三色「即将提交的信息清单」只做分类展示：黄/红不可编辑，Profile 长列表只能滚动，扫描动作对用户不可见。

## Shipped

### P0
| Item | Implementation |
|------|----------------|
| 统一可编辑字段行 | `frontend/components/apply-field-editor.tsx` — `FieldCardRow` |
| 绿：默认收起 + 编辑✎ | auto 摘要行，点编辑展开 |
| 黄：默认展开 + ✓确认无误 | review 输入/下拉，确认后转绿 |
| 红：默认空输入框 | empty 直接可填；长文走 modal |
| 扫描状态条 | `ScanBanner`：字段总数 / 已匹配 / 待核对 / 缺失 + 重新扫描 |

### P1
| Item | Implementation |
|------|----------------|
| Profile 分组折叠 | 基本信息 / 链接类 / 工作资格 / 其他 |
| 组内分页 | 单组 >5 项时上一页/下一页 |
| 缺失字段沉淀 Profile | blur/选完后 toast → `PUT /profile/{id}/library` 或「仅本次」 |

### Preserved
- `fill-tier-auto|review|empty` testids（UI gate 兼容）
- Pause-before-submit / 从不自动 Submit
- Resume / Pause 步骤仍为简要只读清单

## Self-test

```
pytest tests/test_apply_field_persist.py tests/test_iter6_auto_apply.py  → 5 passed
node artifacts/ui/apply-fields/helpers.selftest.js                       → OK
npx tsc --noEmit                                                         → clean
```

## How to try

1. Confirm 简历 → Auto Apply → 看扫描 banner  
2. Profile 步：展开「基本信息」，编辑黄/红字段  
3. 填空字段后失焦 → 选「保存到 Profile」  
4. 「即将提交的信息清单」三列均可操作（绿可纠错）
