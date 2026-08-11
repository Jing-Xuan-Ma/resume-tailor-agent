"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AuthGate, { CurrentUser } from "@/components/auth-gate";
import ChatPanel from "@/components/chat-panel";
import RecordsPanel from "@/components/records-panel";
import ResumeWorkspace from "@/components/resume-workspace";
import ProfilePanel from "@/components/profile-panel";
import UploadOnboarding from "@/components/upload-onboarding";
import FlowStepper from "@/components/flow-stepper";
import AppTopNav from "@/components/app-top-nav";
import { getActiveTemplate } from "@/lib/api";

function WorkspaceShell({ user, onLogout }: { user: CurrentUser; onLogout: () => void }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [workspaceView, setWorkspaceView] = useState<"profile" | "resume" | "records">("profile");
  const [selectedJobId, setSelectedJobId] = useState<string | undefined>();
  const [hasMasterResume, setHasMasterResume] = useState<boolean | null>(null);

  const displayName = user.full_name || user.email;

  useEffect(() => {
    let alive = true;
    getActiveTemplate(user.id)
      .then((tpl) => {
        if (!alive) return;
        setHasMasterResume(Boolean(tpl));
      })
      .catch(() => {
        if (!alive) return;
        setHasMasterResume(false);
      });
    return () => {
      alive = false;
    };
  }, [user.id]);

  useEffect(() => {
    const view = searchParams.get("view");
    const jobId = searchParams.get("jobId") || undefined;
    if (jobId) setSelectedJobId(jobId);
    // Legacy in-app Pipeline view removed — jobs live on /jobs.
    if (view === "jobs") {
      router.replace("/jobs");
      return;
    }
    if (view === "resume" || jobId) setWorkspaceView("resume");
    if (view === "records") setWorkspaceView("records");
    if (view === "profile") setWorkspaceView("profile");
  }, [searchParams, router]);

  const workbenchStep = searchParams.get("step") || undefined;
  const deeplinkVersionId = searchParams.get("versionId") || undefined;
  const deeplinkSessionId = searchParams.get("sessionId") || undefined;

  const flowStep = workspaceView === "records" ? "apply" : "tailor";
  const showChat = workspaceView === "records";
  // No master resume → always land on upload (no deep-link / Jobright bypass).
  const forceUpload = hasMasterResume === false;

  if (hasMasterResume === null) {
    return (
      <main className="flex h-screen items-center justify-center bg-[#f7f7f5] text-sm text-slate-500">
        Checking your resume…
      </main>
    );
  }

  if (forceUpload) {
    return (
      <main className="flex h-screen w-full flex-col overflow-hidden bg-[#f7f7f5] text-slate-950">
        <div className="flex items-center justify-between border-b border-[#e8e8e4] bg-white px-4 py-2.5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#14352b]">Resume Agent</span>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-500 hover:text-slate-900"
          >
            Logout
          </button>
        </div>
        <UploadOnboarding
          userId={user.id}
          displayName={displayName}
          onUploaded={() => {
            setHasMasterResume(true);
            setWorkspaceView("profile");
          }}
        />
      </main>
    );
  }

  return (
    <main className="flex h-screen w-full overflow-hidden bg-[#f7f7f5] text-slate-950">
      {showChat ? <ChatPanel userId={user.id} /> : null}
      <section className="relative flex min-w-0 flex-1 flex-col">
        <AppTopNav
          active={workspaceView === "resume" ? "tailor" : workspaceView}
          displayName={displayName}
          onLogout={onLogout}
          onSelectTab={(tab) => {
            if (tab === "profile") setWorkspaceView("profile");
            if (tab === "tailor") setWorkspaceView("resume");
            if (tab === "records") setWorkspaceView("records");
          }}
        />
        {showChat ? (
          <div className="flex shrink-0 items-center border-b border-[#e8e8e4] bg-white px-4 py-2">
            <FlowStepper
              current={flowStep}
              hrefs={{
                jobs: "/jobs",
                jd: "/?view=resume&step=jd",
                tailor: "/?view=resume&step=tailor",
              }}
            />
          </div>
        ) : null}
        <div className="flex min-h-0 flex-1">
          {workspaceView === "profile" ? (
            <ProfilePanel userId={user.id} displayName={displayName} email={user.email} />
          ) : workspaceView === "resume" ? (
            <ResumeWorkspace
              key={`${selectedJobId || "no-job"}:${deeplinkVersionId || ""}:${deeplinkSessionId || ""}:${workbenchStep || ""}`}
              userId={user.id}
              initialJobId={selectedJobId}
              initialStep={workbenchStep}
              initialVersionId={deeplinkVersionId}
              initialSessionId={deeplinkSessionId}
            />
          ) : (
            <RecordsPanel userId={user.id} />
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
