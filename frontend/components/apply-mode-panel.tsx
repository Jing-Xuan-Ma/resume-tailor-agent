"use client";

import { useMemo, useState } from "react";
import type { FillPlanItem } from "@/lib/api";

export interface ApplyFieldRow {
  field: string;
  value?: string;
  note?: string;
  required?: boolean;
  type?: string;
  ats_type?: string;
  tier?: string;
  confidence?: number;
}

interface ApplyModePanelProps {
  visible: boolean;
  busy?: boolean;
  status?: string | null;
  message?: string | null;
  pausedBeforeSubmit?: boolean;
  filledFields?: ApplyFieldRow[];
  fillPlan?: FillPlanItem[];
  mapProvider?: string | null;
  atsType?: string | null;
  sourceUrl?: string | null;
  boardUrl?: string | null;
  browserFill?: Record<string, unknown> | null;
  onManual: () => void;
  onAuto: () => void;
  /** After pause — user explicitly confirms submit (audit; opens posting). */
  onConfirmSubmit?: () => void;
  confirmSubmitBusy?: boolean;
  applyId?: string | null;
  /** Confirm tailored version without scrolling to header */
  onConfirm?: () => void;
  confirming?: boolean;
  canConfirm?: boolean;
  /** Dedicated Apply workspace URL */
  applyWorkspaceHref?: string | null;
}

function tierOf(item: FillPlanItem): string {
  if (item.tier) return String(item.tier);
  const conf = Number(item.confidence ?? 0);
  const action = String(item.action || "");
  if (action === "leave_empty" || !action) return "empty";
  if (conf >= 0.85) return "auto";
  if (conf >= 0.5) return "review";
  return "empty";
}

