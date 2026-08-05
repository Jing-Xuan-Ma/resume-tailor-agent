"""Main-agent unattended watcher: poll subagent deliverables, takeover if stuck, integrate."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"d:\resume-agent\artifacts\funnel")
PAUSE = Path(r"d:\resume-agent\artifacts\AUTONOMOUS_PAUSE")
STATE = ROOT / "MAIN_WATCH_STATE.json"
STUCK_MIN = 45

AGENTS = {
    "1": {
        "globs": ["agent1-*-report.md", "agent1*/report.json", "sprint-e/report.json"],
        "ready_markers": ["READY_FOR_MAIN_AGENT"],
        "module": "rank",
    },
    "2": {
        "globs": ["agent2-*-report.md", "agent2*/report.json", "sprint-a/report.json"],
        "ready_markers": ["READY_FOR_MAIN_AGENT"],
        "module": "tailor",
    },
    "3": {
        "globs": ["agent3-*-report.md", "agent3*/report.json", "sprint-i/report.json", "sprint-d/report.json"],
        "ready_markers": ["READY_FOR_MAIN_AGENT"],
        "module": "apply",
    },
    "4": {
        "globs": ["agent4-*-report.md", "agent4*/report.json", "sprint-f/report.json", "sprint-c-report.md"],
        "ready_markers": ["READY_FOR_MAIN_AGENT"],
        "module": "outreach",
    },
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_reports(agent_id: str) -> list[Path]:
    conf = AGENTS[agent_id]
    found: list[Path] = []
    for pattern in conf["globs"]:
        found.extend(ROOT.glob(pattern))
        found.extend(ROOT.glob(f"**/{pattern}"))
    # dedupe
    uniq = []
    seen = set()
    for p in found:
        rp = str(p.resolve())
        if rp not in seen and p.exists():
            seen.add(rp)
            uniq.append(p)
    return uniq


def parse_status(paths: list[Path]) -> dict:
    best = {
        "passed": None,
        "ready": False,
        "paths": [str(p) for p in paths],
        "mtime": None,
        "age_min": None,
    }
    if not paths:
        return best
    newest = max(paths, key=lambda p: p.stat().st_mtime)
    best["mtime"] = datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc).isoformat()
    best["age_min"] = round((time.time() - newest.stat().st_mtime) / 60, 1)
    text = ""
    for p in paths:
        try:
            text += "\n" + p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
        if p.suffix == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if "passed" in data:
                    best["passed"] = bool(data["passed"])
            except Exception:
                pass
    if "READY_FOR_MAIN_AGENT" in text:
        best["ready"] = True
    if best["passed"] is None:
        if "**Status: PASS**" in text or "Status: PASS" in text or '"passed": true' in text.lower():
            best["passed"] = True
        elif "Status: FAIL" in text or '"passed": false' in text.lower() or "FAILURE" in text:
            best["passed"] = False
    return best


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"started": utcnow(), "agents": {}, "takeovers": [], "integration_runs": []}


def save_state(state: dict) -> None:
    state["updated"] = utcnow()
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main() -> int:
    if PAUSE.exists():
        print("PAUSED")
        return 2
    state = load_state()
    summary = {"polled_at": utcnow(), "agents": {}, "action": "wait"}
    ready_count = 0
    stuck = []
    failed = []

    for aid, conf in AGENTS.items():
        paths = find_reports(aid)
        st = parse_status(paths)
        summary["agents"][aid] = {"module": conf["module"], **st}
        prev = state.get("agents", {}).get(aid, {})
        first_seen = prev.get("first_seen") or utcnow()
        if paths and not prev.get("first_seen"):
            first_seen = utcnow()
        entry = {
            "first_seen": first_seen,
            "last_status": st,
            "module": conf["module"],
        }
        state.setdefault("agents", {})[aid] = entry

        if st.get("ready") or st.get("passed") is True:
            ready_count += 1
            entry["status"] = "done"
        elif st.get("passed") is False:
            failed.append(aid)
            entry["status"] = "failed"
        else:
            # no report yet — stuck if watch already long (use state started)
            started = datetime.fromisoformat(state["started"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - started).total_seconds() / 60
            # Also if partial report old
            if st.get("age_min") is not None and st["age_min"] > STUCK_MIN and st.get("passed") is not True:
                stuck.append(aid)
                entry["status"] = "stuck_stale_report"
            elif not paths and age > STUCK_MIN:
                stuck.append(aid)
                entry["status"] = "stuck_no_report"
            else:
                entry["status"] = "in_progress"

    if failed or stuck:
        summary["action"] = "takeover_needed"
        summary["failed"] = failed
        summary["stuck"] = stuck
    elif ready_count >= 4:
        summary["action"] = "integrate_now"
    elif ready_count >= 2:
        summary["action"] = "partial_integrate"
    else:
        summary["action"] = "keep_watching"

    state["last_poll"] = summary
    save_state(state)
    out = ROOT / "MAIN_POLL.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
