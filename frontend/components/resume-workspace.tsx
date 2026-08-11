"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { VersionItem, ContentDelta } from "@/lib/api";
import {
  createJdSession,
  analyzeJd,
  workspaceAgentTurn,
  openJobInResumeWorkspace,
  confirmVersion,
  getVersion,
  listVersions,
  exportVersion,
  getVersionPreviewUrl,
  previewVersionPdf,
} from "@/lib/api";
import FlowStepper from "@/components/flow-stepper";
import JdPanel from "@/components/jd-panel";
import WorkspaceChat from "@/components/workspace-chat";
import type { AgentSendResult } from "@/components/workspace-chat";
interface ResumeWorkspaceProps {
  userId: string;
  initialJobId?: string;
  /** Deeplink step: tailor | apply | outreach | confirm | jd */
  initialStep?: string;
  /** Restore a specific tailored version (e.g. back from Apply) */
  initialVersionId?: string;
  initialSessionId?: string;
}

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

const EMPTY_JD_HINT = `Data Analyst role

Paste a full job description (Paste JD above), or open a ranked job.

Requirements:
• SQL and analytical storytelling
• Python or R for data wrangling
• Dashboarding (Tableau / Power BI)
• Clear communication with stakeholders

Preferred:
• Experimentation / A/B testing
• Cloud data warehouse exposure`;

const AUTO_TAILOR_INSTRUCTION =
  "Tailor this resume for the current job description under RESUME_CONSTITUTION.md: no fabrication, evidence-backed bullets only, content-only on the locked master DOCX, fit one page by show/hide. Emphasize matching DA skills from the JD.";

