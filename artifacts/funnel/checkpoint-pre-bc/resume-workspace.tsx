"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { KeywordMatchItem, StartApplyResponse, VersionItem } from "@/lib/api";
import {
  createJdSession,
  analyzeJd,
  workspaceAgentTurn,
  openJobInResumeWorkspace,
  confirmVersion,
  getVersion,
  exportVersion,
  getVersionPreviewUrl,
  getActiveTemplate,
  startApply,
} from "@/lib/api";
import ApplyModePanel from "@/components/apply-mode-panel";
import JdPanel from "@/components/jd-panel";
import WorkspaceChat from "@/components/workspace-chat";
import type { AgentSendResult } from "@/components/workspace-chat";
interface ResumeWorkspaceProps {
  userId: string;
  initialJobId?: string;
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

export default function ResumeWorkspace({ userId, initialJobId }: ResumeWorkspaceProps) {
  const [jdText, setJdText] = useState(initialJobId ? "" : EMPTY_JD_HINT);
  const [showPasteInput, setShowPasteInput] = useState(false);
  const [pasteInput, setPasteInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [keywordMatches, setKeywordMatches] = useState<KeywordMatchItem[]>([]);
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
  const [activeResume, setActiveResume] = useState<Record<string, unknown> | null>(null);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [rewriting, setRewriting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [exporting, setExporting] = useState<"pdf" | "docx" | "text" | null>(null);
  const [initialized, setInitialized] = useState(false);
  const [finalSavePath, setFinalSavePath] = useState<string | null>(null);
  const [jobLabel, setJobLabel] = useState<string | null>(null);
  const [bootNotice, setBootNotice] = useState<string | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyResult, setApplyResult] = useState<StartApplyResponse | null>(null);
  const [confirmedMeta, setConfirmedMeta] = useState<{
    company?: string;
    position?: string;
    final_path?: string;
  } | null>(null);

  const applyRewriteResult = useCallback(
    (result: {
      did_rewrite?: boolean;
      new_version_id?: string | null;
      version_index?: number | null;
      full_resume?: Record<string, unknown> | null;
      keyword_matches?: KeywordMatchItem[];
    }) => {
      if (!result.did_rewrite || !result.new_version_id) return;
      if (result.keyword_matches) setKeywordMatches(result.keyword_matches);
      if (result.full_resume) setActiveResume(result.full_resume);
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
      setPdfPreviewUrl(getVersionPreviewUrl(result.new_version_id, userId));
    },
    [userId]
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
        const analysis = await analyzeJd(session.session_id);
        setKeywordMatches(analysis.keyword_matches);
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
    if (initialized) return;
    setInitialized(true);
    getActiveTemplate(userId).catch(() => {});

    const bootstrap = async () => {
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
        setJdText(handoff.jd_text);
        try {
          const analysis = await analyzeJd(handoff.session_id);
          setKeywordMatches(analysis.keyword_matches);
        } catch {
          setBootNotice("JD loaded, but skill tags failed — you can still tailor.");
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
  }, [initialized, initSession, userId, initialJobId, runAutoTailor]);

  const handlePasteJd = async () => {
    if (!pasteInput.trim()) return;
    setJdText(pasteInput.trim());
    setShowPasteInput(false);
    setPasteInput("");
    setVersions([]);
    setActiveVersionId(null);
    setActiveResume(null);
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
      };
    } finally {
      setRewriting(false);
    }
  };

  const handleConfirm = async () => {
    if (!activeVersionId) return;
    setConfirming(true);
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
      setApplyResult(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Confirm blocked by evidence/format gate";
      alert(msg);
    } finally {
      setConfirming(false);
    }
  };

  const handleStartApply = async (mode: "manual" | "auto") => {
    if (!activeVersionId) return;
    setApplyBusy(true);
    try {
      const result = await startApply(activeVersionId, userId, mode, {
        company: confirmedMeta?.company,
        position: confirmedMeta?.position,
        final_path: confirmedMeta?.final_path || finalSavePath || undefined,
      });
      setApplyResult(result);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Apply start failed";
      setApplyResult({
        apply_id: "",
        mode,
        status: "error",
        submitted: false,
        paused_before_submit: false,
        message: msg,
        filled_fields: [],
      });
    } finally {
      setApplyBusy(false);
    }
  };

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
    setPdfPreviewUrl(getVersionPreviewUrl(versionId, userId));
    try {
      const v = await getVersion(versionId, userId);
      setActiveResume(v.full_resume as Record<string, unknown>);
    } catch {
      setPdfPreviewUrl(null);
    }
  };

