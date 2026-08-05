"use client";

export type FlowStepId = "jobs" | "detail" | "jd" | "tailor" | "apply" | "outreach";

const STEPS: { id: FlowStepId; label: string; hint: string }[] = [
  { id: "jobs", label: "1. Archive", hint: "Local inventory / history (Jobright plugin is primary discovery)" },
  { id: "detail", label: "2. Match", hint: "Score & keywords" },
  { id: "jd", label: "3. JD", hint: "Job description & hard requirements" },
  { id: "tailor", label: "4. Tailor", hint: "Agent + resume PDF" },
  { id: "apply", label: "5. Apply", hint: "Manual or auto" },
  { id: "outreach", label: "6. Outreach", hint: "HM / coffee chat" },
];

const JUMPABLE: FlowStepId[] = ["jd", "tailor", "apply", "outreach"];

interface FlowStepperProps {
  current: FlowStepId;
  className?: string;
  /** Jump within the tailor page (jd / tailor / apply / outreach). */
  onJump?: (step: FlowStepId) => void;
  /** Cross-page hrefs for early funnel steps. */
  hrefs?: Partial<Record<FlowStepId, string>>;
}

export default function FlowStepper({ current, className = "", onJump, hrefs }: FlowStepperProps) {
  const idx = STEPS.findIndex((s) => s.id === current);
  return (
    <nav
      data-testid="flow-stepper"
      aria-label="Application flow"
      className={`flex flex-wrap items-center gap-1 ${className}`}
    >
      {STEPS.map((step, i) => {
        const done = i < idx;
        const active = i === idx;
        const href = hrefs?.[step.id];
        const jumpable = !!onJump && JUMPABLE.includes(step.id);
        const chipClass = `rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ${
          active
            ? "bg-emerald-600 text-white ring-emerald-600"
            : done
              ? "bg-emerald-50 text-emerald-800 ring-emerald-200"
              : "bg-white text-slate-400 ring-slate-200"
        }${jumpable || href ? " cursor-pointer hover:opacity-90" : ""}`;
        return (
          <div key={step.id} className="flex items-center gap-1">
            {i > 0 ? <span className="px-1 text-slate-300">/</span> : null}
            {jumpable ? (
              <button
                type="button"
                data-testid={`flow-step-${step.id}`}
                className={chipClass}
                title={`${step.hint} — click to jump`}
                onClick={() => onJump?.(step.id)}
              >
                {step.label}
              </button>
            ) : href ? (
              <a
                href={href}
                data-testid={`flow-step-${step.id}`}
                className={chipClass}
                title={`${step.hint} — open`}
              >
                {step.label}
              </a>
            ) : (
              <div data-testid={`flow-step-${step.id}`} className={chipClass} title={step.hint}>
                {step.label}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}
