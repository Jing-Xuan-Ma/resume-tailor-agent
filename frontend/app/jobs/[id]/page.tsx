"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

interface JobDetail {
  id: string;
  title: string;
  company: string;
  source: string;
  originalUrl: string;
  location: string;
  workModel: string;
  salary: string;
  status: string;
  atsScore: number;
  semanticScore: number;
  finalScore: number;
  coveredKeywords: string[];
  missingKeywords: string[];
  hasHardConditionIssues: boolean;
}

function pct(v: number) {
  return Math.round(v * 100);
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
      return "bg-slate-100 text-slate-600";
  }
}

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params?.id) return;
    fetch(`${API_BASE}/api/v1/jobs/${params.id}/summary`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await res.text());
        return res.json();
      })
      .then((data) => setJob(data))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load job"));
  }, [params?.id]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f7f8f6] p-8">
        <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <p className="text-sm text-red-600">{error}</p>
          <button type="button" onClick={() => router.push("/jobs")} className="mt-4 text-sm font-semibold text-emerald-700">
            Back to ranked jobs
          </button>
        </div>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f7f8f6] text-sm text-slate-500">
        Loading job detail…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f7f8f6]" data-testid="job-detail-page">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <button
          type="button"
          data-testid="back-to-jobs"
          onClick={() => router.push("/jobs")}
          className="mb-4 text-sm font-semibold text-slate-600 hover:text-slate-950"
        >
          ← Ranked Jobs
        </button>

        <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-slate-500">{job.company}</p>
              <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-950" data-testid="job-detail-title">
                {job.title}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                <span className={`rounded-full px-2.5 py-1 font-semibold ${workModelClass(job.workModel)}`}>
                  {job.workModel}
                </span>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">{job.location}</span>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">{job.salary}</span>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600">{job.source}</span>
              </div>
            </div>
            <div className="rounded-2xl bg-emerald-50 px-5 py-4 text-center ring-1 ring-emerald-100">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Match Score</p>
              <p className="text-3xl font-bold text-emerald-800" data-testid="job-detail-score">
                {pct(job.finalScore)}%
              </p>
            </div>
          </div>

          <div className="mt-8 grid gap-6 md:grid-cols-2">
            <div>
              <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Matched Keywords</h2>
              <div className="flex flex-wrap gap-1.5" data-testid="matched-keywords">
                {job.coveredKeywords?.length ? (
                  job.coveredKeywords.map((kw) => (
                    <span key={kw} className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                      {kw}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-slate-400">None listed</span>
                )}
              </div>
            </div>
            <div>
              <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Missing Keywords</h2>
              <div className="flex flex-wrap gap-1.5" data-testid="missing-keywords">
                {job.missingKeywords?.length ? (
                  job.missingKeywords.map((kw) => (
                    <span key={kw} className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200">
                      {kw}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-emerald-600">No gaps found</span>
                )}
              </div>
            </div>
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <a
              href={`/?view=resume&jobId=${job.id}`}
              className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              Customize Resume
            </a>
            {job.originalUrl ? (
              <a
                href={job.originalUrl}
                target="_blank"
                rel="noreferrer"
                className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                Original Job Post
              </a>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
