"use client";

import { useEffect, useState } from "react";
import { getResumeConstitution, type ConstitutionRule } from "@/lib/api";

export default function ConstitutionPanel() {
  const [rules, setRules] = useState<ConstitutionRule[]>([]);
  const [master, setMaster] = useState("Jingxuan_Resume_Data Analyst.docx");
  const [track, setTrack] = useState("Data Analyst / Analytics");
  const [open, setOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getResumeConstitution()
      .then((data) => {
        if (cancelled) return;
        setRules(data.rules || []);
        if (data.master_template) setMaster(data.master_template);
        if (data.track) setTrack(data.track);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Could not load constitution from API — using built-in summary.");
        setRules([
          {
            id: "no-fabricate",
            title: "No fabrication",
            detail: "Never invent employers, titles, dates, tools, metrics, or certificates.",
          },
          {
            id: "format-lock",
            title: "Format locked",
            detail: "Content-only edits on the master DOCX template.",
          },
          {
            id: "one-page",
            title: "One page",
            detail: "Fit by show/hide — never shrink fonts or margins.",
          },
          {
            id: "confirm",
            title: "Confirm before final",
            detail: "Final save only after you click Confirm.",
          },
        ]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div
      className="shrink-0 rounded-2xl border border-emerald-200/80 bg-gradient-to-br from-emerald-50/90 to-white shadow-sm"
      data-testid="constitution-panel"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left"
        data-testid="constitution-toggle"
      >
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
            Resume rules · {track}
          </p>
          <p className="mt-0.5 text-[12px] text-slate-600">
            Master: <span className="font-medium text-slate-800">{master}</span>
          </p>
        </div>
        <span className="text-xs font-semibold text-emerald-700">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        <div className="border-t border-emerald-100 px-4 pb-3 pt-2">
          {error ? <p className="mb-2 text-[11px] text-amber-700">{error}</p> : null}
          <ul className="space-y-2" data-testid="constitution-rules">
            {rules.map((r) => (
              <li key={r.id} className="flex gap-2 text-[12px] leading-4 text-slate-700">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                <span>
                  <strong className="font-semibold text-slate-900">{r.title}.</strong> {r.detail}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[10px] text-slate-400">
            Source: RESUME_CONSTITUTION.md — highest policy for every tailor turn.
          </p>
        </div>
      ) : null}
    </div>
  );
}
