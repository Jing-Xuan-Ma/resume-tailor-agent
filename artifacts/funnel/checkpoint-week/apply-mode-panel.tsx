"use client";

export interface ApplyFieldRow {
  field: string;
  value?: string;
  note?: string;
  required?: boolean;
  type?: string;
  ats_type?: string;
}

interface ApplyModePanelProps {
  visible: boolean;
  busy?: boolean;
  status?: string | null;
  message?: string | null;
  pausedBeforeSubmit?: boolean;
  filledFields?: ApplyFieldRow[];
  atsType?: string | null;
  sourceUrl?: string | null;
  browserFill?: Record<string, unknown> | null;
  onManual: () => void;
  onAuto: () => void;
}

export default function ApplyModePanel({
  visible,
  busy,
  status,
  message,
  pausedBeforeSubmit,
  filledFields = [],
  atsType,
  sourceUrl,
  browserFill,
  onManual,
  onAuto,
}: ApplyModePanelProps) {
  if (!visible) return null;

  const profileFields = filledFields.filter((f) => !String(f.field).startsWith("ats:"));
  const atsFields = filledFields.filter((f) => String(f.field).startsWith("ats:"));

  return (
    <div
      className="rounded-2xl border border-emerald-200 bg-white p-4 shadow-sm"
      data-testid="apply-mode-panel"
    >
      <h3 className="text-sm font-bold text-slate-950">Step 5 · How do you want to apply?</h3>
      <p className="mt-1 text-xs text-slate-500" data-testid="apply-mode-hint">
        {status === "waiting_confirm"
          ? "Confirm the tailored version above first, then choose Manual or Auto. Auto never clicks Submit."
          : "Manual = you submit. Auto = we map fields and stop before Submit."}
      </p>
      {status === "waiting_confirm" ? (
        <button
          type="button"
          data-testid="apply-goto-confirm"
          onClick={() => {
            document.querySelector("[data-testid=confirm-version]")?.scrollIntoView({ block: "center" });
            (document.querySelector("[data-testid=confirm-version]") as HTMLButtonElement | null)?.focus();
          }}
          className="mt-2 text-[11px] font-semibold text-emerald-700 underline"
        >
          Jump to Confirm ↑
        </button>
      ) : null}
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
              : status === "waiting_confirm"
                ? "bg-amber-50 text-amber-900 ring-amber-200"
                : status === "error"
                  ? "bg-rose-50 text-rose-800 ring-rose-200"
                  : "bg-slate-50 text-slate-700 ring-slate-200"
          }`}
        >
          <div>Status: {status === "waiting_confirm" ? "waiting for Confirm" : status}</div>
          {message ? <div className="mt-1 font-normal opacity-90">{message}</div> : null}
          {atsType ? (
            <div className="mt-1 font-normal" data-testid="apply-ats-type">
              ATS map: {atsType}
            </div>
          ) : null}
          {sourceUrl ? (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-1 block truncate font-normal text-emerald-800 underline"
              data-testid="apply-source-url"
            >
              Open posting
            </a>
          ) : null}
          {pausedBeforeSubmit ? (
            <div className="mt-1" data-testid="paused-before-submit">
              Stopped before Submit — no application was sent.
            </div>
          ) : null}
        </div>
      ) : null}

      {browserFill ? (
        <div
          className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-900"
          data-testid="browser-fill-result"
        >
          <div className="font-bold">Browser fill-pause</div>
          <div className="mt-0.5" data-testid="browser-fill-status">
            status: {String(browserFill.status || "n/a")} · submitted:{" "}
            <span data-testid="browser-fill-submitted">
              {String(browserFill.submitted ?? false)}
            </span>
            {browserFill.sandbox ? " · sandbox" : " · live URL"}
            {browserFill.live_gated ? " · live gated (fixture preferred)" : null}
            {browserFill.ats_type ? ` · ${String(browserFill.ats_type)}` : null}
          </div>
          {browserFill.sandbox || browserFill.live_gated ? (
            <div className="mt-0.5 font-semibold text-emerald-800" data-testid="browser-fill-gate-note">
              Fill uses local ATS fixture by default — live boards only if ALLOW_LIVE_BROWSER_FILL=true. Never submits.
            </div>
          ) : (
            <div className="mt-0.5 font-semibold text-amber-900" data-testid="browser-fill-live-note">
              Live URL fill-pause (gated). Submit is never clicked.
            </div>
          )}
          {Array.isArray(browserFill.filled) ? (
            <div className="mt-0.5" data-testid="browser-fill-count">
              filled {(browserFill.filled as Array<{ status?: string }>).filter((f) => f.status === "filled").length}/
              {(browserFill.filled as unknown[]).length} fields
            </div>
          ) : null}
          {typeof browserFill.message === "string" ? (
            <div className="mt-0.5 opacity-90">{browserFill.message}</div>
          ) : null}
          {Array.isArray(browserFill.filled) && (browserFill.filled as unknown[]).length > 0 ? (
            <ul
              className="mt-1 max-h-24 overflow-y-auto rounded-lg border border-amber-100 bg-white/70 px-2 py-1"
              data-testid="browser-fill-fields"
            >
              {(browserFill.filled as Array<{ field?: string; status?: string }>).map((row, idx) => (
                <li key={`${row.field || "f"}-${idx}`} className="flex justify-between gap-2 py-0.5">
                  <span className="truncate font-medium">{row.field || "field"}</span>
                  <span className={row.status === "filled" ? "text-emerald-700" : "text-slate-500"}>
                    {row.status || "—"}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {profileFields.length > 0 ? (
        <div className="mt-3" data-testid="apply-field-checklist">
          <h4 className="text-[11px] font-bold uppercase tracking-wide text-slate-600">
            Profile autofill checklist
          </h4>
          <ul className="mt-1 max-h-40 overflow-y-auto rounded-xl border border-slate-100 bg-slate-50/80 text-[11px]">
            {profileFields.map((row) => (
              <li
                key={row.field}
                className="grid grid-cols-[120px_minmax(0,1fr)] gap-2 border-b border-slate-100 px-2 py-1.5 last:border-0"
              >
                <span className="font-semibold text-slate-700">{row.field}</span>
                <span className="truncate text-slate-600" title={row.value || ""}>
                  {row.value || "—"}
                  {row.note ? <span className="ml-1 text-amber-700">({row.note})</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {atsFields.length > 0 ? (
        <div className="mt-3" data-testid="apply-ats-checklist">
          <h4 className="text-[11px] font-bold uppercase tracking-wide text-slate-600">
            ATS field map (dry-run)
          </h4>
          <ul className="mt-1 max-h-40 overflow-y-auto rounded-xl border border-slate-100 bg-white text-[11px]">
            {atsFields.map((row) => (
              <li
                key={row.field}
                className="grid grid-cols-[140px_minmax(0,1fr)] gap-2 border-b border-slate-100 px-2 py-1.5 last:border-0"
              >
                <span className="font-semibold text-slate-700">
                  {String(row.field).replace(/^ats:/, "")}
                  {row.required ? " *" : ""}
                </span>
                <span className="truncate text-slate-600" title={row.value || ""}>
                  {row.value || "—"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
