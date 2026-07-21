"use client";

import { useState } from "react";
import { exportText } from "@/lib/api";

interface ResumeWorkspaceProps {
  tailoredResume?: unknown;
}

export default function ResumeWorkspace({ tailoredResume }: ResumeWorkspaceProps) {
  const resume = tailoredResume as Record<string, unknown> | undefined;
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);

  // Determine if we have a real tailored result or just a "no resume" placeholder
  const hasRealResume =
    resume &&
    (Array.isArray(resume.experiences) && resume.experiences.length > 0);

  const hasNoResumeWarning =
    resume &&
    (!Array.isArray(resume.experiences) || resume.experiences.length === 0) &&
    resume.ats_score_estimate === null;

  const handleCopyText = async () => {
    if (!resume || exporting) return;
    setExporting(true);
    try {
      const result = await exportText(resume);
      await navigator.clipboard.writeText(result.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Export failed";
      alert("Copy failed: " + msg);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex w-2/3 flex-col bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <h2 className="text-base font-medium text-gray-900">Resume Workspace</h2>
      </div>

      <div className="flex flex-1 items-center justify-center p-8 overflow-auto">
        {!resume ? (
          // State 1: Nothing happened yet
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-50">
              <svg
                className="h-8 w-8 text-blue-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z"
                />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-gray-900">No resume selected</h3>
            <p className="mt-1 text-sm text-gray-500">
              Upload your resume or paste a job description to begin tailoring.
            </p>
          </div>
        ) : hasNoResumeWarning ? (
          // State 2: User pasted a JD but has no resume uploaded
          <div className="w-full max-w-xl text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-amber-50">
              <svg
                className="h-8 w-8 text-amber-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
                />
              </svg>
            </div>
            <h3 className="text-lg font-medium text-gray-900">Resume Required</h3>
            <p className="mt-2 text-sm text-gray-600 whitespace-pre-wrap leading-relaxed">
              {String(resume.tailoring_summary ||
                "To tailor your resume, I need your original experience first. Please upload your resume in the chat.")}
            </p>
            <div className="mt-6 rounded-lg bg-gray-50 border border-gray-200 p-4 text-left">
              <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                What I found in the JD
              </h4>
              {Array.isArray(resume.skills) && resume.skills.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {resume.skills.map((skill: string, i: number) => (
                    <span
                      key={i}
                      className="inline-flex items-center rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-500">Key skills will appear here after parsing.</p>
              )}
            </div>
          </div>
        ) : (
          // State 3: Real tailored resume preview
          <div className="w-full max-w-2xl bg-white rounded-xl shadow-sm border border-gray-200 p-8">
            <h3 className="text-xl font-bold text-gray-900 mb-4">
              Tailored Resume Preview
            </h3>

            {resume.summary && (
              <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-1">
                  Summary
                </h4>
                <p className="text-gray-800 text-sm leading-relaxed">
                  {String(resume.summary)}
                </p>
              </div>
            )}

            {Array.isArray(resume.skills) && resume.skills.length > 0 && (
              <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-2">
                  Highlighted Skills
                </h4>
                <div className="flex flex-wrap gap-2">
                  {resume.skills.map((skill: string, i: number) => (
                    <span
                      key={i}
                      className="inline-flex items-center rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {resume.tailoring_summary && (
              <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-1">
                  Tailoring Notes
                </h4>
                <p className="text-gray-700 text-sm whitespace-pre-wrap leading-relaxed">
                  {String(resume.tailoring_summary)}
                </p>
              </div>
            )}

            {typeof resume.ats_score_estimate === "number" && (
              <div className="mt-4 flex items-center gap-3">
                <div className="text-sm font-medium text-gray-600">
                  ATS Score Estimate:
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-2 w-32 rounded-full bg-gray-200">
                    <div
                      className="h-2 rounded-full bg-green-500"
                      style={{
                        width: `${Math.min(resume.ats_score_estimate, 100)}%`,
                      }}
                    />
                  </div>
                  <span className="text-sm font-semibold text-gray-900">
                    {resume.ats_score_estimate}%
                  </span>
                </div>
              </div>
            )}

            <div className="mt-6 pt-4 border-t border-gray-200">
              <button
                onClick={handleCopyText}
                disabled={exporting}
                className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
              >
                {copied ? (
                  <>
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    Copied!
                  </>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    {exporting ? "Formatting..." : "Copy as Text"}
                  </>
                )}
              </button>
              <p className="mt-2 text-xs text-gray-500">
                Formats the tailored resume as plain text you can paste into Word, Google Docs, or Notion.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
