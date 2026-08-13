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
屏幕元素定位技能 — 基于 UI-TARS 视觉模型定位截图中的 UI 元素

输入：截图 + 自然语言指令
输出：归一化坐标 / 图片像素坐标 / 屏幕物理坐标（可选）

用法:
  uv run .agents/skills/screen-locate/scripts/locate.py \
      --image /path/to/screenshot.png \
      --instruction "点击搜索按钮"

  # 传入物理屏幕尺寸，同时输出 screen 坐标（用于 adb tap 等）
  uv run .agents/skills/screen-locate/scripts/locate.py \
      --image screenshot.png \
      --instruction "点击设置图标" \
      --screen-width 1080 --screen-height 2400
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

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent

load_dotenv(SKILL_DIR / ".env")
_skill_env = SKILL_DIR / ".env"
for rel in (
    Path(".agents") / "skills" / SKILL_DIR.name,
    Path(".cursor") / "skills" / SKILL_DIR.name,
    Path("skills") / SKILL_DIR.name,
):
    p = Path.cwd() / rel / ".env"
    if p.exists() and p.resolve() != _skill_env.resolve():
        load_dotenv(p, override=True)

MOBILE_USE_PROMPT = """You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task.

## Output Format
```
Thought: ...
Action: ...
```

## Action Space

click(point='<point>x1 y1</point>')
left_double(point='<point>x1 y1</point>')
right_single(point='<point>x1 y1</point>')
drag(start_point='<point>x1 y1</point>', end_point='<point>x2 y2</point>')
hotkey(key='ctrl c') # Split keys with a space and use lowercase. Also, do not use more than 3 keys in one hotkey action.
type(content='xxx') # Use escape characters \\', \\\", and \\n in content part to ensure we can parse the content in normal python string format. If you want to submit your input, use \\n at the end of content.
scroll(point='<point>x1 y1</point>', direction='down or up or right or left') # Show more information on the `direction` side.
wait() #Sleep for 5s and take a screenshot to check for any changes.
finished(content='xxx') # Use escape characters \\', \\", and \\n in content part to ensure we can parse the content in normal python string format.


## Note
- Use {language} in `Thought` part.
- Write a small plan and finally summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
{instruction}
"""


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