export default function ResumeWorkspace({
  userId,
  initialJobId,
  initialStep,
  initialVersionId,
  initialSessionId,
}: ResumeWorkspaceProps) {
  const [jdText, setJdText] = useState(initialJobId || initialVersionId ? "" : EMPTY_JD_HINT);
  const [showPasteInput, setShowPasteInput] = useState(false);
  const [pasteInput, setPasteInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
  const [activeResume, setActiveResume] = useState<Record<string, unknown> | null>(null);
  const [contentDelta, setContentDelta] = useState<ContentDelta | null>(null);
  const [previewMode, setPreviewMode] = useState<"changes" | "master">("changes");
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [pdfReady, setPdfReady] = useState(false);
  const [pdfPending, setPdfPending] = useState(false);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [rewriting, setRewriting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [exporting, setExporting] = useState<"pdf" | "docx" | "text" | null>(null);
  const initializedRef = useRef(false);
  const [finalSavePath, setFinalSavePath] = useState<string | null>(null);
  const [jobLabel, setJobLabel] = useState<string | null>(null);
  const [bootNotice, setBootNotice] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [confirmedMeta, setConfirmedMeta] = useState<{
    company?: string;
    position?: string;
    final_path?: string;
  } | null>(null);
  const [workspacePanel, setWorkspacePanel] = useState<"jd" | "tailor">(() => {
    const step = (initialStep || "").toLowerCase().trim();
    if (step === "jd") return "jd";
    if (step === "tailor" || step === "confirm" || step === "apply" || step === "outreach") {
      return "tailor";
    }
    return "jd";
  });
  /** Manual stepper focus (so Apply highlight works before version is confirmed). */
  const [focusStep, setFocusStep] = useState<"jd" | "tailor" | "apply" | "outreach" | null>(() => {
    const step = (initialStep || "").toLowerCase().trim();
    if (step === "jd" || step === "tailor" || step === "apply" || step === "outreach") return step;
    return null;
  });

  const pdfPollRef = useRef<number>(0);

  const loadPdfWhenReady = useCallback(
    (versionId: string) => {
      const token = ++pdfPollRef.current;
      setPdfPending(true);
      setPdfReady(false);
      void (async () => {
        for (let i = 0; i < 45; i++) {
          if (token !== pdfPollRef.current) return;
          try {
            const blob = await previewVersionPdf(versionId, userId);
            if (token !== pdfPollRef.current) return;
            if (blob && blob.size >= 4000) {
              const url = URL.createObjectURL(blob);
              setPdfPreviewUrl((prev) => {
                if (prev?.startsWith("blob:")) URL.revokeObjectURL(prev);
                return url;
              });
              setPdfReady(true);
              setPdfPending(false);
              setBootNotice((prev) =>
                prev && prev.includes("master PDF rendering")
                  ? "Master PDF ready — review on the right, then Confirm when it looks good."
                  : prev
              );
              return;
            }
          } catch {
            /* PDF still generating */
          }
          await new Promise((r) => setTimeout(r, 800));
        }
        if (token === pdfPollRef.current) {
          setPdfPending(false);
          setPdfPreviewUrl(getVersionPreviewUrl(versionId, userId));
        }
      })();
    },
    [userId]
  );

  const applyRewriteResult = useCallback(
    (result: {
      did_rewrite?: boolean;
      new_version_id?: string | null;
      version_index?: number | null;
      full_resume?: Record<string, unknown> | null;
      content_delta?: ContentDelta | Record<string, unknown> | null;
    }) => {
      if (!result.did_rewrite || !result.new_version_id) return;
      if (result.full_resume) setActiveResume(result.full_resume);
      if (result.content_delta) {
        setContentDelta(result.content_delta as ContentDelta);
        setPreviewMode("changes");
      }
      setFinalSavePath(null);
      const v: VersionItem = {
        id: result.new_version_id,
        version_index: result.version_index || 0,
        is_confirmed: false,
        created_at: new Date().toISOString(),
      };
      setVersions((prev) => {
        const existing = prev.find((x) => x.id === v.id);
        if (existing) return prev;
        const updated = [...prev, v].sort((a, b) => a.version_index - b.version_index);
        while (updated.length > 4) updated.shift();
        return updated;
      });
      setActiveVersionId(result.new_version_id);
      // HTML first-paint from full_resume; master PDF polls in background.
      setBootNotice((prev) =>
        prev && prev.startsWith("Could not")
          ? prev
          : `Draft v${result.version_index || "?"} ready — changed lines highlighted; master PDF rendering…`
      );
      loadPdfWhenReady(result.new_version_id);
    },
    [loadPdfWhenReady]
  );

  const runAutoTailor = useCallback(
    async (sid: string, label?: string | null) => {
      setRewriting(true);
      try {
        const result = await workspaceAgentTurn(userId, sid, AUTO_TAILOR_INSTRUCTION, {
          chat_history: [],
        });
        applyRewriteResult(result);
        const where = label ? ` for ${label}` : " for this job";
        setBootNotice(
          result.agent_message ||
            `I generated a first tailored draft${where}. Check the PDF on the right — tell me what to refine.`
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Auto-tailor failed";
        setBootNotice(`Could not auto-generate the first draft: ${msg}. You can still ask me to tailor it.`);
      } finally {
        setRewriting(false);
      }
    },
    [applyRewriteResult, userId]
  );

  const initSession = useCallback(
    async (text: string, opts?: { autoTailor?: boolean; label?: string | null }) => {
      setAnalyzing(true);
      try {
        const session = await createJdSession(userId, text, initialJobId);
        setSessionId(session.session_id);
        setJdText(text);
        await analyzeJd(session.session_id);
        if (opts?.autoTailor) {
          await runAutoTailor(session.session_id, opts.label);
        }
      } catch {
        setSessionId("mock-session-" + Date.now());
      } finally {
        setAnalyzing(false);
      }
    },
    [userId, initialJobId, runAutoTailor]
  );

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    const bootstrap = async () => {
      // Restore from Apply / deep-link — do NOT wipe versions with a fresh auto-tailor.
      if (initialVersionId || initialSessionId) {
        try {
          setAnalyzing(true);
          let sid = initialSessionId || "";
          let vid = initialVersionId || "";
          if (vid) {
            const v = await getVersion(vid, userId);
            sid = v.session_id || sid;
            setActiveVersionId(v.id);
            setActiveResume(v.full_resume as Record<string, unknown>);
            setContentDelta((v.content_delta as ContentDelta) || null);
            setPreviewMode("changes");
            loadPdfWhenReady(v.id);
          }
          if (!sid) {
            setBootNotice("Could not restore session for this version.");
            setAnalyzing(false);
            return;
          }
          setSessionId(sid);
          const listed = await listVersions(sid, userId);
          setVersions(
            listed.versions.map((x) =>
              vid && x.id === vid
                ? { ...x, is_confirmed: x.is_confirmed }
                : x
            )
          );
          if (!vid && listed.versions.length) {
            const latest = listed.versions[listed.versions.length - 1];
            vid = latest.id;
            setActiveVersionId(vid);
            const v = await getVersion(vid, userId);
            setActiveResume(v.full_resume as Record<string, unknown>);
            setContentDelta((v.content_delta as ContentDelta) || null);
            setPreviewMode("changes");
            loadPdfWhenReady(vid);
          } else if (vid) {
            // refresh confirm flags from getVersion
            try {
              const v = await getVersion(vid, userId);
              setVersions((prev) =>
                prev.map((x) => (x.id === vid ? { ...x, is_confirmed: !!v.is_confirmed } : x))
              );
            } catch {
              /* ignore */
            }
          }
          setWorkspacePanel("tailor");
          setBootNotice("Restored your tailored version — drafts stay in markdown until Confirm; finals live under data/final_resumes/{Company}_{Position}/.");
          setAnalyzing(false);
          return;
        } catch (err) {
          setAnalyzing(false);
          const msg = err instanceof Error ? err.message : "restore failed";
          setBootNotice(`Could not restore version (${msg}).`);
        }
      }

      if (!initialJobId) {
        await initSession(EMPTY_JD_HINT, { autoTailor: false, label: null });
        setBootNotice(
          "Paste a JD or open a ranked job. All rewrites follow RESUME_CONSTITUTION.md."
        );
        return;
      }
      setAnalyzing(true);
      try {
        const handoff = await openJobInResumeWorkspace(initialJobId, userId);
        const label = [handoff.company, handoff.title].filter(Boolean).join(" · ") || null;
        setJobLabel(label);
        setSessionId(handoff.session_id);
        // Defense in depth: strip any residual HTML/CSS from provider JD bodies
        setJdText(
          String(handoff.jd_text || "")
            .replace(/<(br|\/p|\/li|\/div|\/h\d)[^>]*>/gi, "\n")
            .replace(/<li[^>]*>/gi, "\n- ")
            .replace(/<[^>]+>/g, " ")
            .replace(/&nbsp;/gi, " ")
            .replace(/[ \t]+/g, " ")
            .trim()
        );
        try {
          await analyzeJd(handoff.session_id);
        } catch {
          setBootNotice("JD loaded, but analysis failed — you can still tailor.");
        }
        setAnalyzing(false);
        try {
          await runAutoTailor(handoff.session_id, label);
        } catch (err) {
          const msg = err instanceof Error ? err.message : "Auto-tailor failed";
          setBootNotice(`JD loaded for ${label || "this job"}, but auto-draft failed: ${msg}. Ask me to tailor.`);
        }
      } catch (err) {
        setAnalyzing(false);
        const msg = err instanceof Error ? err.message : "handoff failed";
        setBootNotice(
          `Could not load job ${initialJobId.slice(0, 8)}… (${msg}). Paste the real JD — demo backend JD is no longer used.`
        );
        await initSession(EMPTY_JD_HINT, { autoTailor: false, label: null });
      }
    };

    void bootstrap();
  }, [initSession, userId, initialJobId, initialVersionId, initialSessionId, runAutoTailor]);

  // Deeplink: open Tailor panel and scroll to Confirm under PDF.
  useEffect(() => {
    const step = (initialStep || "").toLowerCase().trim();
    if (!step || step === "jd" || step === "outreach" || step === "apply") return;
    if (step === "tailor" || step === "confirm") {
      setWorkspacePanel("tailor");
      setFocusStep("tailor");
    }
    if (step !== "confirm") return;
    let tries = 0;
    const timer = window.setInterval(() => {
      tries += 1;
      const el = document.querySelector("[data-testid=confirm-version]");
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "nearest" });
        window.clearInterval(timer);
        return;
      }
      if (tries > 40) window.clearInterval(timer);
    }, 250);
    return () => window.clearInterval(timer);
  }, [initialStep, sessionId, activeVersionId]);

  const handlePasteJd = async () => {
    if (!pasteInput.trim()) return;
    setJdText(pasteInput.trim());
    setShowPasteInput(false);
    setPasteInput("");
    setVersions([]);
    setActiveVersionId(null);
    setActiveResume(null);
    setContentDelta(null);
    setPreviewMode("changes");
    setPdfPreviewUrl(null);
    setBootNotice(null);
    await initSession(pasteInput.trim(), { autoTailor: true, label: "the pasted JD" });
  };

  const handleAgent = async (
    instruction: string,
    history: Array<{ role: string; content: string }>
  ): Promise<AgentSendResult> => {
    if (!sessionId) {
      return { agent_message: "Session is still starting — try again in a moment." };
    }
    setRewriting(true);
    try {
      const result = await workspaceAgentTurn(userId, sessionId, instruction, {
        base_version_id: activeVersionId || undefined,
        chat_history: history,
      });
      applyRewriteResult(result);
      return {
        agent_message: result.agent_message,
        did_rewrite: result.did_rewrite,
        profile_updated: !!result.profile_updated,
        changed_apply: result.changed_apply || [],
        changed_inventory: result.changed_inventory || [],
        llm_provider: result.llm_provider,
        llm_model: result.llm_model,
      };
    } finally {
      setRewriting(false);
    }
  };

  const buildApplyHref = (meta?: {
    company?: string;
    position?: string;
    final_path?: string;
  }) => {
    if (!activeVersionId) return null;
    const company =
      meta?.company ||
      confirmedMeta?.company ||
      jobLabel?.split("·")[0]?.trim() ||
      "";
    const position =
      meta?.position ||
      confirmedMeta?.position ||
      jobLabel?.split("·").slice(1).join(" · ").trim() ||
      "";
    const q = new URLSearchParams({ versionId: activeVersionId });
    if (sessionId) q.set("sessionId", sessionId);
    if (initialJobId) q.set("jobId", initialJobId);
    if (company) q.set("company", company);
    if (position) q.set("position", position);
    const finalPath = meta?.final_path || confirmedMeta?.final_path || finalSavePath;
    if (finalPath) q.set("finalPath", finalPath);
    return `/apply?${q.toString()}`;
  };

  const handleConfirm = async () => {
    if (!activeVersionId) return;
    const alreadyConfirmed = versions.some((v) => v.id === activeVersionId && v.is_confirmed);
    if (alreadyConfirmed) {
      const href = buildApplyHref();
      if (href) window.location.assign(href);
      return;
    }
    setConfirming(true);
    setConfirmError(null);
    try {
      const result = await confirmVersion(activeVersionId, userId);
      setVersions((prev) =>
        prev.map((v) => (v.id === activeVersionId ? { ...v, is_confirmed: true } : v))
      );
      if (result.final_path) setFinalSavePath(result.final_path);
      setConfirmedMeta({
        company: result.company,
        position: result.position,
        final_path: result.final_path,
      });
      const href = buildApplyHref({
        company: result.company,
        position: result.position,
        final_path: result.final_path,
      });
      if (href) {
        window.location.assign(href);
        return;
      }
    } catch (err) {
      const raw = err instanceof Error ? err.message : "Confirm blocked by evidence/format gate";
      // Prefer readable detail from API 409 JSON when present
      let msg = raw;
      try {
        const m = raw.match(/\{[\s\S]*\}/);
        if (m) {
          const detail = JSON.parse(m[0]);
          const issues = detail?.detail?.issues || detail?.issues;
          if (Array.isArray(issues) && issues.length) {
            msg = issues.slice(0, 3).join(" · ");
          } else if (detail?.detail?.reason) {
            msg = String(detail.detail.reason);
          }
        }
      } catch {
        /* keep raw */
      }
      setConfirmError(msg);
    } finally {
      setConfirming(false);
    }
  };

  const handleOpenOutreach = () => {
    const company =
      confirmedMeta?.company || jobLabel?.split("·")[0]?.trim() || "";
    const position =
      confirmedMeta?.position ||
      jobLabel?.split("·").slice(1).join(" · ").trim() ||
      "";
    const q = new URLSearchParams();
    if (initialJobId) q.set("jobId", initialJobId);
    if (company) q.set("company", company);
    if (position) q.set("position", position);
    const href = `/outreach${q.toString() ? `?${q.toString()}` : ""}`;
    // Same-tab navigation so the flow stepper stays continuous.
    window.location.assign(href);
  };

  const handleOpenApplyWorkspace = () => {
    const href = buildApplyHref();
    if (!href) return;
    window.location.assign(href);
  };

  // Deeplink step=outreach → dedicated tab (never embed beside PDF).
  useEffect(() => {
    if ((initialStep || "").toLowerCase().trim() !== "outreach") return;
    handleOpenOutreach();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialStep, initialJobId]);

  // Deeplink step=apply → dedicated Apply workspace tab.
  useEffect(() => {
    if ((initialStep || "").toLowerCase().trim() !== "apply") return;
    if (!activeVersionId) return;
    handleOpenApplyWorkspace();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialStep, initialJobId, activeVersionId]);

  const handleExport = async (format: "pdf" | "docx" | "text") => {
    if (!activeVersionId || exporting) return;
    setExporting(format);
    try {
      const blob = await exportVersion(activeVersionId, userId, format);
      downloadBlob(
        blob,
        `resume-v${versions.find((v) => v.id === activeVersionId)?.version_index || 1}.${format}`
      );
    } catch {
      alert("Export failed");
    } finally {
      setExporting(null);
    }
  };

  const handleSelectVersion = async (versionId: string) => {
    setActiveVersionId(versionId);
    try {
      const v = await getVersion(versionId, userId);
      setActiveResume(v.full_resume as Record<string, unknown>);
      setContentDelta((v.content_delta as ContentDelta) || null);
      setPreviewMode("changes");
      setVersions((prev) =>
        prev.map((x) =>
          x.id === versionId ? { ...x, is_confirmed: !!v.is_confirmed } : x
        )
      );
      loadPdfWhenReady(versionId);
    } catch {
      setPdfPreviewUrl(null);
      setPdfReady(false);
      setPdfPending(false);
    }
  };

  const activeVersion = versions.find((v) => v.id === activeVersionId);
  const derivedFlowStep =
    workspacePanel === "jd"
      ? "jd"
      : activeVersion?.is_confirmed
        ? "apply"
        : "tailor";
  const flowStep = focusStep || derivedFlowStep;
  const evidenceCheck = (activeResume?.evidence_check || null) as
    | {
        ok?: boolean;
        passed?: boolean;
        notes?: string;
        issues?: string[];
        hard_issues?: string[];
      }
    | null;
  const formatCheck = (activeResume?.format_check || null) as { fabrication?: boolean } | null;
  const hardEvidenceIssues = evidenceCheck?.hard_issues
    ?? (evidenceCheck?.issues || []).filter((i) => !String(i).includes("weak textual support"));
  const softEvidenceWarnings = (evidenceCheck?.issues || []).filter((i) =>
    String(i).includes("weak textual support")
  );
  // Soft wording-overlap warnings alone do not block Confirm.
  const canConfirm =
    hardEvidenceIssues.length === 0 &&
    formatCheck?.fabrication !== true &&
    activeResume?.requires_fix !== true;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && showPasteInput) {
        e.preventDefault();
        setShowPasteInput(false);
        return;
      }
      if (!(e.ctrlKey || e.metaKey) || !e.shiftKey || e.key !== "Enter") return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT" || t.isContentEditable)) return;
      if (!activeVersionId || confirming) return;
      if (!activeVersion?.is_confirmed && !canConfirm) return;
      e.preventDefault();
      void handleConfirm();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeVersionId, activeVersion?.is_confirmed, confirming, canConfirm, handleConfirm, showPasteInput]);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col bg-[#f4f6f4]" data-testid="resume-workspace">
      {/* Slim chrome only */}
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <a
            href="/jobs"
            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-50"
          >
            ← Jobs
          </a>
          <FlowStepper
            current={flowStep}
            className="hidden lg:flex"
            hrefs={{
              jobs: "/jobs",
              ...(initialJobId ? { detail: `/jobs/${initialJobId}` } : {}),
              jd: initialJobId
                ? `/?view=resume&jobId=${encodeURIComponent(initialJobId)}&step=jd`
                : "/?view=resume&step=jd",
              tailor: initialJobId
                ? `/?view=resume&jobId=${encodeURIComponent(initialJobId)}&step=tailor`
                : "/?view=resume&step=tailor",
            }}
            onJump={(step) => {
              if (step === "outreach") {
                setFocusStep("outreach");
                handleOpenOutreach();
                return;
              }
              if (step === "jd") {
                setFocusStep("jd");
                setWorkspacePanel("jd");
                return;
              }
              if (step === "apply") {
                setFocusStep("apply");
                handleOpenApplyWorkspace();
                return;
              }
              if (step === "tailor") {
                setFocusStep("tailor");
                setWorkspacePanel("tailor");
              }
            }}
          />
          {jobLabel ? (
            <span className="truncate rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] text-slate-600" title={jobLabel}>
              {jobLabel}
            </span>
          ) : initialJobId ? (
            <span className="truncate rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] text-slate-600">
              job {initialJobId.slice(0, 8)}…
            </span>
          ) : null}

          {!showPasteInput ? (
            <button
              type="button"
              onClick={() => setShowPasteInput(true)}
              className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50"
            >
              Paste JD
            </button>
          ) : (
            <div className="flex max-w-xl flex-1 items-start gap-2" data-testid="paste-jd-box">
              <textarea
                value={pasteInput}
                onChange={(e) => setPasteInput(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                    e.preventDefault();
                    void handlePasteJd();
                  }
                }}
                onPaste={(e) => {
                  const text = e.clipboardData.getData("text/plain");
                  if (text && (/<[a-z][\s\S]*>/i.test(text) || text.includes("tw-"))) {
                    e.preventDefault();
                    const cleaned = text
                      .replace(/<(br|\/p|\/li|\/div|\/h\d)[^>]*>/gi, "\n")
                      .replace(/<li[^>]*>/gi, "\n- ")
                      .replace(/<[^>]+>/g, " ")
                      .replace(/&nbsp;/gi, " ")
                      .replace(/[ \t]+/g, " ")
                      .trim();
                    setPasteInput(cleaned);
                  }
                }}
                placeholder="Paste full JD… (Ctrl+Enter analyze · Esc cancel)"
                rows={3}
                className="min-h-[4.5rem] w-full min-w-[16rem] resize-y rounded-lg border border-slate-200 px-3 py-2 text-xs outline-none focus:border-emerald-400"
                autoFocus
                data-testid="paste-jd-input"
              />
              <div className="flex shrink-0 flex-col gap-1">
                <button
                  type="button"
                  onClick={() => void handlePasteJd()}
                  disabled={!pasteInput.trim()}
                  className="h-8 rounded-lg bg-emerald-600 px-3 text-xs font-semibold text-white disabled:opacity-50"
                  data-testid="paste-jd-analyze"
                >
                  Analyze
                </button>
                <button
                  type="button"
                  onClick={() => setShowPasteInput(false)}
                  className="h-8 rounded-lg border border-slate-200 px-3 text-xs text-slate-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

        {workspacePanel === "tailor" ? (
        <div className="flex shrink-0 items-center gap-2">
          {versions.length > 0 ? (
            <select
              className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs"
              value={activeVersionId || ""}
              onChange={(e) => void handleSelectVersion(e.target.value)}
              data-testid="version-select"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_index}
                  {v.is_confirmed ? " ✓" : ""}
                </option>
              ))}
            </select>
          ) : null}
          <button
            type="button"
            onClick={() => void handleExport("docx")}
            disabled={!activeVersion?.is_confirmed || !!exporting}
            title={!activeVersion?.is_confirmed ? "Confirm first to export final DOCX" : "Download confirmed DOCX"}
            className="h-8 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-700 disabled:opacity-40"
          >
            DOCX
          </button>
          <button
            type="button"
            onClick={() => void handleExport("pdf")}
            disabled={!activeVersion?.is_confirmed || !!exporting}
            title={!activeVersion?.is_confirmed ? "Confirm first to export final PDF" : "Download confirmed PDF"}
            className="h-8 rounded-lg bg-slate-900 px-3 text-xs font-semibold text-white disabled:opacity-40"
          >
            PDF
          </button>
        </div>
        ) : null}
      </header>

      {softEvidenceWarnings.length > 0 && canConfirm && !activeVersion?.is_confirmed ? (
        <div
          className="shrink-0 bg-amber-50 px-4 py-1.5 text-center text-[11px] text-amber-900"
          data-testid="confirm-soft-warnings"
        >
          Soft evidence notes (Confirm still allowed — weak textual support is not a hard block)
          {softEvidenceWarnings.length > 1 ? (
            <span data-testid="confirm-soft-count"> · {softEvidenceWarnings.length} notes</span>
          ) : null}
          :{" "}
          {softEvidenceWarnings.slice(0, 2).join(" · ")}
        </div>
      ) : null}
      {!canConfirm && activeResume && !activeVersion?.is_confirmed ? (
        <div
          className="shrink-0 bg-rose-50 px-4 py-1.5 text-center text-[11px] text-rose-800"
          data-testid="confirm-blocked-reason"
        >
          Confirm blocked:{" "}
          {hardEvidenceIssues[0] ||
            (formatCheck?.fabrication ? "fabrication flagged" : null) ||
            (activeResume?.requires_fix ? "quality gate requires fix" : "evidence/format gate")}
        </div>
      ) : null}
      {confirmError ? (
        <div
          className="shrink-0 bg-rose-50 px-4 py-1.5 text-center text-[11px] text-rose-800"
          data-testid="confirm-error"
        >
          {confirmError}
        </div>
      ) : null}

      {workspacePanel === "tailor" ? (
      <div
        className="hidden shrink-0 border-b border-slate-100 bg-white px-4 py-1 text-[10px] text-slate-500 sm:block"
        data-testid="tailor-kbd-hints"
      >
        Shortcuts: Confirm <kbd className="rounded bg-slate-100 px-1">Ctrl+Shift+Enter</kbd>
        {" · "}
        Paste JD analyze <kbd className="rounded bg-slate-100 px-1">Ctrl+Enter</kbd>
        {" · "}
        Cancel paste <kbd className="rounded bg-slate-100 px-1">Esc</kbd>
      </div>
      ) : null}

      {finalSavePath ? (
        <div
          className="shrink-0 bg-emerald-50 px-4 py-1.5 text-center text-[11px] font-semibold text-emerald-800"
          data-testid="final-save-path"
        >
          Confirmed → {finalSavePath} (docx + pdf + meta.json)
          <span className="ml-2 font-normal text-emerald-700" data-testid="confirm-next-apply">
            Opening Apply…
          </span>
        </div>
      ) : null}

      {/* Flow panels: 3. JD | 4. Tailor (agent + PDF). */}
      {workspacePanel === "jd" ? (
        <div
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-3 [scrollbar-gutter:stable]"
          data-testid="workspace-jd-panel"
        >
          <div className="mb-3 flex items-center justify-between gap-2">
            <p className="text-[12px] text-slate-500">
              Review JD and hard requirements, then continue to Tailor.
            </p>
            <button
              type="button"
              data-testid="goto-tailor"
              onClick={() => {
                setFocusStep("tailor");
                setWorkspacePanel("tailor");
              }}
              className="shrink-0 rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
            >
              Go to Tailor →
            </button>
          </div>
          <JdPanel jdText={jdText} loading={analyzing} expandContent jobLabel={jobLabel} />
        </div>
      ) : (
        <div
          className="grid min-h-0 w-full flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)]"
          data-testid="workspace-tailor-panel"
        >
          <div className="min-h-[360px] overflow-hidden lg:min-h-0 lg:h-full">
            <WorkspaceChat
              onSend={handleAgent}
              loading={rewriting || analyzing}
              bootNotice={bootNotice}
            />
          </div>

          <div
            className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto overscroll-contain [scrollbar-gutter:stable] lg:h-full"
            data-testid="right-scroll-column"
          >
            <div className="min-h-[640px] shrink-0 pb-1" data-testid="resume-preview">
              <ResumePreviewSection
                pdfPreviewUrl={pdfPreviewUrl}
                pdfReady={pdfReady}
                pdfPending={pdfPending}
                numPages={numPages}
                onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                resume={activeResume}
                contentDelta={contentDelta}
                previewMode={previewMode}
                onPreviewModeChange={setPreviewMode}
                wide
                busy={analyzing || rewriting}
              />
            </div>
            <div
              className="shrink-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
              data-testid="tailor-confirm-card"
            >
              <button
                type="button"
                data-testid="confirm-version"
                onClick={() => void handleConfirm()}
                disabled={
                  !activeVersionId ||
                  confirming ||
                  (!activeVersion?.is_confirmed && !canConfirm)
                }
                title={
                  activeVersion?.is_confirmed
                    ? "Open Apply workspace"
                    : softEvidenceWarnings.length && canConfirm
                      ? "Soft evidence notes only — Confirm is allowed (Ctrl+Shift+Enter)"
                      : !canConfirm
                        ? "Blocked by hard evidence / format gate"
                        : "Confirm resume, then open Apply (Ctrl+Shift+Enter)"
                }
                className="w-full rounded-full bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
              >
                {confirming
                  ? "Confirming…"
                  : activeVersion?.is_confirmed
                    ? "Go to Apply →"
                    : softEvidenceWarnings.length && canConfirm
                      ? "Confirm → Apply*"
                      : "Confirm → Apply"}
              </button>
              <p className="mt-2 text-center text-[11px] text-slate-500">
                Saves final DOCX + PDF, then opens the Apply page. Auto-apply never clicks Submit.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function pathStatus(
  path: string,
  delta: ContentDelta | null
): "changed" | "unchanged" | "unknown" {
  if (!delta) return "unknown";
  const changes = delta.changes || [];
  if (changes.some((c) => c.path === path || c.path.startsWith(path + ".") || c.path.startsWith(path + "["))) {
    return "changed";
  }
  // parent section changed via any bullet
  if (changes.some((c) => c.path.startsWith(path))) {
    return "changed";
  }
  const unchanged = delta.unchanged_paths || [];
  if (unchanged.includes(path) || unchanged.some((p) => p.startsWith(path))) {
    return "unchanged";
  }
  return "unknown";
}

function highlightClass(status: "changed" | "unchanged" | "unknown"): string {
  if (status === "changed") {
    return "rounded-md bg-amber-100 ring-1 ring-amber-300 px-1 -mx-1";
  }
  if (status === "unchanged") {
    return "opacity-45";
  }
  return "";
}

function ResumePreviewSection({
  pdfPreviewUrl,
  pdfReady = false,
  pdfPending = false,
  numPages,
  onLoadSuccess,
  resume,
  contentDelta = null,
  previewMode = "changes",
  onPreviewModeChange,
  wide = false,
  busy = false,
}: {
  pdfPreviewUrl: string | null;
  pdfReady?: boolean;
  pdfPending?: boolean;
  numPages: number | null;
  onLoadSuccess: (info: { numPages: number }) => void;
  resume: Record<string, unknown> | null;
  contentDelta?: ContentDelta | null;
  previewMode?: "changes" | "master";
  onPreviewModeChange?: (mode: "changes" | "master") => void;
  wide?: boolean;
  busy?: boolean;
}) {
  void numPages;
  void onLoadSuccess;
  void wide;
  const hasDelta = !!(contentDelta?.changes && contentDelta.changes.length > 0);
  const showChanges = previewMode === "changes" && !!resume && (hasDelta || busy || pdfPending || !pdfReady);
  const showHtmlFirst = !!resume && (!pdfReady || pdfPending || busy) && previewMode !== "master";

  const modeToggle =
    resume && (hasDelta || pdfReady) ? (
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2" data-testid="preview-mode-toggle">
        <div className="flex items-center gap-1 rounded-full border border-slate-200 bg-white p-0.5 text-[11px]">
          <button
            type="button"
            onClick={() => onPreviewModeChange?.("changes")}
            className={`rounded-full px-2.5 py-1 font-semibold ${
              previewMode === "changes" ? "bg-amber-500 text-white" : "text-slate-600"
            }`}
            data-testid="preview-mode-changes"
          >
            Highlight changes
          </button>
          <button
            type="button"
            onClick={() => onPreviewModeChange?.("master")}
            disabled={!pdfPreviewUrl}
            className={`rounded-full px-2.5 py-1 font-semibold disabled:opacity-40 ${
              previewMode === "master" ? "bg-emerald-600 text-white" : "text-slate-600"
            }`}
            data-testid="preview-mode-master"
          >
            Master PDF
          </button>
        </div>
        {previewMode === "changes" && hasDelta ? (
          <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-500" data-testid="preview-legend">
            <span className="inline-flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-300 ring-1 ring-amber-400" />
              Changed
            </span>
            <span className="inline-flex items-center gap-1 opacity-60">
              <span className="inline-block h-2.5 w-2.5 rounded-sm bg-slate-300" />
              Unchanged
            </span>
            <span className="inline-flex items-center gap-1 text-rose-600">
              <span className="inline-block h-2.5 w-2.5 rounded-sm bg-rose-300" />
              Hidden
            </span>
            <span className="font-semibold text-slate-600">
              {contentDelta?.change_count ?? contentDelta?.changes?.length ?? 0} edits
            </span>
          </div>
        ) : null}
      </div>
    ) : null;

  if ((showChanges || showHtmlFirst) && resume && previewMode !== "master") {
    return (
      <div className="relative" data-testid="preview-first-paint">
        {modeToggle}
        {(busy || pdfPending) && (
          <div
            className="mb-2 flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 px-3 py-1.5"
            data-testid="preview-updating-banner"
          >
            <span className="text-[11px] font-semibold text-amber-900">
              {busy ? "Tailoring…" : "Rendering locked master PDF…"}
            </span>
            <span className="text-[10px] text-amber-700" data-testid="preview-html-first-note">
              Highlights show what changed — switch to Master PDF when ready
            </span>
          </div>
        )}
        <div data-testid="html-preview-fallback">
          <ResumeHtmlPreview resume={resume} delta={contentDelta} highlight />
        </div>
      </div>
    );
  }

  // Native browser PDF viewer — avoids react-pdf worker crashes on large Word PDFs.
  if (pdfPreviewUrl && previewMode === "master") {
    return (
      <div
        className="flex min-h-[780px] w-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
        data-testid="master-pdf-preview"
      >
        <div className="border-b border-slate-100 px-4 py-2">{modeToggle}</div>
        <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-2">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
              Master template preview
            </span>
            <p className="text-[10px] text-slate-400">
              Clean OOXML → Word PDF (Confirm export). No highlight overlays — switch to Highlight changes.
            </p>
          </div>
          <span className="text-[11px] font-semibold text-emerald-700" data-testid="preview-page-count">
            template PDF
          </span>
        </div>
        <iframe
          title="Master resume PDF preview"
          src={pdfPreviewUrl}
          className="min-h-[740px] w-full flex-1 bg-slate-100"
          data-testid="master-pdf-iframe"
        />
      </div>
    );
  }

  if (pdfPreviewUrl && !hasDelta) {
    return (
      <div
        className="flex min-h-[780px] w-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
        data-testid="master-pdf-preview"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-4 py-2">
          <div>
            <span className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
              Master template preview
            </span>
            <p className="text-[10px] text-slate-400">
              OOXML inject → Word PDF (same layout as Confirm DOCX)
            </p>
          </div>
          <span className="text-[11px] font-semibold text-emerald-700" data-testid="preview-page-count">
            template PDF
          </span>
        </div>
        <iframe
          title="Master resume PDF preview"
          src={pdfPreviewUrl}
          className="min-h-[740px] w-full flex-1 bg-slate-100"
          data-testid="master-pdf-iframe"
        />
      </div>
    );
  }

  if (!resume) {
    return (
      <div
        className="flex min-h-[420px] w-full flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center"
        data-testid="preview-empty-skeleton"
      >
        <div className="mb-4 h-2 w-40 animate-pulse rounded bg-slate-200" />
        <div className="mb-2 h-2 w-64 animate-pulse rounded bg-slate-100" />
        <div className="mb-6 h-2 w-52 animate-pulse rounded bg-slate-100" />
        <p className="text-sm font-semibold text-slate-800">
          {busy ? "Generating tailored resume…" : "No resume preview yet"}
        </p>
        <p className="mt-1 max-w-sm text-xs text-slate-500">
          {busy
            ? "Content appears here as soon as the draft is ready — master PDF follows."
            : "Open a job to auto-generate, or chat with the agent to create a tailored version."}
        </p>
      </div>
    );
  }

  return (
    <div data-testid="html-preview-fallback">
      {modeToggle}
      <p className="mb-2 text-center text-[10px] text-amber-700">
        Master PDF unavailable — structured fallback (Confirm DOCX still uses locked master)
      </p>
      <ResumeHtmlPreview resume={resume} delta={contentDelta} highlight={hasDelta} />
    </div>
  );
}

function ResumeHtmlPreview({
  resume,
  delta = null,
  highlight = false,
}: {
  resume: Record<string, unknown>;
  delta?: ContentDelta | null;
  highlight?: boolean;
}) {
  const r = resume;
  const candidateName = r.candidate_name as string | undefined;
  const contactLine = r.contact_line as string | undefined;
  const summary = r.summary as string | undefined;
  const education = r.education as Array<Record<string, unknown>> | undefined;
  const experiences = r.experiences as Array<Record<string, unknown>> | undefined;
  const projects = r.projects as Array<Record<string, unknown>> | undefined;
  const skillsCerts = r.skills_certifications as string | undefined;
  const hidden = (delta?.hidden_entries ||
    (r.hidden_entries as Array<Record<string, unknown>> | undefined) ||
    []) as Array<Record<string, unknown> | string>;

  const mark = (path: string) => (highlight ? pathStatus(path, delta) : ("unknown" as const));

  return (
    <div className="h-full w-full overflow-auto rounded-2xl border border-slate-200 bg-slate-50 p-3">
      <p className="mb-2 text-center text-[10px] text-slate-400">
        {highlight
          ? "Change highlight preview (Confirm still exports clean master PDF)"
          : "Structured preview (Confirm → DOCX uses locked master template)"}
      </p>
      <div className="mx-auto min-h-[900px] w-full max-w-[640px] bg-white px-10 py-8 text-slate-950 shadow-sm ring-1 ring-slate-200">
        {(candidateName || contactLine) && (
          <header className="mb-3 text-center">
            {candidateName && (
              <h1 className="text-[14pt] font-bold uppercase tracking-wide">{candidateName}</h1>
            )}
            {contactLine && (
              <p className={`mt-1 text-[10pt] text-slate-700 ${highlightClass(mark("contact_line"))}`}>
                {contactLine}
              </p>
            )}
          </header>
        )}
        {summary && (
          <p className={`mb-3 text-[10pt] leading-5 text-slate-800 ${highlightClass(mark("summary"))}`}>
            {summary}
          </p>
        )}
        {education && education.length > 0 && (
          <section className="mb-3">
            <h4 className="mb-1 border-b border-slate-300 pb-0.5 text-[10pt] font-bold uppercase">Education</h4>
            {education.map((edu, i) => (
              <div key={i} className="mb-1 text-[10pt]">
                <div className="flex justify-between gap-2">
                  <p className="font-bold">{edu.institution as string}</p>
                  {edu.date_range ? <p className="shrink-0 text-slate-600">{edu.date_range as string}</p> : null}
                </div>
              </div>
            ))}
          </section>
        )}
        {experiences && experiences.length > 0 && (
          <section className="mb-3">
            <h4 className="mb-1 border-b border-slate-300 pb-0.5 text-[10pt] font-bold uppercase">
              Professional Experience
            </h4>
            {experiences.map((exp, i) => (
              <div key={i} className={`mb-2 ${highlightClass(mark(`experiences[${i}]`))}`}>
                <p className="text-[10pt] font-bold">
                  {[exp.title, exp.company].filter(Boolean).join(" | ")}
                </p>
                <ul className="ml-3 text-[10pt] leading-5">
                  {(exp.bullets as Array<{ text: string }> | undefined)?.slice(0, 3).map((b, j) => (
                    <li
                      key={j}
                      className={highlightClass(mark(`experiences[${i}].bullets[${j}]`))}
                      data-testid={
                        mark(`experiences[${i}].bullets[${j}]`) === "changed"
                          ? "resume-line-changed"
                          : mark(`experiences[${i}].bullets[${j}]`) === "unchanged"
                            ? "resume-line-unchanged"
                            : undefined
                      }
                    >
                      • {b.text}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        )}
        {projects && projects.length > 0 && (
          <section className="mb-3">
            <h4 className="mb-1 border-b border-slate-300 pb-0.5 text-[10pt] font-bold uppercase">Projects</h4>
            {projects.map((proj, i) => (
              <div key={i} className={`mb-1.5 text-[10pt] ${highlightClass(mark(`projects[${i}]`))}`}>
                <p className="font-bold">{proj.name as string}</p>
                <ul className="ml-3 leading-5">
                  {(proj.bullets as Array<{ text: string }> | undefined)?.slice(0, 3).map((b, j) => (
                    <li key={j} className={highlightClass(mark(`projects[${i}].bullets[${j}]`))}>
                      • {b.text}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        )}
        {skillsCerts && (
          <section>
            <h4 className="mb-1 border-b border-slate-300 pb-0.5 text-[10pt] font-bold uppercase">
              Skills & Certifications
            </h4>
            <p className={`text-[10pt] leading-5 ${highlightClass(mark("skills_certifications"))}`}>
              {skillsCerts}
            </p>
          </section>
        )}
        {highlight && hidden.length > 0 ? (
          <section className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2" data-testid="resume-hidden-block">
            <h4 className="mb-1 text-[10pt] font-bold uppercase text-rose-800">Hidden this page</h4>
            <ul className="space-y-1 text-[10pt] text-rose-700">
              {hidden.map((h, i) => {
                const label =
                  typeof h === "string"
                    ? h
                    : String(
                        (h as Record<string, unknown>).key ||
                          (h as Record<string, unknown>).name ||
                          (h as Record<string, unknown>).company ||
                          JSON.stringify(h)
                      );
                return <li key={i}>− {label}</li>;
              })}
            </ul>
          </section>
        ) : null}
      </div>
    </div>
  );
}
