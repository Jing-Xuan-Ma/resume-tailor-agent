"use client";

export type AppNavTab = "profile" | "jobs" | "tailor" | "records";

const TABS: { id: AppNavTab; label: string; href: string; testId: string }[] = [
  { id: "profile", label: "Profile", href: "/?view=profile", testId: "nav-profile" },
  { id: "jobs", label: "Jobs", href: "/jobs", testId: "nav-jobs" },
  { id: "tailor", label: "Tailor", href: "/?view=resume&step=tailor", testId: "nav-tailor" },
  { id: "records", label: "Records", href: "/?view=records", testId: "nav-records" },
];

interface AppTopNavProps {
  active: AppNavTab;
  displayName?: string;
  onLogout?: () => void;
  /**
   * Home shell: switch Profile / Tailor / Records in-place.
   * Jobs always navigates to `/jobs`.
   */
  onSelectTab?: (tab: AppNavTab) => void;
}

export default function AppTopNav({ active, displayName, onLogout, onSelectTab }: AppTopNavProps) {
  const handleLogout = () => {
    if (onLogout) {
      onLogout();
      return;
    }
    try {
      window.localStorage.removeItem("resume-agent-auth");
    } catch {
      /* ignore */
    }
    window.location.href = "/";
  };

  return (
    <div
      className="sticky top-0 z-30 flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[#e8e8e4] bg-white/95 px-4 py-2.5 backdrop-blur"
      data-testid="app-top-nav"
    >
      <div className="flex min-w-0 items-center gap-2">
        <a
          href="/"
          className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#14352b]"
          data-testid="nav-brand"
        >
          Resume Agent
        </a>
        {displayName ? (
          <span className="hidden truncate text-xs text-slate-500 sm:inline" data-testid="nav-display-name">
            {displayName}
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div
          className="flex gap-1 rounded-full bg-slate-100 p-1 shadow-sm ring-1 ring-slate-200"
          role="tablist"
          aria-label="Primary"
        >
          {TABS.map((tab) => {
            const isActive = active === tab.id;
            const className = `rounded-full px-3 py-1.5 text-xs font-semibold ${
              isActive ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`;

            if (onSelectTab && tab.id !== "jobs") {
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  data-testid={tab.testId}
                  className={className}
                  onClick={() => onSelectTab(tab.id)}
                >
                  {tab.label}
                </button>
              );
            }

            return (
              <a
                key={tab.id}
                href={tab.href}
                role="tab"
                aria-selected={isActive}
                data-testid={tab.testId}
                className={className}
              >
                {tab.label}
              </a>
            );
          })}
        </div>
        <button
          type="button"
          onClick={handleLogout}
          data-testid="nav-logout"
          className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm ring-1 ring-slate-200 hover:text-slate-950"
        >
          Logout
        </button>
      </div>
    </div>
  );
}
