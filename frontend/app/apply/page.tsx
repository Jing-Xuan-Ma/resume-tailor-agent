"use client";

import { Suspense, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import AuthGate from "@/components/auth-gate";
import ApplyWorkspace from "@/components/apply-workspace";

function ApplyBody({ userId }: { userId: string }) {
  const searchParams = useSearchParams();
  const versionId = searchParams.get("versionId") || undefined;
  const jobId = searchParams.get("jobId") || undefined;
  const company = searchParams.get("company") || undefined;
  const position = searchParams.get("position") || undefined;
  const returnTo = searchParams.get("returnTo") || undefined;
  const sourceUrl = searchParams.get("sourceUrl") || undefined;
  const finalPath = searchParams.get("finalPath") || undefined;
  const applyId = searchParams.get("applyId") || undefined;
  const sessionId = searchParams.get("sessionId") || undefined;

  const missing = useMemo(() => !versionId, [versionId]);

  return (
    <>
      {missing ? (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-[#f4f6f4] p-8" data-testid="apply-missing-version">
          <p className="max-w-md text-center text-sm text-slate-600">
            Apply needs a tailored resume version. Open Tailor, generate a draft, Confirm it, then use{" "}
            <strong>Open Apply workspace</strong>.
          </p>
          <a
            href={jobId ? `/?view=resume&jobId=${encodeURIComponent(jobId)}&step=tailor` : "/?view=resume&step=tailor"}
            className="rounded-full bg-emerald-600 px-4 py-2 text-xs font-semibold text-white"
          >
            ← Go to Tailor
          </a>
        </div>
      ) : (
        <ApplyWorkspace
          userId={userId}
          versionId={versionId}
          jobId={jobId}
          company={company}
          position={position}
          returnTo={returnTo}
          sourceUrl={sourceUrl}
          initialFinalPath={finalPath}
          initialApplyId={applyId}
          initialSessionId={sessionId}
        />
      )}
    </>
  );
}

export default function ApplyPage() {
  return (
    <AuthGate>
      {({ user }) => (
        <Suspense
          fallback={
            <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
              Loading apply workspace…
            </div>
          }
        >
          <ApplyBody userId={user.id} />
        </Suspense>
      )}
    </AuthGate>
  );
}
