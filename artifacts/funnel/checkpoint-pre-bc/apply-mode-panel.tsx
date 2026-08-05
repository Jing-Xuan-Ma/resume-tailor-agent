"use client";

interface ApplyModePanelProps {
  visible: boolean;
  busy?: boolean;
  status?: string | null;
  message?: string | null;
  pausedBeforeSubmit?: boolean;
  onManual: () => void;
  onAuto: () => void;
}

export default function ApplyModePanel({
  visible,
  busy,
  status,
  message,
  pausedBeforeSubmit,
  onManual,
  onAuto,
}: ApplyModePanelProps) {
  if (!visible) return null;

  return (
    <div
      className="rounded-2xl border border-emerald-200 bg-white p-4 shadow-sm"
      data-testid="apply-mode-panel"
    >
      <h3 className="text-sm font-bold text-slate-950">Step 5 · How do you want to apply?</h3>
      <p className="mt-1 text-xs text-slate-500">
        {status === "waiting_confirm"
          ? "Confirm the tailored version above first, then choose Manual or Auto."
          : "Manual = you submit. Auto = we fill the form and stop before Submit."}
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          type="button"
          data-testid="apply-manual"
          disabled={busy}
          onClick={onManual}
          className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left hover:bg-slate-50 disabled:opacity-50"
        >
          <div className="text-xs font-bold text-slate-900">Manual apply</div>
          <div className="mt-0.5 text-[11px] text-slate-500">Download / copy and submit yourself</div>
        </button>
        <button
          type="button"
          data-testid="apply-auto"
          disabled={busy}
          onClick={onAuto}
          className="rounded-xl bg-emerald-600 px-4 py-3 text-left text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          <div className="text-xs font-bold">Auto apply (safe)</div>
          <div className="mt-0.5 text-[11px] text-emerald-50/90">Fills fields, pauses before Submit</div>
        </button>
      </div>
      {status ? (
        <div
          data-testid="apply-status"
          className={`mt-3 rounded-xl px-3 py-2 text-xs font-semibold ring-1 ${
            pausedBeforeSubmit
              ? "bg-amber-50 text-amber-800 ring-amber-200"
              : "bg-slate-50 text-slate-700 ring-slate-200"
          }`}
        >
          <div>Status: {status}</div>
          {message ? <div className="mt-1 font-normal opacity-90">{message}</div> : null}
          {pausedBeforeSubmit ? (
            <div className="mt-1" data-testid="paused-before-submit">
              Stopped before Submit — no application was sent.
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
