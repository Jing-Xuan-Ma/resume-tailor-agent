"""OOXML content inject: replace text / delete entry blocks / carve entry templates.
Never rebuilds the document via python-docx — only edits word/document.xml inside the zip.
"""

from __future__ import annotations

import re
import secrets
from typing import Any
from xml.sax.saxutils import escape, unescape

from app.modules.resume_workspace.ooxml_merge_runs import merge_runs_in_document
from app.modules.resume_workspace.ooxml_pack import read_document_xml, write_document_xml

SECTION_HEADINGS = {
    "EDUCATION",
    "PROFESSIONAL EXPERIENCE",
    "PROJECTS",
    "COMPETITIONS",
    "SKILLS & CERTIFICATIONS",
}

_P_RE = re.compile(r"<w:p[\s\S]*?</w:p>")
# Require whitespace or '>' after w:t so <w:tab/> is never mistaken for <w:t>.
_T_RE = re.compile(r"<w:t((?:\s[^>]*)?)>([\s\S]*?)</w:t>")
_HYPER_RE = re.compile(r"<w:hyperlink[\s\S]*?</w:hyperlink>")
_RUN_RE = re.compile(r"<w:r(?:\s[^>]*)?>[\s\S]*?</w:r>")
_RPR_RE = re.compile(r"<w:rPr>[\s\S]*?</w:rPr>")
_PARA_ID_RE = re.compile(r'w14:paraId="[A-F0-9]+"')
_TEXT_ID_RE = re.compile(r'w14:textId="[A-F0-9]+"')


def _norm(s: str) -> str:
    return " ".join((s or "").replace("\xa0", " ").replace("&amp;", "&").split()).strip().lower()


def _para_text(p_xml: str) -> str:
    return "".join(unescape(m.group(2)) for m in _T_RE.finditer(p_xml)).replace("\xa0", " ")


def _has_hyperlink(p_xml: str) -> bool:
    return "<w:hyperlink" in p_xml


def _is_section(text: str) -> bool:
    return text.strip().upper() in SECTION_HEADINGS


def _is_entry_heading(text: str, section: str) -> bool:
    t = text.strip()
    if not t or _is_section(t):
        return False
    if t.lstrip().startswith(("•", "*", "-", "Coursework")):
        return False
    if section == "EDUCATION":
        # school line usually short-ish and has lots of trailing spaces in XML text
        if "Master of" in t or "Bachelor of" in t or t.startswith("Coursework"):
            return False
        return len(t) < 120 and ("University" in t or "College" in t or "Institute" in t)
    return "|" in t


def _new_para_id() -> str:
    return secrets.token_hex(4).upper()


def _retarget_ids(block_xml: str) -> str:
    def pid(_: re.Match[str]) -> str:
        return f'w14:paraId="{_new_para_id()}"'

    def tid(_: re.Match[str]) -> str:
        return f'w14:textId="{_new_para_id()}"'

    block_xml = _PARA_ID_RE.sub(pid, block_xml)
    block_xml = _TEXT_ID_RE.sub(tid, block_xml)
    return block_xml


def _set_plain_paragraph_text(p_xml: str, new_text: str) -> str:
    """Keep pPr + first run rPr; put all text in first w:t; drop extra plain runs.

    Skip if hyperlinks.
    """
    if _has_hyperlink(p_xml):
        return p_xml
    runs = list(_RUN_RE.finditer(p_xml))
    if not runs:
        return p_xml
    first = runs[0].group(0)
    rpr_m = _RPR_RE.search(first)
    rpr = rpr_m.group(0) if rpr_m else ""
    space_attr = (
        ' xml:space="preserve"' if (new_text[:1].isspace() or new_text[-1:].isspace()) else ""
    )
    new_run = (
        f"<w:r>{rpr}<w:t{space_attr}>{escape(new_text)}</w:t></w:r>"
        if rpr
        else (f"<w:r><w:t{space_attr}>{escape(new_text)}</w:t></w:r>")
    )
    # Replace from first run start to last run end with single run
    start = runs[0].start()
    end = runs[-1].end()
    return p_xml[:start] + new_run + p_xml[end:]


