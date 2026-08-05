"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import FlowStepper from "@/components/flow-stepper";
import { getAuthUserId } from "@/lib/auth-user";
import { discoverJobs } from "@/lib/api";

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
  const [searchLive, setSearchLive] = useState("");
  const [source, setSource] = useState("all");
  const [sourceReady, setSourceReady] = useState(false);
  const [sources, setSources] = useState<string[]>([]);
  const [threshold, setThreshold] = useState(0);
  const [thresholdLive, setThresholdLive] = useState(0);
  const [thresholdReady, setThresholdReady] = useState(false);
  const [sortBy, setSortBy] = useState<"score" | "date">("score");
  const [sortReady, setSortReady] = useState(false);
  const [activeCategory, setActiveCategory] = useState("Data Analysis");
  const [categoryReady, setCategoryReady] = useState(false);
  const [hideStale, setHideStale] = useState(false);
  const [hideStaleReady, setHideStaleReady] = useState(false);
  const [jobspyHealth, setJobspyHealth] = useState<"ok" | "down" | "unknown">("unknown");
  const [discovering, setDiscovering] = useState(false);
  const [discoverNote, setDiscoverNote] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setThreshold(thresholdLive), 280);
    return () => window.clearTimeout(t);
  }, [thresholdLive]);

  useEffect(() => {
    const t = window.setTimeout(() => setSearch(searchLive), 320);
    return () => window.clearTimeout(t);
  }, [searchLive]);

  useEffect(() => {
    try {
      setHideStale(localStorage.getItem("resume-agent-hide-stale") === "1");
      const cat = localStorage.getItem("resume-agent-jobs-category");
      if (cat && CATEGORIES.includes(cat)) setActiveCategory(cat);
      const sort = localStorage.getItem("resume-agent-jobs-sort");
      if (sort === "score" || sort === "date") setSortBy(sort);
      const thrRaw = localStorage.getItem("resume-agent-jobs-threshold");
      if (thrRaw != null) {
        const thr = Number(thrRaw);
        if (Number.isFinite(thr) && thr >= 0 && thr <= 100) {
          setThresholdLive(thr);
          setThreshold(thr);
        }
      }
      const src = localStorage.getItem("resume-agent-jobs-source");
      if (src) setSource(src);
    } catch {
      /* ignore */
    }
    setHideStaleReady(true);
    setCategoryReady(true);
    setSortReady(true);
    setThresholdReady(true);
    setSourceReady(true);
  }, []);

  useEffect(() => {
    if (!categoryReady) return;
    try {
      localStorage.setItem("resume-agent-jobs-category", activeCategory);
    } catch {
      /* ignore */
    }
  }, [activeCategory, categoryReady]);

  useEffect(() => {
    if (!sortReady) return;
    try {
      localStorage.setItem("resume-agent-jobs-sort", sortBy);
    } catch {
      /* ignore */
    }
  }, [sortBy, sortReady]);

  useEffect(() => {
    if (!thresholdReady) return;
    try {
      localStorage.setItem("resume-agent-jobs-threshold", String(threshold));
    } catch {
      /* ignore */
    }
  }, [threshold, thresholdReady]);

  useEffect(() => {
    if (!sourceReady) return;
    try {
      localStorage.setItem("resume-agent-jobs-source", source);
    } catch {
      /* ignore */
    }
  }, [source, sourceReady]);

  useEffect(() => {
    if (!hideStaleReady) return;
    try {
      localStorage.setItem("resume-agent-hide-stale", hideStale ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [hideStale, hideStaleReady]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/jobs/providers/jobspy/health`);
        const data = (await res.json()) as { status?: string };
        if (!cancelled) setJobspyHealth(data.status === "ok" ? "ok" : "down");
      } catch {
        if (!cancelled) setJobspyHealth("down");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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

  const runDiscover = useCallback(async () => {
    setDiscovering(true);
    setDiscoverNote(null);
    setError(null);
    try {
      const res = await discoverJobs({
        user_id: getAuthUserId(),
        query: activeCategory,
        location: "United States",
        limit: 5,
        hours_old: 72,
      });
      const n = res.jobs?.length ?? 0;
      setDiscoverNote(`Discover returned ${n} job(s) for “${activeCategory}”. Refreshing list…`);
      await fetchJobs();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Discover failed");
    } finally {
      setDiscovering(false);
    }
  }, [activeCategory, fetchJobs]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      e.preventDefault();
      document.querySelector<HTMLInputElement>("[data-testid=jobs-search]")?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
              Match = resume↔JD heuristic (skills + ATS keywords). Click a row for Match, then JD.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <FlowStepper
              current="jobs"
              hrefs={{
                jobs: "/jobs",
                jd: "/?view=resume&step=jd",
                tailor: "/?view=resume&step=tailor",
              }}
            />
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
            value={searchLive}
            onChange={(e) => setSearchLive(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                setSearch(searchLive);
                fetchJobs();
              }
            }}
            placeholder="Search title or company (/ to focus)"
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
              value={thresholdLive}
              onChange={(e) => setThresholdLive(Number(e.target.value))}
              className="accent-emerald-600"
            />
            <span className="w-8 font-semibold" data-testid="jobs-threshold-value">
              {thresholdLive}%
            </span>
          </label>
          <div className="flex rounded-xl bg-slate-100 p-0.5 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setSortBy("score")}
              data-testid="jobs-sort-score"
              className={`rounded-lg px-3 py-1.5 ${sortBy === "score" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
            >
              Best match
            </button>
            <button
              type="button"
              onClick={() => setSortBy("date")}
              data-testid="jobs-sort-date"
              className={`rounded-lg px-3 py-1.5 ${sortBy === "date" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}
            >
              Newest
            </button>
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-600" data-testid="jobs-hide-stale" title="Preference saved in this browser">
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
          <button
            type="button"
            data-testid="jobs-discover"
            onClick={() => void runDiscover()}
            disabled={discovering}
            title={`Run JobSpy discover for “${activeCategory}” (limit 5)`}
            className="h-9 rounded-xl border border-emerald-200 bg-emerald-50 px-4 text-sm font-semibold text-emerald-900 hover:bg-emerald-100 disabled:opacity-50"
          >
            {discovering ? "Discovering…" : "Discover"}
          </button>
          {(thresholdLive > 0 || searchLive || hideStale || source !== "all") ? (
            <button
              type="button"
              data-testid="jobs-clear-filters"
              onClick={() => {
                setThresholdLive(0);
                setThreshold(0);
                setSearchLive("");
                setSearch("");
                setHideStale(false);
                setSource("all");
              }}
              className="h-9 rounded-xl border border-slate-200 px-3 text-xs font-semibold text-slate-600 hover:bg-slate-50"
            >
              Clear filters
            </button>
          ) : null}
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
          <span
            data-testid="jobspy-health-chip"
            title="JobSpy discovery worker health"
            className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${
              jobspyHealth === "ok"
                ? "bg-emerald-50 text-emerald-800"
                : jobspyHealth === "down"
                  ? "bg-amber-50 text-amber-900"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            JobSpy {jobspyHealth === "ok" ? "ok" : jobspyHealth === "down" ? "check" : "…"}
          </span>
          {jobs.length ? (
            <span
              data-testid="jobs-freshest"
              className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600"
              title="Newest scraped_at in the current result set"
            >
              Freshest {relativeDate(
                jobs.reduce((best, j) => (j.scrapedAt > best ? j.scrapedAt : best), jobs[0].scrapedAt)
              )}
            </span>
          ) : null}
        </div>

        {error ? (
          <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900" data-testid="jobs-error">
            {error}. Is the API running on {API_BASE}?
          </div>
        ) : null}
        {discoverNote ? (
          <div
            className="mb-4 flex items-start justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
            data-testid="jobs-discover-note"
          >
            <span>{discoverNote}</span>
            <button
              type="button"
              data-testid="jobs-discover-note-dismiss"
              className="shrink-0 text-xs font-semibold text-emerald-800 underline"
              onClick={() => setDiscoverNote(null)}
            >
              Dismiss
            </button>
          </div>
        ) : null}

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="hidden grid-cols-[40px_minmax(0,2fr)_88px_72px_88px_100px_minmax(0,1fr)_minmax(0,1fr)_88px] gap-2 border-b border-slate-100 px-4 py-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500 md:grid">
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
            <span className="text-center">Action</span>
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
                {!loading ? (
                  <a
                    href="/?view=resume&step=tailor"
                    className="mt-3 inline-flex h-8 items-center rounded-lg bg-emerald-600 px-3 text-xs font-semibold text-white hover:bg-emerald-700"
                    data-testid="jobs-empty-goto-paste"
                  >
                    Paste a JD in workspace
                  </a>
                ) : null}
              </div>
                );
              }
              return visible.map((job, idx) => {
                const score = job.stage3Result ? pct(job.stage3Result.finalScore) : null;
                return (
                  <div
                    key={job.id}
                    role="link"
                    tabIndex={0}
                    data-testid={`job-row-${job.id}`}
                    onClick={() => router.push(`/jobs/${job.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        router.push(`/jobs/${job.id}`);
                      }
                    }}
                    className="grid w-full cursor-pointer grid-cols-1 gap-1 border-b border-slate-50 px-4 py-3 text-left transition hover:bg-emerald-50/60 md:grid-cols-[40px_minmax(0,2fr)_88px_72px_88px_100px_minmax(0,1fr)_minmax(0,1fr)_88px] md:items-center md:gap-2"
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
                    <div className="flex md:justify-center">
                      <a
                        href={`/?view=resume&jobId=${encodeURIComponent(job.id)}&step=jd`}
                        data-testid={`job-tailor-${job.id}`}
                        className="rounded-lg bg-emerald-600 px-2.5 py-1 text-[10px] font-semibold text-white hover:bg-emerald-700"
                        onClick={(e) => e.stopPropagation()}
                      >
                        Open
                      </a>
                    </div>
                  </div>
                );
              });
            })()}
          </div>
        </div>
      </div>
    </div>
  );
}
