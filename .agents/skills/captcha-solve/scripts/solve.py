#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "openai>=1.0",
#     "Pillow>=10.0",
#     "python-dotenv>=1.0",
# ]
# ///
"""
通用验证码方案技能 — 火山方舟视觉模型识别验证码并输出有序 action。

只出方案，不操作浏览器。上层 Agent + MCP 负责执行。

用法:
  uv run .agents/skills/captcha-solve/scripts/solve.py \
      --image .debug/shots/captcha.png \
      --hint "选择两个形状相同的物体" \
      --annotate .debug/shots/captcha-annotated.png
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

load_dotenv(SKILL_DIR / ".env")
_cwd_skill = Path.cwd() / ".cursor" / "skills" / SKILL_DIR.name
if _cwd_skill != SKILL_DIR and (_cwd_skill / ".env").exists():
    load_dotenv(_cwd_skill / ".env", override=True)
# 兼容从仓库根或 skill 目录调用时的另一常见相对路径
_alt = Path.cwd() / "skills" / SKILL_DIR.name
if _alt != SKILL_DIR and (_alt / ".env").exists():
    load_dotenv(_alt / ".env", override=True)

CAPTCHA_PROMPT = """你是验证码视觉解题助手。根据截图给出「可执行操作方案」，供自动化程序点击/拖拽/输入。
你只输出方案，不要声称已经点击。

## 任务
1. 读出验证码题干（instruction_text）。
2. 判断题型 captcha_type，取值之一：
   same_shape_click | icon_click | grid_select | slider | text_input | rotate | other
3. 按完成验证码所需的**真实顺序**列出 actions。
4. 所有点击/拖拽坐标使用归一化坐标系：左上 (0,0)，右下 (1000,1000)，格式必须为 <point>x y</point>（整数）。
5. 点选类：每个**谜题图内**目标一个 click。不要输出 Confirm/Refresh/关闭 等弹层控件坐标
   （它们在 puzzle 裁切外；由调用方用 A11y/几何预锁，不在本 JSON）。
6. 滑动类：一个 drag，含 start_point 与 end_point（均在图内）。
7. 文字类：一个 type，content 为识别出的字符（不含空格除非题面要求）。

## 输出格式（严格）
先用简短中文写 1–3 句 rationale，然后给出**唯一**一段 JSON（不要 markdown 围栏外的其它 JSON）：

```json
{{
  "captcha_type": "same_shape_click",
  "instruction_text": "题干原文",
  "confidence": 0.0,
  "crowded": false,
  "rationale": "简短理由",
  "actions": [
    {{
      "type": "click",
      "order": 1,
      "label": "目标简短描述",
      "point": "<point>253 680</point>"
    }},
    {{
      "type": "drag",
      "order": 1,
      "label": "滑块轨迹",
      "start_point": "<point>120 800</point>",
      "end_point": "<point>720 800</point>"
    }},
    {{
      "type": "type",
      "order": 1,
      "label": "验证码文本",
      "content": "AB12"
    }}
  ]
}}
```

规则：
- confidence 为 0~1。
- 可选字段 crowded：目标是否明显拥挤/重叠/难辨（true/false），供调用方决定是否换题。
- click 必须有 point；drag 必须有 start_point/end_point；type 必须有 content。
- 点选类 actions **只含谜题目标**，不要带 Confirm/提交/Refresh。
- 不要输出与解题无关的坐标。
- 若无法判断，仍输出 JSON，actions 为空数组，confidence 取低值并在 rationale 说明原因。

