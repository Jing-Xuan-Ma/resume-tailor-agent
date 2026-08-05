"""RG eval runner: OOXML inject from master, Word PDF page gate, scorecards."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.modules.resume_workspace.format_lock import compare_fingerprints, fingerprint_docx
from app.modules.resume_workspace.master_inject import (
    inject_content,
    content_integrity_check,
    hyperlink_check,
)
from app.modules.resume_workspace.master_template import ensure_master_template_bytes
from app.modules.resume_workspace.quality_gate import project_for_jd, run_quality_gate
from app.modules.resume_workspace.service import MOCK_RESUME, ResumeWorkspaceService

MASTER_SRC = Path(r"d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx")
OUT_ROOT = ROOT / "artifacts" / "rg"

# Import Word exporter
sys.path.insert(0, str(ROOT / "scripts"))
from rg_word_pdf import word_export_pdf  # noqa: E402


def _tailor_for_jd(jd_text: str, instruction: str = "Tailor to JD") -> dict:
    svc = ResumeWorkspaceService()
    projected = project_for_jd(MOCK_RESUME, jd_text)
    tailored = svc._content_only_tailor(projected, instruction, jd_text)
    # Keep JD-projected entry set (incl. Yiling variants + hides)
    tailored["experiences"] = projected.get("experiences") or []
    tailored["projects"] = projected.get("projects") or []
    tailored["competitions"] = projected.get("competitions") or []
    tailored["hidden_entries"] = projected.get("hidden_entries") or []
    tailored["skills_certifications"] = projected.get("skills_certifications") or tailored.get("skills_certifications")
    return tailored


def _word_pdf_and_preview(docx_bytes: bytes, jd_dir: Path) -> tuple[bool, int | None]:
    """Export via Word COM (ASCII temp path). Write resume.pdf + preview.png. Return (ok, pages)."""
    pdf_path = jd_dir / "resume.pdf"
    png_path = jd_dir / "preview.png"
    try:
        pages = word_export_pdf(docx_bytes, pdf_path, label=jd_dir.name[:40])
    except Exception as exc:
        (jd_dir / "word_export_error.txt").write_text(str(exc), encoding="utf-8")
        return False, None

    try:
        import fitz

        doc = fitz.open(pdf_path)
        if doc.page_count:
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.6, 1.6))
            pix.save(str(png_path))
        doc.close()
    except Exception as exc:
        (jd_dir / "preview_error.txt").write_text(str(exc), encoding="utf-8")
        return True, pages  # PDF ok even if preview fails
    return True, pages


def run_round(round_id: str, jd_limit: int | None = None) -> dict:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    round_dir = OUT_ROOT / round_id
    round_dir.mkdir(parents=True, exist_ok=True)

    master_bytes = ensure_master_template_bytes() or MASTER_SRC.read_bytes()
    # Always use fresh master bytes from disk for fidelity
    if MASTER_SRC.exists():
        master_bytes = MASTER_SRC.read_bytes()
    master_fp = fingerprint_docx(master_bytes)
    (round_dir / "master_fingerprint.json").write_text(json.dumps(master_fp, indent=2), encoding="utf-8")

    # Baseline: projected inventory (includes Yiling + project swap) must be 1 page
    from app.modules.resume_workspace.quality_gate import project_for_jd as _proj

    identity_payload = _proj(MOCK_RESUME, "Data Analyst SQL Python Tableau")
    identity = inject_content(master_bytes, identity_payload, MOCK_RESUME)
    id_pdf = round_dir / "_identity.pdf"
    try:
        id_pages = word_export_pdf(identity, id_pdf, label="identity")
    except Exception as exc:
        id_pages = -1
        (round_dir / "identity_export_error.txt").write_text(str(exc), encoding="utf-8")
    (round_dir / "identity_pages.txt").write_text(str(id_pages), encoding="utf-8")

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
        links = hyperlink_check(master_bytes, injected)
        errors = list(fmt.get("errors") or [])
        if not integrity["ok"]:
            errors += list(integrity.get("errors") or [])
        if not links["ok"]:
            errors += list(links.get("errors") or [])

        docx_path = jd_dir / "resume.docx"
        docx_path.write_bytes(injected)
        (jd_dir / "tailored.json").write_text(json.dumps(tailored, ensure_ascii=False, indent=2), encoding="utf-8")

        shot_ok, page_count = _word_pdf_and_preview(injected, jd_dir)
        if page_count is None:
            errors.append("word_pdf_export_failed")
        elif page_count != 1:
            errors.append(f"word_pdf_pages={page_count}!=1")
        if id_pages != 1:
            errors.append(f"identity_pages={id_pages}!=1")

        fmt = {
            **fmt,
            "ok": len(errors) == 0 and links.get("ok", False),
            "score": 10 if not errors else min(fmt.get("score", 10), 3),
            "errors": errors,
        }

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
            if "react" not in skills and "react" not in summary:
                honesty = 10
                match_score = 6

        critique = {
            "jd_id": jd["id"],
            "company": jd["company"],
            "title": jd["title"],
            "format": fmt,
            "quality_gate": gate,
            "scores": {
                "format": fmt["score"],
                "match": match_score,
                "honesty": honesty,
                "one_page": 10 if page_count == 1 else 0,
            },
            "screenshot": shot_ok,
            "pdf_pages": page_count,
            "hyperlinks": links,
            "agent_notes": [],
        }
        if not fmt["ok"]:
            critique["agent_notes"].append("FORMAT FAIL — keep iterating.")
        else:
            critique["agent_notes"].append("Word PDF 1-page + hyperlinks OK.")
        if match_score < 7:
            critique["agent_notes"].append("Match weak or intentionally honest for off-target JD.")

        (jd_dir / "scorecard.json").write_text(json.dumps(critique, indent=2), encoding="utf-8")
        results.append(critique)

    summary = {
        "round": round_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "identity_pages": id_pages,
        "n": len(results),
        "format_pass": sum(1 for r in results if r["format"]["ok"]),
        "avg_format": round(sum(r["scores"]["format"] for r in results) / max(len(results), 1), 2),
        "avg_match": round(sum(r["scores"]["match"] for r in results) / max(len(results), 1), 2),
        "avg_honesty": round(sum(r["scores"]["honesty"] for r in results) / max(len(results), 1), 2),
        "all_format_pass": all(r["format"]["ok"] for r in results),
        "results": results,
    }
    (round_dir / "ROUND_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        f"# RG {round_id} Summary",
        "",
        f"- identity_pages: {id_pages}",
        f"- format_pass: {summary['format_pass']}/{summary['n']}",
        f"- avg format/match/honesty: {summary['avg_format']} / {summary['avg_match']} / {summary['avg_honesty']}",
        "",
        "PDF/preview are **Word COM** exports (not HTML).",
        "",
    ]
    for r in results:
        lines.append(f"## {r['jd_id']}")
        lines.append(f"- pdf_pages: {r['pdf_pages']}")
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
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "round",
                    "identity_pages",
                    "format_pass",
                    "n",
                    "avg_format",
                    "avg_match",
                    "avg_honesty",
                    "all_format_pass",
                )
            },
            indent=2,
        )
    )
    return 0 if summary["all_format_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
