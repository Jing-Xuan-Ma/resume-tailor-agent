"""Agent2 Tailor & Store gate (MAIN takeover): Word PDF + Confirm archive."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(r"d:\resume-agent")
OUT = ROOT / "artifacts" / "funnel" / "agent2"
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000"
REPORT: dict = {"passed": False, "checks": [], "errors": [], "takeover": "main_agent"}


def check(name: str, ok: bool, detail: str = "") -> None:
    REPORT["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), name, detail)


def main() -> int:
    user = str(uuid4())
    job_id = "agent2_gate_job_da_001"
    with httpx.Client(base_url=API, timeout=180.0) as client:
        health = client.get("/health")
        check("api_health", health.status_code == 200, health.text[:80])

        session = client.post(
            "/api/v1/resume-workspace/jd-session",
            json={
                "user_id": user,
                "job_id": job_id,
                "jd_text": (
                    "Data Analyst\nCompany: Agent2 Gate Co\n"
                    "Requirements: SQL, Tableau, Python, ETL, stakeholder dashboards"
                ),
            },
        )
        check("create_session", session.status_code == 200, session.text[:120])
        if session.status_code != 200:
            return fail()
        session_id = session.json()["session_id"]

        t0 = time.time()
        rw = client.post(
            f"/api/v1/resume-workspace/jd-session/{session_id}/rewrite",
            json={
                "user_id": user,
                "session_id": session_id,
                "instruction": (
                    "Content-only under RESUME_CONSTITUTION: show/hide and reorder existing "
                    "inventory for SQL/Tableau/Python. Do not invent employers, tools, or metrics."
                ),
            },
        )
        elapsed = round(time.time() - t0, 1)
        check("rewrite", rw.status_code == 200, f"{elapsed}s")
        if rw.status_code != 200:
            check("rewrite_body", False, rw.text[:200])
            return fail()
        body = rw.json()
        version_id = body["new_version_id"]
        evidence = (body.get("full_resume") or {}).get("evidence_check") or {}
        hard = evidence.get("hard_issues")
        if hard is None:
            hard = [i for i in (evidence.get("issues") or []) if "weak textual support" not in i]
        check("evidence_hard_ok", len(hard) == 0, str(hard)[:160])

        preview = client.get(
            f"/api/v1/resume-workspace/resume-version/{version_id}/preview",
            params={"user_id": user},
        )
        check("preview_pdf_status", preview.status_code == 200, preview.headers.get("content-type", ""))
        pdf = preview.content if preview.status_code == 200 else b""
        (OUT / "preview.pdf").write_bytes(pdf)
        check("preview_word_size", len(pdf) > 20000, f"size={len(pdf)}")

        text = ""
        try:
            import fitz

            doc = fitz.open(stream=pdf, filetype="pdf")
            text = doc[0].get_text("text") if doc.page_count else ""
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            (OUT / "01-preview-page.png").write_bytes(pix.tobytes("png"))
            check("preview_one_page", doc.page_count == 1, f"pages={doc.page_count}")
            check("preview_has_EDUCATION", "EDUCATION" in text.upper())
            check("preview_has_EXPERIENCE", "EXPERIENCE" in text.upper())
            check("preview_text_no_##", "##" not in text)
            check("preview_text_no_**", "**" not in text)
        except Exception as exc:
            check("pymupdf_render", False, str(exc))

        conf = client.post(
            f"/api/v1/resume-workspace/resume-version/{version_id}/confirm",
            params={"user_id": user},
        )
        check("confirm_status", conf.status_code == 200, conf.text[:220])
        if conf.status_code != 200:
            return fail()
        conf_body = conf.json()
        final_path = Path(conf_body["final_path"])
        check("final_folder_exists", final_path.exists(), str(final_path))
        docx = list(final_path.glob("*.docx"))
        pdfs = list(final_path.glob("*.pdf"))
        meta_path = final_path / "meta.json"
        check("final_has_docx", bool(docx), str([p.name for p in docx]))
        check("final_has_pdf", bool(pdfs), str([p.name for p in pdfs]))
        check("final_has_meta", meta_path.exists())
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        (OUT / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        for key in ("job_id", "confirmed_at", "apply_status", "outreach_status"):
            check(f"meta_{key}", key in meta and meta.get(key) not in (None, ""), str(meta.get(key)))
        check("meta_job_id_value", meta.get("job_id") == job_id, str(meta.get("job_id")))

        if pdfs:
            import fitz

            at = fitz.open(pdfs[0]).load_page(0).get_text("text")
            check("archived_text_no_##", "##" not in at)
            check("archived_text_no_**", "**" not in at)

        REPORT["final_path"] = str(final_path)
        REPORT["version_id"] = version_id
        REPORT["meta"] = meta

    REPORT["passed"] = all(c["ok"] for c in REPORT["checks"])
    REPORT["ready"] = "READY_FOR_MAIN_AGENT" if REPORT["passed"] else "FAILURE"
    (OUT / "report.json").write_text(json.dumps(REPORT, indent=2), encoding="utf-8")
    (OUT / "agent2-tailor-report.md").write_text(
        f"# Agent2 Tailor (MAIN takeover)\n\n**Status: {'PASS' if REPORT['passed'] else 'FAIL'}**\n\n"
        f"READY_FOR_MAIN_AGENT\n\nSee report.json\n",
        encoding="utf-8",
    )
    print("RESULT", "PASS" if REPORT["passed"] else "FAIL")
    return 0 if REPORT["passed"] else 1


def fail() -> int:
    REPORT["passed"] = False
    (OUT / "report.json").write_text(json.dumps(REPORT, indent=2), encoding="utf-8")
    print("RESULT FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
