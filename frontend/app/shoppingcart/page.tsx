"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import AuthGate from "@/components/auth-gate";
import AppTopNav from "@/components/app-top-nav";
import FlowStepper from "@/components/flow-stepper";
import ShoppingCartPanel from "@/components/shopping-cart-panel";

function CartBody({ userId }: { userId: string }) {
  const searchParams = useSearchParams();
  const raw = searchParams.get("internJobIds") || "";
  const internJobIds = raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  return (
    <main className="mx-auto max-w-4xl px-4 py-6">
      <div className="mb-4">
        <h2 className="text-base font-bold text-slate-900">Shopping Cart</h2>
        <p className="mt-1 text-xs text-slate-500">
          已选 {internJobIds.length} 个职位 · 先确认列表，再点底部「批量 Refine」
        </p>
      </div>
      {internJobIds.length ? (
        <ShoppingCartPanel userId={userId} internJobIds={internJobIds} />
      ) : (
        <p className="text-sm text-slate-500">
          缺少 internJobIds。请从{" "}
          <a className="text-emerald-700 underline" href="/jobs?tab=internlist">
            Jobs → Intern-list
          </a>{" "}
          勾选后点击 Shopping Cart。
        </p>
      )}
    </main>
  );
}

export default function ShoppingCartPage() {
  return (
    <AuthGate>
      {({ user, onLogout }) => (
        <div className="min-h-screen bg-[#f4f6f4] text-slate-950" data-testid="shopping-cart-page">
          <AppTopNav
            active="tailor"
            displayName={user.full_name || user.email}
            onLogout={onLogout}
          />
          <div className="border-b border-slate-200 bg-white px-4 py-2">
            <div className="mx-auto flex max-w-4xl items-center justify-between gap-3">
              <h1 className="text-sm font-bold">Shopping Cart</h1>
              <FlowStepper
                current="tailor"
                hrefs={{
                  jobs: "/jobs",
                  tailor: "/?view=resume&step=tailor",
                  apply: "/apply",
                  outreach: "/outreach",
                }}
              />
            </div>
          </div>
          <Suspense fallback={<main className="p-6 text-sm text-slate-500">Loading…</main>}>
            <CartBody userId={user.id} />
          </Suspense>
        </div>
      )}
    </AuthGate>
  );
}
