"""Wave 5 gates + light regression."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(r"d:\resume-agent\artifacts\funnel\week")
CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


detail = Path(r"d:\resume-agent\frontend\app\jobs\[id]\page.tsx").read_text(encoding="utf-8")
records = Path(r"d:\resume-agent\frontend\components\records-panel.tsx").read_text(encoding="utf-8")
ok("w20_detail_stale_badge", "job-stale-badge" in detail and "Stale" in detail)
ok("w20_detail_honest_labels", "ATS keywords" in detail and "Skill coverage" in detail)
ok("w21_records_recommended_empty", "records-recommended-empty" in records and "records-goto-jobs" in records)
ok("w21_records_history_empty", "records-history-empty" in records and "records-goto-tailor" in records)

report = {
    "wave": 5,
    "passed": all(c for _, c, _ in CHECKS),
    "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
}
(OUT / "w20-w21-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["passed"] else 1)
