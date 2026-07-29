"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import type { KeywordMatchItem, VersionItem } from "@/lib/api";
import {
  createJdSession,
  analyzeJd,
  rewriteResume,
  confirmVersion,
  getVersion,
  exportVersion,
  getVersionPreviewUrl,
  uploadTemplate,
  getActiveTemplate,
} from "@/lib/api";
import JdPanel from "@/components/jd-panel";
import WorkspaceChat from "@/components/workspace-chat";
import VersionTabs from "@/components/version-tabs";
import KeywordGapSection from "@/components/keyword-gap-section";

pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.mjs`;

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

const MOCK_JD = `Software Engineer - Backend Infrastructure

About the role:
We are looking for a talented backend infrastructure engineer to join our growing team. You will design and build scalable systems that power our core platform.

Requirements:
• 5+ years of experience in backend development
• Strong proficiency in Python or Go
• Experience with distributed systems and microservice architecture
• Hands-on experience with Kafka or similar message queue systems
• Deep understanding of SQL and NoSQL databases (PostgreSQL, Redis)
• Experience with Kubernetes and Docker containerization
• Strong problem-solving and communication skills

Preferred:
• Experience with real-time data processing
• Knowledge of CI/CD pipelines and infrastructure as code
• Experience leading technical projects
• Familiarity with machine learning pipelines`;

export default function ResumeWorkspace({ userId, initialJobId }: ResumeWorkspaceProps) {
  const [jdText, setJdText] = useState(MOCK_JD);
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
  const [templateInfo, setTemplateInfo] = useState<{ filename: string; block_count: number } | null>(null);
  const [uploadingTemplate, setUploadingTemplate] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const initSession = useCallback(async (text: string) => {
    setAnalyzing(true);
    try {
      const session = await createJdSession(userId, text, initialJobId);
      setSessionId(session.session_id);
      setJdText(text);
      const analysis = await analyzeJd(session.session_id);
      setKeywordMatches(analysis.keyword_matches);
    } catch {
      setSessionId("mock-session-" + Date.now());
    } finally {
      setAnalyzing(false);
    }
  }, [userId, initialJobId]);

  useEffect(() => {
    if (!initialized) {
      setInitialized(true);
      initSession(MOCK_JD);
      getActiveTemplate(userId).then((t) => {
        if (t) setTemplateInfo({ filename: t.filename, block_count: t.block_count });
      }).catch(() => {});
    }
  }, [initialized, initSession, userId]);

  const handlePasteJd = async () => {
    if (!pasteInput.trim()) return;
    setJdText(pasteInput.trim());
    setShowPasteInput(false);
    setPasteInput("");
    setVersions([]);
    setActiveVersionId(null);
    setActiveResume(null);
    setPdfPreviewUrl(null);
    await initSession(pasteInput.trim());
  };

  const handleRewrite = async (instruction: string) => {
    if (!sessionId) return;
    setRewriting(true);
    try {
      const result = await rewriteResume(userId, sessionId, instruction, activeVersionId || undefined);
      setKeywordMatches(result.keyword_matches);
      const resumeData = result.full_resume as Record<string, unknown>;
      setActiveResume(resumeData);

      const v: VersionItem = {
        id: result.new_version_id,
        version_index: result.version_index,
        is_confirmed: false,
        created_at: new Date().toISOString(),
      };

      setVersions((prev) => {
        const existing = prev.find((x) => x.id === v.id);
        if (existing) return prev;
        const updated = [...prev, v].sort((a, b) => a.version_index - b.version_index);
        if (updated.length > 5) updated.shift();
        return updated;
      });

      setActiveVersionId(result.new_version_id);
      setPdfPreviewUrl(getVersionPreviewUrl(result.new_version_id, userId));
    } catch {
    } finally {
      setRewriting(false);
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

  const handleConfirm = async (versionId: string) => {
    setConfirming(true);
    try {
      await confirmVersion(versionId, userId);
      setVersions((prev) =>
        prev.map((v) => (v.id === versionId ? { ...v, is_confirmed: true } : v))
      );
    } catch {
    } finally {
      setConfirming(false);
    }
  };

  const handleExport = async (format: "pdf" | "docx" | "text") => {
    if (!activeVersionId || exporting) return;
    setExporting(format);
    try {
      const blob = await exportVersion(activeVersionId, userId, format);
      downloadBlob(blob, `resume-v${versions.find((v) => v.id === activeVersionId)?.version_index || 1}.${format}`);
    } catch {
      alert("Export failed");
    } finally {
      setExporting(null);
    }
  };

  const handleSuggestProject = (keyword: string) => {
    handleRewrite(`Suggest project ideas to develop skills for: ${keyword}`);
  };

  const handleTemplateUpload = async (file: File) => {
    if (uploadingTemplate) return;
    setUploadingTemplate(true);
    try {
      const result = await uploadTemplate(userId, file);
      setTemplateInfo({ filename: result.filename, block_count: result.block_count });
    } catch {
      alert("Template upload failed");
    } finally {
      setUploadingTemplate(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleTemplateUpload(file);
    e.target.value = "";
  };

  const activeVersion = versions.find((v) => v.id === activeVersionId);

  return (
    <div className="flex min-w-0 flex-1 flex-col bg-[#eef2f7]">
      <TopToolbar
        sessionId={sessionId}
        initialJobId={initialJobId}
        showPasteInput={showPasteInput}
        pasteInput={pasteInput}
        onTogglePaste={() => setShowPasteInput(!showPasteInput)}
        onPasteInputChange={setPasteInput}
        onPasteJd={handlePasteJd}
        activeVersion={activeVersion}
        exporting={exporting}
        onExport={handleExport}
        templateInfo={templateInfo}
        uploadingTemplate={uploadingTemplate}
        onTemplateUpload={handleTemplateUpload}
        fileInputRef={fileInputRef}
        onFileChange={handleFileChange}
      />

      <div className="flex-1 overflow-auto p-4">
        <div className="mx-auto flex max-w-[1400px] flex-col gap-4">
          <div className="flex gap-4">
            <div className="flex w-[42%] min-w-0 flex-col gap-4">
              <JdPanel jdText={jdText} keywordMatches={keywordMatches} loading={analyzing} />
              <WorkspaceChat onSend={handleRewrite} loading={rewriting} />
            </div>

            <div className="flex w-[58%] min-w-0 flex-col gap-4">
              <VersionTabs
                versions={versions}
                activeVersionId={activeVersionId}
                onSelect={handleSelectVersion}
                onConfirm={handleConfirm}
                loading={confirming}
              />
              <ResumePreviewSection
                pdfPreviewUrl={pdfPreviewUrl}
                numPages={numPages}
                onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                resume={activeResume}
              />
            </div>
          </div>

          <KeywordGapSection keywordMatches={keywordMatches} onSuggest={handleSuggestProject} userId={userId} versionId={activeVersionId} />
        </div>
      </div>
    </div>
  );
}

function TopToolbar({
  sessionId, initialJobId, showPasteInput, pasteInput,
  onTogglePaste, onPasteInputChange, onPasteJd,
  activeVersion, exporting, onExport,
  templateInfo, uploadingTemplate, onTemplateUpload, fileInputRef, onFileChange,
}: {
  sessionId: string | null;
  initialJobId?: string;
  showPasteInput: boolean;
  pasteInput: string;
  onTogglePaste: () => void;
  onPasteInputChange: (v: string) => void;
  onPasteJd: () => void;
  activeVersion: VersionItem | undefined;
  exporting: "pdf" | "docx" | "text" | null;
  onExport: (format: "pdf" | "docx" | "text") => void;
  templateInfo: { filename: string; block_count: number } | null;
  uploadingTemplate: boolean;
  onTemplateUpload: (file: File) => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <div className="flex items-center justify-between border-b border-slate-200 bg-white/95 px-6 py-3 shadow-sm backdrop-blur">
      <div className="flex items-center gap-3">
        {initialJobId ? (
          <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700 ring-1 ring-blue-200">
            Associated: Software Engineer @ TechCorp
          </span>
        ) : sessionId ? (
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
            JD Active
          </span>
        ) : null}

        {!showPasteInput ? (
          <button onClick={onTogglePaste} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50">
            + Paste New JD
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="text" value={pasteInput} onChange={(e) => onPasteInputChange(e.target.value)}
              placeholder="Paste JD text..." className="h-8 w-80 rounded-lg border border-slate-200 bg-slate-50 px-3 text-xs outline-none focus:border-blue-400" autoFocus
            />
            <button onClick={onPasteJd} disabled={!pasteInput.trim()} className="h-8 rounded-lg bg-blue-600 px-3 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50">Analyze</button>
            <button onClick={onTogglePaste} className="h-8 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600 hover:bg-slate-50">Cancel</button>
          </div>
        )}

        <input ref={fileInputRef} type="file" accept=".docx" onChange={onFileChange} className="hidden" />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadingTemplate}
          className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
        >
          {templateInfo ? "Re-upload Template" : "Upload .docx Template"}
        </button>
        {templateInfo && (
          <span className="text-[11px] text-slate-400" title={`${templateInfo.block_count} editable blocks`}>
            Template: {templateInfo.filename}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {activeVersion && (
          <span className="text-xs text-slate-400">
            v{activeVersion.version_index}{activeVersion.is_confirmed ? " ✓" : ""}
          </span>
        )}
        <button onClick={() => onExport("text")} disabled={!activeVersion?.is_confirmed || !!exporting}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50">
          {exporting === "text" ? "..." : "Copy Text"}
        </button>
        <button onClick={() => onExport("docx")} disabled={!activeVersion?.is_confirmed || !!exporting}
          className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-600 hover:bg-blue-100 disabled:opacity-50">
          {exporting === "docx" ? "..." : "DOCX"}
        </button>
        <button onClick={() => onExport("pdf")} disabled={!activeVersion?.is_confirmed || !!exporting}
          className="rounded-lg bg-slate-950 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-slate-800 disabled:opacity-50">
          {exporting === "pdf" ? "..." : "Export PDF"}
        </button>
      </div>
    </div>
  );
}

function ResumePreviewSection({
  pdfPreviewUrl, numPages, onLoadSuccess, resume,
}: {
  pdfPreviewUrl: string | null;
  numPages: number | null;
  onLoadSuccess: (info: { numPages: number }) => void;
  resume: Record<string, unknown> | null;
}) {
  if (pdfPreviewUrl) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="w-full bg-slate-50 px-4 py-2 border-b border-slate-100 flex items-center justify-between">
          <span className="text-[11px] font-medium text-slate-500">PDF Preview</span>
          {numPages && <span className="text-[11px] text-slate-400">{numPages} page{numPages > 1 ? "s" : ""}</span>}
        </div>
        <div className="flex-1 overflow-auto p-4 flex justify-center">
          <Document file={pdfPreviewUrl} onLoadSuccess={onLoadSuccess} loading={<div className="py-12 text-sm text-slate-400">Loading PDF...</div>} error={<div className="py-12 text-sm text-slate-400">PDF preview unavailable</div>}>
            <Page pageNumber={1} width={600} renderTextLayer={false} renderAnnotationLayer={false} />
          </Document>
        </div>
      </div>
    );
  }

  if (!resume) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-2xl border border-slate-200 bg-white p-12 text-center">
        <div>
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-blue-600">
            <span className="text-lg font-bold">PDF</span>
          </div>
          <h3 className="text-base font-medium text-gray-900">No resume version yet</h3>
          <p className="mt-1 text-sm text-gray-500">Use the chat to rewrite your resume for this job.</p>
        </div>
      </div>
    );
  }

  return <ResumeHtmlPreview resume={resume} />;
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
    <div className="mx-auto min-h-[1056px] w-full max-w-[816px] bg-white px-14 py-12 text-slate-950 shadow-[0_30px_80px_rgba(15,23,42,0.16)] ring-1 ring-slate-200">
      {(candidateName || contactLine) && (
        <header className="mb-3 text-center">
          {candidateName && <h1 className="text-[15pt] font-bold uppercase tracking-wide text-slate-950">{candidateName}</h1>}
          {contactLine && <p className="mt-1 text-[10pt] text-slate-700">{contactLine}</p>}
        </header>
      )}
      {summary && <p className="mb-4 text-[10pt] leading-5 text-slate-800 text-justify">{summary}</p>}
      {education && education.length > 0 && (
        <section className="mb-4">
          <h4 className="mb-1.5 border-b border-slate-300 pb-1 text-[10pt] font-bold uppercase tracking-wider text-slate-950">EDUCATION</h4>
          {education.map((edu, i) => (
            <div key={i} className="mb-1.5 text-[10pt] leading-5 text-slate-800">
              <div className="flex justify-between gap-4">
                <p className="font-bold text-slate-950">{edu.institution as string}</p>
                {edu.date_range && <p className="shrink-0 text-slate-700">{edu.date_range as string}</p>}
              </div>
              {[edu.degree, edu.field].filter(Boolean).join(" in ") && (
                <p className="text-justify">{[edu.degree, edu.field].filter(Boolean).join(" in ")}</p>
              )}
            </div>
          ))}
        </section>
      )}
      {experiences && experiences.length > 0 && (
        <section className="mb-4">
          <h4 className="mb-1.5 border-b border-slate-300 pb-1 text-[10pt] font-bold uppercase tracking-wider text-slate-950">PROFESSIONAL EXPERIENCE</h4>
          {experiences.map((exp, i) => (
            <div key={i} className="mb-3">
              <div className="mb-0.5 flex items-baseline justify-between gap-4">
                <p className="text-[10pt] font-bold text-slate-950">{[exp.title, exp.company].filter(Boolean).join(" | ")}</p>
                {exp.date_range && <span className="shrink-0 text-[10pt] text-slate-500">{exp.date_range as string}</span>}
              </div>
              <ul className="ml-4 text-[10pt] leading-5 text-slate-800">
                {(exp.bullets as Array<{ text: string }> | undefined)?.slice(0, 3).map((bullet, j) => (
                  <li key={j} className="text-justify">• {bullet.text}</li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}
      {projects && projects.length > 0 && (
        <section className="mb-4">
          <h4 className="mb-1.5 border-b border-slate-300 pb-1 text-[10pt] font-bold uppercase tracking-wider text-slate-950">PROJECTS</h4>
          {projects.map((proj, i) => (
            <div key={i} className="mb-2">
              <p className="text-[10pt] font-bold text-slate-950">{[proj.name, (proj.tools as string[] | undefined)?.join(", ")].filter(Boolean).join(" | ")}</p>
              {(proj.bullets as Array<{ text: string }> | undefined)?.slice(0, 2).map((bullet, j) => (
                <p key={j} className="ml-4 text-[10pt] leading-5 text-slate-800 text-justify">• {bullet.text}</p>
              ))}
            </div>
          ))}
        </section>
      )}
      {skillsCerts && (
        <section>
          <h4 className="mb-1.5 border-b border-slate-300 pb-1 text-[10pt] font-bold uppercase tracking-wider text-slate-950">SKILLS & CERTIFICATIONS</h4>
          <p className="text-[10pt] leading-5 text-slate-800 text-justify">{skillsCerts}</p>
        </section>
      )}
    </div>
  );
}
