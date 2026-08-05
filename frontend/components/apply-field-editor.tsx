"use client";

import { useMemo, useState } from "react";
import type { FillPlanItem } from "@/lib/api";

export type FieldTone = "auto" | "review" | "empty";

export type EditableField = {
  id: string;
  label: string;
  profileKey: string;
  value: string;
  confidence?: number;
  reason?: string;
  tone: FieldTone;
  longText?: boolean;
  required?: boolean;
};

export const PROFILE_GROUPS: {
  id: string;
  label: string;
  keys: string[];
}[] = [
  {
    id: "basics",
    label: "基本信息",
    keys: ["full_name", "first_name", "last_name", "email", "phone", "location"],
  },
  {
    id: "links",
    label: "链接类",
    keys: ["linkedin", "linkedin_url", "portfolio", "portfolio_url", "github", "github_url"],
  },
  {
    id: "eligibility",
    label: "工作资格",
    keys: [
      "work_authorization",
      "work_authorized",
      "needs_sponsorship",
      "visa_status",
      "earliest_start",
      "salary_expectation",
      "willing_to_relocate",
    ],
  },
];

const LONG_TEXT_KEYS = new Set([
  "cover_letter",
  "cover_letter_path",
  "why_this_role",
  "additional_info",
  "why_join",
  "additional",
]);

const BOOLISH = new Set([
  "work_authorization",
  "work_authorized",
  "needs_sponsorship",
  "willing_to_relocate",
]);

/** Map UI / fill-plan keys → Candidate Library `apply` keys. */
export function toLibraryApplyKey(profileKey: string): string | null {
  const k = (profileKey || "").trim().toLowerCase().replace(/^ats:/, "");
  if (!k || k === "resume_upload" || k === "submit_button" || k === "resume_path") return null;
  const map: Record<string, string> = {
    full_name: "full_name",
    email: "email",
    phone: "phone",
    location: "location",
    linkedin: "linkedin_url",
    linkedin_url: "linkedin_url",
    portfolio: "portfolio_url",
    portfolio_url: "portfolio_url",
    github: "github_url",
    github_url: "github_url",
    work_authorization: "work_authorized",
    work_authorized: "work_authorized",
    needs_sponsorship: "needs_sponsorship",
    visa_status: "visa_status",
    earliest_start: "earliest_start",
    salary_expectation: "salary_expectation",
    willing_to_relocate: "willing_to_relocate",
    cover_letter: "answers.cover_letter",
    why_this_role: "answers.why_this_role",
    additional_info: "answers.additional_info",
  };
  return map[k] || (k.startsWith("answers.") ? k : null);
}

export function libraryValueFromInput(libraryKey: string, raw: string): unknown {
  if (libraryKey === "work_authorized" || libraryKey === "needs_sponsorship" || libraryKey === "willing_to_relocate") {
    const t = raw.trim().toLowerCase();
    if (["yes", "true", "y", "1"].includes(t)) return true;
    if (["no", "false", "n", "0"].includes(t)) return false;
    return raw;
  }
  return raw;
}

export function mergeApplyPatch(
  current: Record<string, unknown>,
  libraryKey: string,
  value: unknown
): Record<string, unknown> {
  if (libraryKey.startsWith("answers.")) {
    const sub = libraryKey.slice("answers.".length);
    const answers = { ...((current.answers as Record<string, unknown>) || {}), [sub]: value };
    return { ...current, answers };
  }
  if (libraryKey === "full_name" && !String(current.full_name || "").trim()) {
    return { ...current, full_name: value };
  }
  return { ...current, [libraryKey]: value };
}

export function tierOf(item: FillPlanItem | { tier?: string; confidence?: number; action?: string }): FieldTone {
  if (item.tier === "auto" || item.tier === "review" || item.tier === "empty") return item.tier;
  const conf = Number(item.confidence ?? 0);
  const action = String(item.action || "");
  if (action === "leave_empty" || !action) return "empty";
  if (conf >= 0.85) return "auto";
  if (conf >= 0.5) return "review";
  return "empty";
}

export function isLongTextField(key: string, label: string): boolean {
  const blob = `${key} ${label}`.toLowerCase();
  if (LONG_TEXT_KEYS.has(key.toLowerCase())) return true;
  return /cover\s*letter|why\s+(do\s+you|this|join)|additional\s+info|essay|statement/.test(blob);
}

