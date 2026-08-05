#!/usr/bin/env python3
"""Inject light context only. Never auto-arm the ITERATION_PLAN loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"


def latest_checkpoint() -> str:
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
        print(json.dumps({}))
        return

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    run_flag = ARTIFACTS / "AUTONOMOUS_RUN"
    paused = (ARTIFACTS / "AUTONOMOUS_PAUSE").exists()
    done = (ARTIFACTS / "AUTONOMOUS_DONE").exists()
    # Do NOT auto-create AUTONOMOUS_RUN. Only user "go" arms via before_submit.
    enabled = run_flag.exists() and not paused and not done

    context = f"""
# Session bootstrap

Project: resume-agent
Latest checkpoint hint: {latest_checkpoint()}
ITERATION_PLAN auto-continue: {"ARMED" if enabled else "OFF (say go only when you want the long iteration mission)"}

Rules:
1. For normal questions/tasks: just do that task. Do NOT start ITERATION_PLAN.
2. Only when the user says go / 继续 / start: run ITERATION_PLAN.md autonomously.
3. Obey data-safety: never delete outside this repo; never real Submit; cold email frozen.
""".strip()

    print(
        json.dumps(
            {
                "additional_context": context,
                "env": {"RESUME_AGENT_AUTONOMOUS": "1" if enabled else "0"},
            }
        )
    )


if __name__ == "__main__":
    main()