{hint_block}
"""

CONFIRM_LABEL_RE = re.compile(r"confirm|确认|提交|submit|verify|验证", re.I)
# 归一化坐标系下，两目标中心距小于此值视为「挨得太近」
CLOSE_TARGET_DIST = 80
LOW_CONFIDENCE = 0.75


def _env(key: str, fallback: str = "") -> str:
    return os.environ.get(key, fallback)


def _env_int(key: str, fallback: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return fallback
    try:
        return int(val)
    except ValueError:
        return fallback


def _env_float(key: str, fallback: float) -> float:
    val = os.environ.get(key)
    if val is None:
        return fallback
    try:
        return float(val)
    except ValueError:
        return fallback


def image_to_base64(image_path: Path) -> str:
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def get_image_mime_type(image_path: Path) -> str:
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return mime_types.get(image_path.suffix.lower(), "image/png")


def parse_point(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    match = re.search(r"<point>\s*(\d+)\s+(\d+)\s*</point>", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    # 容忍 "253 680" / "253,680"
    match = re.search(r"(\d+)\s*[, ]\s*(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start : i + 1]
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    return None
    return None


def fallback_points_as_clicks(raw: str) -> list[dict[str, Any]]:
    points = re.findall(r"<point>\s*(\d+)\s+(\d+)\s*</point>", raw)
    actions: list[dict[str, Any]] = []
    for idx, (x, y) in enumerate(points, start=1):
        actions.append(
            {
                "type": "click",
                "order": idx,
                "label": f"point_{idx}",
                "point": f"<point>{x} {y}</point>",
            }
        )
    return actions


def normalized_to_image(
    norm_x: int,
    norm_y: int,
    image_width: int,
    image_height: int,
    scale: int,
) -> tuple[int, int]:
    x = int((norm_x / scale) * image_width)
    y = int((norm_y / scale) * image_height)
    return x, y


def image_to_screen(
    image_x: int,
    image_y: int,
    image_width: int,
    image_height: int,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    x = int(image_x * screen_width / image_width)
    y = int(image_y * screen_height / image_height)
    return x, y


def build_coord_bundle(
    norm: tuple[int, int],
    *,
    image_width: int,
    image_height: int,
    coordinate_scale: int,
    screen_width: int | None,
    screen_height: int | None,
) -> dict[str, Any]:
    img_x, img_y = normalized_to_image(
        norm[0], norm[1], image_width, image_height, coordinate_scale
    )
    coords: dict[str, Any] = {
        "normalized": {"x": norm[0], "y": norm[1]},
        "image": {"x": img_x, "y": img_y},
        "screen": None,
    }
    if screen_width is not None and screen_height is not None:
        scr_x, scr_y = image_to_screen(
            img_x, img_y, image_width, image_height, screen_width, screen_height
        )
        coords["screen"] = {"x": scr_x, "y": scr_y}
    return coords


def normalize_actions(
    parsed: dict[str, Any] | None,
    raw: str,
    *,
    image_width: int,
    image_height: int,
    coordinate_scale: int,
    screen_width: int | None,
    screen_height: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {
        "captcha_type": "other",
        "instruction_text": "",
        "confidence": 0.0,
        "rationale": "",
        "crowded": None,
    }
    raw_actions: list[dict[str, Any]] = []

    if parsed:
        meta["captcha_type"] = str(parsed.get("captcha_type") or "other")
        meta["instruction_text"] = str(parsed.get("instruction_text") or "")
        try:
            meta["confidence"] = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            meta["confidence"] = 0.0
        meta["rationale"] = str(parsed.get("rationale") or "")
        if "crowded" in parsed:
            meta["crowded"] = bool(parsed.get("crowded"))
        maybe = parsed.get("actions")
        if isinstance(maybe, list):
            raw_actions = [a for a in maybe if isinstance(a, dict)]

    if not raw_actions:
        raw_actions = fallback_points_as_clicks(raw)
        if raw_actions and not meta["rationale"]:
            meta["rationale"] = "从模型文本中回退解析 <point> 标签"
            meta["confidence"] = max(meta["confidence"], 0.4)

    actions: list[dict[str, Any]] = []
    for idx, item in enumerate(raw_actions, start=1):
        action_type = str(item.get("type") or "click").lower().strip()
        order = item.get("order", idx)
        try:
            order_i = int(order)
        except (TypeError, ValueError):
            order_i = idx
        label = str(item.get("label") or f"{action_type}_{order_i}")
        base: dict[str, Any] = {
            "type": action_type,
            "order": order_i,
            "label": label,
        }

        if action_type == "type":
            content = item.get("content")
            if content is None:
                continue
            base["content"] = str(content)
            actions.append(base)
            continue

        if action_type == "wait":
            base["seconds"] = float(item.get("seconds") or 1.0)
            actions.append(base)
            continue

        if action_type == "drag":
            start = parse_point(
                str(item.get("start_point") or item.get("start") or "")
            )
            end = parse_point(str(item.get("end_point") or item.get("end") or ""))
            if not start or not end:
                continue
            base["start"] = build_coord_bundle(
                start,
                image_width=image_width,
                image_height=image_height,
                coordinate_scale=coordinate_scale,
                screen_width=screen_width,
                screen_height=screen_height,
            )
            base["end"] = build_coord_bundle(
                end,
                image_width=image_width,
                image_height=image_height,
                coordinate_scale=coordinate_scale,
                screen_width=screen_width,
                screen_height=screen_height,
            )
            actions.append(base)
            continue

        # default: click
        point = parse_point(str(item.get("point") or item.get("target") or ""))
        if not point:
            continue
        base["type"] = "click"
        base["coordinates"] = build_coord_bundle(
            point,
            image_width=image_width,
            image_height=image_height,
            coordinate_scale=coordinate_scale,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        actions.append(base)

    actions.sort(key=lambda a: a.get("order", 0))
    return actions, meta


def _is_confirm_action(action: dict[str, Any]) -> bool:
    return bool(CONFIRM_LABEL_RE.search(str(action.get("label") or "")))


def _click_norm_points(actions: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Puzzle 目标点（排除 Confirm 类），用于拥挤度估计。"""
    pts: list[tuple[int, int]] = []
    for action in actions:
        if action.get("type") != "click" or not action.get("coordinates"):
            continue
        if _is_confirm_action(action):
            continue
        n = action["coordinates"]["normalized"]
        pts.append((int(n["x"]), int(n["y"])))
    return pts


