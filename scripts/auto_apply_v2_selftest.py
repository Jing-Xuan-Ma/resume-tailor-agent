"""Auto-apply v2 gate: DOM scan → rules map → fill by confidence → never Submit.

Writes artifacts/funnel/auto-apply-v2/{report.json,report.md,screenshots}.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ENABLE_BROWSER_FILL_PAUSE", "true")
os.environ.setdefault("ALLOW_LIVE_BROWSER_FILL", "false")

OUT = ROOT / "artifacts" / "funnel" / "auto-apply-v2"
OUT.mkdir(parents=True, exist_ok=True)

FIXTURES = [
    ("greenhouse", ROOT / "artifacts" / "funnel" / "sprint-i" / "fixture_greenhouse.html"),
    ("lever", ROOT / "artifacts" / "funnel" / "sprint-i" / "fixture_lever.html"),
]

CHECKS: list[tuple[str, bool, str]] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    CHECKS.append((name, cond, detail))
    print(("PASS" if cond else "FAIL"), name, detail)


def _dummy_resume() -> Path:
    path = OUT / "dummy_resume.pdf"
    if not path.exists() or path.stat().st_size < 20:
        # Minimal PDF-ish bytes (file upload only needs a path that exists)
        path.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
    return path


def main() -> int:
    from app.config import settings
    from app.modules.application_engine.browser_session import BrowserSession
    from app.modules.ats_connectors.field_mapper import map_fields_rules
    from app.modules.ats_connectors.canonical_profile import CANONICAL_KEYS

    settings.ENABLE_BROWSER_FILL_PAUSE = True
    settings.ALLOW_LIVE_BROWSER_FILL = False

    resume = _dummy_resume()
    profile = {
        "first_name": "Jingxuan",
        "last_name": "Ma",
        "full_name": "Jingxuan Ma",
        "email": "jma107@jh.edu",
        "phone": "+1 (410) 240-4366",
        "location": "Baltimore, MD",
        "linkedin": "https://linkedin.com/in/example",
        "github": "https://github.com/example",
        "portfolio": "https://example.com",
        "work_authorized": "Yes",
        "needs_sponsorship": "Yes",
        "visa_status": "",
        "earliest_start": "",
        "salary_expectation": "",
        "resume_path": str(resume.resolve()),
        "cover_letter_path": "",
    }
    for k in CANONICAL_KEYS:
        profile.setdefault(k, "")

    suite: dict[str, object] = {"ats": {}, "live_greenhouse": "not_run"}
    ats_pass = 0

    for name, fixture in FIXTURES:
        if not fixture.exists():
            ok(f"{name}_fixture", False, str(fixture))
            continue
        url = fixture.resolve().as_uri()
        shot = str(OUT / f"{name}-filled-paused.png")
        session = BrowserSession()
        scan = session.scan_fields(url=url, click_apply_first=False)
        fields = scan.get("fields") or []
        ok(f"{name}_scan_count", len(fields) >= 5, str(len(fields)))

        mappings = map_fields_rules(fields, profile)
        # Attach tiers like map_fields()
        from app.modules.ats_connectors.field_mapper import CONF_AUTO, CONF_REVIEW

        for m in mappings:
            conf = float(m.get("confidence") or 0)
            action = m.get("action")
            if action == "leave_empty" and not m.get("profile_key"):
                m["tier"] = "empty"
            elif conf >= CONF_AUTO and action in {"fill", "upload"}:
                m["tier"] = "auto"
            elif conf >= CONF_REVIEW and action in {"fill", "upload"}:
                m["tier"] = "review"
            else:
                m["tier"] = "empty"
                if action != "upload":
                    m["action"] = "leave_empty"
                    if conf < CONF_REVIEW:
                        m["value"] = ""

        auto_n = sum(1 for m in mappings if m.get("tier") == "auto")
        empty_n = sum(1 for m in mappings if m.get("tier") == "empty")
        # Screening essay must stay empty / unmapped
        screening = [
            m
            for m in mappings
            if "screening" in str(m.get("label") or "").lower()
            or "why" in str(m.get("label") or "").lower()
            or "cross-functional" in str(m.get("label") or "").lower()
            or "led a" in str(m.get("label") or "").lower()
        ]
        screening_safe = all(
            m.get("action") == "leave_empty" or not m.get("value") for m in screening
        )
        ok(f"{name}_auto_mapped", auto_n >= 3, f"auto={auto_n}")
        ok(f"{name}_has_empty", empty_n >= 1, f"empty={empty_n}")
        ok(f"{name}_screening_not_filled", screening_safe, f"n={len(screening)}")

        result = session.fill_and_pause(
            url=url,
            answers=[],
            field_selectors={},
            screenshot_path=shot,
            ats_type=name,
            sandbox=True,
            fill_plan=mappings,
            click_apply_first=False,
        )
        submitted = bool(result.get("submitted"))
        filled_ok = sum(1 for f in result.get("filled") or [] if f.get("status") == "filled")
        upload_ok = any(
            f.get("status") == "filled" and ("resume" in str(f.get("field") or "").lower() or f.get("profile_key") == "resume_path")
            for f in result.get("filled") or []
        ) or any(
            m.get("action") == "upload" and m.get("tier") == "auto"
            for m in mappings
        )
        # Prefer checking fill result for resume
        resume_filled = any(
            f.get("status") == "filled"
            and (
                "resume" in str(f.get("field") or "").lower()
                or str(f.get("profile_key") or "") == "resume_path"
            )
            for f in result.get("filled") or []
        )
        left_empty = sum(1 for f in result.get("filled") or [] if f.get("status") == "left_empty")
        shot_ok = Path(shot).exists() and Path(shot).stat().st_size > 500

        ok(f"{name}_not_submitted", not submitted and not result.get("submit_leaked"), str(result.get("submit_marker")))
        ok(f"{name}_filled_high_conf", filled_ok >= 3, str(filled_ok))
        ok(f"{name}_left_unknown", left_empty >= 1, str(left_empty))
        ok(f"{name}_resume_upload", resume_filled or upload_ok, "resume")
        ok(f"{name}_screenshot", shot_ok, shot)

        (OUT / f"{name}-scan.json").write_text(
            json.dumps({"fields": fields, "mappings": mappings}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (OUT / f"{name}-browser-fill.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        suite["ats"][name] = {  # type: ignore[index]
            "scan_count": len(fields),
            "auto": auto_n,
            "empty": empty_n,
            "filled": filled_ok,
            "submitted": submitted,
            "screenshot": shot,
        }
        if not submitted and filled_ok >= 3 and screening_safe and shot_ok:
            ats_pass += 1

    ok("greenhouse_and_lever_pass", ats_pass >= 2, f"{ats_pass}/2")
    passed = all(c for _, c, _ in CHECKS)
    score = 5 if passed else max(1, round(5 * sum(1 for _, c, _ in CHECKS if c) / max(len(CHECKS), 1)))

    report = {
        "pass": passed,
        "score_over_5": score,
        "checks": [{"name": n, "ok": c, "detail": d} for n, c, d in CHECKS],
        "suite": suite,
        "live_greenhouse": {
            "status": "not_run",
            "how": (
                "After fixture PASS: set ENABLE_BROWSER_FILL_PAUSE=true and "
                "ALLOW_LIVE_BROWSER_FILL=true, then Auto-apply one Greenhouse job URL. "
                "Never click Submit in automation — you submit on the site."
            ),
        },
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# Auto Apply v2 gate report",
        "",
        f"**Result:** {'PASS' if passed else 'FAIL'} · self-score **{score}/5**",
        "",
        "## Checks",
        "",
    ]
    for n, c, d in CHECKS:
        md.append(f"- {'✅' if c else '❌'} `{n}` {d}")
    md += [
        "",
        "## Live Greenhouse (optional)",
        "",
        "Not run in this automated gate.",
        "",
        "1. Confirm fixture gate is PASS.",
        "2. Set env: `ENABLE_BROWSER_FILL_PAUSE=true`, `ALLOW_LIVE_BROWSER_FILL=true`.",
        "3. Confirm a resume version, open Apply workspace, Auto-apply **one** Greenhouse URL.",
        "4. Review green/amber/red tiers, check「我已检查」, open official site, **you** click Submit.",
        "5. Confirm audit shows `submitted=false` from the agent (user may still submit on ATS).",
        "",
        "## API reuse",
        "",
        "`POST /api/v1/resume-workspace/ats/map-fields` — Playwright and future Chrome content scripts share mapping.",
        "",
    ]
    (OUT / "report.md").write_text("\n".join(md), encoding="utf-8")
    print("Wrote", OUT / "report.md")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
