"""Diagnose master vs generated DOCX: hyperlinks, paragraph stats, approx pages."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import re

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
MASTER = Path(r"d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx")
GEN = ROOT / "artifacts" / "rg" / "round-3" / "jd01_da_sql_tableau" / "resume.docx"


def hyperlink_count(docx_path: Path) -> int:
    with ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        rels = ""
        if "word/_rels/document.xml.rels" in z.namelist():
            rels = z.read("word/_rels/document.xml.rels").decode("utf-8", errors="ignore")
    # hyperlink elements + external targets
    h1 = len(re.findall(r"w:hyperlink", xml))
    h2 = len(re.findall(r'TargetMode="External"', rels))
    return h1, h2, rels.count("http")


def summarize(docx_path: Path) -> dict:
    doc = Document(str(docx_path))
    texts = [p.text for p in doc.paragraphs]
    chars = sum(len(t) for t in texts)
    non_empty = sum(1 for t in texts if t.strip())
    h1, h2, http = hyperlink_count(docx_path)
    # crude page estimate: ~3000-3500 chars/page for dense resume; better use sections
    return {
        "path": str(docx_path),
        "paragraphs": len(texts),
        "non_empty": non_empty,
        "chars": chars,
        "hyperlink_tags": h1,
        "external_rels": h2,
        "http_in_rels": http,
        "name_line": texts[0] if texts else "",
        "contact_line": texts[1] if len(texts) > 1 else "",
        "summary_preview": next((t[:120] for t in texts if len(t) > 80), ""),
    }


def main() -> None:
    for label, path in [("MASTER", MASTER), ("GEN", GEN)]:
        s = summarize(path)
        print(f"=== {label} ===")
        for k, v in s.items():
            print(f"{k}: {v}")
        print()


if __name__ == "__main__":
    main()
