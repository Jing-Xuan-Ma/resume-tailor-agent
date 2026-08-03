#!/usr/bin/env python3
"""When an Agent turn ends, auto-submit a follow-up if work remains."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"


def has_tag(name: str) -> bool:
    try:
        out = subprocess.check_output(
            ["git", "tag", "--list", name],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return bool(out.strip())
    except Exception:
        return False


def next_iter() -> str | None:
    """Return next iteration id to work on, or None if finished."""
    order = [
        "baseline",
        "iter-0",
        "iter-1",
        "iter-2",
        "iter-3",
        "iter-4",
        "iter-5",
        "iter-6",
        "iter-7",
        "iter-8",
    ]
    # Map plan names to tags
    tag_for = {
        "baseline": "checkpoint/baseline",
        "iter-0": "checkpoint/iter-0-pass",
        "iter-1": "checkpoint/iter-1-pass",
        "iter-2": "checkpoint/iter-2-pass",
        "iter-3": "checkpoint/iter-3-pass",
        "iter-4": "checkpoint/iter-4-pass",
        "iter-5": "checkpoint/iter-5-pass",
        "iter-6": "checkpoint/iter-6-pass",
        "iter-7": "checkpoint/iter-7-pass",
        "iter-8": "checkpoint/iter-8-pass",
    }

    if has_tag(tag_for["iter-8"]) or (ARTIFACTS / "AUTONOMOUS_DONE").exists():
        return None

    for key in order:
        tag = tag_for[key]
        report = ARTIFACTS / f"{key}-report.md"
        # baseline/iter-0 may share naming; treat missing tag as unfinished
        if key == "baseline":
            if not has_tag(tag) and not (ARTIFACTS / "iter-0-report.md").exists():
                return "Iter-0 (baseline freeze)"
            continue
        if key == "iter-0":
            if not has_tag(tag) and not report.exists():
                # If baseline missing, still start at 0
                return "Iter-0"
            if not has_tag(tag):
                # report exists but tag missing — still finish/tag iter-0
                return "Iter-0"
            continue
        if not has_tag(tag):
            return key.replace("iter-", "Iter-")
    return None


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    status = (payload.get("status") or "").lower()
    # Only auto-continue clean completions; respect user abort.
    if status and status not in {"completed", "success", ""}:
        print(json.dumps({}))
        return

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if (ARTIFACTS / "AUTONOMOUS_PAUSE").exists():
        print(json.dumps({}))
        return
    if not (ARTIFACTS / "AUTONOMOUS_RUN").exists():
        print(json.dumps({}))
        return
    if (ARTIFACTS / "AUTONOMOUS_DONE").exists():
        print(json.dumps({}))
        return

    nxt = next_iter()
    if nxt is None:
        (ARTIFACTS / "AUTONOMOUS_DONE").write_text(
            "All planned iterations appear complete (iter-8 pass or DONE flag).\n",
            encoding="utf-8",
        )
        print(json.dumps({}))
        return

    msg = (
        f"Continue autonomously. Do not ask questions. "
        f"Next target: {nxt}. "
        f"Follow AGENTS.md + ITERATION_PLAN.md + .cursor/rules. "
        f"Implement, test, write artifacts report, checkpoint on pass, then proceed. "
        f"Stop only for safety violations or if artifacts/AUTONOMOUS_PAUSE exists."
    )
    print(json.dumps({"followup_message": msg}))


if __name__ == "__main__":
    main()
