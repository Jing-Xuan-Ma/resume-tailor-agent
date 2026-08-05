"""Export DOCX → PDF via WPS COM (Word COM hangs on this machine)."""

from __future__ import annotations

import sys
from pathlib import Path


def export_docx_to_pdf(docx: Path, pdf: Path) -> int:
    """Return page count from WPS ComputeStatistics; write PDF beside it."""
    import win32com.client  # type: ignore

    wps = win32com.client.Dispatch("KWPS.Application")
    wps.Visible = False
    try:
        doc = wps.Documents.Open(str(docx.resolve()))
        pages = int(doc.ComputeStatistics(2))  # wdStatisticPages
        pdf.parent.mkdir(parents=True, exist_ok=True)
        if pdf.exists():
            pdf.unlink()
        # 17 = PDF export format (same as Word wdExportFormatPDF)
        doc.ExportAsFixedFormat(str(pdf.resolve()), 17)
        doc.Close(False)
        return pages
    finally:
        try:
            wps.Quit()
        except Exception:
            pass


def export_round(round_dir: Path) -> dict:
    gallery = round_dir / "_pdf_preview_wps"
    gallery.mkdir(exist_ok=True)
    results = {}
    import win32com.client  # type: ignore

    wps = win32com.client.Dispatch("KWPS.Application")
    wps.Visible = False
    try:
        for folder in sorted(p for p in round_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
            docx = folder / "resume.docx"
            if not docx.exists():
                continue
            pdf = folder / "resume_wps.pdf"
            doc = wps.Documents.Open(str(docx.resolve()))
            pages = int(doc.ComputeStatistics(2))
            if pdf.exists():
                pdf.unlink()
            doc.ExportAsFixedFormat(str(pdf.resolve()), 17)
            doc.Close(False)
            target = gallery / f"{folder.name}.pdf"
            target.write_bytes(pdf.read_bytes())
            results[folder.name] = {"pages": pages, "pdf": str(pdf)}
            print(f"OK {folder.name} pages={pages}")
    finally:
        try:
            wps.Quit()
        except Exception:
            pass
    return results


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    round_id = sys.argv[1] if len(sys.argv) > 1 else "round-4"
    round_dir = root / "artifacts" / "rg" / round_id
    if len(sys.argv) > 2 and sys.argv[2] == "master":
        master = Path(r"d:\Jingxuan's Resumes\Jingxuan_Resume_Data Analyst.docx")
        out = round_dir / "_pdf_preview_wps" / "MASTER.pdf"
        pages = export_docx_to_pdf(master, out)
        print({"master_pages": pages, "pdf": str(out)})
    else:
        print(export_round(round_dir))