def min_pairwise_distance(points: list[tuple[int, int]]) -> float | None:
    if len(points) < 2:
        return None
    best = float("inf")
    for i in range(len(points)):
        x1, y1 = points[i]
        for j in range(i + 1, len(points)):
            x2, y2 = points[j]
            dist = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
            if dist < best:
                best = dist
    return best if best != float("inf") else None


def strip_confirm_actions(
    actions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """模型若误带 Confirm，从可执行 actions 剔除（坐标相对 puzzle，不可用）。"""
    kept: list[dict[str, Any]] = []
    discarded: list[dict[str, Any]] = []
    for action in actions:
        if action.get("type") == "click" and _is_confirm_action(action):
            discarded.append(action)
            continue
        kept.append(action)
    for i, action in enumerate(kept, start=1):
        action["order"] = i
    return kept, discarded


def needs_external_confirm(captcha_type: str, actions: list[dict[str, Any]]) -> bool:
    """点选类默认需要弹层 Confirm；slider/text 通常不需要。"""
    if captcha_type in {"slider", "text_input", "rotate"}:
        return False
    return any(a.get("type") == "click" for a in actions)


def build_advice(
    actions: list[dict[str, Any]],
    *,
    confidence: float,
    crowded: bool | None,
    captcha_type: str,
    discarded_confirm: list[dict[str, Any]],
) -> dict[str, Any]:
    pts = _click_norm_points(actions)
    min_dist = min_pairwise_distance(pts)
    reasons: list[str] = []

    if confidence < LOW_CONFIDENCE:
        reasons.append("low_confidence")
    if min_dist is not None and min_dist < CLOSE_TARGET_DIST:
        reasons.append("targets_too_close")
    if crowded is True:
        reasons.append("model_marked_crowded")

    recommend_refresh = len(reasons) > 0
    confirm_required = needs_external_confirm(captcha_type, actions)
    return {
        "recommend_refresh_before_click": recommend_refresh,
        "reasons": reasons,
        "min_click_distance_normalized": (
            None if min_dist is None else round(min_dist, 1)
        ),
        "close_target_threshold": CLOSE_TARGET_DIST,
        "low_confidence_threshold": LOW_CONFIDENCE,
        "execute_mode": "burst_then_verify",
        "prefer_puzzle_crop": True,
        "pacing": {
            "note": "验证码：识别可慢，动作要连点；中间禁止逐步截图/a11y",
            "inter_action_ms_hint": "300-800",
            "cooldown_env_hint": "COOLDOWN_MIN_MS=200 COOLDOWN_MAX_MS=600",
            "max_ms_solve_to_first_click": 2000,
        },
        "refresh_max_per_dialog": 2,
        # 外层契约：Confirm 不在本 JSON；通用走 A11y，几何兜底须显式 fallback/site
        "controls": {
            "confirm": {
                "required": confirm_required,
                "in_actions": False,
                "in_this_json": False,
                "use_model_point": False,
                "prelock": "scripts/prelock_controls.py",
                "preferred": "a11y --confirm-x/y",
                "site_packs": "references/sites.json；URL 命中时 --url 优先用站点包",
                "optional_fallback": "--fallback footer_primary（无站点包时的显式退路）",
                "confirm_name_hints": [
                    "Confirm",
                    "Submit",
                    "Verify",
                    "Continue",
                    "确认",
                    "提交",
                    "验证",
                    "确定",
                ],
                "note": (
                    "Confirm 在 puzzle 裁切外；本 JSON 无其坐标。"
                    "通用：A11y 预锁。站点经验在 references/，仅 URL 命中采用。"
                    "模型若输出 Confirm 点已丢弃。"
                ),
                "model_confirm_discarded": len(discarded_confirm) > 0,
            },
            "refresh": {
                "in_this_json": False,
                "source": "a11y_prelock",
                "refresh_name_hints": [
                    "Refresh",
                    "Reload",
                    "换一张",
                    "刷新",
                    "重试",
                ],
                "note": "换题用；solve 前从 A11y 取坐标（有则预锁）。",
            },
        },
        "agent_contract": {
            "actions_scope": "puzzle_targets_only",
            "burst_order": (
                ["actions_by_order", "confirm_prelocked"]
                if confirm_required
                else ["actions_by_order"]
            ),
            "post_solve_forbidden": [
                "get_page_accessibility_tree",
                "take_screenshot",
                "color_locate_confirm",
                "read_annotate_before_click",
            ],
            "css_mapping": (
                "puzzle_origin_css + image_coord / device_scale_factor"
            ),
        },
    }


def draw_annotations(image_path: Path, actions: list[dict[str, Any]], output_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for action in actions:
        if action.get("type") == "click" and action.get("coordinates"):
            x = action["coordinates"]["image"]["x"]
            y = action["coordinates"]["image"]["y"]
            r = 28
            draw.ellipse([x - r, y - r, x + r, y + r], outline="red", width=4)
            tag = str(action.get("order", ""))
            if font:
                draw.text((x + r + 4, y - r), tag, fill="red", font=font)
            else:
                draw.text((x + r + 4, y - r), tag, fill="red")
        elif action.get("type") == "drag" and action.get("start") and action.get("end"):
            x1 = action["start"]["image"]["x"]
            y1 = action["start"]["image"]["y"]
            x2 = action["end"]["image"]["x"]
            y2 = action["end"]["image"]["y"]
            draw.line([(x1, y1), (x2, y2)], fill="red", width=4)
            draw.ellipse([x1 - 12, y1 - 12, x1 + 12, y1 + 12], outline="red", width=3)
            draw.ellipse([x2 - 12, y2 - 12, x2 + 12, y2 + 12], outline="orange", width=3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def call_model(
    image_path: Path,
    *,
    hint: str,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    with Image.open(image_path) as img:
        width, height = img.size

    hint_block = ""
    if hint.strip():
        hint_block = f"## 调用方提示（优先参考）\n{hint.strip()}\n"

    prompt = CAPTCHA_PROMPT.format(hint_block=hint_block)
    img_b64 = image_to_base64(image_path)
    mime = get_image_mime_type(image_path)

    client = OpenAI(api_key=api_key, base_url=base_url)
    print(
        f"!7LOG! captcha-solve call model={model} image={image_path} "
        f"size={width}x{height} hint_len={len(hint.strip())}",
        file=sys.stderr,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{img_b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    raw = response.choices[0].message.content or ""
    print(f"!7LOG! captcha-solve raw_len={len(raw)}", file=sys.stderr)
    return {
        "raw_response": raw,
        "image_size": {"width": width, "height": height},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="通用验证码方案技能")
    ap.add_argument("--image", required=True, help="验证码截图路径")
    ap.add_argument("--hint", default="", help="题干/提示，可选但推荐")
    ap.add_argument("--screen-width", type=int, default=None)
    ap.add_argument("--screen-height", type=int, default=None)
    ap.add_argument("--annotate", default="", help="标注图输出路径")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(
            json.dumps(
                {"success": False, "found": False, "error": f"图片不存在: {image_path}"},
                ensure_ascii=False,
            )
        )
        sys.exit(2)

    if (args.screen_width is None) ^ (args.screen_height is None):
        print(
            json.dumps(
                {
                    "success": False,
                    "found": False,
                    "error": "--screen-width 和 --screen-height 必须同时提供",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(2)

    api_key = _env("CAPTCHA_API_KEY") or _env("ARK_API_KEY") or _env("LOCATE_API_KEY")
    if not api_key:
        print(
            json.dumps(
                {
                    "success": False,
                    "found": False,
                    "error": "未配置 CAPTCHA_API_KEY（也可回退 ARK_API_KEY / LOCATE_API_KEY）",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(2)

    base_url = _env("CAPTCHA_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    # 默认名仅作占位；方舟控制台以实际 Model/接入点 ID 为准（你截图验证过的 Doubao-Seed-2.1-pro 一类）
    model = _env("CAPTCHA_MODEL", "doubao-seed-2-1-pro-250628")
    max_tokens = _env_int("CAPTCHA_MAX_TOKENS", 1024)
    temperature = _env_float("CAPTCHA_TEMPERATURE", 0.1)
    coordinate_scale = _env_int("CAPTCHA_COORDINATE_SCALE", 1000)

    start = time.time()
    try:
        locate_result = call_model(
            image_path,
            hint=args.hint,
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as exc:
        print(
            json.dumps(
                {"success": False, "found": False, "error": str(exc)},
                ensure_ascii=False,
            )
        )
        sys.exit(2)

    raw = locate_result["raw_response"]
    if args.verbose:
        print(raw, file=sys.stderr)

    parsed = extract_json_object(raw)
    actions, meta = normalize_actions(
        parsed,
        raw,
        image_width=locate_result["image_size"]["width"],
        image_height=locate_result["image_size"]["height"],
        coordinate_scale=coordinate_scale,
        screen_width=args.screen_width,
        screen_height=args.screen_height,
    )
    actions, discarded_confirm = strip_confirm_actions(actions)
    if discarded_confirm:
        print(
            f"!7LOG! captcha-solve discarded_model_confirm n={len(discarded_confirm)} "
            f"(puzzle-relative Confirm points are unusable)",
            file=sys.stderr,
        )

    found = any(
        a.get("type") in {"click", "drag", "type"}
        and (a.get("coordinates") or a.get("start") or a.get("content") is not None)
        for a in actions
    )

    advice = build_advice(
        actions,
        confidence=float(meta["confidence"]),
        crowded=meta.get("crowded"),
        captcha_type=str(meta["captcha_type"]),
        discarded_confirm=discarded_confirm,
    )
    print(
        f"!7LOG! captcha-solve advice refresh={advice['recommend_refresh_before_click']} "
        f"reasons={advice['reasons']} min_dist={advice['min_click_distance_normalized']} "
        f"confirm_required={advice['controls']['confirm']['required']}",
        file=sys.stderr,
    )

    result: dict[str, Any] = {
        "success": True,
        "found": found,
        "captcha_type": meta["captcha_type"],
        "instruction_text": meta["instruction_text"],
        "confidence": meta["confidence"],
        "rationale": meta["rationale"],
        "crowded": meta.get("crowded"),
        "image_size": locate_result["image_size"],
        "coordinate_scale": coordinate_scale,
        "actions": actions,
        "advice": advice,
        "raw_response": raw,
        "elapsed_time": round(time.time() - start, 2),
    }
    if args.screen_width is not None and args.screen_height is not None:
        result["screen_size"] = {
            "width": args.screen_width,
            "height": args.screen_height,
        }
    else:
        result["screen_size"] = None

    if not found:
        result["error"] = "未能解析出可执行 action，请检查 raw_response 或补充 --hint"

    if args.annotate and found:
        out = Path(args.annotate)
        draw_annotations(image_path, actions, out)
        result["annotated_image"] = str(out)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if found else 1)


if __name__ == "__main__":
    main()
