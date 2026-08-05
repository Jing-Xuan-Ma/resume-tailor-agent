"use client";

import { Suspense, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import AuthGate from "@/components/auth-gate";
import FlowStepper from "@/components/flow-stepper";
import OutreachStepPanel from "@/components/outreach-step-panel";

function OutreachBody({
  userId,
}: {
  userId: string;
}) {
  const searchParams = useSearchParams();
  const jobId = searchParams.get("jobId") || undefined;
  const company = searchParams.get("company") || undefined;
  const position = searchParams.get("position") || undefined;
  const returnTo = searchParams.get("returnTo") || undefined;

  const tailorHref = useMemo(() => {
    if (!jobId) return "/?view=resume&step=tailor";
    const q = new URLSearchParams({ view: "resume", jobId, step: "tailor" });
    if (returnTo) q.set("returnTo", returnTo);
    return `/?${q.toString()}`;
  }, [jobId, returnTo]);

  const jdHref = useMemo(() => {
    if (!jobId) return "/?view=resume&step=jd";
    const q = new URLSearchParams({ view: "resume", jobId, step: "jd" });
    if (returnTo) q.set("returnTo", returnTo);
    return `/?${q.toString()}`;
  }, [jobId, returnTo]);

  const applyHref = useMemo(() => {
    if (!jobId) return "/?view=resume&step=apply";
    const q = new URLSearchParams({ view: "resume", jobId, step: "apply" });
    if (returnTo) q.set("returnTo", returnTo);
    return `/?${q.toString()}`;
  }, [jobId, returnTo]);

  return (
    <main className="min-h-screen bg-[#f4f6f4] text-slate-950" data-testid="outreach-page">
      <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {returnTo ? (
            <a
              href={returnTo}
              className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800 hover:bg-emerald-100"
            >
              ← Jobright
            </a>
          ) : null}
          <a
            href={tailorHref}
            className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            data-testid="outreach-back-tailor"
          >
            ← Tailor
          </a>
          <FlowStepper
            current="outreach"
            className="hidden md:flex"
            hrefs={{
              jobs: "/jobs",
              ...(jobId ? { detail: `/jobs/${jobId}` } : {}),
              jd: jdHref,
              tailor: tailorHref,
              apply: applyHref,
            }}
          />
          {company || position ? (
            <span className="truncate rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600">
              {[company, position].filter(Boolean).join(" · ")}
            </span>
          ) : null}
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-6">
        <OutreachStepPanel
          visible
          userId={userId}
          jobId={jobId}
          company={company}
          position={position}
        />
      </div>
    </main>
  );
}

export default function OutreachPage() {
  return (
    <AuthGate>
      {({ user }) => (
        <Suspense
          fallback={
            <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
              Loading outreach…
            </div>
          }
        >
          <OutreachBody userId={user.id} />
        </Suspense>
      )}
    </AuthGate>
  );
}
