"""DOM field scan for ATS forms (Playwright page or pre-extracted dicts)."""

from __future__ import annotations

from typing import Any

# Runs inside page.evaluate — keep self-contained.
_SCAN_JS = r"""
() => {
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return "";
    if (el.id) return "#" + String(el.id).replace(/([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g, "\\$1");
    const tag = el.tagName.toLowerCase();
    const name = el.getAttribute("name");
    if (name) return tag + "[name=" + JSON.stringify(name) + "]";
    const parent = el.parentElement;
    if (!parent) return tag;
    const siblings = Array.from(parent.children).filter((c) => c.tagName === el.tagName);
    const idx = siblings.indexOf(el) + 1;
    return cssPath(parent) + " > " + tag + ":nth-of-type(" + idx + ")";
  }
  function labelFor(el) {
    const id = el.getAttribute("id");
    if (id) {
      const lab = document.querySelector('label[for="' + String(id).replace(/"/g, '\\"') + '"]');
      if (lab) return (lab.innerText || lab.textContent || "").trim();
    }
    const wrap = el.closest("label");
    if (wrap) return (wrap.innerText || wrap.textContent || "").trim().slice(0, 120);
    const prev = el.previousElementSibling;
    if (prev && prev.tagName === "LABEL") return (prev.innerText || "").trim();
    return "";
  }
  const out = [];
  const nodes = document.querySelectorAll("input, select, textarea");
  let i = 0;
  for (const el of nodes) {
    const type = (el.getAttribute("type") || el.tagName.toLowerCase()).toLowerCase();
    if (["hidden", "submit", "button", "image", "reset"].includes(type)) continue;
    if (el.disabled || el.getAttribute("aria-hidden") === "true") continue;
    const rect = el.getBoundingClientRect();
    if (type !== "file" && rect.width === 0 && rect.height === 0) continue;
    const options = [];
    if (el.tagName === "SELECT") {
      for (const opt of el.options) {
        options.push({ value: opt.value, label: (opt.textContent || "").trim() });
      }
    }
    out.push({
      field_id: "f" + (i++),
      tag: el.tagName.toLowerCase(),
      type: type === "select" ? "select" : type,
      name: el.getAttribute("name") || "",
      id: el.getAttribute("id") || "",
      label: labelFor(el),
      aria_label: el.getAttribute("aria-label") || "",
      placeholder: el.getAttribute("placeholder") || "",
      autocomplete: el.getAttribute("autocomplete") || "",
      required: !!el.required,
      options: options.slice(0, 30),
      selector: cssPath(el),
    });
  }
  return out;
}
"""


def scan_page_fields(page) -> list[dict[str, Any]]:
    """Scan main frame + child frames for fillable controls."""
    fields: list[dict[str, Any]] = []
    frames = list(page.frames)
    for fi, frame in enumerate(frames):
        try:
            raw = frame.evaluate(_SCAN_JS)
        except Exception:
            continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row["frame_index"] = fi
            row["field_id"] = f"fr{fi}_{row.get('field_id') or len(fields)}"
            fields.append(row)
    return fields


def normalize_client_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize fields posted by a content script / API client."""
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(fields[:80]):
        if not isinstance(raw, dict):
            continue
        out.append(
            {
                "field_id": str(raw.get("field_id") or f"c{i}"),
                "tag": str(raw.get("tag") or "input").lower(),
                "type": str(raw.get("type") or "text").lower(),
                "name": str(raw.get("name") or ""),
                "id": str(raw.get("id") or ""),
                "label": str(raw.get("label") or "")[:200],
                "aria_label": str(raw.get("aria_label") or "")[:200],
                "placeholder": str(raw.get("placeholder") or "")[:200],
                "autocomplete": str(raw.get("autocomplete") or ""),
                "required": bool(raw.get("required")),
                "options": raw.get("options") if isinstance(raw.get("options"), list) else [],
                "selector": str(raw.get("selector") or ""),
                "frame_index": int(raw.get("frame_index") or 0),
            }
        )
    return out
