"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

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
const DEMO_USER = "00000000-0000-0000-0000-0000000000a1";

const CATEGORIES = [
  "Data Analysis",
  "Machine Learning and AI",
  "Software Engineering",
  "Product Management",
  "Business Analyst",
  "Consulting",
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
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("all");
  const [sources, setSources] = useState<string[]>([]);
  const [threshold, setThreshold] = useState(0);
  const [sortBy, setSortBy] = useState<"score" | "date">("score");
  const [activeCategory, setActiveCategory] = useState("Software Engineering");

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        user_id: DEMO_USER,
        threshold: String(threshold),
        sort_by: sortBy,
        top_n: "0",
        source: source === "all" ? "" : source,
        search,
      });
      const res = await fetch(`${API_BASE}/api/v1/jobs/list?${params}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setJobs(data.jobs || []);
      setTotal(data.total || 0);
      setFilteredTotal(data.filtered_total || 0);
    } finally {
      setLoading(false);
    }
  }, [threshold, sortBy, source, search]);

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
    <div className="min-h-screen bg-[#f7f8f6] text-slate-900" data-testid="ranked-jobs-page">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">Resume Agent</p>
            <h1 className="text-2xl font-bold tracking-tight">Ranked Jobs</h1>
          </div>
          <a href="/" className="text-sm font-semibold text-slate-600 hover:text-slate-950">
            Workspace
          </a>
        </div>
        <div className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-6 pb-4">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setActiveCategory(cat)}
              className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ${
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
            Threshold
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
              className={`rounded-lg px-3 py-1.5 ${sortBy === "score" ? "bg-white shadow-sm" : "text-slate-500"}`}
            >
              Score
            </button>
            <button
              type="button"
              onClick={() => setSortBy("date")}
              className={`rounded-lg px-3 py-1.5 ${sortBy === "date" ? "bg-white shadow-sm" : "text-slate-500"}`}
            >
              Date
            </button>
          </div>
          <button
            type="button"
            data-testid="jobs-refresh"
            onClick={fetchJobs}
            className="h-9 rounded-xl bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-700"
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
          <span className="ml-auto text-xs text-slate-500">
            {filteredTotal} ranked · {total} shown
          </span>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="grid grid-cols-[40px_minmax(0,2fr)_90px_90px_100px_minmax(0,1fr)_minmax(0,1fr)_120px] gap-2 border-b border-slate-100 px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span>#</span>
            <span>Position</span>
            <span>Date</span>
            <span className="text-center">Score</span>
            <span className="text-center">Work Model</span>
            <span>Location</span>
            <span>Company</span>
            <span>Salary</span>
          </div>
          <div data-testid="jobs-table-body">
            {jobs.length === 0 ? (
              <div className="px-4 py-16 text-center text-sm text-slate-400">
                {loading ? "Loading ranked jobs…" : "No jobs match your filters."}
              </div>
            ) : (
              jobs.map((job, idx) => {
                const score = job.stage3Result ? pct(job.stage3Result.finalScore) : null;
                return (
                  <button
                    key={job.id}
                    type="button"
                    data-testid={`job-row-${job.id}`}
                    onClick={() => router.push(`/jobs/${job.id}`)}
                    className="grid w-full grid-cols-[40px_minmax(0,2fr)_90px_90px_100px_minmax(0,1fr)_minmax(0,1fr)_120px] gap-2 border-b border-slate-50 px-4 py-3 text-left text-sm transition hover:bg-emerald-50/50"
                  >
                    <span className="text-slate-400">{idx + 1}</span>
                    <span className="truncate font-semibold text-slate-950">{job.title}</span>
                    <span className="text-xs text-slate-500">{relativeDate(job.scrapedAt)}</span>
                    <span className="text-center">
                      {score !== null ? (
                        <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${scoreClass(score)}`}>
                          {score}%
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </span>
                    <span className="text-center">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${workModelClass(job.workModel)}`}>
                        {job.workModel || "—"}
                      </span>
                    </span>
                    <span className="truncate text-xs text-slate-600">{job.location || "—"}</span>
                    <span className="truncate text-xs font-medium text-slate-800">{job.company}</span>
                    <span className="truncate text-xs text-slate-600">{job.salary || "N/A"}</span>
                  </button>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
