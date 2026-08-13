"""Export RG round DOCX files to PDF via Microsoft Word COM."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import win32com.client  # type: ignore
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "pywin32", "-q"])
    import win32com.client  # type: ignore


def export_round(round_dir: Path) -> list[Path]:
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    out_paths: list[Path] = []
    try:
        for folder in sorted(p for p in round_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
            docx = folder / "resume.docx"
            if not docx.exists():
                continue
            pdf = folder / "resume.pdf"
            doc = word.Documents.Open(str(docx.resolve()))
            # 17 = wdFormatPDF
            doc.SaveAs(str(pdf.resolve()), FileFormat=17)
            doc.Close(False)
            out_paths.append(pdf)
            print(f"OK {folder.name}")
    finally:
        word.Quit()
    gallery = round_dir / "_pdf_preview"
    gallery.mkdir(exist_ok=True)
    for pdf in out_paths:
        target = gallery / f"{pdf.parent.name}.pdf"
        target.write_bytes(pdf.read_bytes())
    return out_paths


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    round_id = sys.argv[1] if len(sys.argv) > 1 else "round-3"
    paths = export_round(root / "artifacts" / "rg" / round_id)
    print(f"exported {len(paths)} pdfs")