  const activeVersion = versions.find((v) => v.id === activeVersionId);
  const evidenceCheck = (activeResume?.evidence_check || null) as
    | { ok?: boolean; passed?: boolean; notes?: string; issues?: string[] }
    | null;
  const formatCheck = (activeResume?.format_check || null) as { fabrication?: boolean } | null;
  const evidencePassed =
    evidenceCheck == null
      ? true
      : evidenceCheck.passed !== false && evidenceCheck.ok !== false;
  const canConfirm =
    evidencePassed && formatCheck?.fabrication !== true && activeResume?.requires_fix !== true;

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
          <span className="text-sm font-bold text-slate-950">Tailor</span>
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
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={pasteInput}
                onChange={(e) => setPasteInput(e.target.value)}
                placeholder="Paste JD text…"
                className="h-8 w-64 rounded-lg border border-slate-200 px-3 text-xs outline-none focus:border-emerald-400 sm:w-80"
                autoFocus
              />
              <button
                type="button"
                onClick={() => void handlePasteJd()}
                disabled={!pasteInput.trim()}
                className="h-8 rounded-lg bg-emerald-600 px-3 text-xs font-semibold text-white disabled:opacity-50"
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
          )}
        </div>

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
            data-testid="confirm-version"
            onClick={() => void handleConfirm()}
            disabled={!activeVersionId || activeVersion?.is_confirmed || confirming || !canConfirm}
            className="h-8 rounded-lg bg-emerald-600 px-3 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-40"
          >
            {confirming ? "…" : activeVersion?.is_confirmed ? "Confirmed" : "Confirm"}
          </button>
          <button
            type="button"
            onClick={() => void handleExport("docx")}
            disabled={!activeVersion?.is_confirmed || !!exporting}
            className="h-8 rounded-lg border border-slate-200 px-3 text-xs font-semibold text-slate-700 disabled:opacity-40"
          >
            DOCX
          </button>
          <button
            type="button"
            onClick={() => void handleExport("pdf")}
            disabled={!activeVersion?.is_confirmed || !!exporting}
            className="h-8 rounded-lg bg-slate-900 px-3 text-xs font-semibold text-white disabled:opacity-40"
          >
            PDF
          </button>
        </div>
      </header>

      {finalSavePath ? (
        <div className="shrink-0 bg-emerald-50 px-4 py-1.5 text-center text-[11px] font-semibold text-emerald-800">
          Saved: {finalSavePath}
        </div>
      ) : null}

      {/* Left: Agent | Right: Qualification + PDF (one scroll column) */}
      <div className="grid min-h-0 w-full flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)]">
        <div className="min-h-[360px] overflow-hidden lg:min-h-0 lg:h-full">
          <WorkspaceChat onSend={handleAgent} loading={rewriting || analyzing} bootNotice={bootNotice} />
        </div>

        <div
          className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto overscroll-contain [scrollbar-gutter:stable] lg:h-full"
          data-testid="right-scroll-column"
        >
          <JdPanel
            jdText={jdText}
            keywordMatches={keywordMatches}
            loading={analyzing}
            expandContent
          />
          <div className="min-h-[640px] shrink-0 pb-3" data-testid="resume-preview">
            <ResumePreviewSection
              pdfPreviewUrl={pdfPreviewUrl}
              numPages={numPages}
              onLoadSuccess={({ numPages: n }) => setNumPages(n)}
              resume={activeResume}
              wide
              busy={analyzing || rewriting}
            />
          </div>
          <ApplyModePanel
            visible={!!activeVersionId}
            busy={applyBusy || !activeVersion?.is_confirmed}
            status={
              applyResult?.status
              || (!activeVersion?.is_confirmed ? "waiting_confirm" : null)
            }
            message={
              applyResult?.message
              || (!activeVersion?.is_confirmed
                ? "Confirm this version first to unlock Manual / Auto apply."
                : null)
            }
            pausedBeforeSubmit={!!applyResult?.paused_before_submit}
            onManual={() => {
              if (!activeVersion?.is_confirmed) return;
              void handleStartApply("manual");
            }}
            onAuto={() => {
              if (!activeVersion?.is_confirmed) return;
              void handleStartApply("auto");
            }}
          />
        </div>
      </div>
    </div>
  );
}

