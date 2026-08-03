#!/usr/bin/env python3
"""Inject autonomous mission context at every Agent session start."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"


def latest_checkpoint() -> str:
    # Prefer git tags when available; fall back to report files.
    try:
        import subprocess

        out = subprocess.check_output(
            ["git", "tag", "--list", "checkpoint/*", "--sort=-creatordate"],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        tags = [t.strip() for t in out.splitlines() if t.strip()]
        if tags:
            return tags[0]
    except Exception:
        pass
    reports = sorted(ARTIFACTS.glob("iter-*-report.md"), reverse=True)
    if reports:
        return reports[0].name
    return "none (start Iter-0)"


def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    mode = (payload.get("composer_mode") or "agent").lower()
    if mode in {"ask", "edit"}:
        # Do not force long-running iteration loops in Ask/Edit modes.
        print(json.dumps({}))
        return

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    run_flag = ARTIFACTS / "AUTONOMOUS_RUN"
    if not run_flag.exists() and not (ARTIFACTS / "AUTONOMOUS_PAUSE").exists():
        run_flag.write_text(
            "Autonomous iteration enabled.\n"
            "Delete this file or create AUTONOMOUS_PAUSE to stop auto-continue.\n",
            encoding="utf-8",
        )

    paused = (ARTIFACTS / "AUTONOMOUS_PAUSE").exists()
    done = (ARTIFACTS / "AUTONOMOUS_DONE").exists()
    enabled = run_flag.exists() and not paused and not done

    context = f"""
# Autonomous session bootstrap (injected by project hook)

Project: resume-agent
Mission file: AGENTS.md + ITERATION_PLAN.md
Latest checkpoint hint: {latest_checkpoint()}
Autonomous continue: {"ENABLED" if enabled else "DISABLED (paused/done/missing AUTONOMOUS_RUN)"}

Instructions for this session:
1. Do not ask the user questions. Use ITERATION_PLAN.md defaults.
2. Continue unfinished iterations until Iter-8 pass, safety stop, AUTONOMOUS_PAUSE, or AUTONOMOUS_DONE.
3. Obey .cursor/rules data-safety: never delete files outside this repo; never real Submit; cold email frozen.
4. If the user message is short (go/继续/start) or empty of new scope, execute the mission.
""".strip()

    print(
        json.dumps(
            {
                "additional_context": context,
                "env": {
                    "RESUME_AGENT_AUTONOMOUS": "1" if enabled else "0",
                },
            }
        )
    )


if __name__ == "__main__":
    main()
