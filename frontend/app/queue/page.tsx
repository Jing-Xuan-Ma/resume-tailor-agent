"use client";

import AuthGate from "@/components/auth-gate";
import ApplicationQueuePanel from "@/components/application-queue-panel";
import AppTopNav from "@/components/app-top-nav";
import FlowStepper from "@/components/flow-stepper";

export default function QueuePage() {
  return (
    <AuthGate>
      {({ user, onLogout }) => (
        <div className="min-h-screen bg-[#f4f6f4] text-slate-950" data-testid="queue-page">
          <AppTopNav
            active="records"
            displayName={user.full_name || user.email}
            onLogout={onLogout}
          />
          <header className="border-b border-slate-200 bg-white">
            <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
              <h1 className="text-sm font-bold">Apply queue</h1>
              <FlowStepper
                current="apply"
                hrefs={{
                  jobs: "/jobs",
                  tailor: "/?view=resume&step=tailor",
                  apply: "/apply",
                  outreach: "/outreach",
                }}
              />
            </div>
          </header>
          <main className="mx-auto max-w-4xl px-4 py-6">
            <ApplicationQueuePanel userId={user.id} />
          </main>
        </div>
      )}
    </AuthGate>
  );
}
