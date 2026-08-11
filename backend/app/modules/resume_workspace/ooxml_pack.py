"""DOCX zip helpers: rewrite only word/document.xml, preserve all other parts byte-for-byte."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def read_document_xml(docx_bytes: bytes) -> str:
    with ZipFile(BytesIO(docx_bytes)) as z:
        return z.read("word/document.xml").decode("utf-8")


def write_document_xml(docx_bytes: bytes, document_xml: str) -> bytes:
    """Return new docx bytes with document.xml replaced; other members copied unchanged."""
    src = ZipFile(BytesIO(docx_bytes))
    out_buf = BytesIO()
    with ZipFile(out_buf, "w", compression=ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "word/document.xml":
                data = document_xml.encode("utf-8")
            # Preserve original compress type when possible
            dst.writestr(info, data)
    src.close()
    return out_buf.getvalue()
