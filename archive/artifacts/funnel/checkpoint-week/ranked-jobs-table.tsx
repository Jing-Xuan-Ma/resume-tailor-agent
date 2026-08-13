"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import FlowStepper from "@/components/flow-stepper";
import { getAuthUserId } from "@/lib/auth-user";

interface Stage3Result {
  atsScore: number;
  semanticScore: number;
  hardConditionsPassed: boolean;
  finalScore: number;
  coveredKeywords: string[];
  missingKeywords: string[];
}

export interface RankedJob {
  id: string;
  company: string;
  title: string;
  source: string;
  originalUrl: string;
  scrapedAt: string;
  location?: string;
  workModel?: string;
  salary?: string;
  stage3Result: Stage3Result | null;
  status: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";


const CATEGORIES = [
  "Data Analysis",
  "Business Analyst",
  "Machine Learning and AI",
  "AI Agent",
  "Software Engineering",
  "Risk / Insurance Analytics",
];

function pct(v: number) {
  return Math.round(v * 100);
}

function relativeDate(iso: string) {
  const ms = Date.now() - new Date(iso).getTime();
  const hours = Math.max(1, Math.round(ms / 3600000));
  if (hours < 48) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function isStaleOver14d(iso: string) {
  const ms = Date.now() - new Date(iso).getTime();
  return ms > 14 * 24 * 3600000;
}

function workModelClass(model?: string) {
  switch (model) {
    case "Hybrid":
      return "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200";
    case "Remote":
      return "bg-cyan-50 text-cyan-800 ring-1 ring-cyan-200";
    case "On Site":
      return "bg-violet-50 text-violet-800 ring-1 ring-violet-200";
    default:
      return "bg-slate-100 text-slate-600 ring-1 ring-slate-200";
  }
}

function scoreClass(score: number) {
  if (score >= 85) return "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200";
  if (score >= 60) return "bg-amber-50 text-amber-800 ring-1 ring-amber-200";
  return "bg-slate-100 text-slate-500 ring-1 ring-slate-200";
}

export default function RankedJobsTable() {
  const router = useRouter();
  const [jobs, setJobs] = useState<RankedJob[]>([]);
  const [filteredTotal, setFilteredTotal] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("all");
  const [sources, setSources] = useState<string[]>([]);
  const [threshold, setThreshold] = useState(0);
  const [sortBy, setSortBy] = useState<"score" | "date">("score");
  const [activeCategory, setActiveCategory] = useState("Data Analysis");
  const [hideStale, setHideStale] = useState(false);

  useEffect(() => {
    try {
      setHideStale(localStorage.getItem("resume-agent-hide-stale") === "1");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem("resume-agent-hide-stale", hideStale ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [hideStale]);

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        user_id: getAuthUserId(),
        threshold: String(threshold),
        sort_by: sortBy,
        top_n: "0",
        source: source === "all" ? "" : source,
        search,
        category: activeCategory,
      });
      const res = await fetch(`${API_BASE}/api/v1/jobs/list?${params}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setJobs(data.jobs || []);
      setTotal(data.total || 0);
      setFilteredTotal(data.filtered_total || 0);
    } catch (err: unknown) {
      setJobs([]);
      setError(err instanceof Error ? err.message : "Could not load jobs");
    } finally {
      setLoading(false);
    }
  }, [threshold, sortBy, source, search, activeCategory]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/jobs/sources/list`)
      .then((r) => (r.ok ? r.json() : { sources: [] }))
      .then((d) => setSources(d.sources || []))
      .catch(() => setSources([]));
  }, []);

  return (
    <div className="min-h-screen bg-[#f4f6f4] text-slate-900" data-testid="ranked-jobs-page">
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-700">Resume Agent</p>
            <h1 className="text-2xl font-bold tracking-tight text-slate-950">Ranked Jobs</h1>
            <p className="mt-0.5 text-xs text-slate-500">
              Match = resume↔JD heuristic (skills + ATS keywords). Click a row to tailor.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <FlowStepper current="jobs" />
            <a
              href="/"
              className="text-xs font-semibold text-slate-500 hover:text-slate-900"
              data-testid="link-workspace"
            >
              Open full workspace →
            </a>
          </div>
        </div>
        <div className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-6 pb-3">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setActiveCategory(cat)}
              className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition ${
                activeCategory === cat
                  ? "bg-emerald-600 text-white ring-emerald-600"
                  : "bg-white text-slate-700 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-6 py-4">
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
          <input
            data-testid="jobs-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchJobs()}
            placeholder="Search title or company"
            className="h-9 min-w-[200px] flex-1 rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-emerald-500"
          />
          <select
            data-testid="jobs-source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="h-9 rounded-xl border border-slate-200 bg-white px-3 text-sm"
          >
            <option value="all">All Sources</option>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-xs text-slate-600">
            Min score
            <input
              type="range"
              min={0}
              max={100}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="accent-emerald-600"
            />
            <span className="w-8 font-semibold">{threshold}%</span>
          </label>
          <div className="flex rounded-xl bg-slate-100 p-0.5 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setSortBy("score")}
              className={`rounded-lg px-3 py-1.5 ${sortBy === "score" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
            >
              Best match
            </button>
            <button
              type="button"
              onClick={() => setSortBy("date")}
              className={`rounded-lg px-3 py-1.5 ${sortBy === "date" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
            >
              Newest
            </button>
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-600" data-testid="jobs-hide-stale">
            <input
              type="checkbox"
              checked={hideStale}
              onChange={(e) => setHideStale(e.target.checked)}
              className="accent-emerald-600"
            />
            Hide stale &gt;14d
          </label>
          <button
            type="button"
            data-testid="jobs-refresh"
            onClick={fetchJobs}
            className="h-9 rounded-xl bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-700"
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
          <span className="ml-auto text-xs text-slate-500" data-testid="jobs-count">
            {(() => {
              if (!hideStale) {
                return `${filteredTotal || jobs.length} shown${total ? ` / ${total} indexed` : ""}`;
              }
              const shown = jobs.filter((j) => !isStaleOver14d(j.scrapedAt)).length;
              const hidden = jobs.length - shown;
              return `${shown} shown${hidden ? ` · ${hidden} stale hidden` : ""}${total ? ` / ${total} indexed` : ""}`;
            })()}
          </span>
        </div>

        {error ? (
          <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="jobs-error">
            {error}. Is the API running on {API_BASE}?
          </div>
        ) : null}

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="hidden grid-cols-[40px_minmax(0,2fr)_88px_72px_88px_100px_minmax(0,1fr)_minmax(0,1fr)_100px] gap-2 border-b border-slate-100 px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500 md:grid">
            <span>#</span>
            <span>Position</span>
            <span>Posted</span>
            <span
              className="text-center"
              data-testid="jobs-match-header"
              title="Heuristic resume↔JD fit (skills + ATS keywords), not a vendor ATS parse"
            >
              Match
            </span>
            <span className="text-center">Work</span>
            <span>Location</span>
            <span>Company</span>
            <span>Source</span>
          </div>
          <div data-testid="jobs-table-body">
            {(() => {
              const visible = hideStale ? jobs.filter((j) => !isStaleOver14d(j.scrapedAt)) : jobs;
              if (visible.length === 0) {
                return (
              <div className="px-4 py-16 text-center" data-testid="jobs-empty">
                <p className="text-sm font-semibold text-slate-700">
                  {loading ? "Loading ranked jobs…" : "No jobs match your filters"}
                </p>
                {!loading ? (
                  <p className="mt-2 text-xs text-slate-500">
                    Lower the min score, clear search, or refresh. You can still open Workspace to paste a JD.
                  </p>
                ) : null}
              </div>
                );
              }
              return visible.map((job, idx) => {
                const score = job.stage3Result ? pct(job.stage3Result.finalScore) : null;
                return (
                  <button
                    key={job.id}
                    type="button"
                    data-testid={`job-row-${job.id}`}
                    onClick={() => router.push(`/jobs/${job.id}`)}
                    className="grid w-full grid-cols-1 gap-1 border-b border-slate-50 px-4 py-3 text-left transition hover:bg-emerald-50/60 md:grid-cols-[40px_minmax(0,2fr)_88px_72px_88px_100px_minmax(0,1fr)_minmax(0,1fr)_100px] md:gap-2 md:items-center"
                  >
                    <span className="hidden text-slate-400 md:inline">{idx + 1}</span>
                    <span className="truncate font-semibold text-slate-950">{job.title}</span>
                    <span className="flex items-center gap-1 text-xs text-slate-500" data-testid="job-posted-age">
                      {relativeDate(job.scrapedAt)}
                      {isStaleOver14d(job.scrapedAt) ? (
                        <span
                          className="rounded bg-amber-100 px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide text-amber-800"
                          data-testid="job-stale-badge"
                          title="Posted age over 14 days"
                        >
                          Stale
                        </span>
                      ) : null}
                    </span>
                    <span className="text-left md:text-center">
                      {score !== null ? (
                        <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${scoreClass(score)}`}>
                          {score}%
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </span>
                    <span className="text-left md:text-center">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${workModelClass(job.workModel)}`}>
                        {job.workModel || "—"}
                      </span>
                    </span>
                    <span className="truncate text-xs text-slate-600">{job.location || "—"}</span>
                    <span className="truncate text-xs font-medium text-slate-800">{job.company}</span>
                    <span className="truncate text-[11px] font-semibold uppercase tracking-wide text-slate-500" data-testid="job-source">
                      {job.source || "—"}
                    </span>
                  </button>
                );
              });
            })()}
          </div>
        </div>
      </div>
    </div>
  );
}
