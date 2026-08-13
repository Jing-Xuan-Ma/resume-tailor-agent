"""W87–W90 static + light UI gates for waves 26–28."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


fe_ws = Path(r"d:\resume-agent\frontend\components\resume-workspace.tsx").read_text(encoding="utf-8")
fe_rank = Path(r"d:\resume-agent\frontend\components\ranked-jobs-table.tsx").read_text(encoding="utf-8")
fe_jobs = Path(r"d:\resume-agent\frontend\components\jobs-workspace.tsx").read_text(encoding="utf-8")
fe_step = Path(r"d:\resume-agent\frontend\components\flow-stepper.tsx").read_text(encoding="utf-8")

ok("w81_confirm_shortcut", "Ctrl+Shift+Enter" in fe_ws and "keydown" in fe_ws)
ok("w83_hide_stale_ready_guard", "hideStaleReady" in fe_rank)
ok("w87_escape_paste_jd", 'e.key === "Escape"' in fe_ws and "showPasteInput" in fe_ws)
ok("w87_confirm_next_apply", "confirm-next-apply" in fe_ws and "never Submit" in fe_ws)
ok("w87_scroll_apply_after_confirm", "apply-mode-panel" in fe_ws and "scrollIntoView" in fe_ws)
ok("w88_pipeline_match_honesty", "not interview odds" in fe_jobs)
ok("w90_stepper_jump", "onJump" in fe_step and "flow-step-${step.id}" in fe_step)

report = {
    "wave": "26-28",
    "passed": all(c for _, c, _ in CHECKS),
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
}
(OUT / "w87-w90-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
