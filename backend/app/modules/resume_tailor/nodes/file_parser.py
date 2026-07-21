"""
Resume File Parser — Extract plain text from .docx and .pdf files.
"""

from io import BytesIO
from pathlib import Path


def parse_docx(file_bytes: bytes) -> str:
    """Extract text from a .docx file."""
    try:
        from docx import Document
    except ImportError as e:
        raise RuntimeError("python-docx not installed") from e

    doc = Document(BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def parse_pdf(file_bytes: bytes) -> str:
    """Extract text from a .pdf file."""
    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError("pdfplumber not installed") from e

    text_parts = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text.strip())
    return "\n\n".join(text_parts)


def parse_resume_file(filename: str, file_bytes: bytes) -> str:
    """
    Detect file type from extension and parse to plain text.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".docx":
        return parse_docx(file_bytes)
    elif ext == ".pdf":
        return parse_pdf(file_bytes)
    elif ext == ".txt":
        return file_bytes.decode("utf-8", errors="ignore")
    else:
        raise ValueError(f"Unsupported file type: {ext}. Please upload .docx, .pdf, or .txt")