export function fieldIdOf(item: FillPlanItem, index: number): string {
  return String(item.field_id || item.profile_key || item.label || `field-${index}`);
}

export function planItemToEditable(item: FillPlanItem, index: number): EditableField {
  const profileKey = String(item.profile_key || item.label || item.field_id || "");
  const label = String(item.label || item.profile_key || item.field_id || "field");
  const tone = tierOf(item);
  return {
    id: fieldIdOf(item, index),
    label,
    profileKey,
    value: String(item.value || ""),
    confidence: typeof item.confidence === "number" ? item.confidence : undefined,
    reason: item.reason ? String(item.reason) : undefined,
    tone,
    longText: isLongTextField(profileKey, label),
    required: Boolean(item.needs_review && tone === "empty"),
  };
}

export function filledRowToEditable(row: {
  field: string;
  value?: string;
  note?: string;
  required?: boolean;
  tier?: string;
  confidence?: number;
  profile_key?: string;
  action?: string;
}): EditableField {
  const field = String(row.field || "");
  const profileKey = String(row.profile_key || field.replace(/^ats:/, ""));
  const label = field.replace(/^ats:/, "");
  const tone = tierOf({
    tier: row.tier,
    confidence: row.confidence,
    action: row.action || (row.value && !String(row.value).startsWith("(") ? "fill" : "leave_empty"),
  });
  return {
    id: field,
    label,
    profileKey,
    value: String(row.value || ""),
    confidence: row.confidence,
    reason: row.note,
    tone,
    longText: isLongTextField(profileKey, label),
    required: Boolean(row.required),
  };
}

function groupIdForKey(key: string): string {
  const k = key.toLowerCase().replace(/^ats:/, "");
  for (const g of PROFILE_GROUPS) {
    if (g.keys.includes(k)) return g.id;
  }
  return "other";
}

export function groupFields(fields: EditableField[]): { id: string; label: string; items: EditableField[] }[] {
  const buckets: Record<string, EditableField[]> = {
    basics: [],
    links: [],
    eligibility: [],
    other: [],
  };
  for (const f of fields) {
    const gid = groupIdForKey(f.profileKey || f.label);
    (buckets[gid] || buckets.other).push(f);
  }
  const labels: Record<string, string> = {
    basics: "基本信息",
    links: "链接类",
    eligibility: "工作资格",
    other: "其他 / 职位特定",
  };
  return (["basics", "links", "eligibility", "other"] as const)
    .map((id) => ({ id, label: labels[id], items: buckets[id] }))
    .filter((g) => g.items.length > 0);
}

/* ─── UI pieces ───────────────────────────────────────────── */

