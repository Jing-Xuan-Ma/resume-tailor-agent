"""RG eval runner: generate from master, format-lock inject, score, screenshot, scorecard."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.modules.resume_workspace.format_lock import compare_fingerprints, fingerprint_docx
from app.modules.resume_workspace.master_inject import inject_content, content_integrity_check
from app.modules.resume_workspace.master_template import ensure_master_template_bytes
from app.modules.resume_workspace.quality_gate import project_for_jd, run_quality_gate
from app.modules.resume_workspace.service import MOCK_RESUME, ResumeWorkspaceService

MASTER_SRC = Path(r"d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx")
OUT_ROOT = ROOT / "artifacts" / "rg"


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)[:80]


def _tailor_for_jd(jd_text: str, instruction: str = "Tailor to JD") -> dict:
    svc = ResumeWorkspaceService()
    projected = project_for_jd(MOCK_RESUME, jd_text)
    tailored = svc._content_only_tailor(projected, instruction, jd_text)
    tailored["hidden_entries"] = projected.get("hidden_entries") or []
    return tailored


def _try_pdf_preview(docx_bytes: bytes, out_png: Path) -> bool:
    """Render first page preview via LibreOffice/Word unavailable — use HTML fallback screenshot."""
    try:
        from docx import Document
        from io import BytesIO

        doc = Document(BytesIO(docx_bytes))
        html_parts = [
            "<html><head><meta charset='utf-8'><style>",
            "body{font-family:Calibri,Arial,sans-serif;font-size:11pt;max-width:800px;margin:24px auto;line-height:1.25;}",
            "h1{text-align:center;font-size:18pt;margin:0 0 4px}",
            ".c{text-align:center;font-size:10pt;margin-bottom:10px}",
            ".sec{font-weight:700;text-transform:uppercase;margin-top:12px;border-bottom:1px solid #ccc}",
            "p{margin:2px 0}",
            "</style></head><body>",
        ]
        for i, p in enumerate(doc.paragraphs):
            t = p.text
            if not t.strip():
                continue
            if t.strip().isupper() and len(t.strip()) < 40:
                html_parts.append(f"<div class='sec'>{t}</div>")
            elif i < 2:
                html_parts.append(f"<h1>{t}</h1>" if i == 0 else f"<div class='c'>{t}</div>")
            else:
                html_parts.append(f"<p>{t}</p>")
        html_parts.append("</body></html>")
        html_path = out_png.with_suffix(".html")
        html_path.write_text("\n".join(html_parts), encoding="utf-8")

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True, channel="chrome")
            except Exception:
                browser = p.chromium.launch(headless=True, channel="msedge")
            page = browser.new_page(viewport={"width": 900, "height": 1200})
            page.goto(html_path.as_uri(), wait_until="load")
            page.screenshot(path=str(out_png), full_page=True)
            browser.close()
        return True
    except Exception as exc:
        out_png.with_suffix(".screenshot_error.txt").write_text(str(exc), encoding="utf-8")
        return False


def run_round(round_id: str, jd_limit: int | None = None) -> dict:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    round_dir = OUT_ROOT / round_id
    round_dir.mkdir(parents=True, exist_ok=True)

    master_bytes = ensure_master_template_bytes() or MASTER_SRC.read_bytes()
    master_fp = fingerprint_docx(master_bytes)
    (round_dir / "master_fingerprint.json").write_text(json.dumps(master_fp, indent=2), encoding="utf-8")

    fixtures = json.loads((OUT_ROOT / "jd_fixtures.json").read_text(encoding="utf-8"))
    if jd_limit:
        fixtures = fixtures[:jd_limit]

    results = []
    for jd in fixtures:
        jd_dir = round_dir / jd["id"]
        jd_dir.mkdir(parents=True, exist_ok=True)
        tailored = _tailor_for_jd(jd["jd_text"])
        gate = run_quality_gate(tailored, jd["jd_text"])

        injected = inject_content(master_bytes, tailored, MOCK_RESUME)
        gen_fp = fingerprint_docx(injected)
        fmt = compare_fingerprints(master_fp, gen_fp)
        integrity = content_integrity_check(injected, MOCK_RESUME)
        if not integrity["ok"]:
            fmt = {
                **fmt,
                "ok": False,
                "score": min(fmt["score"], 4),
                "errors": list(fmt.get("errors") or []) + list(integrity["errors"]),
            }

        docx_path = jd_dir / "resume.docx"
        docx_path.write_bytes(injected)
        (jd_dir / "tailored.json").write_text(json.dumps(tailored, ensure_ascii=False, indent=2), encoding="utf-8")

        png = jd_dir / "preview.png"
        shot_ok = _try_pdf_preview(injected, png)

        # Self critique scores
        format_score = fmt["score"]
        honesty = 10 if gate["ok"] and not any("fabricated" in e for e in gate["errors"]) else 4
        match_score = 8
        skills = str(tailored.get("skills_certifications") or "").lower()
        summary = str(tailored.get("summary") or "").lower()
        jd_l = jd["jd_text"].lower()
        hits = sum(1 for kw in ("sql", "python", "tableau", "airflow", "etl", "risk") if kw in jd_l and (kw in skills or kw in summary))
        reqs = sum(1 for kw in ("sql", "python", "tableau", "airflow", "etl", "risk") if kw in jd_l)
        if reqs:
            match_score = min(10, int(round(10 * hits / reqs)))
        if "react" in jd_l and "frontend" in jd_l:
            # weak match JD: honesty high if we don't invent react
            if "react" not in skills and "react" not in summary:
                honesty = 10
                match_score = 6  # honest weak match

        critique = {
            "jd_id": jd["id"],
            "company": jd["company"],
            "title": jd["title"],
            "format": fmt,
            "quality_gate": gate,
            "scores": {
                "format": format_score,
                "match": match_score,
                "honesty": honesty,
                "one_page_heuristic": 10 if "content likely exceeds one page" not in gate["errors"] else 2,
            },
            "screenshot": shot_ok,
            "agent_notes": [],
        }
        if not fmt["ok"]:
            critique["agent_notes"].append("FORMAT FAIL — content score discarded until format lock fixed.")
        else:
            critique["agent_notes"].append("Format lock OK (paragraph/style fingerprint).")
        if match_score < 7:
            critique["agent_notes"].append("Match weak or intentionally honest for off-target JD.")
        if honesty < 10:
            critique["agent_notes"].append("Honesty issues detected.")

        (jd_dir / "scorecard.json").write_text(json.dumps(critique, indent=2), encoding="utf-8")
        results.append(critique)

    summary = {
        "round": round_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "n": len(results),
        "format_pass": sum(1 for r in results if r["format"]["ok"]),
        "avg_format": round(sum(r["scores"]["format"] for r in results) / max(len(results), 1), 2),
        "avg_match": round(sum(r["scores"]["match"] for r in results) / max(len(results), 1), 2),
        "avg_honesty": round(sum(r["scores"]["honesty"] for r in results) / max(len(results), 1), 2),
        "all_format_pass": all(r["format"]["ok"] for r in results),
        "results": results,
    }
    (round_dir / "ROUND_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Markdown gallery
    lines = [
        f"# RG {round_id} Summary",
        "",
        f"- format_pass: {summary['format_pass']}/{summary['n']}",
        f"- avg format/match/honesty: {summary['avg_format']} / {summary['avg_match']} / {summary['avg_honesty']}",
        "",
    ]
    for r in results:
        lines.append(f"## {r['jd_id']}")
        lines.append(f"- scores: {r['scores']}")
        lines.append(f"- format_ok: {r['format']['ok']} errors={r['format']['errors']}")
        lines.append(f"- notes: {'; '.join(r['agent_notes'])}")
        if (round_dir / r["jd_id"] / "preview.png").exists():
            lines.append(f"- ![]({r['jd_id']}/preview.png)")
        lines.append("")
    (round_dir / "ROUND_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main(argv: list[str]) -> int:
    round_id = argv[1] if len(argv) > 1 else "round-0"
    limit = int(argv[2]) if len(argv) > 2 else None
    summary = run_round(round_id, jd_limit=limit)
    print(json.dumps({k: summary[k] for k in ("round", "format_pass", "n", "avg_format", "avg_match", "avg_honesty", "all_format_pass")}, indent=2))
    return 0 if summary["all_format_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
