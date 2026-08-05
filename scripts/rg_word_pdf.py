"""Export DOCX→PDF via Word VBScript using ASCII-safe temp paths (apostrophe paths hang Word)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VBS = ROOT / "scripts" / "rg_word_export.vbs"


def word_export_pdf(docx: Path | bytes, pdf_out: Path, *, label: str = "doc") -> int:
    """Return page count. Writes pdf_out. Raises on failure."""
    pdf_out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rg_word_") as td:
        td_path = Path(td)
        src = td_path / f"{label}.docx"
        dst = td_path / f"{label}.pdf"
        if isinstance(docx, bytes):
            src.write_bytes(docx)
        else:
            shutil.copy2(docx, src)
        proc = subprocess.run(
            ["cscript", "//nologo", str(VBS), str(src), str(dst)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 or not dst.exists():
            raise RuntimeError(f"Word export failed rc={proc.returncode}: {out}")
        pages = 1
        for line in out.splitlines():
            if line.startswith("PAGES="):
                pages = int(line.split("=", 1)[1].strip())
        shutil.copy2(dst, pdf_out)
        return pages


if __name__ == "__main__":
    import sys

    docx = Path(sys.argv[1])
    pdf = Path(sys.argv[2])
    print({"pages": word_export_pdf(docx, pdf), "pdf": str(pdf)})
