---
name: screen-locate
description: 基于 UI-TARS 视觉模型定位截图中的 UI 元素，按自然语言指令返回可点击坐标（归一化/图片像素/屏幕物理三种）。当需要在截图或设备屏幕上找到按钮、图标、文字的 x,y 坐标用于点击时使用，如手机自动化、adb tap、Playwright click、GUI 操作。
disable-model-invocation: true
---
# 屏幕定位技能 — Screen Locate

输入截图 + 自然语言指令，输出目标元素坐标，供后续 tap/click 使用。

## 配置（首次）

```bash
cp .agents/skills/screen-locate/.env.example .agents/skills/screen-locate/.env
# 填入 LOCATE_API_KEY，其余有默认值，详见 .env.example
```

## 调用

```bash
uv run .agents/skills/screen-locate/scripts/locate.py \
  --image screenshot.png --instruction "点击搜索按钮"
```

`--screen-width W --screen-height H` 成对传入设备物理分辨率时，额外返回屏幕坐标（用于 adb tap）。调试可加 `--annotate out.png --verbose`。

## 输出与选坐标

stdout 输出 JSON，`coordinates` 含三种坐标，按场景选用：

| 坐标           | 何时用                                            |
| ------------ | ---------------------------------------------- |
| `image`      | 截图与屏幕 1:1（默认首选，直接点击截图坐标）                       |
| `screen`     | 截图有缩放，需传 `--screen-width/height`；为 `null` 表示未传 |
| `normalized` | 跨分辨率复用、调试（模型原始 0–1000 坐标）                      |

```json
{ "found": true,
  "image_size": {"width": 1080, "height": 2400},
  "coordinates": {
    "normalized": {"x": 850, "y": 120},
    "image": {"x": 918, "y": 288},
    "screen": {"x": 918, "y": 288} } }
```

屏幕物理尺寸不由 skill 探测，由调用方传入（调用自动化工具时已知分辨率）。

Exit code：`0` 成功 / `1` 未解析到坐标 / `2` 配置或 API 错误。

***

## 可选：配合 ghost-driver-mcp（浏览器自动化）

本节**仅在与 ghost-driver-mcp MCP 联用、且任务涉及真实 Chrome 浏览器时**参考。\
截图来源仍是「一张图 + 一条指令」；`locate.py` 的入参、出参、坐标含义**与上文完全相同**，不因是否使用 MCP 而改变。

未配置 MCP、或截图来自 adb / 手工保存 / 其他工具时，**忽略本节**，按「配置 → 调用 → 输出与选坐标」即可。

### 分工

| 能力                                      | 谁负责                                                        |
| --------------------------------------- | ---------------------------------------------------------- |
| 截图、元数据（视口 CSS 尺寸、`device_scale_factor`） | MCP `take_screenshot`                                      |
| 在截图上按自然语言找元素坐标                          | 本 skill `locate.py`（不变）                                    |
| 拟人点击、输入、滚动                              | MCP `physical_click` / `physical_type` / `physical_scroll` |
| 打开 URL、切换标签                             | MCP `browser_navigate` / `list_tabs` / `select_tab`        |

### 推荐循环（看图 → 定位 → 操作）

1. （按需）`browser_navigate` 打开目标页，等待页面稳定。

2. `take_screenshot`：响应含 **image 块**（base64）与 **text 块**（JSON 元数据）。将 image 存为本地文件（如 `.debug/shots/step.png`）。

3. 用存下的文件调用本 skill（与上文「调用」相同）：

   ```bash
   uv run .agents/skills/screen-locate/scripts/locate.py \
     --image .debug/shots/step.png --instruction "点击搜索输入框"
   ```

4. 取 stdout 中 `coordinates.image` 的 `x`、`y`（**图片像素坐标**）。

5. 从 `take_screenshot` 元数据读取 `device_scale_factor`，换算为 MCP 所需的 **CSS 像素**：

   ```
   css_x = round(image_x / device_scale_factor)
   css_y = round(image_y / device_scale_factor)
   ```

6. `physical_click(x=css_x, y=css_y)`；需输入时先点输入框再 `physical_type`。

7. 页面变化后回到步骤 2，对新截图重新定位（不要复用旧坐标）。

### 坐标选用说明（与核心表的关系）

配合 MCP 时，**定位仍用** **`coordinates.image`**；换算后的 CSS 坐标只交给 `physical_click`，不写入 `locate.py` 参数。

Retina / 高 DPR 屏常见 `device_scale_factor = 2`（例：`image_px` 3840×1742、`viewport_css` 1920×871）。未做换算会导致点击偏移。

一般**不需要**向 `locate.py` 传 `--screen-width/height`：截图与 MCP 视口同源，`image` 坐标经 `device_scale_factor` 换算即可。

### 与本 skill 内置能力的选择

* **优先本 skill（UI-TARS）**：页面结构复杂、A11y 树不足、或需按视觉描述找元素时。

* **可跳过本 skill**：目标在 A11y 树中已有清晰 `role`+`name`+坐标时，可直接 `get_page_accessibility_tree` → `physical_click`（更快，仍走 MCP）。

两种路径互斥于**单次定位**，不因本节而强制走 MCP 或强制走 UI-TARS。

### 失败与重试

* `locate.py` exit `1`（`found: false`）：换更具体的 instruction，或重新 `take_screenshot` 后再定位。

* 点击后页面无预期变化：重新截图定位，勿沿用旧坐标。

* `take_screenshot` 的 `truncated: true`：图片可能被截断，定位不可靠，应缩小页面或调大 `max_bytes` 后重截。

