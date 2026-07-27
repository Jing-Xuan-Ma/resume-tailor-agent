"use client";

import { useEffect, useState, useCallback } from "react";

interface Stage3Result {
  atsScore: number;
  semanticScore: number;
  hardConditionsPassed: boolean;
  finalScore: number;
  coveredKeywords: string[];
  missingKeywords: string[];
}

interface MockJob {
  id: string;
  company: string;
  title: string;
  source: string;
  originalUrl: string;
  scrapedAt: string;
  passedStage1: boolean;
  stage2Score: number | null;
  stage3Result: Stage3Result | null;
  status: string;
  linkedApplicationId?: string;
}

interface JobSummary {
  title: string;
  company: string;
  atsScore: number;
  semanticScore: number;
  finalScore: number;
  coveredKeywords: string[];
  missingKeywords: string[];
  hasHardConditionIssues: boolean;
  status: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

function pct(v: number) { return Math.round(v * 100); }

function colorClass(score: number): string {
  if (score >= 85) return "bg-green-50 text-green-800 ring-1 ring-green-200";
  if (score >= 60) return "bg-amber-50 text-amber-800 ring-1 ring-amber-200";
  return "bg-slate-100 text-slate-500 ring-1 ring-slate-200";
}

function statusBadge(status: string): { label: string; className: string } {
  switch (status) {
    case "unprocessed": return { label: "Unprocessed", className: "bg-slate-100 text-slate-600" };
    case "resume_generated": return { label: "Resume Ready", className: "bg-blue-50 text-blue-700" };
    case "applied": return { label: "Applied", className: "bg-indigo-50 text-indigo-700" };
    case "replied": return { label: "Replied", className: "bg-green-50 text-green-700" };
    case "rejected": return { label: "Rejected", className: "bg-red-50 text-red-700" };
    default: return { label: status, className: "bg-slate-100 text-slate-600" };
  }
}

interface JobsWorkspaceProps {
  userId: string;
  resumeId?: string;
  onPreparedResume?: (result: unknown) => void;
  onGoToWorkspace?: (jobId: string) => void;
}

export default function JobsWorkspace({ userId, onGoToWorkspace }: JobsWorkspaceProps) {
  const [jobs, setJobs] = useState<MockJob[]>([]);
  const [total, setTotal] = useState(0);
  const [filteredTotal, setFilteredTotal] = useState(0);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [summary, setSummary] = useState<JobSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("all");
  const [availableSources, setAvailableSources] = useState<string[]>([]);
  const [threshold, setThreshold] = useState(0);
  const [sortBy, setSortBy] = useState<"score" | "date">("score");
  const [topNEnabled, setTopNEnabled] = useState(false);

  const selectedJob = jobs.find((j) => j.id === selectedJobId) || null;

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        user_id: userId,
        threshold: String(threshold),
        sort_by: sortBy,
        top_n: topNEnabled ? "10" : "0",
        source: source === "all" ? "" : source,
        search,
      });
      const res = await fetch(`${API_BASE}/api/v1/jobs/list?${params}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setJobs(data.jobs);
      setTotal(data.total);
      setFilteredTotal(data.filtered_total);
      if (!selectedJobId && data.jobs.length > 0) setSelectedJobId(data.jobs[0].id);
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, [userId, threshold, sortBy, topNEnabled, source, search, selectedJobId]);

  useEffect(() => {
    fetchJobs();
  }, [threshold, sortBy, topNEnabled]);

  useEffect(() => {
    async function loadSources() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/jobs/sources/list`);
        if (res.ok) {
          const data = await res.json();
          setAvailableSources(data.sources);
        }
      } catch { /* ignore */ }
    }
    loadSources();
  }, []);

  const handleSelectJob = async (jobId: string) => {
    setSelectedJobId(jobId);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}/summary`);
      if (res.ok) {
        setSummary(await res.json());
      }
    } catch { /* ignore */ }
    setLoading(false);
  };

  const handleToWorkspace = async () => {
    if (!selectedJobId) return;
    try {
      const params = new URLSearchParams({ user_id: userId });
      const res = await fetch(`${API_BASE}/api/v1/jobs/${selectedJobId}/to-resume-workspace?${params}`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      onGoToWorkspace?.(selectedJobId);
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : "Failed to open workspace");
    }
  };

  const handleSearch = () => {
    fetchJobs();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div className="flex min-w-0 flex-1 flex-col bg-[#eef2f7]">
      {/* Top Filter Bar */}
      <div className="flex items-center gap-3 border-b border-slate-200 bg-white/95 px-6 py-3 shadow-sm backdrop-blur">
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search company or title..."
            className="h-8 w-56 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs outline-none focus:border-blue-400"
          />
          <button onClick={handleSearch} disabled={loading}
            className="h-8 rounded-lg bg-blue-600 px-3 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50">
            Search
          </button>
        </div>

        <div className="h-5 w-px bg-slate-200" />

        <select value={source} onChange={(e) => setSource(e.target.value)}
          className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700 outline-none">
          <option value="all">All Sources</option>
          {availableSources.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        <div className="h-5 w-px bg-slate-200" />

        <div className="flex items-center gap-2">
          <span className="text-[11px] text-slate-500">Threshold:</span>
          <input type="range" min={0} max={100} value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="h-1.5 w-24 accent-blue-600" />
          <span className="w-8 text-xs font-semibold text-slate-700">{threshold}%</span>
        </div>

        <div className="h-5 w-px bg-slate-200" />

        <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-0.5">
          <button onClick={() => setSortBy("score")}
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${sortBy === "score" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}>
            Score
          </button>
          <button onClick={() => setSortBy("date")}
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${sortBy === "date" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"}`}>
            Date
          </button>
        </div>

        <div className="h-5 w-px bg-slate-200" />

        <label className="flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" checked={topNEnabled} onChange={(e) => setTopNEnabled(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 accent-blue-600" />
          <span className="text-[11px] font-medium text-slate-600">Top 10</span>
        </label>

        <div className="ml-auto flex items-center gap-2">
          <span className="text-[11px] text-slate-400">
            {filteredTotal} matched · {total} total
          </span>
          <button onClick={fetchJobs} disabled={loading}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50">
            {loading ? "..." : "Refresh"}
          </button>
        </div>
      </div>

      {message && (
        <div className="mx-6 mt-2 rounded-xl bg-slate-100 px-4 py-2 text-xs text-slate-700">
          {message}
          <button onClick={() => setMessage(null)} className="ml-2 text-slate-400 hover:text-slate-600">✕</button>
        </div>
      )}

      {/* Main Content: 62% table + 38% summary */}
      <div className="flex min-h-0 flex-1 gap-4 overflow-hidden p-4">
        {/* Left: Job Table */}
        <div className="flex w-[62%] min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center gap-4 border-b border-slate-100 px-5 py-3 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            <span className="flex-1">Company / Position</span>
            <span className="w-16 text-center">Match</span>
            <span className="w-16 text-center">Source</span>
            <span className="w-24 text-center">Status</span>
          </div>
          <div className="flex-1 overflow-y-auto">
            {jobs.length === 0 ? (
              <div className="flex items-center justify-center py-16 text-sm text-slate-400">
                {loading ? "Loading..." : "No jobs match your criteria."}
              </div>
            ) : (
              <div className="divide-y divide-slate-50">
                {jobs.map((job) => {
                  const score = job.stage3Result ? pct(job.stage3Result.finalScore) : null;
                  const isSelected = job.id === selectedJobId;
                  const sb = statusBadge(job.status);
                  return (
                    <div key={job.id}
                      onClick={() => handleSelectJob(job.id)}
                      className={`flex cursor-pointer items-center gap-4 px-5 py-3 transition hover:bg-slate-50 ${isSelected ? "bg-blue-50/60 ring-1 ring-blue-200" : ""}`}>
                      <div className="flex-1 min-w-0">
                        <a href={job.originalUrl} target="_blank" rel="noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="text-sm font-bold text-slate-950 hover:text-blue-600 hover:underline">
                          {job.company}
                        </a>
                        <p className="truncate text-xs text-slate-500">{job.title}</p>
                      </div>
                      <div className="w-16 text-center">
                        {score !== null ? (
                          <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${colorClass(score)}`}>
                            {score}%
                          </span>
                        ) : (
                          <span className="text-[11px] text-slate-400">—</span>
                        )}
                      </div>
                      <div className="w-16 text-center">
                        <span className="text-xs text-slate-500">{job.source}</span>
                      </div>
                      <div className="w-24 text-center">
                        <span className={`inline-block rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${sb.className}`}>
                          {sb.label}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right: Adaptation Summary */}
        <div className="flex w-[38%] min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {selectedJob && summary ? (
            <div className="flex flex-1 flex-col overflow-y-auto p-5">
              <div className="mb-4">
                <h3 className="text-lg font-bold text-slate-950">{selectedJob.title}</h3>
                <p className="text-sm text-slate-500">{selectedJob.company}</p>
              </div>

              {/* Score Breakdown */}
              <div className="mb-5 rounded-2xl bg-slate-50 p-4">
                <div className="mb-3 flex items-baseline justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Composite Match</span>
                  <span className={`text-2xl font-bold ${pct(summary.finalScore) >= 85 ? "text-green-700" : pct(summary.finalScore) >= 60 ? "text-amber-700" : "text-slate-500"}`}>
                    {pct(summary.finalScore)}%
                  </span>
                </div>
                <div className="space-y-2 text-xs text-slate-600">
                  <div className="flex items-center justify-between">
                    <span>ATS Score</span>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200">
                        <div className="h-full rounded-full bg-blue-500" style={{ width: `${pct(summary.atsScore)}%` }} />
                      </div>
                      <span className="w-8 text-right font-semibold">{pct(summary.atsScore)}%</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Semantic Score</span>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200">
                        <div className="h-full rounded-full bg-indigo-500" style={{ width: `${pct(summary.semanticScore)}%` }} />
                      </div>
                      <span className="w-8 text-right font-semibold">{pct(summary.semanticScore)}%</span>
                    </div>
                  </div>
                  {summary.hasHardConditionIssues && (
                    <div className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-[11px] font-medium text-red-700">
                      Hard conditions not met (years of experience, degree, etc.)
                    </div>
                  )}
                </div>
              </div>

              {/* Keywords */}
              <div className="mb-5">
                <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Covered Keywords</h4>
                <div className="flex flex-wrap gap-1.5">
                  {summary.coveredKeywords.length > 0 ? summary.coveredKeywords.map((kw) => (
                    <span key={kw} className="rounded-full bg-green-50 px-2.5 py-1 text-[11px] font-semibold text-green-700 ring-1 ring-green-200">
                      {kw}
                    </span>
                  )) : <span className="text-xs text-slate-400">None</span>}
                </div>
              </div>

              <div className="mb-5">
                <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Missing Keywords</h4>
                <div className="flex flex-wrap gap-1.5">
                  {summary.missingKeywords.length > 0 ? summary.missingKeywords.map((kw) => (
                    <span key={kw} className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700 ring-1 ring-amber-200">
                      {kw}
                    </span>
                  )) : <span className="text-xs text-green-600">No gaps found!</span>}
                </div>
              </div>

              {/* Actions */}
              <div className="mt-auto flex flex-col gap-2">
                <button onClick={handleToWorkspace}
                  className="w-full rounded-xl bg-blue-600 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700">
                  Go to Resume Workspace
                </button>
                <div className="flex gap-2">
                  <button onClick={() => setMessage(`Scoring triggered for ${selectedJob.id}`)}
                    className="flex-1 rounded-xl border border-slate-200 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50">
                    Re-score
                  </button>
                  <a href={selectedJob.originalUrl} target="_blank" rel="noreferrer"
                    className="flex-1 rounded-xl border border-slate-200 py-2 text-center text-xs font-semibold text-slate-600 hover:bg-slate-50">
                    Open Original
                  </a>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center p-8 text-center">
              <div>
                <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
                  <span className="text-lg font-bold">JD</span>
                </div>
                <h3 className="text-sm font-medium text-slate-600">Select a job</h3>
                <p className="mt-1 text-xs text-slate-400">Click a row to see the adaptation summary.</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
