# Tailor UI simplify

**Status: PASS (visual QA)**

## Goal

Simplify tailor to core only:

- Left: resume LLM chat agent
- Right: JobRight-style Qualification JD + resume PDF preview
- Remove Keyword Gap, Diff, Apply Mode, version tabs clutter, outer ChatPanel on tailor view

## Iteration

1. Redesign `resume-workspace.tsx` two-column layout  
2. Rewrite `jd-panel.tsx` as Qualification (tags + Required/Preferred)  
3. Expand `workspace-chat.tsx` as full-height agent  
4. Hide global `ChatPanel` when `view=resume`  
5. Playwright screenshots → polish thumbs icon / spacing  

## Evidence

Screenshots: `artifacts/ui/tailor-simplify/`

- `01-full.png` — full layout  
- `02-jd-panel.png` — Qualification  
- `03-chat.png` — agent  
- `checks.json` — structural checks all true  

## Kept (core)

Paste JD · chat rewrite · Confirm · version select · DOCX/PDF export after confirm
