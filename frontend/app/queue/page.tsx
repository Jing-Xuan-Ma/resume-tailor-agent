"use client";

import AuthGate from "@/components/auth-gate";
import ApplicationQueuePanel from "@/components/application-queue-panel";
import FlowStepper from "@/components/flow-stepper";

export default function QueuePage() {
  return (
    <AuthGate>
      {({ user }) => (
        <div className="min-h-screen bg-[#f4f6f4] text-slate-950" data-testid="queue-page">
          <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
            <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-700">
                  Resume Agent
                </p>
                <h1 className="text-sm font-bold">Apply queue</h1>
              </div>
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
