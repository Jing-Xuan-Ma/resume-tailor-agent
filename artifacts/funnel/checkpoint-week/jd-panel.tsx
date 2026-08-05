"use client";

import { useMemo, useState, useEffect } from "react";
import type { KeywordMatchItem } from "@/lib/api";

interface JdPanelProps {
  jdText: string;
  keywordMatches: KeywordMatchItem[];
  loading?: boolean;
  /** When true, grow with content (parent scrolls). Avoids tiny nested scroll areas. */
  expandContent?: boolean;
}

function stripJdHtml(raw: string): string {
  let text = raw || "";
  text = text.replace(/<(br|\/p|\/li|\/div|\/h\d)[^>]*>/gi, "\n");
  text = text.replace(/<li[^>]*>/gi, "\n- ");
  text = text.replace(/<[^>]+>/g, " ");
  text = text
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">");
  const cssNoise =
    /^(?:tw-|sm:|md:|lg:|xl:|hover:|focus:|ring-|border-|shadow-|bg-|text-|flex|grid|rounded|px-|py-|mt-|mb-|w-|h-|font-|leading-|tracking-|opacity-|transition|absolute|relative|inset-|overflow-|items-|justify-|gap-|prose)/i;
  return text
    .split(/\r?\n/)
    .map((l) => l.replace(/[ \t]+/g, " ").trim())
    .filter((l) => {
      if (!l) return true;
      const tokens = l.split(/\s+/);
      const noisy = tokens.filter((t) => cssNoise.test(t) || t.startsWith("tw-")).length;
      return noisy < Math.max(2, Math.ceil(tokens.length / 2));
    })
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function parseSections(jdText: string): { required: string[]; preferred: string[]; other: string[] } {
  const cleaned = stripJdHtml(jdText);
  const lines = cleaned.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const required: string[] = [];
  const preferred: string[] = [];
  const other: string[] = [];
  let mode: "required" | "preferred" | "other" = "other";

  for (const line of lines) {
    const lower = line.toLowerCase().replace(/:$/, "");
    if (/^(requirements?|required|qualifications?|must[\s-]have|what you.?ll need)/i.test(lower)) {
      mode = "required";
      continue;
    }
    if (/^(preferred|nice[\s-]to[\s-]have|bonus|plus|desired)/i.test(lower)) {
      mode = "preferred";
      continue;
    }
    if (/^(about|responsibilities|what you.?ll do|role|overview)/i.test(lower)) {
      mode = "other";
      continue;
    }
    const bullet = line.replace(/^[•\-\*]\s*/, "").trim();
    if (!bullet || bullet.length < 3) continue;
    if (mode === "required") required.push(bullet);
    else if (mode === "preferred") preferred.push(bullet);
    else other.push(bullet);
  }

  // If no structured sections, put first half-ish of bullets into required
  if (!required.length && !preferred.length && other.length) {
    return {
      required: other.slice(0, Math.max(3, Math.ceil(other.length * 0.6))),
      preferred: other.slice(Math.max(3, Math.ceil(other.length * 0.6))),
      other: [],
    };
  }
  return { required, preferred, other };
}

function isCovered(status: string) {
  return status === "covered" || status === "matched" || status === "partial";
}

