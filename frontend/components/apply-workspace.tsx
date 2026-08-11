"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import AppTopNav from "@/components/app-top-nav";
import FlowStepper from "@/components/flow-stepper";
import {
  EditableTierPanel,
  GroupedFieldList,
  PersistToast,
  ScanBanner,
  filledRowToEditable,
  libraryValueFromInput,
  mergeApplyPatch,
  planItemToEditable,
  toLibraryApplyKey,
  type EditableField,
  type FieldTone,
} from "@/components/apply-field-editor";
import {
  confirmApplySubmit,
  confirmVersion,
  exportVersion,
  getApply,
  getCandidateLibrary,
  getVersion,
  startApply,
  updateCandidateLibrary,
  type FillPlanItem,
  type StartApplyResponse,
} from "@/lib/api";
import { isLivePostingUrl, pickOpenablePostingUrl } from "@/lib/posting-url";

type ReviewStep = "profile" | "ats" | "resume" | "pause";

const REVIEW_STEPS: { id: ReviewStep; label: string; hint: string }[] = [
  { id: "profile", label: "1. Profile", hint: "Name, email, phone, location" },
  { id: "ats", label: "2. ATS fields", hint: "Mapped form fields" },
  { id: "resume", label: "3. Resume", hint: "Upload path / file" },
  { id: "pause", label: "4. Pause", hint: "You confirm Submit" },
];

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

interface ApplyWorkspaceProps {
  userId: string;
  versionId?: string;
  jobId?: string;
  company?: string;
  position?: string;
  sourceUrl?: string;
  initialFinalPath?: string;
  initialApplyId?: string;
  initialSessionId?: string;
  displayName?: string;
  onLogout?: () => void;
}

function applyStorageKey(versionId: string) {
  return `resume-agent-apply:${versionId}`;
}

