"""
PDF Rendering Node — Generate ATS-friendly PDF from tailored resume.
"""

from pathlib import Path
from textwrap import wrap

from app.modules.resume_tailor.nodes.text_export import TextExportNode


class PDFRenderNode:
    """
    Renders a TailoredResume into an ATS-optimized PDF.
    """

    def __init__(self):
        self.template_dir = Path(__file__).parent.parent / "templates"

    async def render(self, tailored_resume: dict) -> bytes:
        """
        Render tailored resume dict to PDF bytes.
        """
        text = TextExportNode().render(tailored_resume)
        lines = []
        for raw in text.splitlines():
            lines.extend(wrap(raw, width=120) or [""])
        return self._simple_pdf(lines[:92])

    def _simple_pdf(self, lines: list[str]) -> bytes:
        objects: list[bytes] = []

        def add(obj: str) -> int:
            objects.append(obj.encode("cp1252", errors="replace"))
            return len(objects)

        add("<< /Type /Catalog /Pages 2 0 R >>")
        add("<< /Type /Pages /Kids [] /Count 0 >>")
        font_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        commands = ["BT", "/F1 7.4 Tf", "48 752 Td", "8.6 TL"]
        for line in lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({safe}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands)
        content_id = add(f"<< /Length {len(stream.encode('cp1252', errors='replace'))} >>\nstream\n{stream}\nendstream")
        page_id = add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>")
        objects[1] = f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode("latin-1")

        pdf = bytearray(b"%PDF-1.4\n")
        offsets = []
        for idx, obj in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{idx} 0 obj\n".encode("latin-1"))
            pdf.extend(obj)
            pdf.extend(b"\nendobj\n")
        xref_at = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
        for offset in offsets:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        pdf.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode("latin-1"))
        return bytes(pdf)
