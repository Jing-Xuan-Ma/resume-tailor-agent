"""Quick OOXML identity + one JD smoke test with Word PDF pages."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.modules.resume_workspace.master_inject import inject_content, hyperlink_check
from app.modules.resume_workspace.format_lock import fingerprint_docx, compare_fingerprints
from app.modules.resume_workspace.quality_gate import project_for_jd
from app.modules.resume_workspace.service import MOCK_RESUME, ResumeWorkspaceService
from rg_word_pdf import word_export_pdf

MASTER = Path(r"d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx")
OUT = Path(r"d:\resume-agent\artifacts\rg\_ooxml_smoke")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    master = MASTER.read_bytes()
    # 1) identity
    identity = inject_content(master, MOCK_RESUME, MOCK_RESUME)
    (OUT / "identity.docx").write_bytes(identity)
    links = hyperlink_check(master, identity)
    fmt = compare_fingerprints(fingerprint_docx(master), fingerprint_docx(identity))
    pages = word_export_pdf(identity, OUT / "identity.pdf", label="identity")
    print("IDENTITY", {"pages": pages, "links": links, "fmt": fmt})

    # 2) one JD
    fixtures = json.loads((ROOT / "artifacts/rg/jd_fixtures.json").read_text(encoding="utf-8"))
    jd = fixtures[0]
    svc = ResumeWorkspaceService()
    projected = project_for_jd(MOCK_RESUME, jd["jd_text"])
    tailored = svc._content_only_tailor(projected, "Tailor", jd["jd_text"])
    tailored["hidden_entries"] = projected.get("hidden_entries") or []
    gen = inject_content(master, tailored, MOCK_RESUME)
    (OUT / "jd01.docx").write_bytes(gen)
    (OUT / "jd01_tailored.json").write_text(json.dumps(tailored, indent=2), encoding="utf-8")
    links2 = hyperlink_check(master, gen)
    fmt2 = compare_fingerprints(fingerprint_docx(master), fingerprint_docx(gen))
    pages2 = word_export_pdf(gen, OUT / "jd01.pdf", label="jd01")
    print("JD01", {"pages": pages2, "links": links2, "fmt": fmt2, "hidden": tailored.get("hidden_entries")})


if __name__ == "__main__":
    main()