function ResumePreviewSection({
  pdfPreviewUrl,
  numPages,
  onLoadSuccess,
  resume,
  wide = false,
  busy = false,
}: {
  pdfPreviewUrl: string | null;
  numPages: number | null;
  onLoadSuccess: (info: { numPages: number }) => void;
  resume: Record<string, unknown> | null;
  wide?: boolean;
  busy?: boolean;
}) {
  // Native browser PDF viewer — avoids react-pdf worker crashes on large Word PDFs.
  if (pdfPreviewUrl) {
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
      <div className="flex min-h-[420px] w-full flex-col items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
        <p className="text-sm font-semibold text-slate-800">
          {busy ? "Generating tailored resume…" : "No resume preview yet"}
        </p>
        <p className="mt-1 max-w-sm text-xs text-slate-500">
          {busy
            ? "Injecting content into your locked master DOCX and exporting PDF…"
            : "Open a job to auto-generate, or chat with the agent to create a tailored version."}
        </p>
      </div>
    );
  }

  return (
    <div data-testid="html-preview-fallback">
      <p className="mb-2 text-center text-[10px] text-amber-700">
        Master PDF unavailable — structured fallback (Confirm DOCX still uses locked master)
      </p>
      <ResumeHtmlPreview resume={resume} />
    </div>
  );
}

function ResumeHtmlPreview({ resume }: { resume: Record<string, unknown> }) {
  const r = resume;
  const candidateName = r.candidate_name as string | undefined;
  const contactLine = r.contact_line as string | undefined;
  const summary = r.summary as string | undefined;
  const education = r.education as Array<Record<string, unknown>> | undefined;
  const experiences = r.experiences as Array<Record<string, unknown>> | undefined;
  const projects = r.projects as Array<Record<string, unknown>> | undefined;
  const skillsCerts = r.skills_certifications as string | undefined;

  return (
    <div className="h-full w-full overflow-auto rounded-2xl border border-slate-200 bg-slate-50 p-3">
      <p className="mb-2 text-center text-[10px] text-slate-400">
        Structured preview (Confirm → DOCX uses locked master template)
      </p>
      <div className="mx-auto min-h-[900px] w-full max-w-[640px] bg-white px-10 py-8 text-slate-950 shadow-sm ring-1 ring-slate-200">
        {(candidateName || contactLine) && (
          <header className="mb-3 text-center">
            {candidateName && (
              <h1 className="text-[14pt] font-bold uppercase tracking-wide">{candidateName}</h1>
            )}
            {contactLine && <p className="mt-1 text-[10pt] text-slate-700">{contactLine}</p>}
          </header>
        )}
        {summary && <p className="mb-3 text-[10pt] leading-5 text-slate-800">{summary}</p>}
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
              <div key={i} className="mb-2">
                <p className="text-[10pt] font-bold">
                  {[exp.title, exp.company].filter(Boolean).join(" | ")}
                </p>
                <ul className="ml-3 text-[10pt] leading-5">
                  {(exp.bullets as Array<{ text: string }> | undefined)?.slice(0, 3).map((b, j) => (
                    <li key={j}>• {b.text}</li>
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
              <div key={i} className="mb-1.5 text-[10pt]">
                <p className="font-bold">{proj.name as string}</p>
              </div>
            ))}
          </section>
        )}
        {skillsCerts && (
          <section>
            <h4 className="mb-1 border-b border-slate-300 pb-0.5 text-[10pt] font-bold uppercase">
              Skills & Certifications
            </h4>
            <p className="text-[10pt] leading-5">{skillsCerts}</p>
          </section>
        )}
      </div>
    </div>
  );
}