export default function ApplyWorkspace({
  userId,
  versionId: initialVersionId,
  jobId,
  company: initialCompany,
  position: initialPosition,
  sourceUrl: initialSourceUrl,
  initialFinalPath,
  initialApplyId,
  initialSessionId,
  displayName,
  onLogout,
}: ApplyWorkspaceProps) {
  const [versionId, setVersionId] = useState(initialVersionId || "");
  const [sessionId, setSessionId] = useState(initialSessionId || "");
  const [confirmed, setConfirmed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** Which mode card is mid-flight — drives label + keeps the other card clickable feedback clear. */
  const [busyMode, setBusyMode] = useState<"manual" | "auto" | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [company, setCompany] = useState(initialCompany || "");
  const [position, setPosition] = useState(initialPosition || "");
  const [finalPath, setFinalPath] = useState<string | undefined>(initialFinalPath || undefined);
  const [result, setResult] = useState<StartApplyResponse | null>(null);
  const [reviewStep, setReviewStep] = useState<ReviewStep>("profile");
  const [exporting, setExporting] = useState<"pdf" | "docx" | null>(null);
  const [confirmSubmitBusy, setConfirmSubmitBusy] = useState(false);
  const [humanReviewed, setHumanReviewed] = useState(false);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [editingIds, setEditingIds] = useState<Set<string>>(() => new Set());
  const [confirmedIds, setConfirmedIds] = useState<Set<string>>(() => new Set());
  const [scannedAt, setScannedAt] = useState<Date | null>(null);
  const [persistPrompt, setPersistPrompt] = useState<{
    id: string;
    label: string;
    value: string;
    libraryKey: string;
  } | null>(null);
  const [persistNote, setPersistNote] = useState<string | null>(null);

  const tailorHref = useMemo(() => {
    const q = new URLSearchParams({ view: "resume", step: "tailor" });
    if (jobId) q.set("jobId", jobId);
    if (sessionId) q.set("sessionId", sessionId);
    if (versionId) q.set("versionId", versionId);
    return `/?${q.toString()}`;
  }, [jobId, sessionId, versionId]);

  const outreachHref = useMemo(() => {
    const q = new URLSearchParams();
    if (jobId) q.set("jobId", jobId);
    if (company) q.set("company", company);
    if (position) q.set("position", position);
    if (versionId) q.set("versionId", versionId);
    if (sessionId) q.set("sessionId", sessionId);
    return `/outreach?${q.toString()}`;
  }, [jobId, company, position, versionId, sessionId]);

  const persistApplyUrl = useCallback(
    (applyId: string) => {
      if (typeof window === "undefined" || !versionId) return;
      try {
        const url = new URL(window.location.href);
        url.searchParams.set("versionId", versionId);
        url.searchParams.set("applyId", applyId);
        if (sessionId) url.searchParams.set("sessionId", sessionId);
        if (finalPath) url.searchParams.set("finalPath", finalPath);
        if (jobId) url.searchParams.set("jobId", jobId);
        if (company) url.searchParams.set("company", company);
        if (position) url.searchParams.set("position", position);
        if (initialSourceUrl) url.searchParams.set("sourceUrl", initialSourceUrl);
        window.history.replaceState({}, "", `${url.pathname}?${url.searchParams.toString()}`);
        sessionStorage.setItem(
          applyStorageKey(versionId),
          JSON.stringify({ applyId, finalPath, sessionId, company, position })
        );
      } catch {
        /* ignore */
      }
    },
    [versionId, sessionId, finalPath, jobId, company, position, initialSourceUrl]
  );

  const refreshVersion = useCallback(async () => {
    if (!versionId) {
      setLoadError("No resume version. Go back to Tailor, Confirm a draft, then open Apply.");
      return;
    }
    setLoadError(null);
    try {
      const v = await getVersion(versionId, userId);
      setConfirmed(!!v.is_confirmed);
      if (v.session_id) setSessionId(v.session_id);
      const resume = (v.full_resume || {}) as Record<string, unknown>;
      if (!company && typeof resume.company === "string") setCompany(resume.company);
      if (!position && typeof resume.target_title === "string") setPosition(resume.target_title);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load version");
    }
  }, [versionId, userId, company, position]);

  useEffect(() => {
    void refreshVersion();
  }, [refreshVersion]);

  useEffect(() => {
    if (initialVersionId) setVersionId(initialVersionId);
  }, [initialVersionId]);

  // Restore prior apply session (URL / sessionStorage) so refresh & back don't wipe the review.
  useEffect(() => {
    if (!versionId || result) return;
    let cancelled = false;
    const run = async () => {
      let applyId = initialApplyId || "";
      if (!applyId) {
        try {
          const raw = sessionStorage.getItem(applyStorageKey(versionId));
          if (raw) {
            const parsed = JSON.parse(raw) as { applyId?: string; finalPath?: string; sessionId?: string };
            applyId = parsed.applyId || "";
            if (!finalPath && parsed.finalPath) setFinalPath(parsed.finalPath);
            if (!sessionId && parsed.sessionId) setSessionId(parsed.sessionId);
          }
        } catch {
          /* ignore */
        }
      }
      if (!applyId) return;
      try {
        const res = await getApply(applyId);
        if (cancelled) return;
        setResult(res);
        setScannedAt(new Date());
        if (res.final_path) setFinalPath(res.final_path);
        if (res.paused_before_submit) setReviewStep("pause");
      } catch {
        /* stale apply id */
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [versionId, initialApplyId, result, finalPath, sessionId]);

  const handleConfirm = async () => {
    if (!versionId) return;
    setConfirming(true);
    setConfirmError(null);
    try {
      const res = await confirmVersion(versionId, userId);
      setConfirmed(true);
      if (res.final_path) setFinalPath(res.final_path);
      if (res.company) setCompany(res.company);
      if (res.position) setPosition(res.position);
    } catch (err) {
      setConfirmError(err instanceof Error ? err.message : "Confirm failed");
    } finally {
      setConfirming(false);
    }
  };

  const handleStart = async (mode: "manual" | "auto") => {
    if (!versionId) {
      setStartError("缺少 versionId — 请回 Tailor Confirm 后再进 Apply。");
      return;
    }
    if (busy) return;
    setBusy(true);
    setBusyMode(mode);
    setStartError(null);
    // Auto path may scan ATS with Playwright — cap wait so UI never looks "frozen forever".
    const timeoutMs = mode === "auto" ? 45_000 : 30_000;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await startApply(versionId, userId, mode, {
        company: company || undefined,
        position: position || undefined,
        final_path: finalPath,
        job_id: jobId,
        source_url: initialSourceUrl,
        signal: controller.signal,
      });
      setResult(res);
      setConfirmed(true);
      setHumanReviewed(false);
      setConfirmedIds(new Set());
      setEditingIds(new Set());
      setFieldValues({});
      setScannedAt(new Date());
      setPersistPrompt(null);
      if (res.final_path) setFinalPath(res.final_path);
      if (res.apply_id) persistApplyUrl(res.apply_id);
      if (mode === "auto") setReviewStep("profile");
      // Manual + Auto: open usable posting (ATS or board). Skip dead Workday roots.
      const openUrl = pickOpenablePostingUrl(res.source_url, res.board_url);
      if (openUrl) {
        window.open(openUrl, "_blank", "noopener,noreferrer");
      }
      requestAnimationFrame(() => {
        document.querySelector("[data-testid=apply-result-section]")?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    } catch (err) {
      const aborted =
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && /abort/i.test(err.message));
      const msg = aborted
        ? mode === "auto"
          ? "Auto apply 超时。请重试，或先用 Manual apply 打开官网。"
          : "Manual apply 请求超时，请确认后端 :8000 在跑后重试。"
        : err instanceof Error
          ? err.message
          : "Apply failed";
      setStartError(msg);
      setResult({
        apply_id: "",
        mode,
        status: "error",
        submitted: false,
        paused_before_submit: false,
        message: msg,
        filled_fields: [],
      });
    } finally {
      window.clearTimeout(timer);
      setBusy(false);
      setBusyMode(null);
    }
  };

  const handleExport = async (format: "pdf" | "docx") => {
    if (!versionId || exporting) return;
    setExporting(format);
    try {
      const blob = await exportVersion(versionId, userId, format);
      downloadBlob(blob, `resume-apply.${format}`);
    } catch {
      alert("Export failed — confirm the version first.");
    } finally {
      setExporting(null);
    }
  };

  const openableUrl = pickOpenablePostingUrl(result?.source_url || initialSourceUrl, result?.board_url) || "";
  const sourceUrl = openableUrl;

  const handleConfirmSubmit = async () => {
    if (!result?.apply_id || confirmSubmitBusy) return;
    setConfirmSubmitBusy(true);
    try {
      const res = await confirmApplySubmit(result.apply_id, userId, true);
      setResult((prev) =>
        prev
          ? {
              ...prev,
              status: res.status,
              submitted: res.submitted,
              paused_before_submit: res.paused_before_submit,
              message: res.message,
            }
          : prev
      );
      persistApplyUrl(result.apply_id);
      setReviewStep("pause");
      const url = pickOpenablePostingUrl(res.source_url || sourceUrl, result?.board_url);
      if (url) {
        window.open(url, "_blank", "noopener,noreferrer");
      }
      requestAnimationFrame(() => {
        document.querySelector("[data-testid=submit-confirmed]")?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Confirm submit failed";
      setResult((prev) =>
        prev ? { ...prev, message: `${prev.message || ""}\nConfirm error: ${msg}`.trim() } : prev
      );
    } finally {
      setConfirmSubmitBusy(false);
    }
  };
  const fields = result?.filled_fields || [];
  const profileFields = fields.filter((f) => !String(f.field).startsWith("ats:"));
  const atsFields = fields.filter((f) => String(f.field).startsWith("ats:"));
  const resumeField = profileFields.find((f) => f.field === "resume_upload");
  const pauseField = profileFields.find((f) => f.field === "submit_button");

  const fillPlan = useMemo(() => {
    const fromApi = result?.fill_plan || [];
    if (fromApi.length > 0) return fromApi;
    // Fallback: derive tiers from filled_fields when API omitted fill_plan
    return (result?.filled_fields || [])
      .filter((f) => String(f.field).startsWith("ats:") || f.field === "resume_upload")
      .map((f, i) => {
        const tier = String(f.tier || (f.value && !String(f.value).startsWith("(") ? "review" : "empty"));
        return {
          field_id: `fe-${i}`,
          label: String(f.field).replace(/^ats:/, ""),
          profile_key: f.profile_key,
          value: f.value || "",
          confidence: f.confidence,
          needs_review: f.needs_review ?? tier !== "auto",
          action: f.action || (f.value ? "fill" : "leave_empty"),
          reason: f.note,
          tier,
        } as FillPlanItem;
      });
  }, [result?.fill_plan, result?.filled_fields]);

  const editablePlan = useMemo(
    () => fillPlan.map((m, i) => planItemToEditable(m, i)),
    [fillPlan]
  );

  const tierBuckets = useMemo(() => {
    const auto: EditableField[] = [];
    const review: EditableField[] = [];
    const empty: EditableField[] = [];
    for (const m of editablePlan) {
      if (confirmedIds.has(m.id) && m.tone === "review") {
        auto.push({ ...m, tone: "auto" });
        continue;
      }
      const t = m.tone as FieldTone;
      if (t === "auto") auto.push(m);
      else if (t === "review") review.push(m);
      else empty.push(m);
    }
    return { auto, review, empty };
  }, [editablePlan, confirmedIds]);

  const needsReviewGate =
    Boolean(result?.requires_human_review) ||
    tierBuckets.review.length > 0 ||
    tierBuckets.empty.some((f) => !(fieldValues[f.id] ?? f.value).trim()) ||
    Boolean(result?.paused_before_submit);

  const visibleEditable = useMemo(() => {
    if (reviewStep === "profile") {
      return profileFields
        .filter((f) => f.field !== "resume_upload" && f.field !== "submit_button")
        .map(filledRowToEditable);
    }
    if (reviewStep === "ats") return atsFields.map(filledRowToEditable);
    if (reviewStep === "resume") return resumeField ? [filledRowToEditable(resumeField)] : [];
    return pauseField
      ? [filledRowToEditable(pauseField)]
      : [
          filledRowToEditable({
            field: "submit_button",
            value: "NOT_CLICKED",
            note: "hard stop",
            tier: "empty",
          }),
        ];
  }, [reviewStep, profileFields, atsFields, resumeField, pauseField]);

  const toggleEdit = useCallback((id: string) => {
    setEditingIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const confirmField = useCallback((id: string) => {
    setConfirmedIds((prev) => new Set(prev).add(id));
    setEditingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  const handleFieldChange = useCallback((id: string, value: string, field: EditableField) => {
    setFieldValues((prev) => ({ ...prev, [id]: value }));
  }, []);

  const handleFieldCommit = useCallback((id: string, value: string, field: EditableField) => {
    const libraryKey = toLibraryApplyKey(field.profileKey || field.label);
    const wasEmpty = !(field.value || "").trim();
    const trimmed = value.trim();
    if (libraryKey && trimmed && (wasEmpty || field.tone === "empty")) {
      setPersistPrompt({
        id,
        label: field.label,
        value: trimmed,
        libraryKey,
      });
    }
  }, []);

  const handlePersistSave = useCallback(async () => {
    if (!persistPrompt) return;
    try {
      const lib = await getCandidateLibrary(userId);
      const apply = { ...(lib.apply || {}) } as Record<string, unknown>;
      const next = mergeApplyPatch(
        apply,
        persistPrompt.libraryKey,
        libraryValueFromInput(persistPrompt.libraryKey, persistPrompt.value)
      );
      await updateCandidateLibrary(userId, { apply: next });
      setPersistNote(
        `已保存 "${persistPrompt.label}: ${persistPrompt.value.slice(0, 40)}" 到 Profile，下次申请会自动带入`
      );
    } catch (err) {
      setPersistNote(err instanceof Error ? err.message : "保存 Profile 失败");
    } finally {
      setPersistPrompt(null);
    }
  }, [persistPrompt, userId]);

  const fillUrl =
    (result?.browser_fill?.fill_url as string | undefined) ||
    (result?.browser_fill?.original_url as string | undefined) ||
    sourceUrl;
  const shotPath =
    typeof result?.browser_fill?.screenshot_path === "string"
      ? result.browser_fill.screenshot_path
      : null;

  const scanTotal = editablePlan.length || visibleEditable.length;
  const scanAuto = tierBuckets.auto.length;
  const scanReview = tierBuckets.review.length;
  const scanEmpty = tierBuckets.empty.length;

  return (
    <div className="min-h-screen bg-[#f4f6f4] text-slate-950" data-testid="apply-workspace-page">
      <AppTopNav active="tailor" displayName={displayName} onLogout={onLogout} />
      <header className="border-b border-slate-200 bg-white/95">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <a
              href={tailorHref}
              className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              data-testid="apply-back-tailor"
            >
              ← Tailor / Confirm
            </a>
            <div>
              <h1 className="text-sm font-bold">Apply workspace</h1>
            </div>
            {(company || position) && (
              <span className="truncate rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600">
                {[company, position].filter(Boolean).join(" · ")}
              </span>
            )}
          </div>
          <FlowStepper
            current="apply"
            hrefs={{
              jobs: "/jobs",
              tailor: tailorHref,
              outreach: outreachHref,
            }}
          />
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-4 px-4 py-6">
        {loadError ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900" data-testid="apply-load-error">
            {loadError}{" "}
            <a href={tailorHref} className="font-semibold underline">
              Open Tailor
            </a>
          </div>
        ) : null}

        {/* Gate: Confirm */}
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="apply-confirm-gate">
          <h2 className="text-lg font-bold tracking-tight">1. Confirm tailored resume</h2>
          <p className="mt-1 text-sm text-slate-500">
            Apply is locked until this version is confirmed and saved under{" "}
            <code className="rounded bg-slate-100 px-1 text-[11px]">data/final_resumes/{"{Company}_{Position}"}/</code>
            {" "}(PDF + DOCX). Intermediate drafts stay as markdown in the DB until Confirm.
          </p>
          {finalPath ? (
            <p className="mt-2 break-all text-[11px] text-emerald-800" data-testid="apply-final-path-hint">
              Final folder: {finalPath}
            </p>
          ) : null}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            {confirmed ? (
              <span
                className="rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-800 ring-1 ring-emerald-200"
                data-testid="apply-confirmed-badge"
              >
                Confirmed ✓
              </span>
            ) : (
              <button
                type="button"
                data-testid="apply-page-confirm"
                disabled={!versionId || confirming}
                onClick={() => void handleConfirm()}
                className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
              >
                {confirming ? "Confirming…" : "Confirm this resume"}
              </button>
            )}
            <button
              type="button"
              disabled={!confirmed || !!exporting}
              onClick={() => void handleExport("docx")}
              className="rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-semibold text-slate-700 disabled:opacity-40"
              data-testid="apply-download-docx"
            >
              Download DOCX
            </button>
            <button
              type="button"
              disabled={!confirmed || !!exporting}
              onClick={() => void handleExport("pdf")}
              className="rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-semibold text-slate-700 disabled:opacity-40"
              data-testid="apply-download-pdf"
            >
              Download PDF
            </button>
            {versionId ? (
              <span className="text-[11px] text-slate-400">version {versionId.slice(0, 8)}…</span>
            ) : null}
          </div>
          {confirmError ? (
            <p className="mt-3 text-xs font-medium text-rose-700" data-testid="apply-confirm-error">
              {confirmError}
            </p>
          ) : null}
        </section>

        {/* Mode pick — these cards ARE the enter actions (no separate 进去 button). */}
        <section className="rounded-3xl border border-emerald-200 bg-white p-6 shadow-sm" data-testid="apply-mode-section">
          <h2 className="text-lg font-bold tracking-tight">2. How do you want to apply?</h2>
          <p className="mt-1 text-sm text-slate-500">
            点下面任一卡片即可进入。Manual 打开官网；Auto 映射字段且{" "}
            <strong>never clicks Submit</strong>。
          </p>
          <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-amber-800">
            Safety: Auto-apply never clicks Submit
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              data-testid="apply-manual"
              disabled={!confirmed || busy}
              aria-busy={busyMode === "manual"}
              onClick={() => void handleStart("manual")}
              className="rounded-2xl border border-slate-200 bg-white px-5 py-4 text-left hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div className="text-sm font-bold text-slate-950">
                {busyMode === "manual" ? "正在进入 Manual…" : "进入 Manual apply"}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Open official site · download resume · you fill & submit
              </div>
            </button>
            <button
              type="button"
              data-testid="apply-auto"
              disabled={!confirmed || busy}
              aria-busy={busyMode === "auto"}
              onClick={() => void handleStart("auto")}
              className="rounded-2xl bg-emerald-600 px-5 py-4 text-left text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div className="text-sm font-bold">
                {busyMode === "auto" ? "正在扫描 ATS / 进入中…" : "进入 Auto apply (safe)"}
              </div>
              <div className="mt-1 text-xs text-emerald-50/90">
                Prefill checklist · pause before Submit · you review
              </div>
            </button>
          </div>
          {busy ? (
            <p
              className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-900 ring-1 ring-amber-200"
              data-testid="apply-busy-hint"
            >
              {busyMode === "auto"
                ? "Auto apply：单次打开申请页并预填（通常十几秒；超时约 45 秒）。完成后展开第 3 步 Review。"
                : "正在打开 Manual apply，请稍候…"}
            </p>
          ) : null}
          {startError ? (
            <p className="mt-3 text-xs font-medium text-rose-700" data-testid="apply-start-error">
              {startError}
            </p>
          ) : null}
          {!confirmed ? (
            <p className="mt-3 text-xs font-semibold text-amber-800" data-testid="apply-need-confirm-hint">
              Confirm the resume above first — Manual / Auto stay locked until then.
            </p>
          ) : null}
        </section>

        {/* Official URL + status */}
        {result ? (
          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="apply-result-section">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold tracking-tight">3. Review before you submit</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Flip through what we prepared. Open the official form to verify. You click Submit.
                </p>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${
                  result.paused_before_submit
                    ? "bg-amber-50 text-amber-900 ring-amber-200"
                    : result.status === "error"
                      ? "bg-rose-50 text-rose-800 ring-rose-200"
                      : "bg-emerald-50 text-emerald-800 ring-emerald-200"
                }`}
                data-testid="apply-status"
              >
                {result.status}
              </span>
            </div>

            {result.message ? (
              <p className="mt-3 text-xs text-slate-600" data-testid="apply-message">
                {result.message}
              </p>
            ) : null}

            <div className="mt-4 flex flex-wrap gap-2">
              {isLivePostingUrl(sourceUrl) ? (
                <a
                  href={sourceUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-semibold text-white hover:bg-slate-800"
                  data-testid="apply-open-official"
                >
                  Open official posting
                </a>
              ) : (
                <span className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-2.5 text-xs text-slate-500">
                  No live posting URL on file
                </span>
              )}
              {fillUrl && isLivePostingUrl(fillUrl) && fillUrl !== sourceUrl ? (
                <a
                  href={fillUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-semibold text-slate-700"
                  data-testid="apply-open-fill-url"
                >
                  Open filled / apply form
                </a>
              ) : null}
              {result.ats_type ? (
                <span className="rounded-full bg-slate-100 px-3 py-2 text-[11px] font-semibold text-slate-600" data-testid="apply-ats-type">
                  ATS: {result.ats_type}
                </span>
              ) : null}
            </div>

            {result.mode === "auto" && result.status !== "error" || result.paused_before_submit ? (
              <>
                {(scanTotal > 0 || editablePlan.length > 0) ? (
                  <div className="mt-5">
                    <ScanBanner
                      total={scanTotal || editablePlan.length}
                      auto={scanAuto}
                      review={scanReview}
                      empty={scanEmpty}
                      scannedAt={scannedAt}
                      mapProvider={result.map_provider}
                      atsType={result.ats_type}
                      onRescan={() => void handleStart("auto")}
                      rescanBusy={busy}
                    />
                  </div>
                ) : null}

                <div className="mt-4 flex flex-wrap gap-1.5" data-testid="apply-review-steps">
                  {REVIEW_STEPS.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      data-testid={`apply-review-step-${s.id}`}
                      onClick={() => setReviewStep(s.id)}
                      className={`rounded-full px-3 py-1.5 text-[11px] font-semibold ring-1 ${
                        reviewStep === s.id
                          ? "bg-emerald-600 text-white ring-emerald-600"
                          : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                      }`}
                      title={s.hint}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>

                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    data-testid="apply-review-prev"
                    disabled={REVIEW_STEPS.findIndex((s) => s.id === reviewStep) <= 0}
                    onClick={() => {
                      const i = REVIEW_STEPS.findIndex((s) => s.id === reviewStep);
                      if (i > 0) setReviewStep(REVIEW_STEPS[i - 1].id);
                    }}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] font-semibold disabled:opacity-40"
                  >
                    ← Previous
                  </button>
                  <button
                    type="button"
                    data-testid="apply-review-next"
                    disabled={REVIEW_STEPS.findIndex((s) => s.id === reviewStep) >= REVIEW_STEPS.length - 1}
                    onClick={() => {
                      const i = REVIEW_STEPS.findIndex((s) => s.id === reviewStep);
                      if (i < REVIEW_STEPS.length - 1) setReviewStep(REVIEW_STEPS[i + 1].id);
                    }}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-[11px] font-semibold disabled:opacity-40"
                  >
                    Next →
                  </button>
                </div>

                <div className="mt-3">
                  {reviewStep === "profile" || reviewStep === "ats" ? (
                    <GroupedFieldList
                      fields={visibleEditable}
                      values={fieldValues}
                      editingIds={editingIds}
                      confirmedIds={confirmedIds}
                      onToggleEdit={toggleEdit}
                      onChange={handleFieldChange}
                      onCommit={handleFieldCommit}
                      onConfirm={confirmField}
                      defaultOpen={reviewStep === "profile" ? "basics" : "other"}
                    />
                  ) : (
                    <ul
                      className="rounded-2xl border border-slate-100 bg-slate-50/80 text-sm"
                      data-testid="apply-review-fields"
                    >
                      {visibleEditable.length === 0 ? (
                        <li className="px-4 py-6 text-center text-xs text-slate-400">
                          No fields in this step
                        </li>
                      ) : (
                        visibleEditable.map((row) => (
                          <li
                            key={row.id}
                            className="grid grid-cols-[140px_minmax(0,1fr)] gap-3 border-b border-slate-100 px-4 py-2.5 last:border-0"
                          >
                            <span className="text-xs font-semibold text-slate-700">{row.label}</span>
                            <span
                              className="truncate text-xs text-slate-600"
                              title={fieldValues[row.id] ?? row.value}
                            >
                              {(fieldValues[row.id] ?? row.value) || "—"}
                              {row.reason ? (
                                <span className="ml-1 text-amber-700">({row.reason})</span>
                              ) : null}
                            </span>
                          </li>
                        ))
                      )}
                    </ul>
                  )}
                </div>

                {editablePlan.length > 0 ? (
                  <div className="mt-4 space-y-2" data-testid="apply-fill-plan-tiers">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-bold tracking-tight">即将提交的信息清单</h3>
                      <span className="text-[10px] text-slate-500">
                        绿=已自动填（可纠错）· 黄=待核对（默认展开）· 红=未填（直接输入）
                      </span>
                    </div>
                    <div className="grid gap-2 lg:grid-cols-3">
                      <EditableTierPanel
                        title="已自动填"
                        tone="auto"
                        items={tierBuckets.auto}
                        values={fieldValues}
                        editingIds={editingIds}
                        confirmedIds={confirmedIds}
                        testId="fill-tier-auto"
                        onToggleEdit={toggleEdit}
                        onChange={handleFieldChange}
                        onCommit={handleFieldCommit}
                        onConfirm={confirmField}
                      />
                      <EditableTierPanel
                        title="待你核对"
                        tone="review"
                        items={tierBuckets.review}
                        values={fieldValues}
                        editingIds={editingIds}
                        confirmedIds={confirmedIds}
                        testId="fill-tier-review"
                        onToggleEdit={toggleEdit}
                        onChange={handleFieldChange}
                        onCommit={handleFieldCommit}
                        onConfirm={confirmField}
                      />
                      <EditableTierPanel
                        title="未填"
                        tone="empty"
                        items={tierBuckets.empty}
                        values={fieldValues}
                        editingIds={editingIds}
                        confirmedIds={confirmedIds}
                        testId="fill-tier-empty"
                        onToggleEdit={toggleEdit}
                        onChange={handleFieldChange}
                        onCommit={handleFieldCommit}
                        onConfirm={confirmField}
                      />
                    </div>
                  </div>
                ) : null}

                {persistNote ? (
                  <p className="mt-2 text-xs text-emerald-700" data-testid="apply-persist-note">
                    {persistNote}
                  </p>
                ) : null}

                {shotPath ? (
                  <p className="mt-2 text-[11px] text-slate-500" data-testid="apply-screenshot-path">
                    Browser screenshot: {shotPath}
                  </p>
                ) : null}

                {result.paused_before_submit ? (
                  <div
                    className="mt-4 rounded-2xl bg-amber-50 px-4 py-3 text-xs font-semibold text-amber-950 ring-1 ring-amber-200"
                    data-testid="paused-before-submit"
                  >
                    Paused before Submit — nothing was sent. Review the green / amber / red lists, then open the
                    official form yourself.
                    {needsReviewGate ? (
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
                        <span>我已检查 — 已核对自动填写与未填项，准备在官网亲手 Submit</span>
                      </label>
                    ) : null}
                    {humanReviewed || !needsReviewGate ? (
                      <button
                        type="button"
                        data-testid="confirm-submit-btn"
                        disabled={confirmSubmitBusy || !result.apply_id}
                        onClick={() => void handleConfirmSubmit()}
                        className="mt-3 block w-full rounded-xl bg-slate-900 px-3 py-2.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
                      >
                        {confirmSubmitBusy
                          ? "Recording confirm…"
                          : "打开官网亲手 Submit"}
                      </button>
                    ) : (
                      <p
                        className="mt-3 rounded-xl border border-dashed border-amber-300 bg-white/60 px-3 py-2 text-[11px] font-medium text-amber-900"
                        data-testid="confirm-submit-locked"
                      >
                        勾选「我已检查」后才会显示打开官网按钮。
                      </p>
                    )}
                  </div>
                ) : null}
                {result.status === "submitted_by_user_confirm" ? (
                  <div
                    className="mt-4 space-y-3 rounded-2xl bg-emerald-50 px-4 py-4 text-xs font-semibold text-emerald-950 ring-1 ring-emerald-200"
                    data-testid="submit-confirmed"
                  >
                    <p>
                      已记录你的确认。官网标签页应已打开 — 在雇主站点亲手 Submit。本页不会清空；定稿简历仍在磁盘上。
                    </p>
                    <div
                      className="rounded-xl border border-emerald-200/80 bg-white/80 px-3 py-2.5 font-normal text-emerald-950"
                      data-testid="final-resume-path"
                    >
                      <div className="text-[10px] font-bold uppercase tracking-wide text-emerald-700">
                        定稿文件夹（Company_Position）
                      </div>
                      <div className="mt-1 break-all text-[11px]" title={finalPath || result.final_path || ""}>
                        {finalPath || result.final_path || "Confirm 后写入 data/final_resumes/{Company}_{Position}/"}
                      </div>
                      <p className="mt-1 text-[10px] text-emerald-800/80">
                        内含 resume.pdf / resume.docx（及同名定稿）。中间稿在库里用 markdown，未 Confirm 不写此目录。
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {isLivePostingUrl(sourceUrl) ? (
                        <a
                          href={sourceUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-xl bg-slate-900 px-3 py-2 text-[11px] font-semibold text-white"
                          data-testid="reopen-official-after-confirm"
                        >
                          再次打开官网
                        </a>
                      ) : null}
                      <button
                        type="button"
                        disabled={!!exporting}
                        onClick={() => void handleExport("pdf")}
                        className="rounded-xl border border-emerald-300 bg-white px-3 py-2 text-[11px] font-semibold text-emerald-900"
                        data-testid="post-confirm-download-pdf"
                      >
                        下载定稿 PDF
                      </button>
                      <button
                        type="button"
                        disabled={!!exporting}
                        onClick={() => void handleExport("docx")}
                        className="rounded-xl border border-emerald-300 bg-white px-3 py-2 text-[11px] font-semibold text-emerald-900"
                        data-testid="post-confirm-download-docx"
                      >
                        下载定稿 DOCX
                      </button>
                      <a
                        href={tailorHref}
                        className="rounded-xl border border-emerald-300 bg-white px-3 py-2 text-[11px] font-semibold text-emerald-900"
                        data-testid="back-to-tailor-with-version"
                      >
                        ← 回到 Tailor（保留此版本）
                      </a>
                      <a
                        href={outreachHref}
                        className="rounded-xl bg-emerald-700 px-3 py-2 text-[11px] font-semibold text-white"
                        data-testid="goto-outreach-after-apply"
                      >
                        下一步：Outreach →
                      </a>
                    </div>
                  </div>
                ) : null}

                {result.browser_fill ? (
                  <div className="mt-3 rounded-2xl border border-amber-100 bg-amber-50/50 px-4 py-3 text-[11px] text-amber-950" data-testid="browser-fill-result">
                    <div className="font-bold">Browser fill-pause</div>
                    <div className="mt-0.5" data-testid="browser-fill-status">
                      status: {String(result.browser_fill.status || "n/a")} · submitted:{" "}
                      <span data-testid="browser-fill-submitted">
                        {String(result.browser_fill.submitted ?? false)}
                      </span>
                      {result.browser_fill.sandbox ? " · sandbox" : ""}
                    </div>
                    {typeof result.browser_fill.message === "string" ? (
                      <div className="mt-1 opacity-90">{result.browser_fill.message}</div>
                    ) : null}
                  </div>
                ) : null}
              </>
            ) : null}

            {result.mode === "manual" && result.status !== "error" ? (
              <div className="mt-4 rounded-2xl bg-slate-50 px-4 py-3 text-xs text-slate-700" data-testid="manual-apply-guide">
                Manual path: download DOCX/PDF above, open the official posting, attach the resume yourself, and submit when ready.
              </div>
            ) : null}
          </section>
        ) : null}

        <p className="pb-8 text-center text-[11px] text-slate-400">
          Next: after you submit (or skip), open Outreach to find hiring managers.{" "}
          <a href="/queue" className="font-semibold text-emerald-800 underline" data-testid="open-queue-link">
            Batch queue
          </a>{" "}
          supports multiple jobs with per-job Confirm Submit.
        </p>
      </main>

      {persistPrompt ? (
        <PersistToast
          label={persistPrompt.label}
          value={persistPrompt.value}
          onSave={() => void handlePersistSave()}
          onSessionOnly={() => setPersistPrompt(null)}
        />
      ) : null}
    </div>
  );
}
