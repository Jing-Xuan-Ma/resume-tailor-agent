"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import FlowStepper from "@/components/flow-stepper";
import AppTopNav from "@/components/app-top-nav";
import { isLivePostingUrl } from "@/lib/posting-url";
import { getAuthUserId } from "@/lib/auth-user";

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
  scrapedAt?: string;
  atsScore: number;
  semanticScore: number;
  finalScore: number;
  coveredKeywords: string[];
  missingKeywords: string[];
  hasHardConditionIssues: boolean;
  scoredForUser?: boolean;
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
  const [copyNote, setCopyNote] = useState<string | null>(null);

  useEffect(() => {
    if (!params?.id) return;
    const uid = getAuthUserId();
    const qs = uid ? `?user_id=${encodeURIComponent(uid)}` : "";
    fetch(`${API_BASE}/api/v1/jobs/${params.id}/summary${qs}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await res.text());
        return res.json();
      })
      .then((data) => setJob(data))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load job"));
  }, [params?.id]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f4f6f4] p-8">
        <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <p className="text-sm text-red-600">{error}</p>
          <button
            type="button"
            onClick={() => router.push("/jobs")}
            className="mt-4 text-sm font-semibold text-emerald-700"
          >
            Back to ranked jobs
          </button>
        </div>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f4f6f4] text-sm text-slate-500">
        Loading job detail…
      </div>
    );
  }

  const tailorHref = `/?view=resume&jobId=${encodeURIComponent(job.id)}&step=tailor`;
  const jdHref = `/?view=resume&jobId=${encodeURIComponent(job.id)}&step=jd`;

  return (
    <div className="min-h-screen bg-[#f4f6f4]" data-testid="job-detail-page">
      <AppTopNav active="jobs" />
      <div className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            data-testid="back-to-jobs"
            onClick={() => router.push("/jobs")}
            className="text-sm font-semibold text-slate-600 hover:text-slate-950"
          >
            ← Jobs
          </button>
          <FlowStepper
            current="detail"
            hrefs={{
              jobs: "/jobs",
              detail: `/jobs/${job.id}`,
              jd: jdHref,
              tailor: tailorHref,
            }}
          />
        </div>

        <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="min-w-0 flex-1">
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
                <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600" data-testid="job-source">
                  {job.source}
                </span>
                {job.scrapedAt ? (
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-600" data-testid="job-posted-age">
                    Posted {(() => {
                      const ms = Date.now() - new Date(job.scrapedAt).getTime();
                      const hours = Math.max(1, Math.round(ms / 3600000));
                      if (hours < 48) return `${hours}h ago`;
                      return `${Math.round(hours / 24)}d ago`;
                    })()}
                  </span>
                ) : null}
                {job.scrapedAt && Date.now() - new Date(job.scrapedAt).getTime() > 14 * 24 * 3600000 ? (
                  <span
                    className="rounded-full bg-amber-100 px-2.5 py-1 font-bold uppercase tracking-wide text-amber-800"
                    data-testid="job-stale-badge"
                  >
                    Stale &gt;14d
                  </span>
                ) : null}
              </div>
            </div>
            <div className="w-full max-w-[200px] rounded-2xl bg-emerald-50 px-5 py-4 text-center ring-1 ring-emerald-100 sm:w-auto">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Match Score</p>
              <p className="text-4xl font-bold text-emerald-800" data-testid="job-detail-score">
                {pct(job.finalScore)}%
              </p>
              <p className="mt-1 text-[10px] text-emerald-800/70">Heuristic resume↔JD fit (not a vendor ATS parse)</p>
              {job.scoredForUser ? (
                <p className="mt-1 text-[10px] font-semibold text-emerald-900" data-testid="scored-for-user">
                  Scored for your resume
                </p>
              ) : null}
              <div className="mt-3 grid grid-cols-2 gap-2 text-left text-[10px] text-emerald-900/80">
                <div className="rounded-lg bg-white/70 px-2 py-1.5">
                  <div className="font-semibold uppercase tracking-wide opacity-70">ATS keywords</div>
                  <div className="text-sm font-bold">{pct(job.atsScore)}%</div>
                </div>
                <div className="rounded-lg bg-white/70 px-2 py-1.5">
                  <div className="font-semibold uppercase tracking-wide opacity-70">Skill coverage</div>
                  <div className="text-sm font-bold">{pct(job.semanticScore)}%</div>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-8 grid gap-6 md:grid-cols-2">
            <div>
              <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-emerald-700">Matched keywords</h2>
              <p className="mb-2 text-[11px] text-slate-500">Already covered on your profile / resume inventory.</p>
              <div className="flex flex-wrap gap-1.5" data-testid="matched-keywords">
                {job.coveredKeywords?.length ? (
                  job.coveredKeywords.map((kw) => (
                    <span
                      key={kw}
                      className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200"
                    >
                      {kw}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-slate-400">None listed</span>
                )}
              </div>
            </div>
            <div>
              <h2 className="mb-2 text-xs font-bold uppercase tracking-wide text-amber-700">Missing keywords</h2>
              <p className="mb-2 text-[11px] text-slate-500">Gaps to close honestly when you tailor (no fabrication).</p>
              <div className="flex flex-wrap gap-1.5" data-testid="missing-keywords">
                {job.missingKeywords?.length ? (
                  job.missingKeywords.map((kw) => (
                    <span
                      key={kw}
                      className="rounded-full bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200"
                    >
                      {kw}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-emerald-600">No gaps found</span>
                )}
              </div>
            </div>
          </div>

          {job.hasHardConditionIssues ? (
            <div className="mt-6 rounded-xl bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-900 ring-1 ring-amber-200">
              Some hard requirements may not be met — review carefully before applying.
            </div>
          ) : null}

          <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-slate-100 pt-6">
            <a
              href={jdHref}
              data-testid="cta-customize-resume"
              className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700"
            >
              Next · Review JD
            </a>
            <a
              href={tailorHref}
              data-testid="cta-skip-to-tailor"
              className="rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              title="Skip JD panel and open Tailor directly"
            >
              Skip to Tailor
            </a>
            {isLivePostingUrl(job.originalUrl) ? (
              <>
                <a
                  href={job.originalUrl}
                  target="_blank"
                  rel="noreferrer"
                  data-testid="open-original-posting"
                  className="rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Open original posting
                </a>
                <button
                  type="button"
                  data-testid="copy-posting-url"
                  className="rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                  onClick={() => {
                    void navigator.clipboard.writeText(job.originalUrl).then(
                      () => {
                        setCopyNote("Posting URL copied");
                        window.setTimeout(() => setCopyNote(null), 2000);
                      },
                      () => setCopyNote("Copy failed")
                    );
                  }}
                >
                  Copy URL
                </button>
              </>
            ) : (
              <span
                data-testid="demo-posting-note"
                className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-500"
                title={job.originalUrl || undefined}
              >
                Demo listing — no live posting URL
              </span>
            )}
            {copyNote ? (
              <span className="text-xs font-semibold text-emerald-700" data-testid="copy-posting-note">
                {copyNote}
              </span>
            ) : null}
            <p className="w-full text-xs text-slate-500 sm:w-auto sm:ml-auto">
              Next: tailor → confirm → manual or auto-apply (stops before submit)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
