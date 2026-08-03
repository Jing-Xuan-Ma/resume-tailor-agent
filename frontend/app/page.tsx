"use client";

import { useEffect, useState } from "react";
import AuthGate, { CurrentUser } from "@/components/auth-gate";
import ChatPanel from "@/components/chat-panel";
import JobsWorkspace from "@/components/jobs-workspace";
import RecordsPanel from "@/components/records-panel";
import ResumeWorkspace from "@/components/resume-workspace";
import { getLatestResume } from "@/lib/api";

function WorkspaceShell({ user, onLogout }: { user: CurrentUser; onLogout: () => void }) {
  const [resumeId, setResumeId] = useState<string | undefined>();
  const [workspaceState, setWorkspaceState] = useState<unknown>(undefined);
  const [workspaceView, setWorkspaceView] = useState<"resume" | "jobs" | "records">("resume");
  const [selectedJobId, setSelectedJobId] = useState<string | undefined>();

  const displayName = user.full_name || user.email;

  useEffect(() => {
    getLatestResume(user.id)
      .then((resume) => setResumeId(resume?.id))
      .catch(() => setResumeId(undefined));
  }, [user.id]);

  return (
    <main className="flex h-screen w-full overflow-hidden bg-[#eef2f7] text-slate-950">
      <ChatPanel
        userId={user.id}
        resumeId={resumeId}
        onResumeUploaded={setResumeId}
        onTailored={(result) => {
          setWorkspaceState(result);
          setWorkspaceView("resume");
        }}
      />
      <section className="relative flex min-w-0 flex-1">
        <div className="absolute right-6 top-3 z-10 flex items-center gap-2">
          <div className="hidden max-w-[220px] truncate rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200 xl:block">
            {displayName}
          </div>
          <div className="flex gap-1 rounded-full bg-slate-100 p-1 shadow-sm ring-1 ring-slate-200">
            <button
              onClick={() => setWorkspaceView("resume")}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${workspaceView === "resume" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              Resume
            </button>
            <a
              href="/jobs"
              className="rounded-full px-3 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-white hover:shadow-sm"
            >
              Ranked
            </a>
            <button
              onClick={() => setWorkspaceView("jobs")}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${workspaceView === "jobs" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              Jobs
            </button>
            <button
              onClick={() => setWorkspaceView("records")}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${workspaceView === "records" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}
            >
              Records
            </button>
          </div>
          <button
            onClick={onLogout}
            className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200 hover:text-slate-950"
          >
            Logout
          </button>
        </div>
        {workspaceView === "resume" ? (
          <ResumeWorkspace userId={user.id} initialJobId={selectedJobId} />
        ) : workspaceView === "records" ? (
          <RecordsPanel userId={user.id} />
        ) : (
          <JobsWorkspace
            userId={user.id}
            resumeId={resumeId}
            onPreparedResume={(result) => {
              setWorkspaceState(result);
              setWorkspaceView("resume");
            }}
            onGoToWorkspace={(jobId) => {
              setSelectedJobId(jobId);
              setWorkspaceView("resume");
            }}
          />
        )}
      </section>
    </main>
  );
}

export default function Home() {
  return (
    <AuthGate>
      {({ user, onLogout }) => <WorkspaceShell user={user} onLogout={onLogout} />}
    </AuthGate>
  );
}
