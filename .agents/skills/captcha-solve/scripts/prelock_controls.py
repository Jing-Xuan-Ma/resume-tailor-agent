#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""
验证码控件预锁。

- 通用：A11y Confirm（--confirm-x/y）
- 站点包：references/sites.json；仅 URL 命中或显式 --site 时采用
- 布局启发式：--fallback（无站点包时的显式退路）

用法见 skill SKILL.md / references/README.md。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REFERENCES_DIR = SCRIPT_DIR.parent / "references"
SITES_JSON = REFERENCES_DIR / "sites.json"

FALLBACK_ASSUMPTIONS: dict[str, str] = {
    "footer_primary": (
        "假设 Confirm 为主按钮，位于 dialog（或 puzzle）右缘向内 inset，"
        "y 与 Refresh 中心同高。仅适用于「底栏左辅助、右确认」布局。"
    ),
}

CONFIRM_NAME_HINTS = [
    "Confirm",
    "Submit",
    "Verify",
    "Continue",
    "确认",
    "提交",
    "验证",
    "确定",
]
REFRESH_NAME_HINTS = ["Refresh", "Reload", "换一张", "刷新", "重试"]


def load_site_profiles() -> dict[str, dict[str, Any]]:
    if not SITES_JSON.is_file():
        return {}
    data = json.loads(SITES_JSON.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def match_site_by_url(url: str, profiles: dict[str, dict[str, Any]]) -> str | None:
    url_l = url.lower()
    for site_id, prof in profiles.items():
        needles = prof.get("url_includes") or []
        if not isinstance(needles, list):
            continue
        for n in needles:
            if str(n).lower() in url_l:
                return site_id
    return None


def box_from_center(cx: float, cy: float, w: float, h: float) -> dict[str, float]:
    left = cx - w / 2
    top = cy - h / 2
    return {
        "left": left,
        "top": top,
        "width": w,
        "height": h,
        "right": left + w,
        "bottom": top + h,
        "cx": cx,
        "cy": cy,
    }


def resolve_confirm(
    *,
    confirm_x: float | None,
    confirm_y: float | None,
    refresh_y: float | None,
    dialog_box: dict[str, float] | None,
    puzzle: dict[str, float],
    fallback: str | None,
    inset: float,
    site: str | None,
    site_assumption: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []

    if confirm_x is not None and confirm_y is not None:
        return (
            {
                "x": round(confirm_x, 2),
                "y": round(confirm_y, 2),
                "source": "a11y",
                "universal": True,
            },
            warnings,
        )

    if not fallback:
        return None, warnings

    if refresh_y is None:
        warnings.append("fallback_needs_refresh_y")
        return None, warnings

    assumption = site_assumption or FALLBACK_ASSUMPTIONS.get(
        fallback, "custom_fallback"
    )
    if fallback == "footer_primary":
        if dialog_box is not None:
            x = dialog_box["right"] - inset
            source = "fallback_footer_primary_dialog"
        else:
            x = puzzle["right"] - inset
            source = "fallback_footer_primary_puzzle"
            warnings.append("no_dialog_box_used_puzzle_right")
        return (
            {
                "x": round(x, 2),
                "y": round(refresh_y, 2),
                "source": source,
                "universal": False,
                "fallback": fallback,
                "site": site,
                "assumption": assumption,
                "inset": inset,
            },
            warnings,
        )

    warnings.append(f"unknown_fallback:{fallback}")
    return None, warnings


def main() -> None:
    profiles = load_site_profiles()
    p = argparse.ArgumentParser(
        description="预锁 captcha 控件：通用 A11y；站点包见 references/"
    )
    p.add_argument(
        "--list-sites",
        action="store_true",
        help="列出 references/sites.json 后退出",
    )
    p.add_argument("--puzzle-x", type=float, default=None)
    p.add_argument("--puzzle-y", type=float, default=None)
    p.add_argument("--puzzle-w", type=float, default=None)
    p.add_argument("--puzzle-h", type=float, default=None)
    p.add_argument("--refresh-x", type=float, default=None)
    p.add_argument("--refresh-y", type=float, default=None)
    p.add_argument("--dialog-x", type=float, default=None)
    p.add_argument("--dialog-y", type=float, default=None)
    p.add_argument("--dialog-w", type=float, default=None)
    p.add_argument("--dialog-h", type=float, default=None)
    p.add_argument("--confirm-x", type=float, default=None)
    p.add_argument("--confirm-y", type=float, default=None)
    p.add_argument(
        "--url",
        default=None,
        help="当前页 URL；命中 references/sites.json 时自动采用该站点包",
    )
    p.add_argument(
        "--site",
        choices=sorted(profiles.keys()) or None,
        default=None,
        help="显式站点包 id（须与 URL 场景一致；见 references/）",
    )
    p.add_argument(
        "--fallback",
        choices=sorted(FALLBACK_ASSUMPTIONS.keys()),
        default=None,
        help="无站点包时的显式布局启发式",
    )
    p.add_argument("--inset", type=float, default=None)
    args = p.parse_args()

    if args.list_sites:
        listing = []
        for sid, prof in profiles.items():
            listing.append(
                {
                    "site": sid,
                    "url_includes": prof.get("url_includes"),
                    "doc": prof.get("doc"),
                    "fallback": prof.get("fallback"),
                }
            )
        print(
            json.dumps(
                {"sites": listing, "dir": str(REFERENCES_DIR)},
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(0)

    if None in (args.puzzle_x, args.puzzle_y, args.puzzle_w, args.puzzle_h):
        p.error("--puzzle-x/y/w/h are required unless --list-sites")

    warnings: list[str] = []
    site = args.site
    fallback = args.fallback
    inset = args.inset
    site_assumption: str | None = None

    if args.url:
        matched_from_url = match_site_by_url(args.url, profiles)
        if matched_from_url:
            if site and site != matched_from_url:
                warnings.append(
                    f"url_matched_{matched_from_url}_overrides_explicit_site_{site}"
                )
            site = matched_from_url
            warnings.append(f"url_matched_site:{site}")
        else:
            warnings.append("url_no_site_pack_use_generic")

    site_doc = None
    if site:
        if site not in profiles:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": f"unknown_site:{site}",
                        "known": sorted(profiles.keys()),
                    },
                    ensure_ascii=False,
                )
            )
            sys.exit(2)
        prof = profiles[site]
        if fallback and fallback != prof.get("fallback"):
            warnings.append(
                f"site_{site}_overrides_fallback_to_{prof.get('fallback')}"
            )
        fallback = str(prof.get("fallback") or fallback or "") or None
        if inset is None and prof.get("inset") is not None:
            inset = float(prof["inset"])
        doc_name = prof.get("doc")
        if doc_name:
            site_doc = str((REFERENCES_DIR / str(doc_name)).as_posix())
        if prof.get("assumption"):
            site_assumption = str(prof["assumption"])
        warnings.append(f"site_pack_applied:{site}")

    if inset is None:
        inset = 50.0

    puzzle = box_from_center(
        float(args.puzzle_x),
        float(args.puzzle_y),
        float(args.puzzle_w),
        float(args.puzzle_h),
    )
    dialog_box = None
    if all(
        v is not None
        for v in (args.dialog_x, args.dialog_y, args.dialog_w, args.dialog_h)
    ):
        dialog_box = box_from_center(
            args.dialog_x, args.dialog_y, args.dialog_w, args.dialog_h
        )

    confirm, fb_warnings = resolve_confirm(
        confirm_x=args.confirm_x,
        confirm_y=args.confirm_y,
        refresh_y=args.refresh_y,
        dialog_box=dialog_box,
        puzzle=puzzle,
        fallback=fallback,
        inset=inset,
        site=site,
        site_assumption=site_assumption,
    )
    warnings.extend(fb_warnings)

    refresh_css = None
    if args.refresh_x is not None and args.refresh_y is not None:
        refresh_css = {
            "x": round(args.refresh_x, 2),
            "y": round(args.refresh_y, 2),
            "source": "a11y",
            "universal": True,
        }

    ready = confirm is not None
    out: dict[str, Any] = {
        "ok": True,
        "ready_for_burst": ready,
        "matched_site": site,
        "site_doc": site_doc,
        "puzzle_origin_css": {
            "x": round(puzzle["left"], 2),
            "y": round(puzzle["top"], 2),
        },
        "puzzle_box_css": {
            "left": round(puzzle["left"], 2),
            "top": round(puzzle["top"], 2),
            "width": round(puzzle["width"], 2),
            "height": round(puzzle["height"], 2),
        },
        "refresh_css": refresh_css,
        "confirm_css": confirm,
        "confirm_name_hints": CONFIRM_NAME_HINTS,
        "refresh_name_hints": REFRESH_NAME_HINTS,
        "capture_cli": (
            f"--left {puzzle['left']:.2f} --top {puzzle['top']:.2f} "
            f"--width {puzzle['width']:.2f} --height {puzzle['height']:.2f}"
        ),
        "warnings": warnings,
        "agent_note": (
            "通用：A11y --confirm-x/y。"
            "站点包：references/ + --url 命中或 --site；未命中禁止套用。"
            "solve 后用预锁 burst，禁止再探 Confirm。"
        ),
    }
    if dialog_box is not None:
        out["dialog_box_css"] = {
            "left": round(dialog_box["left"], 2),
            "top": round(dialog_box["top"], 2),
            "width": round(dialog_box["width"], 2),
            "height": round(dialog_box["height"], 2),
            "right": round(dialog_box["right"], 2),
        }

    if not ready:
        out["next"] = (
            "A11y 查找 Confirm/Submit/确认/提交 → --confirm-x/y。"
            "若当前 URL 在 references/sites.json 中，传 --url 采用站点包；"
            "否则不要套用其它站的几何。"
        )

    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if ready else 1)


if __name__ == "__main__":
    main()