export default function ApplyModePanel({
  visible,
  busy,
  status,
  message,
  pausedBeforeSubmit,
  filledFields = [],
  fillPlan = [],
  mapProvider,
  atsType,
  sourceUrl,
  boardUrl,
  browserFill,
  onManual,
  onAuto,
  onConfirmSubmit,
  confirmSubmitBusy,
  applyId,
  onConfirm,
  confirming,
  canConfirm = true,
  applyWorkspaceHref,
}: ApplyModePanelProps) {
  const [humanReviewed, setHumanReviewed] = useState(false);
  const buckets = useMemo(() => {
    const auto: FillPlanItem[] = [];
    const review: FillPlanItem[] = [];
    const empty: FillPlanItem[] = [];
    for (const m of fillPlan) {
      const t = tierOf(m);
      if (t === "auto") auto.push(m);
      else if (t === "review") review.push(m);
      else empty.push(m);
    }
    return { auto, review, empty };
  }, [fillPlan]);

  if (!visible) return null;

  const waitingConfirm = status === "waiting_confirm";
  const waitingVersion = status === "waiting_version";
  const locked = waitingConfirm || waitingVersion;
  const needsGate = buckets.review.length > 0 || buckets.empty.length > 0 || Boolean(pausedBeforeSubmit);
  const canShowConfirm = !needsGate || humanReviewed;

  return (
    <div
      className="rounded-2xl border border-emerald-200 bg-white p-4 shadow-sm"
      data-testid="apply-mode-panel"
    >
      <h3 className="text-sm font-bold text-slate-950">Step 5 · How do you want to apply?</h3>
      <p className="mt-1 text-xs text-slate-500" data-testid="apply-mode-hint">
        {waitingVersion
          ? "Waiting for a tailored version — Paste JD or open a ranked job first."
          : waitingConfirm
            ? "Confirm this tailored version first (button below). Then open the Apply workspace or use Manual / Auto here."
            : "Prefer the full Apply workspace (separate page). Manual = official site. Auto = map fields, never Submit."}
      </p>
      <p
        className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-amber-800"
        data-testid="apply-never-submit"
      >
        Safety: Auto-apply never clicks Submit
      </p>

      {waitingConfirm && onConfirm ? (
        <button
          type="button"
          data-testid="apply-inline-confirm"
          disabled={!!confirming || !canConfirm || busy}
          onClick={onConfirm}
          className="mt-3 w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
        >
          {confirming
            ? "Confirming…"
            : canConfirm
              ? "Confirm this resume → unlock Apply"
              : "Confirm blocked (fix evidence/format)"}
        </button>
      ) : null}

      {waitingConfirm && !onConfirm ? (
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

      {waitingVersion ? (
        <button
          type="button"
          data-testid="apply-goto-confirm"
          onClick={() => {
            document.querySelector("[data-testid=confirm-version]")?.scrollIntoView({ block: "center" });
          }}
          className="mt-2 text-[11px] font-semibold text-emerald-700 underline"
        >
          Jump to Tailor ↑
        </button>
      ) : null}

      {applyWorkspaceHref && !waitingVersion ? (
        <a
          href={applyWorkspaceHref}
          data-testid="open-apply-workspace"
          className={`mt-3 flex w-full items-center justify-center rounded-xl px-4 py-3 text-sm font-semibold ${
            waitingConfirm
              ? "border border-emerald-200 bg-emerald-50 text-emerald-900"
              : "bg-slate-900 text-white hover:bg-slate-800"
          }`}
        >
          {waitingConfirm ? "Open Apply workspace (confirm there too) →" : "Open Apply workspace →"}
        </a>
      ) : null}

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          type="button"
          data-testid="apply-manual"
          disabled={busy || locked}
          onClick={onManual}
          className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-left hover:bg-slate-50 disabled:opacity-50"
        >
          <div className="text-xs font-bold text-slate-900">Manual apply</div>
          <div className="mt-0.5 text-[11px] text-slate-500">Download / open official site yourself</div>
        </button>
        <button
          type="button"
          data-testid="apply-auto"
          disabled={busy || locked}
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
          {mapProvider ? (
            <div className="mt-1 font-normal opacity-80">Field map: {mapProvider}</div>
          ) : null}
          {sourceUrl ? (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-1 block truncate font-normal text-emerald-800 underline"
              data-testid="apply-source-url"
            >
              Open apply page
            </a>
          ) : null}
          {boardUrl && boardUrl !== sourceUrl ? (
            <a
              href={boardUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-1 block truncate font-normal text-slate-600 underline"
              data-testid="apply-board-url"
              title="Job-board listing (Indeed etc.) — use if company ATS fails to load"
            >
              Fallback: job board listing
            </a>
          ) : null}
          {pausedBeforeSubmit ? (
            <div className="mt-1" data-testid="paused-before-submit">
              Stopped before Submit — no application was sent.
            </div>
          ) : null}

          {fillPlan.length > 0 ? (
            <div className="mt-3 space-y-1.5 font-normal" data-testid="apply-panel-fill-tiers">
              <div className="text-[10px] font-bold uppercase tracking-wide text-emerald-800">
                已自动填 ({buckets.auto.length})
              </div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-amber-800">
                待你核对 ({buckets.review.length})
              </div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-rose-800">
                未填 ({buckets.empty.length})
              </div>
            </div>
          ) : null}

          {pausedBeforeSubmit && onConfirmSubmit ? (
            <>
              {needsGate ? (
                <label
                  className="mt-3 flex cursor-pointer items-start gap-2 font-medium"
                  data-testid="human-reviewed-gate"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={humanReviewed}
                    onChange={(e) => setHumanReviewed(e.target.checked)}
                    data-testid="human-reviewed-checkbox"
                  />
                  <span>我已检查</span>
                </label>
              ) : null}
              {canShowConfirm ? (
                <button
                  type="button"
                  data-testid="confirm-submit-btn"
                  disabled={!!confirmSubmitBusy || !applyId}
                  onClick={onConfirmSubmit}
                  className="mt-3 w-full rounded-xl bg-slate-900 px-3 py-2.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
                >
                  {confirmSubmitBusy ? "Recording confirm…" : "打开官网亲手 Submit"}
                </button>
              ) : (
                <p className="mt-2 text-[11px] font-medium text-amber-900" data-testid="confirm-submit-locked">
                  勾选「我已检查」后显示打开官网按钮。
                </p>
              )}
            </>
          ) : null}
          {status === "submitted_by_user_confirm" ? (
            <div className="mt-2 text-[11px] font-semibold text-emerald-800" data-testid="submit-confirmed">
              Confirmed by you — open the posting to finish Submit on the employer site.
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
          </div>
          {typeof browserFill.message === "string" ? (
            <div className="mt-1 opacity-90">{browserFill.message}</div>
          ) : null}
        </div>
      ) : null}

      {filledFields.length > 0 && !locked ? (
        <details className="mt-3 rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2" open={pausedBeforeSubmit}>
          <summary className="cursor-pointer text-[11px] font-semibold text-slate-700">
            Field checklist ({filledFields.length})
          </summary>
          <ul className="mt-2 max-h-48 overflow-y-auto text-[11px] text-slate-600">
            {filledFields.slice(0, 40).map((row) => (
              <li key={row.field} className="border-b border-slate-100 py-1 last:border-0">
                <span className="font-semibold">{row.field}</span>
                {row.value ? `: ${row.value}` : null}
                {row.note ? <span className="text-amber-700"> ({row.note})</span> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
