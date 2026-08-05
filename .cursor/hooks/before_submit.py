#!/usr/bin/env python3
"""Arm ITERATION_PLAN auto-continue only when the user submits go/继续/start."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
RUN = ARTIFACTS / "AUTONOMOUS_RUN"
PAUSE = ARTIFACTS / "AUTONOMOUS_PAUSE"

_GO = re.compile(
    r"^\s*(go|继续|開始|开始|start|resume)\b",
    re.IGNORECASE,
)


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    mode = str(payload.get("composer_mode") or payload.get("mode") or "agent").lower()
    if mode in {"ask", "edit"}:
        print(json.dumps({}))
        return

    text = ""
    for key in ("prompt", "text", "message", "user_message", "content"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            text = val.strip()
            break

    if text and _GO.match(text) and len(text) < 80:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        if PAUSE.exists():
            PAUSE.unlink()
        RUN.write_text(
            "Armed by user go — ITERATION_PLAN auto-continue enabled.\n"
            "Press Stop or create AUTONOMOUS_PAUSE to stop.\n",
            encoding="utf-8",
        )

    print(json.dumps({}))


if __name__ == "__main__":
    main()