def parse_action_point(response: str) -> tuple[int, int] | None:
    """Parse <point>x y</point> from model response."""
    match = re.search(r"<point>(\d+)\s+(\d+)</point>", response)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def parse_thought(response: str) -> str | None:
    match = re.search(r"Thought:\s*(.+?)(?:\nAction:|\Z)", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def parse_action_type(response: str) -> str | None:
    match = re.search(r"Action:\s*(\w+)", response)
    if match:
        return match.group(1)
    return None


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


def draw_annotation(image_path: Path, center: tuple[int, int], output_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    x, y = center
    box_size = 80
    half = box_size // 2
    left = max(0, x - half)
    top = max(0, y - half)
    right = min(image.width, x + half)
    bottom = min(image.height, y + half)
    for i in range(5):
        draw.rectangle([left + i, top + i, right - i, bottom - i], outline="red")
    cross = 10
    draw.line([(x - cross, y), (x + cross, y)], fill="red", width=2)
    draw.line([(x, y - cross), (x, y + cross)], fill="red", width=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def call_locate(
    image_path: Path,
    instruction: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    language: str,
    max_tokens: int,
) -> dict:
    with Image.open(image_path) as img:
        width, height = img.size

    img_base64 = image_to_base64(image_path)
    mime_type = get_image_mime_type(image_path)
    prompt = MOBILE_USE_PROMPT.format(language=language, instruction=instruction)

    client = OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{img_base64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        max_tokens=max_tokens,
    )

    raw = response.choices[0].message.content or ""
    return {
        "raw_response": raw,
        "image_size": {"width": width, "height": height},
    }


def build_result(
    instruction: str,
    locate_result: dict,
    *,
    coordinate_scale: int,
    screen_width: int | None,
    screen_height: int | None,
    elapsed_time: float,
) -> dict:
    raw = locate_result["raw_response"]
    image_size = locate_result["image_size"]
    norm_point = parse_action_point(raw)

    result: dict = {
        "success": True,
        "found": norm_point is not None,
        "instruction": instruction,
        "image_size": image_size,
        "coordinate_scale": coordinate_scale,
        "action": parse_action_type(raw),
        "thought": parse_thought(raw),
        "raw_response": raw,
        "elapsed_time": round(elapsed_time, 2),
    }

    if screen_width is not None and screen_height is not None:
        result["screen_size"] = {"width": screen_width, "height": screen_height}
    else:
        result["screen_size"] = None

    if not norm_point:
        result["coordinates"] = None
        result["error"] = "未能从模型响应中解析坐标，请检查 raw_response"
        return result

    norm_x, norm_y = norm_point
    img_x, img_y = normalized_to_image(
        norm_x, norm_y, image_size["width"], image_size["height"], coordinate_scale
    )

    coords: dict = {
        "normalized": {"x": norm_x, "y": norm_y},
        "image": {"x": img_x, "y": img_y},
        "screen": None,
    }

    if screen_width is not None and screen_height is not None:
        scr_x, scr_y = image_to_screen(
            img_x, img_y,
            image_size["width"], image_size["height"],
            screen_width, screen_height,
        )
        coords["screen"] = {"x": scr_x, "y": scr_y}

    result["coordinates"] = coords
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="屏幕元素定位技能")
    ap.add_argument("--image", required=True, help="截图路径")
    ap.add_argument("--instruction", required=True, help="定位指令，如「点击搜索按钮」")
    ap.add_argument("--screen-width", type=int, default=None, help="物理屏幕宽度（像素）")
    ap.add_argument("--screen-height", type=int, default=None, help="物理屏幕高度（像素）")
    ap.add_argument("--language", default=None, help="Thought 语言（默认读 .env）")
    ap.add_argument("--annotate", default="", help="保存标注图路径（可选）")
    ap.add_argument("--verbose", action="store_true", help="调试：stderr 输出原始响应")
    args = ap.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(json.dumps({"success": False, "error": f"图片不存在: {image_path}"}, ensure_ascii=False))
        sys.exit(2)

    if (args.screen_width is None) ^ (args.screen_height is None):
        print(json.dumps({
            "success": False,
            "error": "--screen-width 和 --screen-height 必须同时提供",
        }, ensure_ascii=False))
        sys.exit(2)

    api_key = _env("LOCATE_API_KEY")
    if not api_key:
        print(json.dumps({"success": False, "error": "未配置 LOCATE_API_KEY"}, ensure_ascii=False))
        sys.exit(2)

    base_url = _env("LOCATE_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    model = _env("LOCATE_MODEL", "ui-tars-72b")
    language = args.language or _env("LOCATE_LANGUAGE", "Chinese")
    max_tokens = _env_int("LOCATE_MAX_TOKENS", 512)
    coordinate_scale = _env_int("LOCATE_COORDINATE_SCALE", 1000)

    start = time.time()
    try:
        locate_result = call_locate(
            image_path,
            args.instruction,
            api_key=api_key,
            base_url=base_url,
            model=model,
            language=language,
            max_tokens=max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary, any failure becomes a JSON error
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(2)

    result = build_result(
        args.instruction,
        locate_result,
        coordinate_scale=coordinate_scale,
        screen_width=args.screen_width,
        screen_height=args.screen_height,
        elapsed_time=time.time() - start,
    )

    if args.verbose:
        print(result.get("raw_response", ""), file=sys.stderr)

    if args.annotate and result.get("found"):
        coords = result["coordinates"]["image"]
        draw_annotation(image_path, (coords["x"], coords["y"]), Path(args.annotate))
        result["annotated_image"] = args.annotate

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("found") else 1)


if __name__ == "__main__":
    main()