def _bullets(entry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not entry:
        return []
    out = []
    for b in entry.get("bullets") or []:
        if isinstance(b, dict):
            out.append(b)
        else:
            out.append({"text": str(b)})
    return out


def _build_bullet_map(tailored: dict[str, Any], inventory: dict[str, Any]) -> dict[str, str]:
    bullet_map: dict[str, str] = {}
    for section in ("experiences", "projects", "competitions"):
        inv_by_key: dict[str, dict] = {}
        for e in inventory.get(section) or []:
            if not isinstance(e, dict):
                continue
            if section == "experiences":
                key = f"{e.get('company', '')}|{e.get('title', '')}"
            else:
                key = str(e.get("name") or "")
            inv_by_key[_norm(key)] = e
        for e in tailored.get(section) or []:
            if not isinstance(e, dict):
                continue
            if section == "experiences":
                key = f"{e.get('company', '')}|{e.get('title', '')}"
            else:
                key = str(e.get("name") or "")
            inv = inv_by_key.get(_norm(key))
            t_bullets = _bullets(e)
            i_bullets = _bullets(inv)
            for i, tb in enumerate(t_bullets):
                new_t = str(tb.get("text") or "").strip()
                if not new_t:
                    continue
                orig = str(tb.get("original_text") or "").strip()
                if orig and len(new_t) > len(orig) + 8:
                    continue  # never lengthen beyond original
                if orig:
                    bullet_map[_norm(orig)] = new_t
                if i < len(i_bullets):
                    inv_t = str(i_bullets[i].get("text") or "").strip()
                    if inv_t and len(new_t) <= len(inv_t) + 8:
                        bullet_map[_norm(inv_t)] = new_t
    return bullet_map


def _hide_keys(hidden: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for h in hidden or []:
        if not isinstance(h, dict):
            continue
        k = str(h.get("key") or "").strip()
        if not k:
            continue
        keys.add(_norm(k))
        keys.add(_norm(k.split("|")[0]))
    return keys


def _should_hide_heading(text: str, hide_keys: set[str]) -> bool:
    n = _norm(text)
    for hk in hide_keys:
        if hk and (hk in n or n.startswith(hk)):
            return True
    return False


def split_paragraphs(document_xml: str) -> tuple[str, list[str], str]:
    """Return (prefix, paragraphs, suffix) where document body paragraphs are listed."""
    paras = list(_P_RE.finditer(document_xml))
    if not paras:
        return document_xml, [], ""
    prefix = document_xml[: paras[0].start()]
    suffix = document_xml[paras[-1].end() :]
    return prefix, [m.group(0) for m in paras], suffix


def join_paragraphs(prefix: str, paragraphs: list[str], suffix: str) -> str:
    return prefix + "".join(paragraphs) + suffix


def delete_hidden_entries(paragraphs: list[str], tailored: dict[str, Any]) -> list[str]:
    """Delete whole entry blocks listed in hidden_entries.

    Optionally drops an empty COMPETITIONS section.
    """
    hidden = [h for h in (tailored.get("hidden_entries") or []) if isinstance(h, dict)]
    hide_keys = _hide_keys(hidden)
    hide_competitions = (tailored.get("competitions") == []) and any(
        h.get("kind") == "competition" for h in hidden
    )

    if not hide_keys and not hide_competitions:
        return paragraphs

    current_section = ""
    removing = False
    out: list[str] = []

    for p in paragraphs:
        text = _para_text(p).strip()
        upper = text.upper()
        if upper in SECTION_HEADINGS:
            current_section = upper
            removing = False
            if hide_competitions and upper == "COMPETITIONS":
                removing = True
                continue
            out.append(p)
            continue

        if not text:
            if removing:
                continue
            out.append(p)
            continue

        if current_section in {"PROFESSIONAL EXPERIENCE", "PROJECTS", "COMPETITIONS"}:
            if _is_entry_heading(text, current_section):
                should = False
                if current_section == "COMPETITIONS" and hide_competitions:
                    should = True
                elif _should_hide_heading(text, hide_keys):
                    should = True
                removing = should
                if should:
                    continue
                out.append(p)
                continue
            if removing:
                continue
            out.append(p)
            continue

        out.append(p)

    # Drop orphan blank lines before SKILLS if competitions removed left doubles
    cleaned: list[str] = []
    for p in out:
        text = _para_text(p).strip()
        if not text and cleaned and not _para_text(cleaned[-1]).strip():
            continue
        cleaned.append(p)
    return cleaned


def apply_text_replacements(
    paragraphs: list[str], tailored: dict[str, Any], inventory: dict[str, Any]
) -> list[str]:
    bullet_map = _build_bullet_map(tailored, inventory)
    new_summary = str(tailored.get("summary") or "").strip()
    old_summary = str(inventory.get("summary") or "").strip()
    new_skills = str(tailored.get("skills_certifications") or "").strip()
    old_skills = str(inventory.get("skills_certifications") or "").strip()

    current_section = ""
    out: list[str] = []
    for idx, p in enumerate(paragraphs):
        text = _para_text(p)
        raw = text.strip()
        if _has_hyperlink(p) or idx <= 1:
            out.append(p)
            if raw:
                pass
            continue
        if raw.upper() in SECTION_HEADINGS:
            current_section = raw.upper()
            out.append(p)
            continue

        # Summary: only shorten/same length
        if (
            current_section == ""
            and new_summary
            and old_summary
            and len(raw) > 80
            and (_norm(raw) == _norm(old_summary) or _norm(old_summary)[:50] in _norm(raw))
        ):
            if len(new_summary) <= len(old_summary) + 5:
                out.append(_set_plain_paragraph_text(p, new_summary))
            else:
                out.append(p)
            continue

        if current_section.startswith("SKILLS") and new_skills and raw.count(",") >= 3:
            if (not old_skills) or len(new_skills) <= len(old_skills) + 10:
                out.append(_set_plain_paragraph_text(p, new_skills))
            else:
                out.append(p)
            continue

        if current_section in {"PROFESSIONAL EXPERIENCE", "PROJECTS", "COMPETITIONS", "EDUCATION"}:
            stripped = raw.lstrip("•*-–— ").strip()
            ns = _norm(stripped)
            if ns in bullet_map:
                out.append(_set_plain_paragraph_text(p, _sanitize_resume_text(bullet_map[ns])))
                continue
            replaced = False
            for old_n, new_t in bullet_map.items():
                if len(old_n) > 60 and (old_n[:70] in ns or ns[:70] in old_n):
                    if len(new_t) <= len(stripped) + 8:
                        out.append(_set_plain_paragraph_text(p, _sanitize_resume_text(new_t)))
                        replaced = True
                        break
            if replaced:
                continue

        out.append(p)
    return out


def carve_experience_block(paragraphs: list[str], donor_heading_substr: str) -> list[str] | None:
    """Return a deep-copied experience entry block (heading+bullets[+spacer]) as XML paragraphs."""
    current_section = ""
    start = None
    for i, p in enumerate(paragraphs):
        text = _para_text(p).strip()
        if text.upper() in SECTION_HEADINGS:
            current_section = text.upper()
            continue
        if current_section != "PROFESSIONAL EXPERIENCE":
            continue
        if start is None and donor_heading_substr.lower() in text.lower() and "|" in text:
            start = i
            continue
        if start is not None and _is_entry_heading(text, current_section):
            block = paragraphs[start:i]
            return [_retarget_ids(x) for x in block]
        if start is not None and text.upper() in SECTION_HEADINGS:
            block = paragraphs[start:i]
            return [_retarget_ids(x) for x in block]
    if start is not None:
        end = start + 1
        while end < len(paragraphs):
            t = _para_text(paragraphs[end]).strip()
            if t.upper() in SECTION_HEADINGS or (
                t and _is_entry_heading(t, "PROFESSIONAL EXPERIENCE")
            ):
                break
            end += 1
        return [_retarget_ids(x) for x in paragraphs[start:end]]
    return None


def _run_rpr_flags(run_xml: str) -> tuple[str, bool]:
    m = _RPR_RE.search(run_xml)
    rpr = m.group(0) if m else ""
    bold = "<w:b/>" in rpr or "<w:b " in rpr
    return rpr, bold


def _make_run_with_rpr(rpr: str, text: str) -> str:
    space_attr = (
        ' xml:space="preserve"'
        if (text[:1].isspace() or text[-1:].isspace() or "  " in text)
        else ""
    )
    body = escape(text)
    if rpr:
        return f"<w:r>{rpr}<w:t{space_attr}>{body}</w:t></w:r>"
    return f"<w:r><w:t{space_attr}>{body}</w:t></w:r>"


def _set_experience_heading(p_xml: str, left: str, right: str) -> str:
    """Fill experience heading like母本: bold left (title|company), plain right (location|dates).

    Root cause of prior bug: collapsing the whole line into the first (bold) run made
    location/dates bold. Donor Shenwan uses separate runs — bold left, non-bold right.

    Avoid huge space-padding (target ~118): when left+right is already wide, Word wraps
    mid-padding and the right fragment visually collides with the next entry's title,
    which looks like duplicated/merged headers in the PDF.
    """
    runs = list(_RUN_RE.finditer(p_xml))
    if not runs:
        return _set_plain_paragraph_text(p_xml, f"{left}  {right}")

    bold_rpr = ""
    plain_rpr = ""
    for m in runs:
        rpr, is_bold = _run_rpr_flags(m.group(0))
        if is_bold and not bold_rpr:
            bold_rpr = rpr
        if (not is_bold) and rpr and not plain_rpr:
            plain_rpr = rpr
    if not bold_rpr:
        bold_rpr, _ = _run_rpr_flags(runs[0].group(0))
    if not plain_rpr:
        # Strip bold tags from bold_rpr to synthesize plain
        plain_rpr = re.sub(r"<w:b\s*/>|<w:bCs\s*/>|<w:b[^/]*/>|<w:bCs[^/]*/>", "", bold_rpr)

    left = left.rstrip()
    right = right.strip()
    # Keep a modest gap only — never pad out to 118+ chars (causes wrap/overlap in PDF).
    room = 96 - len(left) - len(right)
    gap = max(2, min(room, 8))
    new_runs = (
        _make_run_with_rpr(bold_rpr, left)
        + _make_run_with_rpr(plain_rpr, " " * gap)
        + _make_run_with_rpr(plain_rpr, right)
    )
    start = runs[0].start()
    end = runs[-1].end()
    return p_xml[:start] + new_runs + p_xml[end:]


def _pad_heading_line(left: str, right: str, target_width: int = 118) -> str:
    """Approximate master right-align via trailing spaces between left and right."""
    left = left.rstrip()
    right = right.strip()
    gap = max(2, target_width - len(left) - len(right))
    return f"{left}{' ' * gap}{right}"


def fill_experience_block(block: list[str], entry: dict[str, Any]) -> list[str]:
    """Replace heading + bullet texts inside a carved block; keep XML styling."""
    title = str(entry.get("title") or "").strip()
    company = str(entry.get("company") or "").strip()
    location = str(entry.get("location") or "").strip()
    dates = str(entry.get("date_range") or "").strip()
    left = f"{title} | {company}"
    right = f"{location} | {dates}" if location and dates else (dates or location)
    bullets = [
        _sanitize_resume_text(str(b.get("text") or "").strip())
        for b in _bullets(entry)
        if str(b.get("text") or "").strip()
    ]

    out: list[str] = []
    bullet_i = 0
    heading_done = False
    for p in block:
        text = _para_text(p).strip()
        if not heading_done and text and "|" in text:
            out.append(_set_experience_heading(p, left, right))
            heading_done = True
            continue
        if not text:
            out.append(p)
            continue
        if bullet_i < len(bullets):
            out.append(_set_plain_paragraph_text(p, bullets[bullet_i]))
            bullet_i += 1
        else:
            out.append(p)
    return out


def _sanitize_resume_text(text: str) -> str:
    """Strip ATS-hostile glyphs (arrows, fancy bullets, etc.)."""
    banned = {
        "→": " to ",
        "←": " from ",
        "⇒": " to ",
        "⇐": " from ",
        "➜": " to ",
        "➔": " to ",
        "➡": " to ",
        "•": "",  # list style comes from numbering, not glyph in text
        "●": "",
        "◆": "",
        "■": "",
        "★": "",
        "✓": "",
        "✔": "",
        "✗": "",
        "–": "-",  # en-dash ok-ish but normalize to hyphen for ATS
        "—": "-",
    }
    out = text
    for a, b in banned.items():
        out = out.replace(a, b)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def apply_experience_headings(paragraphs: list[str], tailored: dict[str, Any]) -> list[str]:
    """Rewrite experience headings from tailored entries (modest gap, no 118-char pad)."""
    entries = [e for e in (tailored.get("experiences") or []) if isinstance(e, dict)]
    if not entries:
        return paragraphs

    # Match master headings even when legal name word order differs slightly.
    matchers: list[tuple[str, dict[str, Any]]] = []
    for e in entries:
        company = str(e.get("company") or "").strip()
        if not company:
            continue
        matchers.append((_norm(company), e))
        token = company.split(",")[0].strip()
        if token:
            matchers.append((_norm(token), e))
        for word in company.replace(",", " ").replace(".", " ").split():
            w = word.strip()
            if len(w) >= 5 and w.lower() not in {
                "beijing",
                "shanghai",
                "network",
                "technology",
                "technologies",
                "limited",
                "management",
                "company",
            }:
                matchers.append((_norm(w), e))

    current_section = ""
    out: list[str] = []
    for p in paragraphs:
        text = _para_text(p).strip()
        if text.upper() in SECTION_HEADINGS:
            current_section = text.upper()
            out.append(p)
            continue
        if (
            current_section == "PROFESSIONAL EXPERIENCE"
            and text
            and _is_entry_heading(text, current_section)
            and not _has_hyperlink(p)
        ):
            matched = None
            n = _norm(text)
            for key, entry in matchers:
                if key and key in n:
                    matched = entry
                    break
            if matched:
                title = str(matched.get("title") or "").strip()
                company = str(matched.get("company") or "").strip()
                location = str(matched.get("location") or "").strip()
                dates = str(matched.get("date_range") or "").strip()
                left = f"{title} | {company}" if title and company else (title or company)
                right = f"{location} | {dates}" if location and dates else (dates or location)
                out.append(_set_experience_heading(p, left, right))
                continue
        out.append(p)
    return out


def _company_already_in_body(company: str, body_text: str) -> bool:
    """True if this employer already has an experience block in the DOCX.

    Exact / prefix match first; then a distinctive token (e.g. Yiling) so a
    slightly different legal name in the master does not trigger a duplicate
    carve/insert of the same role.
    """
    company = (company or "").strip()
    if not company:
        return False
    if company in body_text:
        return True
    token = company.split(",")[0].strip()
    if token and token in body_text:
        return True
    skip = {
        "beijing",
        "shanghai",
        "network",
        "technology",
        "technologies",
        "limited",
        "management",
        "company",
        "co.",
        "ltd.",
        "inc.",
        "corp.",
        "group",
        "fund",
        "securities",
    }
    for word in company.replace(",", " ").replace(".", " ").split():
        w = word.strip()
        if len(w) < 5 or w.lower() in skip:
            continue
        if w in body_text:
            return True
    return False


def insert_missing_experiences(paragraphs: list[str], tailored: dict[str, Any]) -> list[str]:
    """Carve donor experience XML for inventory entries not present in the DOCX."""
    from app.modules.resume_workspace.yiling_experience import YILING_COMPANY, YILING_DONOR

    body_text = "\n".join(_para_text(p) for p in paragraphs)
    to_insert: list[list[str]] = []
    for entry in tailored.get("experiences") or []:
        if not isinstance(entry, dict):
            continue
        company = str(entry.get("company") or "")
        if not company:
            continue
        if _company_already_in_body(company, body_text):
            continue
        if "Yiling" in company or company == YILING_COMPANY:
            donor = carve_experience_block(paragraphs, YILING_DONOR)
            if not donor:
                continue
            to_insert.append(fill_experience_block(donor, entry))

    if not to_insert:
        return paragraphs

    # Insert immediately after PROFESSIONAL EXPERIENCE heading (most recent first)
    out: list[str] = []
    inserted = False
    for p in paragraphs:
        out.append(p)
        if not inserted and _para_text(p).strip().upper() == "PROFESSIONAL EXPERIENCE":
            for block in to_insert:
                out.extend(block)
            inserted = True
    return out


def inject_ooxml(master_docx: bytes, tailored: dict[str, Any], inventory: dict[str, Any]) -> bytes:
    # NOTE: this used to force-hide one project whenever Yiling was present,
    # hardcoded to that one company, independent of whatever project_for_jd
    # (Phase 2a) actually decided about relevance. That's now redundant AND
    # can silently override a real JD-relevance decision (e.g. force-hiding a
    # project project_for_jd legitimately kept, because "Yiling needs room" —
    # not because the project wasn't relevant to this JD). project_for_jd's
    # hidden_entries is the single source of truth for what's hidden; this
    # layer only injects/deletes paragraphs according to it, it doesn't make
    # its own hide decisions anymore.
    tailored = dict(tailored or {})

    xml = read_document_xml(master_docx)
    xml = merge_runs_in_document(xml)
    prefix, paragraphs, suffix = split_paragraphs(xml)
    # 1) carve+insert new experiences (e.g. Yiling) using Shenwan XML mold
    paragraphs = insert_missing_experiences(paragraphs, tailored)
    # 2) delete hidden entry blocks (swap project, etc.)
    paragraphs = delete_hidden_entries(paragraphs, tailored)
    # 3) content-only text replacements on remaining paras
    paragraphs = apply_text_replacements(paragraphs, tailored, inventory)
    # 4) rewrite experience headings with safe spacing (avoids PDF wrap/overlap)
    paragraphs = apply_experience_headings(paragraphs, tailored)
    new_xml = join_paragraphs(prefix, paragraphs, suffix)
    return write_document_xml(master_docx, new_xml)


def validate_ooxml(master_docx: bytes, gen_docx: bytes) -> dict[str, Any]:
    import re as _re
    from io import BytesIO
    from zipfile import ZipFile

    def counts(data: bytes) -> dict[str, Any]:
        with ZipFile(BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
            rels = z.read("word/_rels/document.xml.rels").decode("utf-8", errors="ignore")
        paras = _P_RE.findall(xml)
        pids = _PARA_ID_RE.findall(xml)
        return {
            "paragraphs": len(paras),
            "hyperlinks": len(_re.findall(r"<w:hyperlink", xml)),
            "external_rels": len(_re.findall(r'TargetMode="External"', rels)),
            "para_ids": len(pids),
            "unique_para_ids": len(set(pids)),
        }

    m, g = counts(master_docx), counts(gen_docx)
    errors = []
    if g["hyperlinks"] < m["hyperlinks"]:
        errors.append(f"hyperlinks {m['hyperlinks']}->{g['hyperlinks']}")
    if g["external_rels"] < m["external_rels"]:
        errors.append(f"external_rels {m['external_rels']}->{g['external_rels']}")
    if g["para_ids"] and g["unique_para_ids"] != g["para_ids"]:
        errors.append("duplicate_paraId")
    # Contact line must still contain LinkedIn + Portfolio as hyperlink display text
    gen_xml = read_document_xml(gen_docx)
    if "LinkedIn" not in gen_xml or "Portfolio" not in gen_xml:
        errors.append("missing_link_labels")
    if "<w:hyperlink" not in gen_xml:
        errors.append("no_hyperlink_elements")
    return {"ok": not errors, "errors": errors, "master": m, "generated": g}
