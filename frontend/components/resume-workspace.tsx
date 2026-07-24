"use client";

import { useMemo, useState } from "react";
import { exportDraft, exportText, KeyMapItem } from "@/lib/api";

interface Experience {
  company: string;
  title: string;
  location?: string;
  date_range: string;
  bullets: { text: string; evidence_from?: string }[];
  skills_highlighted?: string[];
}

interface Project {
  name: string;
  description?: string;
  tools?: string[];
  context?: string;
  date_range?: string;
  bullets?: { text: string; evidence_from?: string }[];
  skills?: string[];
}

interface Competition {
  name: string;
  role?: string;
  location?: string;
  date_range?: string;
  bullets?: { text: string; evidence_from?: string }[];
}

interface TailoredResumeData {
  candidate_name?: string;
  contact_line?: string;
  summary?: string;
  skills?: string[];
  skills_certifications?: string;
  experiences?: Experience[];
  projects?: Project[];
  competitions?: Competition[];
  education?: { institution: string; degree: string; field?: string; location?: string; date_range?: string; coursework?: string[] }[];
  certifications?: string[];
  tailoring_summary?: string;
  ats_score_estimate?: number | null;
}

interface WorkspaceState {
  tailored_resume?: TailoredResumeData;
  tailored_resume_id?: string;
  draft_id?: string;
  revision_id?: string;
  markdown?: string;
  key_map?: KeyMapItem[];
}

interface ResumeWorkspaceProps {
  userId: string;
  workspaceState?: unknown;
}

