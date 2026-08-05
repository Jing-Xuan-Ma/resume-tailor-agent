"use client";

export interface DiffChange {
  path: string;
  kind: "add" | "remove" | "replace" | string;
  before?: string;
  after?: string;
}

export interface ContentDelta {
  changed_fields?: string[];
  changes?: DiffChange[];
  change_count?: number;
  instruction?: string;
}

interface ResumeDiffProps {
  delta: ContentDelta | null;
}

export default function ResumeDiff({ delta }: ResumeDiffProps) {
  const changes = delta?.changes || [];
  if (!delta || changes.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-xs text-slate-400" data-testid="resume-diff-empty">
        No content changes yet. Run a rewrite to see highlighted diffs.
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="resume-diff">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">Content Changes</h3>
        <span className="text-[11px] font-semibold text-slate-500">{delta.change_count ?? changes.length} edits</span>
      </div>
      <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
        {changes.map((c, idx) => (
          <div key={`${c.path}-${idx}`} className="rounded-xl border border-slate-200 bg-white p-3 text-xs">
            <p className="mb-1 font-semibold text-slate-700">{c.path}</p>
            {c.before ? (
              <p className="mb-1 rounded-lg bg-red-50 px-2 py-1 text-red-700 ring-1 ring-red-100">
                <span className="mr-1 font-bold">{c.kind === "hide" ? "hidden" : "−"}</span>
                {c.before}
              </p>
            ) : null}
            {c.after ? (
              <p className="rounded-lg bg-emerald-50 px-2 py-1 text-emerald-800 ring-1 ring-emerald-100">
                <span className="mr-1 font-bold">+</span>
                {c.after}
              </p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
