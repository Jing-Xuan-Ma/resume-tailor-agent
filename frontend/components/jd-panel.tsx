"use client";

import { useMemo } from "react";
import type { KeywordMatchItem } from "@/lib/api";

interface JdPanelProps {
  jdText: string;
  keywordMatches: KeywordMatchItem[];
  loading?: boolean;
}

export default function JdPanel({ jdText, keywordMatches, loading }: JdPanelProps) {
  const highlightedJd = useMemo(() => {
    if (!jdText || !keywordMatches.length) return jdText;

    const coveredTerms = keywordMatches
      .filter((m) => m.status === "covered")
      .map((m) => m.keyword)
      .sort((a, b) => b.length - a.length);

    const missingTerms = keywordMatches
      .filter((m) => m.status === "missing")
      .map((m) => m.keyword)
      .sort((a, b) => b.length - a.length);

    let text = jdText;
    for (const term of coveredTerms) {
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      text = text.replace(new RegExp(escaped, "gi"), (match) => `__COV__${match}__/COV__`);
    }
    for (const term of missingTerms) {
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      text = text.replace(new RegExp(escaped, "gi"), (match) => `__MIS__${match}__/MIS__`);
    }

    const parts = text.split(/(__COV__.*?__\/COV__|__MIS__.*?__\/MIS__)/g);
    return parts.map((part, idx) => {
      if (part.startsWith("__COV__")) {
        const content = part.replace("__COV__", "").replace("__/COV__", "");
        return { type: "covered", content, key: idx };
      }
      if (part.startsWith("__MIS__")) {
        const content = part.replace("__MIS__", "").replace("__/MIS__", "");
        return { type: "missing", content, key: idx };
      }
      return { type: "plain", content: part, key: idx };
    });
  }, [jdText, keywordMatches]);

  if (!jdText) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Job Description</h3>
        <p className="text-sm text-slate-400">Paste a JD to see keyword analysis.</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">Job Description</h3>
        <span className="text-[11px] text-slate-400">
          {keywordMatches.filter((m) => m.status === "covered").length}/{keywordMatches.length} covered
        </span>
      </div>
      <div className="relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-white/70">
            <span className="text-sm text-slate-500">Analyzing...</span>
          </div>
        )}
        <div className="max-h-[280px] overflow-y-auto rounded-xl bg-slate-50 p-4 text-[13px] leading-6 text-slate-800">
          {highlightedJd && Array.isArray(highlightedJd)
            ? highlightedJd.map((part) => {
                if (part.type === "covered") {
                  return (
                    <span key={part.key} className="rounded bg-green-100 px-0.5 text-green-900">
                      {part.content}
                    </span>
                  );
                }
                if (part.type === "missing") {
                  return (
                    <span key={part.key} className="rounded bg-amber-100 px-0.5 text-amber-900 underline decoration-amber-400 decoration-dashed">
                      {part.content}
                    </span>
                  );
                }
                return <span key={part.key}>{part.content}</span>;
              })
            : jdText}
        </div>
      </div>
      <div className="mt-3 flex gap-3 text-[11px] text-slate-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-green-100" /> Covered in resume
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-100 underline decoration-amber-400 decoration-dashed" /> Missing from resume
        </span>
      </div>
    </div>
  );
}
