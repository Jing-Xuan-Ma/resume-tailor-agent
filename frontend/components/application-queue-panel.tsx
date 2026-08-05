"use client";

import { useCallback, useEffect, useState } from "react";
import {
  confirmQueueItem,
  enqueueApplications,
  listApplicationQueue,
  processQueueItem,
  skipQueueItem,
  type QueueItem,
} from "@/lib/api";

interface ApplicationQueuePanelProps {
  userId: string;
}

export default function ApplicationQueuePanel({ userId }: ApplicationQueuePanelProps) {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [versionId, setVersionId] = useState("");
  const [jobId, setJobId] = useState("");
  const [company, setCompany] = useState("");
  const [position, setPosition] = useState("");

  const refresh = useCallback(async () => {
    if (!userId) return;
    try {
      const res = await listApplicationQueue(userId);
      setItems(res.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load queue");
    }
  }, [userId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleEnqueue = async () => {
    if (!versionId.trim()) {
      setError("version_id required (confirm tailored resume first)");
      return;
    }
    setError(null);
    try {
      await enqueueApplications(userId, [
        {
          version_id: versionId.trim(),
          job_id: jobId.trim() || undefined,
          company: company.trim() || undefined,
          position: position.trim() || undefined,
        },
      ]);
      setVersionId("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enqueue failed");
    }
  };

  const run = async (id: string, fn: () => Promise<QueueItem>) => {
    setBusyId(id);
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-4" data-testid="application-queue-panel">
      <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-950">
        Batch queue fills forms and <strong>pauses before Submit</strong>. Confirm each job
        separately — there is no one-click submit-all.
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-bold">Add to queue</h2>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <input
            className="rounded-lg border border-slate-200 px-3 py-2 text-xs"
            placeholder="version_id (required)"
            value={versionId}
            onChange={(e) => setVersionId(e.target.value)}
            data-testid="queue-version-id"
          />
          <input
            className="rounded-lg border border-slate-200 px-3 py-2 text-xs"
            placeholder="job_id (optional)"
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
          />
          <input
            className="rounded-lg border border-slate-200 px-3 py-2 text-xs"
            placeholder="company"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
          <input
            className="rounded-lg border border-slate-200 px-3 py-2 text-xs"
            placeholder="position"
            value={position}
            onChange={(e) => setPosition(e.target.value)}
          />
        </div>
        <button
          type="button"
          data-testid="queue-enqueue-btn"
          onClick={() => void handleEnqueue()}
          className="mt-3 rounded-xl bg-slate-900 px-4 py-2 text-xs font-semibold text-white"
        >
          Enqueue job
        </button>
      </section>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
          {error}
        </div>
      ) : null}

      <section className="space-y-2" data-testid="queue-list">
        {items.length === 0 ? (
          <p className="text-sm text-slate-500">Queue empty.</p>
        ) : (
          items.map((item) => (
            <div
              key={item.id}
              className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
              data-testid={`queue-item-${item.id}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="text-sm font-bold text-slate-900">
                    {[item.company, item.position].filter(Boolean).join(" · ") || item.id.slice(0, 8)}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    status: <span data-testid="queue-fill-status">{item.fill_status}</span>
                    {item.awaiting_confirm ? " · awaiting your confirm" : ""}
                    {item.error ? ` · ${item.error}` : ""}
                  </div>
                </div>
                <div className="flex flex-wrap gap-1">
                  {item.fill_status === "queued" || item.fill_status === "failed" ? (
                    <button
                      type="button"
                      disabled={busyId === item.id}
                      data-testid="queue-process-btn"
                      className="rounded-lg bg-emerald-700 px-2.5 py-1.5 text-[10px] font-semibold text-white disabled:opacity-40"
                      onClick={() => void run(item.id, () => processQueueItem(item.id, userId))}
                    >
                      Fill & pause
                    </button>
                  ) : null}
                  {item.awaiting_confirm || item.fill_status === "awaiting_confirm" ? (
                    <button
                      type="button"
                      disabled={busyId === item.id}
                      data-testid="queue-confirm-btn"
                      className="rounded-lg bg-slate-900 px-2.5 py-1.5 text-[10px] font-semibold text-white disabled:opacity-40"
                      onClick={() =>
                        void run(item.id, () => confirmQueueItem(item.id, userId, true))
                      }
                    >
                      Confirm Submit
                    </button>
                  ) : null}
                  {item.fill_status !== "submitted" && item.fill_status !== "skipped" ? (
                    <button
                      type="button"
                      disabled={busyId === item.id}
                      data-testid="queue-skip-btn"
                      className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-[10px] font-semibold text-slate-700 disabled:opacity-40"
                      onClick={() => void run(item.id, () => skipQueueItem(item.id, userId))}
                    >
                      Skip
                    </button>
                  ) : null}
                </div>
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
