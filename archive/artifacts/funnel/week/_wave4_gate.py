"""Wave 4 gates: stale filter + apply confirm CTA."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


jobs = Path(r"d:\resume-agent\frontend\components\ranked-jobs-table.tsx").read_text(encoding="utf-8")
apply = Path(r"d:\resume-agent\frontend\components\apply-mode-panel.tsx").read_text(encoding="utf-8")
ok("w17_hide_stale_toggle", "jobs-hide-stale" in jobs and "hideStale" in jobs)
ok("w17_filters_stale_rows", "isStaleOver14d" in jobs and "visible.map" in jobs)
ok("w18_goto_confirm_cta", "apply-goto-confirm" in apply and "Jump to Confirm" in apply)

report = {
    "wave": 4,
    "passed": all(c for _, c, _ in CHECKS),
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
}
(OUT / "w17-w18-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
