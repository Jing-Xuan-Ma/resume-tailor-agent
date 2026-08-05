"use client";

import { useEffect, useState } from "react";
import {
  getJobHistory,
  getRecommendedJobs,
  RecommendedJob,
  HistoryRecord,
} from "@/lib/api";

interface RecordsPanelProps {
  userId: string;
}

function shortId(value?: string) {
  return value ? value.slice(0, 8) : "";
}

function actionBadge(action: string) {
  const map: Record<string, string> = {
    resume_prepared: "bg-blue-50 text-blue-700",
    prepared_for_submit: "bg-amber-50 text-amber-700",
    auto_submitted: "bg-green-50 text-green-700",
    submitted_by_user: "bg-emerald-50 text-emerald-700",
    auto_submit_blocked: "bg-red-50 text-red-700",
  };
  const label: Record<string, string> = {
    resume_prepared: "Resume Prepared",
    prepared_for_submit: "Package Prepared",
    auto_submitted: "Auto-Submitted",
    submitted_by_user: "Manually Submitted",
    auto_submit_blocked: "Submit Blocked",
  };
  const cls = map[action] || "bg-slate-50 text-slate-600";
  return (
    <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${cls}`}>
      {label[action] || action}
    </span>
  );
}

export default function RecordsPanel({ userId }: RecordsPanelProps) {
  const [recommended, setRecommended] = useState<RecommendedJob[]>([]);
  const [history, setHistory] = useState<HistoryRecord[]>([]);
  const [totalCandidates, setTotalCandidates] = useState(0);
  const [alreadyProcessed, setAlreadyProcessed] = useState(0);
  const [loading, setLoading] = useState<string | null>(null);
  const [message, setMessage] = useState<string | undefined>();
  const [tab, setTab] = useState<"recommended" | "history">("recommended");
  const [historyFilter, setHistoryFilter] = useState<string>("all");

  const refresh = async () => {
    setLoading("refresh");
    setMessage(undefined);
    try {
      const [recRes, histRes] = await Promise.all([
        getRecommendedJobs(userId, 10),
        getJobHistory(userId, 50),
      ]);
      setRecommended(recRes.jobs);
      setTotalCandidates(recRes.total_candidates);
      setAlreadyProcessed(recRes.already_processed);
      setHistory(histRes.records);
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : "Failed to load records");
    } finally {
      setLoading(null);
    }
  };

  useEffect(() => {
    refresh();
  }, [userId]);

  const source = (platform: string) => platform.split(":")[0] || platform;
  const sourceBadgeColor = (s: string) =>
    s === "jobspy" ? "bg-blue-50 text-blue-700" :
    s === "remotive" ? "bg-green-50 text-green-700" :
    s === "remoteok" ? "bg-purple-50 text-purple-700" :
    s === "himalayas" ? "bg-orange-50 text-orange-700" :
    s === "jobicy" ? "bg-pink-50 text-pink-700" :
    s === "adzuna" ? "bg-teal-50 text-teal-700" :
    "bg-slate-50 text-slate-600";

  return (
    <div className="flex min-w-0 flex-1 flex-col bg-[#eef2f7]">
      <div className="border-b border-slate-200 bg-white/95 px-6 py-3 shadow-sm backdrop-blur">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-[15px] font-bold tracking-tight text-slate-950">Job Records</h2>
            <p className="text-xs text-slate-500">
              Track recommended jobs (≥85% match) and processing history.
            </p>
          </div>
          <button
            onClick={refresh}
            disabled={!!loading}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"
          >
            {loading === "refresh" ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        {message && <p className="mt-2 rounded-xl bg-slate-100 px-3 py-2 text-xs text-slate-700">{message}</p>}
      </div>

      <div className="flex gap-1 border-b border-slate-200 bg-white/80 px-6 pt-3 backdrop-blur">
        <button
          onClick={() => setTab("recommended")}
          className={`rounded-t-xl px-4 py-2 text-xs font-bold transition ${tab === "recommended" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
        >
          Recommended ({totalCandidates})
        </button>
        <button
          onClick={() => setTab("history")}
          className={`rounded-t-xl px-4 py-2 text-xs font-bold transition ${tab === "history" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
        >
          History ({history.length})
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        {tab === "recommended" ? (
          <div className="space-y-3">
            {totalCandidates > 0 && (
              <p className="rounded-2xl bg-blue-50 px-4 py-3 text-xs text-blue-800">
                {totalCandidates} job{totalCandidates !== 1 ? "s" : ""} with match score ≥85%.
                {alreadyProcessed > 0 && ` ${alreadyProcessed} already processed (excluded from list).`}
                Showing top {recommended.length}.
              </p>
            )}
            {recommended.length ? recommended.map((job) => {
              const s = source(job.source_platform);
              return (
                <div key={job.id} className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${sourceBadgeColor(s)}`}>{s}</span>
                        <span className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-bold text-green-700">★ {Math.round(job.match_score)}%</span>
                      </div>
                      <p className="mt-2 text-base font-bold text-slate-950">{job.title}</p>
                      <p className="text-sm text-slate-600">{[job.company, job.location].filter(Boolean).join(" · ") || ""}</p>
                    </div>
                    {job.source_url && (
                      <a href={job.source_url} target="_blank" rel="noreferrer" className="shrink-0 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
                        Open
                      </a>
                    )}
                  </div>
                </div>
              );
            }) : (
              <div
                className="rounded-3xl border border-dashed border-slate-300 bg-white p-8 text-center shadow-sm"
                data-testid="records-recommended-empty"
              >
                <p className="text-sm font-semibold text-slate-800">No ≥85% matches yet</p>
                <p className="mt-1 text-xs text-slate-500">
                  Open Ranked Jobs, raise your profile coverage, then Refresh here.
                </p>
                <a
                  href="/jobs"
                  className="mt-4 inline-flex h-9 items-center rounded-xl bg-emerald-600 px-4 text-xs font-semibold text-white hover:bg-emerald-700"
                  data-testid="records-goto-jobs"
                >
                  Browse ranked jobs
                </a>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-1.5" data-testid="records-history-filters">
              {[
                { id: "all", label: "All" },
                { id: "resume_prepared", label: "Prepared" },
                { id: "prepared_for_submit", label: "Package" },
                { id: "auto_submit_blocked", label: "Blocked" },
                { id: "submitted_by_user", label: "Manual" },
              ].map((f) => (
                <button
                  key={f.id}
                  type="button"
                  data-testid={`records-filter-${f.id}`}
                  onClick={() => setHistoryFilter(f.id)}
                  className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ring-1 ${
                    historyFilter === f.id
                      ? "bg-slate-900 text-white ring-slate-900"
                      : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>
            {(() => {
              const visible =
                historyFilter === "all"
                  ? history
                  : history.filter((r) => r.action === historyFilter);
              if (!history.length) {
                return (
              <div
                className="rounded-3xl border border-dashed border-slate-300 bg-white p-8 text-center shadow-sm"
                data-testid="records-history-empty"
              >
                <p className="text-sm font-semibold text-slate-800">No application history yet</p>
                <p className="mt-1 text-xs text-slate-500">
                  Tailor → Confirm → Apply on a job; records appear here after each dry-run or save.
                </p>
                <a
                  href="/?view=resume"
                  className="mt-4 inline-flex h-9 items-center rounded-xl border border-slate-300 bg-white px-4 text-xs font-semibold text-slate-800 hover:bg-slate-50"
                  data-testid="records-goto-tailor"
                >
                  Open Tailor workspace
                </a>
              </div>
                );
              }
              if (!visible.length) {
                return (
                  <div
                    className="rounded-3xl border border-dashed border-slate-200 bg-white p-6 text-center text-xs text-slate-500"
                    data-testid="records-history-filter-empty"
                  >
                    No history rows for this filter.
                  </div>
                );
              }
              return visible.map((rec) => (
              <div key={rec.id} className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {rec.source_platform && (
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${sourceBadgeColor(source(rec.source_platform))}`}>{source(rec.source_platform)}</span>
                      )}
                      {actionBadge(rec.action)}
                      {typeof rec.match_score === "number" && rec.match_score >= 85 && (
                        <span className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-bold text-green-700">★ {Math.round(rec.match_score)}%</span>
                      )}
                    </div>
                    <p className="mt-2 text-base font-bold text-slate-950">{rec.title || "Unknown Title"}</p>
                    <p className="text-sm text-slate-600">{[rec.company, rec.location].filter(Boolean).join(" · ") || ""}</p>
                    <p className="mt-1 text-xs text-slate-400">{rec.created_at?.slice(0, 16).replace("T", " ")}</p>
                  </div>
                  <div className="shrink-0 text-right text-xs text-slate-400">
                    #{shortId(rec.job_id)}
                  </div>
                </div>
              </div>
            ));
            })()}
          </div>
        )}
      </div>
    </div>
  );
}
