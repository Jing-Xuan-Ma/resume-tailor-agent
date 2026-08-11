"use client";

import { Suspense } from "react";
import AuthGate from "@/components/auth-gate";
import RankedJobsTable from "@/components/ranked-jobs-table";

export default function JobsPage() {
  return (
    <AuthGate>
      {({ user, onLogout }) => (
        <Suspense
          fallback={
            <main className="flex min-h-screen items-center justify-center bg-[#f4f6f4] text-sm text-slate-500">
              Loading jobs…
            </main>
          }
        >
          <RankedJobsTable
            displayName={user.full_name || user.email}
            onLogout={onLogout}
          />
        </Suspense>
      )}
    </AuthGate>
  );
}