function normalizeState(value: unknown): WorkspaceState | undefined {
  if (!value) return undefined;
  const maybe = value as WorkspaceState;
  if (maybe.tailored_resume || maybe.key_map || maybe.draft_id) return maybe;
  return { tailored_resume: value as TailoredResumeData };
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function HighlightText({ text, terms }: { text?: string; terms: string[] }) {
  if (!text) return null;
  const cleanTerms = terms.filter((term) => term && term.length > 2).slice(0, 20);
  if (!cleanTerms.length) return <>{text}</>;
  const pattern = new RegExp(`(${cleanTerms.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, idx) =>
        cleanTerms.some((term) => term.toLowerCase() === part.toLowerCase()) ? (
          <mark key={idx} className="rounded bg-amber-200 px-0.5 text-gray-950">
            {part}
          </mark>
        ) : (
          <span key={idx}>{part}</span>
        )
      )}
    </>
  );
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

function entryHeading(left?: string, middle?: string, location?: string, dateRange?: string) {
  const first = [left, middle].filter(Boolean).join(" | ");
  const second = [location, dateRange].filter(Boolean).join(" - ");
  return [first, second].filter(Boolean).join(" ");
}

function bulletText(bullet: unknown) {
  if (typeof bullet === "object" && bullet && "text" in bullet) {
    return String((bullet as { text?: string }).text || "");
  }
  return String(bullet || "");
}

export default function ResumeWorkspace({ userId, workspaceState }: ResumeWorkspaceProps) {
  const state = normalizeState(workspaceState);
  const resume = state?.tailored_resume;
  const keyMap = state?.key_map || [];
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState<"pdf" | "docx" | "text" | null>(null);

  const highlightTerms = useMemo(() => {
    const terms = new Set<string>();
    for (const item of keyMap) {
      if (item.status !== "missing") {
        item.highlight_terms?.forEach((term) => terms.add(term));
      }
    }
    return Array.from(terms);
  }, [keyMap]);

  const hasNoResumeWarning =
    resume &&
    (!Array.isArray(resume.experiences) || resume.experiences.length === 0) &&
    resume.ats_score_estimate === null;

  const handleCopyText = async () => {
    if (!resume || exporting) return;
    setExporting("text");
    try {
      const result = await exportText(resume);
      await navigator.clipboard.writeText(result.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Export failed";
      alert("Copy failed: " + msg);
    } finally {
      setExporting(null);
    }
  };

  const handleExport = async (format: "pdf" | "docx") => {
    if (!state?.draft_id || exporting) return;
    setExporting(format);
    try {
      const blob = await exportDraft(userId, state.draft_id, format);
      downloadBlob(blob, `tailored-resume.${format}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Export failed";
      alert("Export failed: " + msg);
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="flex min-w-0 flex-1 flex-col bg-[#eef2f7]">
      <div className="flex items-center justify-between border-b border-slate-200 bg-white/95 px-6 py-3 shadow-sm backdrop-blur">
        <div>
          <h2 className="text-[15px] font-bold tracking-tight text-slate-950">Resume Workspace</h2>
          <p className="text-xs text-slate-500">
            {state?.revision_id ? `Draft ${state.draft_id?.slice(0, 8)} · Revision ${state.revision_id.slice(0, 8)}` : "PDF-style resume preview"}
          </p>
        </div>
        {resume && !hasNoResumeWarning && (
          <div className="flex gap-2">
            <button
              onClick={handleCopyText}
              disabled={!!exporting}
              className="rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"
            >
              {copied ? "Copied" : exporting === "text" ? "Copying..." : "Copy Text"}
            </button>
            <button
              onClick={() => handleExport("docx")}
              disabled={!state?.draft_id || !!exporting}
              className="rounded-xl border border-blue-200 bg-blue-50 px-3.5 py-2 text-xs font-semibold text-blue-700 shadow-sm hover:bg-blue-100 disabled:opacity-50"
            >
              {exporting === "docx" ? "Exporting..." : "Export Word"}
            </button>
            <button
              onClick={() => handleExport("pdf")}
              disabled={!state?.draft_id || !!exporting}
              className="rounded-xl bg-slate-950 px-3.5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-slate-800 disabled:opacity-50"
            >
              {exporting === "pdf" ? "Exporting..." : "Export PDF"}
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto p-6">
        {!resume ? (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-blue-50 text-blue-600">
                <span className="text-2xl">PDF</span>
              </div>
              <h3 className="text-lg font-medium text-gray-900">No resume draft yet</h3>
              <p className="mt-1 text-sm text-gray-500">Upload your resume, paste a JD, then edit the generated draft with the agent.</p>
            </div>
          </div>
        ) : hasNoResumeWarning ? (
          <div className="mx-auto max-w-xl rounded-2xl border border-amber-200 bg-white p-8 text-center shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900">Resume Required</h3>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-600">
              {String(resume.tailoring_summary || "Upload your original resume before tailoring.")}
            </p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-[1080px] flex-col gap-5">
            <aside className="rounded-3xl border border-slate-200 bg-white/95 p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-950">JD Key Match</h3>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">
                  {keyMap.filter((item) => item.status === "matched").length}/{keyMap.length} matched
                </span>
              </div>
              <div className="flex gap-3 overflow-x-auto pb-1">
                {keyMap.length ? keyMap.map((item, idx) => (
                  <div key={idx} className="min-w-[260px] max-w-[300px] rounded-2xl border border-slate-100 bg-slate-50 p-3">
                    <div className="mb-1 flex items-center gap-2">
                      <span className={`h-2 w-2 rounded-full ${item.status === "matched" ? "bg-green-500" : item.status === "partial" ? "bg-amber-500" : "bg-gray-300"}`} />
                      <span className="text-[11px] font-bold uppercase tracking-wide text-slate-500">{item.status}</span>
                    </div>
                    <p className="line-clamp-2 text-xs font-semibold text-slate-950">JD: {item.jd_key}</p>
                    <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-slate-600">Resume: {item.resume_phrase}</p>
                    <p className="mt-1 text-[11px] text-slate-500">{item.note}</p>
                  </div>
                )) : (
                  <p className="text-sm text-gray-500">Key matches will appear after JD parsing.</p>
                )}
              </div>
            </aside>

            <section className="mx-auto min-h-[1120px] w-full max-w-[900px] bg-white px-16 py-14 text-slate-950 shadow-[0_30px_80px_rgba(15,23,42,0.16)] ring-1 ring-slate-200 print:shadow-none">
              {(resume.candidate_name || resume.contact_line) && (
                <header className="mb-4 text-center">
                  {resume.candidate_name && (
                    <h1 className="text-[19px] font-bold uppercase tracking-wide text-slate-950">
                      <HighlightText text={resume.candidate_name} terms={highlightTerms} />
                    </h1>
                  )}
                  {resume.contact_line && (
                    <p className="mt-1 text-[12px] text-slate-700">
                      <HighlightText text={resume.contact_line} terms={highlightTerms} />
                    </p>
                  )}
                </header>
              )}

              {resume.summary && (
                <p className="mb-5 text-[13.5px] leading-6 text-slate-800">
                  <HighlightText text={String(resume.summary)} terms={highlightTerms} />
                </p>
              )}

              {Array.isArray(resume.education) && resume.education.length > 0 && (
                <section className="mb-5">
                  <h4 className="mb-2 border-b border-slate-300 pb-1 text-[13px] font-bold uppercase tracking-[0.18em] text-slate-950">EDUCATION</h4>
                  {resume.education.map((edu, i) => (
                    <div key={i} className="mb-2 break-inside-avoid text-[13px] leading-5 text-slate-800">
                      <div className="flex justify-between gap-4">
                        <p className="font-bold text-slate-950"><HighlightText text={edu.institution} terms={highlightTerms} /></p>
                        {edu.date_range && <p className="shrink-0 text-slate-700"><HighlightText text={edu.date_range} terms={highlightTerms} /></p>}
                      </div>
                      <p><HighlightText text={[edu.degree, edu.field, edu.location].filter(Boolean).join(" ")} terms={highlightTerms} /></p>
                      {Array.isArray(edu.coursework) && edu.coursework.length > 0 && (
                        <p className="ml-3">• Coursework: <HighlightText text={edu.coursework.join(" | ")} terms={highlightTerms} /></p>
                      )}
                    </div>
                  ))}
                </section>
              )}

              {Array.isArray(resume.experiences) && resume.experiences.length > 0 && (
                <section className="mb-5">
                  <h4 className="mb-2 border-b border-slate-300 pb-1 text-[13px] font-bold uppercase tracking-[0.18em] text-slate-950">PROFESSIONAL EXPERIENCE</h4>
                  {resume.experiences.map((exp, i) => (
                    <div key={i} className="mb-3 break-inside-avoid">
                      <div className="mb-1 flex items-baseline justify-between gap-4">
                        <p className="text-[13px] font-bold text-slate-950">
                          <HighlightText text={entryHeading(exp.title, exp.company, exp.location, undefined)} terms={highlightTerms} />
                        </p>
                        {exp.date_range && <span className="shrink-0 text-[12px] text-slate-500">{exp.date_range}</span>}
                      </div>
                      <ul className="ml-4 list-disc space-y-1 text-[13px] leading-5 text-slate-800">
                        {exp.bullets.slice(0, 3).map((bullet, j) => (
                          <li key={j}>
                            <HighlightText text={bullet.text} terms={highlightTerms} />
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </section>
              )}

              {Array.isArray(resume.projects) && resume.projects.length > 0 && (
                <section className="mb-5">
                  <h4 className="mb-2 border-b border-slate-300 pb-1 text-[13px] font-bold uppercase tracking-[0.18em] text-slate-950">PROJECTS</h4>
                  {resume.projects.map((proj, i) => (
                    <div key={i} className="mb-3 break-inside-avoid">
                      <p className="text-[13px] font-bold text-slate-950">
                        <HighlightText text={entryHeading(proj.name, (proj.tools || proj.skills || []).join(", "), proj.context || "Independent Project", proj.date_range)} terms={highlightTerms} />
                      </p>
                      {Array.isArray(proj.bullets) && proj.bullets.length > 0 ? (
                        <ul className="ml-4 mt-1 list-disc space-y-1 text-[13px] leading-5 text-slate-800">
                          {proj.bullets.slice(0, 3).map((bullet, j) => (
                            <li key={j}><HighlightText text={bulletText(bullet)} terms={highlightTerms} /></li>
                          ))}
                        </ul>
                      ) : proj.description ? (
                        <p className="mt-1 text-[13px] leading-5 text-slate-800"><HighlightText text={proj.description} terms={highlightTerms} /></p>
                      ) : null}
                    </div>
                  ))}
                </section>
              )}

              {Array.isArray(resume.competitions) && resume.competitions.length > 0 && (
                <section className="mb-5">
                  <h4 className="mb-2 border-b border-slate-300 pb-1 text-[13px] font-bold uppercase tracking-[0.18em] text-slate-950">COMPETITIONS</h4>
                  {resume.competitions.map((comp, i) => (
                    <div key={i} className="mb-2 break-inside-avoid">
                      <p className="text-[13px] font-bold text-slate-950">
                        <HighlightText text={entryHeading(comp.name, comp.role, comp.location, comp.date_range)} terms={highlightTerms} />
                      </p>
                      {Array.isArray(comp.bullets) && comp.bullets.length > 0 && (
                        <ul className="ml-4 mt-1 list-disc space-y-1 text-[13px] leading-5 text-slate-800">
                          {comp.bullets.map((bullet, j) => (
                            <li key={j}><HighlightText text={bulletText(bullet)} terms={highlightTerms} /></li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </section>
              )}

              {(resume.skills_certifications || (Array.isArray(resume.skills) && resume.skills.length > 0)) && (
                <section className="mb-5">
                  <h4 className="mb-2 border-b border-slate-300 pb-1 text-[13px] font-bold uppercase tracking-[0.18em] text-slate-950">SKILLS & CERTIFICATIONS</h4>
                  <p className="text-[13px] leading-5 text-slate-800">
                    <HighlightText text={resume.skills_certifications || [...(resume.skills || []), ...(resume.certifications || [])].join(", ")} terms={highlightTerms} />
                  </p>
                </section>
              )}

            </section>
          </div>
        )}
      </div>
    </div>
  );
}
