"use client";

import type { VersionItem } from "@/lib/api";

interface VersionTabsProps {
  versions: VersionItem[];
  activeVersionId: string | null;
  onSelect: (versionId: string) => void;
  onConfirm: (versionId: string) => void;
  loading?: boolean;
  /** When false, Confirm is disabled (evidence/format gate). */
  canConfirm?: boolean;
  confirmBlockedReason?: string | null;
}

export default function VersionTabs({
  versions,
  activeVersionId,
  onSelect,
  onConfirm,
  loading,
  canConfirm = true,
  confirmBlockedReason = null,
}: VersionTabsProps) {
  if (!versions.length) {
    return (
      <div className="mb-3 flex items-center gap-2 text-sm text-slate-400">
        No versions yet. Rewrite your resume to create one.
      </div>
    );
  }

  return (
    <div className="mb-3 flex items-center gap-2">
      <span className="mr-1 text-xs font-medium text-slate-500">Versions:</span>
      {versions.map((v) => {
        const isActive = v.id === activeVersionId;
        return (
          <button
            key={v.id}
            onClick={() => onSelect(v.id)}
            disabled={loading}
            className={`relative rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
              isActive
                ? "bg-slate-950 text-white shadow-sm"
                : v.is_confirmed
                ? "bg-green-50 text-green-700 ring-1 ring-green-200 hover:bg-green-100"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            v{v.version_index}
            {v.is_confirmed && (
              <span className="ml-1 text-[10px]">✓</span>
            )}
          </button>
        );
      })}

      <div className="ml-auto flex items-center gap-2">
        {activeVersionId && (() => {
          const active = versions.find((v) => v.id === activeVersionId);
          if (!active || active.is_confirmed) return null;
          return (
            <>
              {!canConfirm && confirmBlockedReason ? (
                <span className="max-w-[220px] truncate text-[11px] text-amber-700" title={confirmBlockedReason}>
                  {confirmBlockedReason}
                </span>
              ) : null}
              <button
                type="button"
                data-testid="confirm-version"
                onClick={() => onConfirm(activeVersionId)}
                disabled={loading || !canConfirm}
                className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-green-700 disabled:opacity-50"
              >
                Confirm v{active.version_index}
              </button>
            </>
          );
        })()}
      </div>
    </div>
  );
}