export default function JdPanel({ jdText, keywordMatches, loading, expandContent = false }: JdPanelProps) {
  const sections = useMemo(() => parseSections(jdText || ""), [jdText]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const next: Record<string, boolean> = {};
    for (const m of keywordMatches) {
      next[m.keyword] = isCovered(m.status);
    }
    setSelected(next);
  }, [keywordMatches]);

  const toggle = (keyword: string) => {
    setSelected((prev) => ({ ...prev, [keyword]: !prev[keyword] }));
  };

  if (!jdText) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="jd-panel">
        <h3 className="text-base font-bold text-slate-900">Qualification</h3>
        <p className="mt-2 text-sm text-slate-500">Paste a job description to see skill alignment.</p>
      </div>
    );
  }

  const shellClass = expandContent
    ? "shrink-0 rounded-2xl border border-slate-200 bg-white shadow-sm"
    : "flex h-full min-h-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm";
  const bodyClass = expandContent
    ? "px-5 py-4"
    : "min-h-0 flex-1 overflow-y-auto px-5 py-4";

  return (
    <div className={shellClass} data-testid="jd-panel">
      <div className="border-b border-slate-100 px-5 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor" aria-hidden>
                  <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
                  <circle cx="10" cy="10" r="3" />
                </svg>
              </span>
              <h3 className="text-base font-bold tracking-tight text-slate-950">Qualification</h3>
            </div>
            <p className="mt-1 max-w-xl text-[12px] leading-4 text-slate-500">
              Click tags to mark skills you actually have. Green = matched to your resume.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5 text-[11px] text-slate-500">
            <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-white">
              <svg viewBox="0 0 20 20" className="h-3 w-3" fill="currentColor" aria-hidden>
                <path d="M7.5 17h7.2c.7 0 1.3-.4 1.5-1.1l1.5-5.2c.2-.7-.3-1.4-1-1.4H12V6.2C12 4.7 11 4 10.2 4c-.5 0-.8.4-.9.9L8.5 9.5H5.8c-.7 0-1.3.6-1.3 1.3v5c0 .7.6 1.2 1.3 1.2h1.7z" />
              </svg>
            </span>
            Represents the skills you have.
          </div>
        </div>

        <div className="relative mt-4">
          {loading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-white/70 text-sm text-slate-500">
              Analyzing…
            </div>
          )}
          <div className="flex flex-wrap gap-2" data-testid="qualification-tags">
            {keywordMatches.length === 0 && !loading ? (
              <span className="text-sm text-slate-400">Skill tags appear after JD analysis.</span>
            ) : (
              keywordMatches.map((m) => {
                const on = selected[m.keyword] ?? isCovered(m.status);
                return (
                  <button
                    key={m.keyword}
                    type="button"
                    onClick={() => toggle(m.keyword)}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] font-medium ring-1 transition ${
                      on
                        ? "bg-emerald-50 text-emerald-900 ring-emerald-200 hover:bg-emerald-100"
                        : "bg-slate-50 text-slate-600 ring-slate-200 hover:bg-slate-100"
                    }`}
                  >
                    {on ? (
                      <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500 text-white">
                        <svg viewBox="0 0 20 20" className="h-2.5 w-2.5" fill="currentColor" aria-hidden>
                          <path d="M7.5 17h7.2c.7 0 1.3-.4 1.5-1.1l1.5-5.2c.2-.7-.3-1.4-1-1.4H12V6.2C12 4.7 11 4 10.2 4c-.5 0-.8.4-.9.9L8.5 9.5H5.8c-.7 0-1.3.6-1.3 1.3v5c0 .7.6 1.2 1.3 1.2h1.7z" />
                        </svg>
                      </span>
                    ) : null}
                    {m.keyword}
                  </button>
                );
              })
            )}
          </div>
        </div>
      </div>

      <div className={bodyClass}>
        {sections.required.length > 0 && (
          <section className="mb-5">
            <h4 className="mb-2 text-sm font-bold text-slate-950">Required</h4>
            <ul className="space-y-1.5 text-[13px] leading-5 text-slate-700">
              {sections.required.map((item, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {sections.preferred.length > 0 && (
          <section className="mb-5">
            <h4 className="mb-2 text-sm font-bold text-slate-950">Preferred</h4>
            <ul className="space-y-1.5 text-[13px] leading-5 text-slate-700">
              {sections.preferred.map((item, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {!sections.required.length && !sections.preferred.length && (
          <pre className="whitespace-pre-wrap font-sans text-[13px] leading-5 text-slate-700" data-testid="jd-plaintext">
            {stripJdHtml(jdText)}
          </pre>
        )}
      </div>
    </div>
  );
}
