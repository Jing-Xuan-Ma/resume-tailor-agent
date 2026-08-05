"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getLlmStatus,
  setLlmPreference,
  type LlmProviderInfo,
  type LlmStatus,
} from "@/lib/api";

interface LlmModelPickerProps {
  /** Last provider/model reported by an agent turn */
  lastUsed?: { provider?: string | null; model?: string | null } | null;
}

function labelFor(p: Pick<LlmProviderInfo, "name" | "default_model">, model?: string | null) {
  const m = model || p.default_model;
  return m ? `${p.name} · ${m}` : p.name;
}

export default function LlmModelPicker({ lastUsed }: LlmModelPickerProps) {
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await getLlmStatus();
      setStatus(s);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load models");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!lastUsed?.provider && !lastUsed?.model) return;
    setStatus((prev) =>
      prev
        ? {
            ...prev,
            last_provider: lastUsed.provider || prev.last_provider,
            last_model: lastUsed.model || prev.last_model,
            active_provider: lastUsed.provider || prev.active_provider,
            active_model: lastUsed.model || prev.active_model,
            active_provider_name:
              prev.configured.find((c) => c.id === lastUsed.provider)?.name ||
              prev.active_provider_name,
          }
        : prev
    );
  }, [lastUsed?.provider, lastUsed?.model]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const display = useMemo(() => {
    if (!status) return "Loading model…";
    const providerId = lastUsed?.provider || status.active_provider || status.preferred_provider;
    const model = lastUsed?.model || status.active_model;
    const row =
      status.configured.find((c) => c.id === providerId) ||
      status.configured.find((c) => c.preferred) ||
      status.configured[0];
    if (!row) return "No model configured";
    return labelFor(row, model);
  }, [status, lastUsed]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = status?.configured || [];
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.id.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q) ||
        r.default_model.toLowerCase().includes(q)
    );
  }, [status, query]);

  const selectProvider = async (id: string) => {
    setBusy(true);
    try {
      const s = await setLlmPreference({ provider: id });
      setStatus(s);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to switch model");
    } finally {
      setBusy(false);
    }
  };

  const toggleAuto = async () => {
    if (!status) return;
    setBusy(true);
    try {
      const s = await setLlmPreference({ failover: !status.failover });
      setStatus(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle Auto");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative" ref={rootRef} data-testid="llm-model-picker">
      <button
        type="button"
        data-testid="llm-model-trigger"
        disabled={busy}
        onClick={() => {
          setOpen((v) => !v);
          void refresh();
        }}
        className="inline-flex max-w-[260px] items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-700 ring-1 ring-slate-200 hover:bg-white disabled:opacity-60"
        title="Current LLM — click to switch"
      >
        <span className="truncate">{display}</span>
        <svg viewBox="0 0 12 12" className="h-3 w-3 shrink-0 text-slate-400" aria-hidden>
          <path d="M3 4.5 L6 7.5 L9 4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>

      {open ? (
        <div
          className="absolute left-0 top-[calc(100%+6px)] z-40 w-[300px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl"
          data-testid="llm-model-menu"
        >
          <div className="border-b border-slate-100 p-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models"
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[12px] outline-none focus:border-emerald-400 focus:bg-white"
              data-testid="llm-model-search"
            />
          </div>

          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2.5">
            <div>
              <div className="text-[12px] font-semibold text-slate-900">Auto</div>
              <div className="text-[10px] text-slate-500">Failover when a provider is down</div>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={!!status?.failover}
              data-testid="llm-auto-toggle"
              disabled={busy || !status}
              onClick={() => void toggleAuto()}
              className={`relative h-5 w-9 rounded-full transition ${
                status?.failover ? "bg-emerald-600" : "bg-slate-300"
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
                  status?.failover ? "left-4" : "left-0.5"
                }`}
              />
            </button>
          </div>

          <ul className="max-h-64 overflow-y-auto py-1" data-testid="llm-model-list">
            {filtered.map((row) => {
              const active =
                row.id === (lastUsed?.provider || status?.active_provider || status?.preferred_provider);
              return (
                <li key={row.id}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void selectProvider(row.id)}
                    className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[12px] hover:bg-slate-50 ${
                      active ? "bg-emerald-50/80" : ""
                    }`}
                    data-testid={`llm-model-option-${row.id}`}
                  >
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-slate-900">{row.name}</div>
                      <div className="truncate text-[10px] text-slate-500">
                        {row.default_model}
                        {row.cooled_down ? " · cooling down" : ""}
                        {row.preferred ? " · preferred" : ""}
                      </div>
                    </div>
                    {active ? (
                      <span className="shrink-0 text-emerald-600" aria-hidden>
                        ✓
                      </span>
                    ) : null}
                  </button>
                </li>
              );
            })}
            {!filtered.length ? (
              <li className="px-3 py-4 text-center text-[11px] text-slate-400">
                No configured models match
              </li>
            ) : null}
          </ul>

          {error ? (
            <p className="border-t border-rose-100 bg-rose-50 px-3 py-2 text-[10px] text-rose-700">
              {error}
            </p>
          ) : (
            <p className="border-t border-slate-100 px-3 py-2 text-[10px] text-slate-400">
              Showing providers with API keys in .env. Auto tries the next one on 503/timeout.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
