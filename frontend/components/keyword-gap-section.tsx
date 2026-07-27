"use client";

import { useState } from "react";
import type { KeywordMatchItem } from "@/lib/api";

interface KeywordGapSectionProps {
  keywordMatches: KeywordMatchItem[];
  onSuggest: (keyword: string) => void;
  loading?: boolean;
}

export default function KeywordGapSection({
  keywordMatches,
  onSuggest,
  loading,
}: KeywordGapSectionProps) {
  const [suggesting, setSuggesting] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Record<string, string>>({});

  const missingKeywords = keywordMatches.filter((m) => m.status === "missing");

  if (!missingKeywords.length) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">
          Keyword Gap Analysis
        </h3>
        <p className="text-sm text-green-600">All keywords are covered! Great match.</p>
      </div>
    );
  }

  const handleSuggest = async (keyword: string) => {
    if (suggestions[keyword] || suggesting === keyword) return;
    setSuggesting(keyword);
    try {
      onSuggest(keyword);
      setSuggestions((prev) => ({
        ...prev,
        [keyword]: "Consider building a practical project to demonstrate this skill. This will make your resume more competitive for roles requiring this keyword.",
      }));
    } finally {
      setSuggesting(null);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">
          Keyword Gap Analysis
        </h3>
        <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
          {missingKeywords.length} gaps found
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {missingKeywords.map((item) => {
          const hasSuggestion = !!suggestions[item.keyword];
          return (
            <div
              key={item.keyword}
              className="rounded-xl border border-amber-100 bg-amber-50/50 p-4"
            >
              <div className="mb-2 flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-amber-500" />
                <span className="text-sm font-semibold text-slate-950">{item.keyword}</span>
              </div>

              {hasSuggestion ? (
                <p className="mb-2 text-[13px] leading-5 text-slate-600">
                  {suggestions[item.keyword]}
                </p>
              ) : item.suggestion ? (
                <p className="mb-2 text-[13px] leading-5 text-slate-600">
                  {item.suggestion}
                </p>
              ) : (
                <p className="mb-2 text-[13px] leading-5 text-slate-500">
                  This keyword is not reflected in your resume.
                </p>
              )}

              <button
                onClick={() => handleSuggest(item.keyword)}
                disabled={loading || suggesting === item.keyword || hasSuggestion}
                className="mt-1 rounded-lg bg-amber-100 px-3 py-1.5 text-[11px] font-semibold text-amber-800 hover:bg-amber-200 disabled:opacity-50"
              >
                {suggesting === item.keyword
                  ? "Thinking..."
                  : hasSuggestion
                  ? "Suggested ✓"
                  : "Ask AI for suggestion"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
