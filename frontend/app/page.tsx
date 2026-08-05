"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import AuthGate, { CurrentUser } from "@/components/auth-gate";
import ChatPanel from "@/components/chat-panel";
import JobsWorkspace from "@/components/jobs-workspace";
import RecordsPanel from "@/components/records-panel";
import ResumeWorkspace from "@/components/resume-workspace";
import ProfilePanel from "@/components/profile-panel";
import FlowStepper from "@/components/flow-stepper";
import { getLatestResume } from "@/lib/api";

function WorkspaceShell({ user, onLogout }: { user: CurrentUser; onLogout: () => void }) {
  const searchParams = useSearchParams();
  const [resumeId, setResumeId] = useState<string | undefined>();
  const [workspaceView, setWorkspaceView] = useState<"profile" | "resume" | "jobs" | "records">("resume");
  const [selectedJobId, setSelectedJobId] = useState<string | undefined>();

  const displayName = user.full_name || user.email;

  useEffect(() => {
    getLatestResume(user.id)
      .then((resume) => setResumeId(resume?.id))
      .catch(() => setResumeId(undefined));
  }, [user.id]);

  useEffect(() => {
    const view = searchParams.get("view");
    const jobId = searchParams.get("jobId") || undefined;
    if (jobId) setSelectedJobId(jobId);
    if (view === "resume" || jobId) setWorkspaceView("resume");
    if (view === "jobs") setWorkspaceView("jobs");
    if (view === "records") setWorkspaceView("records");
    if (view === "profile") setWorkspaceView("profile");
  }, [searchParams]);

  const workbenchStep = searchParams.get("step") || undefined;
  const returnTo = searchParams.get("returnTo") || undefined;
  const deeplinkVersionId = searchParams.get("versionId") || undefined;
  const deeplinkSessionId = searchParams.get("sessionId") || undefined;

  const flowStep = workspaceView === "jobs" ? "jobs" : workspaceView === "records" ? "apply" : "tailor";
  const showChat = workspaceView === "jobs" || workspaceView === "records";

  return (
    <main className="flex h-screen w-full overflow-hidden bg-[#f4f6f4] text-slate-950">
      {showChat ? (
        <ChatPanel
          userId={user.id}
          resumeId={resumeId}
          onResumeUploaded={setResumeId}
          onTailored={() => {
            setWorkspaceView("resume");
          }}
        />
      ) : null}
      <section className="relative flex min-w-0 flex-1 flex-col">
        <div className="z-10 flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/80 bg-white/90 px-4 py-2.5 backdrop-blur">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-700">Resume Agent</span>
              <span className="hidden truncate text-xs text-slate-500 sm:inline">{displayName}</span>
            </div>
            {showChat ? (
              <FlowStepper
                current={flowStep}
                hrefs={{
                  jobs: "/jobs",
                  jd: "/?view=resume&step=jd",
                  tailor: "/?view=resume&step=tailor",
                }}
              />
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <a
              href="/jobs"
              data-testid="nav-ranked"
              className="rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700"
            >
              Ranked jobs
            </a>
            <div className="flex gap-1 rounded-full bg-slate-100 p-1 shadow-sm ring-1 ring-slate-200">
              <button
                type="button"
                onClick={() => setWorkspaceView("profile")}
                data-testid="nav-profile"
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${workspaceView === "profile" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Profile
              </button>
              <button
                type="button"
                onClick={() => setWorkspaceView("resume")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${workspaceView === "resume" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Tailor
              </button>
              <button
                type="button"
                onClick={() => setWorkspaceView("jobs")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${workspaceView === "jobs" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Pipeline
              </button>
              <button
                type="button"
                onClick={() => setWorkspaceView("records")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${workspaceView === "records" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
              >
                Records
              </button>
            </div>
            <button
              type="button"
              onClick={onLogout}
              className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200 hover:text-slate-950"
            >
              Logout
            </button>
          </div>
        </div>
        <div className="flex min-h-0 flex-1">
          {workspaceView === "profile" ? (
            <ProfilePanel userId={user.id} />
          ) : workspaceView === "resume" ? (
            <ResumeWorkspace
              key={`${selectedJobId || "no-job"}:${deeplinkVersionId || ""}:${deeplinkSessionId || ""}:${workbenchStep || ""}:${returnTo || ""}`}
              userId={user.id}
              initialJobId={selectedJobId}
              initialStep={workbenchStep}
              initialReturnTo={returnTo}
              initialVersionId={deeplinkVersionId}
              initialSessionId={deeplinkSessionId}
            />
          ) : workspaceView === "records" ? (
            <RecordsPanel userId={user.id} />
          ) : (
            <JobsWorkspace
              userId={user.id}
              resumeId={resumeId}
              onPreparedResume={() => {
                setWorkspaceView("resume");
              }}
              onGoToWorkspace={(jobId) => {
                setSelectedJobId(jobId);
                setWorkspaceView("resume");
              }}
            />
          )}
        </div>
      </section>
    </main>
  );
}

export default function Home() {
  return (
    <AuthGate>
      {({ user, onLogout }) => (
        <Suspense fallback={<div className="flex h-screen items-center justify-center text-sm text-slate-500">Loading workspace…</div>}>
          <WorkspaceShell user={user} onLogout={onLogout} />
        </Suspense>
      )}
    </AuthGate>
  );
}
