"""Merge adjacent Word runs with identical rPr (outside hyperlinks) so text replace is reliable."""

from __future__ import annotations

import re
from xml.sax.saxutils import escape, unescape


_P_RE = re.compile(r"<w:p[\s\S]*?</w:p>")
_HYPER_RE = re.compile(r"<w:hyperlink[\s\S]*?</w:hyperlink>")
_RUN_RE = re.compile(r"<w:r(?:\s[^>]*)?>[\s\S]*?</w:r>")
_RPR_RE = re.compile(r"<w:rPr>[\s\S]*?</w:rPr>")
# Require whitespace or '>' after w:t so <w:tab/> is never mistaken for <w:t>.
_T_RE = re.compile(r"<w:t((?:\s[^>]*)?)>([\s\S]*?)</w:t>")
# Runs with these children must be left verbatim — rebuilding via <w:t> drops them.
_STRUCTURAL_RE = re.compile(
    r"<w:(?:tab|br|cr|drawing|object|pict|fldChar|instrText|sym|footnoteReference|endnoteReference)\b"
)


def _run_rpr(run_xml: str) -> str:
    m = _RPR_RE.search(run_xml)
    return m.group(0) if m else ""


def _run_text(run_xml: str) -> str:
    parts = []
    for m in _T_RE.finditer(run_xml):
        parts.append(unescape(m.group(2)))
    return "".join(parts)


def _run_is_structural(run_xml: str) -> bool:
    return bool(_STRUCTURAL_RE.search(run_xml))


def _make_run(rpr: str, text: str) -> str:
    # Preserve spaces at edges
    space_attr = ' xml:space="preserve"' if (text[:1].isspace() or text[-1:].isspace() or "  " in text) else ""
    body = escape(text)
    if rpr:
        return f"<w:r>{rpr}<w:t{space_attr}>{body}</w:t></w:r>"
    return f"<w:r><w:t{space_attr}>{body}</w:t></w:r>"


def _merge_run_sequence(segment: str) -> str:
    """Merge consecutive plain text runs with identical rPr; leave structural runs intact."""
    runs = list(_RUN_RE.finditer(segment))
    if len(runs) <= 1:
        return segment

    out: list[str] = []
    last_end = 0
    i = 0
    while i < len(runs):
        # copy gap before this run
        out.append(segment[last_end : runs[i].start()])
        run_xml = runs[i].group(0)
        if _run_is_structural(run_xml):
            # Keep <w:tab/> / breaks / fields verbatim — _make_run would drop them.
            out.append(run_xml)
            last_end = runs[i].end()
            i += 1
            continue
        rpr = _run_rpr(run_xml)
        texts = [_run_text(run_xml)]
        j = i + 1
        while j < len(runs):
            nxt = runs[j].group(0)
            if _run_is_structural(nxt):
                break
            # only merge if nothing but whitespace between runs
            between = segment[runs[j - 1].end() : runs[j].start()]
            if between.strip():
                break
            if _run_rpr(nxt) != rpr:
                break
            texts.append(_run_text(nxt))
            j += 1
        out.append(_make_run(rpr, "".join(texts)))
        last_end = runs[j - 1].end()
        i = j
    out.append(segment[last_end:])
    return "".join(out)


def merge_runs_in_paragraph(p_xml: str) -> str:
    """Merge redundant runs in one paragraph; leave hyperlink interiors untouched."""
    # Split by hyperlink blocks; merge only outside them
    pieces: list[str] = []
    pos = 0
    for h in _HYPER_RE.finditer(p_xml):
        pieces.append(_merge_run_sequence(p_xml[pos : h.start()]))
        pieces.append(h.group(0))  # keep hyperlink XML verbatim
        pos = h.end()
    pieces.append(_merge_run_sequence(p_xml[pos:]))
    return "".join(pieces)


def merge_runs_in_document(document_xml: str) -> str:
    def repl(m: re.Match[str]) -> str:
        return merge_runs_in_paragraph(m.group(0))

    return _P_RE.sub(repl, document_xml)
