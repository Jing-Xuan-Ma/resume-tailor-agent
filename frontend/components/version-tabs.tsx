"use client";

import type { VersionItem } from "@/lib/api";

interface VersionTabsProps {
  versions: VersionItem[];
  activeVersionId: string | null;
  onSelect: (versionId: string) => void;
  onConfirm: (versionId: string) => void;
  loading?: boolean;
}

export default function VersionTabs({
  versions,
  activeVersionId,
  onSelect,
  onConfirm,
  loading,
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

      <div className="ml-auto">
        {activeVersionId && (() => {
          const active = versions.find((v) => v.id === activeVersionId);
          if (!active || active.is_confirmed) return null;
          return (
            <button
              onClick={() => onConfirm(activeVersionId)}
              disabled={loading}
              className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-green-700 disabled:opacity-50"
            >
              Confirm v{active.version_index}
            </button>
          );
        })()}
      </div>
    </div>
  );
}
