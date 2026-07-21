"use client";

interface ResumeWorkspaceProps {
  tailoredResume?: unknown;
}

export default function ResumeWorkspace({ tailoredResume }: ResumeWorkspaceProps) {
  const resume = tailoredResume as Record<string, unknown> | undefined;

  return (
    <div className="flex w-2/3 flex-col bg-gray-50">
      <div className="border-b border-gray-200 bg-white px-6 py-4">
        <h2 className="text-base font-medium text-gray-900">Resume Workspace</h2>
      </div>

      <div className="flex flex-1 items-center justify-center p-8 overflow-auto">
        {resume ? (
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
                  Skills
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
                <p className="text-gray-700 text-sm whitespace-pre-wrap">
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
          </div>
        ) : (
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
        )}
      </div>
    </div>
  );
}