export function ScanBanner({
  total,
  auto,
  review,
  empty,
  scannedAt,
  mapProvider,
  atsType,
  onRescan,
  rescanBusy,
}: {
  total: number;
  auto: number;
  review: number;
  empty: number;
  scannedAt: Date | null;
  mapProvider?: string | null;
  atsType?: string | null;
  onRescan?: () => void;
  rescanBusy?: boolean;
}) {
  const ago = scannedAt
    ? (() => {
        const sec = Math.max(0, Math.round((Date.now() - scannedAt.getTime()) / 1000));
        if (sec < 60) return `${sec}秒前`;
        if (sec < 3600) return `${Math.round(sec / 60)}分钟前`;
        return `${Math.round(sec / 3600)}小时前`;
      })()
    : null;

  return (
    <div
      className="rounded-2xl border border-emerald-200 bg-emerald-50/90 px-3 py-2.5 text-[11px] text-emerald-950"
      data-testid="apply-scan-banner"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold">
            ✓ 已扫描该职位申请表单，识别出 {total} 个字段（{auto} 个已匹配 / {review} 个待核对 / {empty}{" "}
            个缺失）
          </p>
          <p className="mt-0.5 text-emerald-800/80">
            {ago ? `最后扫描时间：${ago}` : "扫描结果来自本次 Auto Apply"}
            {mapProvider ? ` · map: ${mapProvider}` : ""}
            {atsType ? ` · ATS: ${atsType}` : ""}
          </p>
        </div>
        {onRescan ? (
          <button
            type="button"
            data-testid="apply-rescan-btn"
            disabled={rescanBusy}
            onClick={onRescan}
            className="shrink-0 rounded-lg border border-emerald-300 bg-white px-2.5 py-1 text-[10px] font-semibold text-emerald-900 hover:bg-emerald-50 disabled:opacity-50"
          >
            {rescanBusy ? "扫描中…" : "重新扫描"}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function LongTextModal({
  open,
  label,
  value,
  onChange,
  onClose,
}: {
  open: boolean;
  label: string;
  value: string;
  onChange: (v: string) => void;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/40 p-4 sm:items-center"
      data-testid="apply-longtext-modal"
      role="dialog"
      aria-modal="true"
    >
      <div className="flex max-h-[85vh] w-full max-w-xl flex-col rounded-2xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h3 className="text-sm font-bold text-slate-900">{label}</h3>
          <button
            type="button"
            className="rounded-lg px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50"
            onClick={onClose}
            data-testid="apply-longtext-close"
          >
            完成
          </button>
        </div>
        <textarea
          className="min-h-[220px] flex-1 resize-y px-4 py-3 text-sm text-slate-800 outline-none"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="在此输入…"
          data-testid="apply-longtext-input"
          autoFocus
        />
      </div>
    </div>
  );
}

export function FieldCardRow({
  field,
  value,
  tone,
  editing,
  onToggleEdit,
  onChange,
  onCommit,
  onConfirm,
  confirmed,
}: {
  field: EditableField;
  value: string;
  tone: FieldTone;
  editing: boolean;
  onToggleEdit: () => void;
  onChange: (v: string) => void;
  onCommit?: (v: string) => void;
  onConfirm?: () => void;
  confirmed?: boolean;
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const showInput = tone === "empty" || tone === "review" || editing;
  const ring = {
    auto: "border-emerald-200 bg-emerald-50/70",
    review: "border-amber-200 bg-amber-50/80",
    empty: "border-rose-200 bg-rose-50/80",
  }[tone];
  const dot = { auto: "🟢", review: "🟡", empty: "🔴" }[tone];

  const commit = () => onCommit?.(value);

  return (
    <li
      className={`rounded-xl border px-3 py-2.5 ${ring}`}
      data-testid={`apply-field-row-${field.id}`}
      data-tone={tone}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-xs font-semibold text-slate-900">
            <span aria-hidden>{dot}</span>
            <span className="truncate">
              {field.label}
              {field.required ? " *" : ""}
            </span>
            {typeof field.confidence === "number" ? (
              <span className="text-[10px] font-medium opacity-60">
                置信度 {Math.round(field.confidence * 100)}%
              </span>
            ) : null}
            {confirmed ? (
              <span className="rounded-full bg-emerald-600 px-1.5 py-0.5 text-[9px] font-bold uppercase text-white">
                已确认
              </span>
            ) : null}
          </div>
          {tone === "review" && !confirmed ? (
            <p className="mt-0.5 text-[10px] text-amber-800">建议核对后确认</p>
          ) : null}
          {tone === "empty" ? (
            <p className="mt-0.5 text-[10px] text-rose-800">需要填写才能提交</p>
          ) : null}
          {field.reason && tone !== "empty" && !showInput ? (
            <p className="mt-0.5 truncate text-[10px] opacity-60">{field.reason}</p>
          ) : null}
        </div>
        {tone === "auto" || (tone === "review" && confirmed) ? (
          <button
            type="button"
            data-testid="apply-field-edit-toggle"
            onClick={onToggleEdit}
            className="shrink-0 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-700 hover:bg-slate-50"
          >
            {editing ? "收起" : "编辑✎"}
          </button>
        ) : null}
        {tone === "review" && !confirmed && onConfirm ? (
          <button
            type="button"
            data-testid="apply-field-confirm"
            onClick={onConfirm}
            className="shrink-0 rounded-lg border border-emerald-300 bg-emerald-600 px-2 py-1 text-[10px] font-semibold text-white hover:bg-emerald-700"
          >
            ✓ 确认无误
          </button>
        ) : null}
      </div>

      {!showInput ? (
        <p className="mt-1 truncate text-xs text-slate-700" title={value}>
          {value || "—"}
        </p>
      ) : field.longText ? (
        <button
          type="button"
          data-testid="apply-field-open-longtext"
          onClick={() => setModalOpen(true)}
          className="mt-2 w-full rounded-lg border border-dashed border-slate-300 bg-white px-3 py-2 text-left text-xs text-slate-600 hover:border-slate-400"
        >
          {value ? (
            <span className="line-clamp-2 text-slate-800">{value}</span>
          ) : (
            <span className="text-slate-400">点击此处输入…</span>
          )}
        </button>
      ) : BOOLISH.has(field.profileKey.toLowerCase()) ? (
        <select
          data-testid="apply-field-input"
          className="mt-2 h-8 w-full rounded-lg border border-slate-200 bg-white px-2 text-xs"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            onCommit?.(e.target.value);
          }}
        >
          <option value="">选择…</option>
          <option value="Yes">Yes</option>
          <option value="No">No</option>
        </select>
      ) : (
        <input
          data-testid="apply-field-input"
          className="mt-2 h-8 w-full rounded-lg border border-slate-200 bg-white px-2 text-xs"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={commit}
          placeholder="点击此处输入…"
        />
      )}

      <LongTextModal
        open={modalOpen}
        label={field.label}
        value={value}
        onChange={onChange}
        onClose={() => {
          setModalOpen(false);
          commit();
        }}
      />
    </li>
  );
}

export function EditableTierPanel({
  title,
  tone,
  items,
  values,
  editingIds,
  confirmedIds,
  testId,
  onToggleEdit,
  onChange,
  onCommit,
  onConfirm,
}: {
  title: string;
  tone: FieldTone;
  items: EditableField[];
  values: Record<string, string>;
  editingIds: Set<string>;
  confirmedIds: Set<string>;
  testId: string;
  onToggleEdit: (id: string) => void;
  onChange: (id: string, value: string, field: EditableField) => void;
  onCommit: (id: string, value: string, field: EditableField) => void;
  onConfirm: (id: string) => void;
}) {
  const styles = {
    auto: "border-emerald-200 bg-emerald-50/80 text-emerald-950",
    review: "border-amber-200 bg-amber-50/80 text-amber-950",
    empty: "border-rose-200 bg-rose-50/80 text-rose-950",
  }[tone];
  const badge = {
    auto: "bg-emerald-600 text-white",
    review: "bg-amber-500 text-white",
    empty: "bg-rose-600 text-white",
  }[tone];

  return (
    <div className={`rounded-2xl border px-3 py-3 ${styles}`} data-testid={testId}>
      <div className="mb-2 flex items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${badge}`}>{title}</span>
        <span className="text-[11px] opacity-70">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-[11px] opacity-60">None</p>
      ) : (
        <ul className="max-h-80 space-y-2 overflow-y-auto">
          {items.map((f) => {
            const effectiveTone: FieldTone =
              tone === "review" && confirmedIds.has(f.id) ? "auto" : tone;
            return (
              <FieldCardRow
                key={f.id}
                field={f}
                value={values[f.id] ?? f.value}
                tone={effectiveTone}
                editing={editingIds.has(f.id)}
                confirmed={confirmedIds.has(f.id)}
                onToggleEdit={() => onToggleEdit(f.id)}
                onChange={(v) => onChange(f.id, v, f)}
                onCommit={(v) => onCommit(f.id, v, f)}
                onConfirm={tone === "review" ? () => onConfirm(f.id) : undefined}
              />
            );
          })}
        </ul>
      )}
    </div>
  );
}

const PAGE_SIZE = 5;

export function GroupedFieldList({
  fields,
  values,
  editingIds,
  confirmedIds,
  onToggleEdit,
  onChange,
  onCommit,
  onConfirm,
  defaultOpen = "basics",
}: {
  fields: EditableField[];
  values: Record<string, string>;
  editingIds: Set<string>;
  confirmedIds: Set<string>;
  onToggleEdit: (id: string) => void;
  onChange: (id: string, value: string, field: EditableField) => void;
  onCommit: (id: string, value: string, field: EditableField) => void;
  onConfirm: (id: string) => void;
  defaultOpen?: string;
}) {
  const groups = useMemo(() => groupFields(fields), [fields]);
  const [openId, setOpenId] = useState(defaultOpen);
  const [pages, setPages] = useState<Record<string, number>>({});

  if (fields.length === 0) {
    return (
      <p className="px-4 py-6 text-center text-xs text-slate-400" data-testid="apply-review-fields-empty">
        No fields in this step
      </p>
    );
  }

  return (
    <div className="space-y-2" data-testid="apply-review-fields">
      {groups.map((g) => {
        const open = openId === g.id || groups.length === 1;
        const page = pages[g.id] || 0;
        const needsPaging = g.items.length > PAGE_SIZE;
        const slice = needsPaging
          ? g.items.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE)
          : g.items;
        const pageCount = Math.max(1, Math.ceil(g.items.length / PAGE_SIZE));
        return (
          <div
            key={g.id}
            className="overflow-hidden rounded-2xl border border-slate-200 bg-white"
            data-testid={`apply-field-group-${g.id}`}
          >
            <button
              type="button"
              className="flex w-full items-center justify-between px-4 py-2.5 text-left text-xs font-bold text-slate-800 hover:bg-slate-50"
              onClick={() => setOpenId(open ? "" : g.id)}
              data-testid={`apply-field-group-toggle-${g.id}`}
            >
              <span>
                {g.label}
                <span className="ml-2 font-medium text-slate-400">{g.items.length}</span>
              </span>
              <span className="text-slate-400">{open ? "▾" : "▸"}</span>
            </button>
            {open ? (
              <div className="space-y-2 border-t border-slate-100 px-3 py-3">
                <ul className="space-y-2">
                  {slice.map((f) => {
                    const tone: FieldTone =
                      confirmedIds.has(f.id) && f.tone === "review" ? "auto" : f.tone;
                    return (
                      <FieldCardRow
                        key={f.id}
                        field={f}
                        value={values[f.id] ?? f.value}
                        tone={tone}
                        editing={editingIds.has(f.id)}
                        confirmed={confirmedIds.has(f.id)}
                        onToggleEdit={() => onToggleEdit(f.id)}
                        onChange={(v) => onChange(f.id, v, f)}
                        onCommit={(v) => onCommit(f.id, v, f)}
                        onConfirm={f.tone === "review" ? () => onConfirm(f.id) : undefined}
                      />
                    );
                  })}
                </ul>
                {needsPaging ? (
                  <div
                    className="flex items-center justify-between pt-1 text-[11px]"
                    data-testid={`apply-field-group-pager-${g.id}`}
                  >
                    <button
                      type="button"
                      disabled={page <= 0}
                      onClick={() => setPages((p) => ({ ...p, [g.id]: page - 1 }))}
                      className="rounded-lg border border-slate-200 px-2 py-1 font-semibold disabled:opacity-40"
                    >
                      ← 上一页
                    </button>
                    <span className="text-slate-500">
                      {page + 1} / {pageCount}
                    </span>
                    <button
                      type="button"
                      disabled={page >= pageCount - 1}
                      onClick={() => setPages((p) => ({ ...p, [g.id]: page + 1 }))}
                      className="rounded-lg border border-slate-200 px-2 py-1 font-semibold disabled:opacity-40"
                    >
                      下一页 →
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function PersistToast({
  label,
  value,
  onSave,
  onSessionOnly,
}: {
  label: string;
  value: string;
  onSave: () => void;
  onSessionOnly: () => void;
}) {
  return (
    <div
      className="fixed bottom-4 left-1/2 z-50 w-[min(92vw,420px)] -translate-x-1/2 rounded-2xl border border-slate-200 bg-white p-3 shadow-lg"
      data-testid="apply-persist-toast"
      role="status"
    >
      <p className="text-xs text-slate-800">
        已填写 <span className="font-semibold">{label}</span>
        {value ? `: ${value.slice(0, 48)}${value.length > 48 ? "…" : ""}` : ""}。是否沉淀回 Profile，下次申请自动带入？
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="apply-persist-save"
          onClick={onSave}
          className="rounded-lg bg-emerald-700 px-3 py-1.5 text-[11px] font-semibold text-white"
        >
          ✓ 好的，保存到 Profile
        </button>
        <button
          type="button"
          data-testid="apply-persist-session-only"
          onClick={onSessionOnly}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] font-semibold text-slate-700"
        >
          仅本次使用
        </button>
      </div>
    </div>
  );
}
