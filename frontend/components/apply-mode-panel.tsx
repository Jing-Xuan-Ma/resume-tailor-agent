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
      <h3 className="text-sm font-bold text-slate-950">Choose how to apply</h3>
      <p className="mt-1 text-xs text-slate-500">
        Resume is confirmed. Pick manual fill or auto-apply dry run (stops before Submit).
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="apply-manual"
          disabled={busy}
          onClick={onManual}
          className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Manual Apply
        </button>
        <button
          type="button"
          data-testid="apply-auto"
          disabled={busy}
          onClick={onAuto}
          className="rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Auto Apply (pause before submit)
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
