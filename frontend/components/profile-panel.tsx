"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  activateTemplate,
  getActiveTemplate,
  getCandidateLibrary,
  listTemplates,
  resetCandidateLibrary,
  updateCandidateLibrary,
  uploadTemplate,
  type ActiveTemplate,
  type TemplateVersionItem,
} from "@/lib/api";

interface ProfilePanelProps {
  userId: string;
  displayName?: string;
  email?: string;
}

type Exp = {
  company?: string;
  title?: string;
  location?: string;
  date_range?: string;
  github_url?: string;
  evidence_url?: string;
  tags?: string[];
  bullets?: Array<{ text?: string; evidence_from?: string; original_text?: string }>;
};

type Proj = {
  name?: string;
  tools?: string[];
  context?: string;
  date_range?: string;
  bullets?: Array<{ text?: string; evidence_from?: string; original_text?: string }>;
};

type Edu = {
  institution?: string;
  degree?: string;
  field?: string;
  location?: string;
  date_range?: string;
  coursework?: string[];
};

type EditSection = "identity" | "summary" | "education" | "experience" | "apply" | null;

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
      {children}
    </h2>
  );
}

function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-[#e8e8e4] bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)] ${className}`}
    >
      {children}
    </div>
  );
}

function EditLink({ onClick, label = "Edit" }: { onClick: () => void; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 text-xs font-semibold text-[#14352b] hover:opacity-70"
    >
      {label}
      <span aria-hidden>→</span>
    </button>
  );
}

function Field({
  label,
  value,
  onChange,
  multiline,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium text-slate-500">{label}</span>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          placeholder={placeholder}
          className="w-full resize-y rounded-lg border border-[#e8e8e4] bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#14352b]"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-9 w-full rounded-lg border border-[#e8e8e4] bg-white px-3 text-sm text-slate-800 outline-none focus:border-[#14352b]"
        />
      )}
    </label>
  );
}

function bulletsToText(bullets?: Array<{ text?: string }>) {
  return (bullets || []).map((b) => b.text || "").filter(Boolean).join("\n");
}

function textToBullets(text: string, prev?: Array<{ text?: string; evidence_from?: string; original_text?: string }>) {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  return lines.map((line, i) => {
    const old = prev?.[i];
    return {
      text: line,
      evidence_from: old?.evidence_from || `manual_${i + 1}`,
      original_text: old?.original_text || line,
    };
  });
}

function versionCounts(t: TemplateVersionItem): { roles: number; highlights: number } {
  const sections = t.resume_structure?.sections || [];
  const roles = sections.find((s) => s.type === "professional_experience")?.entries?.length || 0;
  const highlights = sections.reduce(
    (sum, s) => sum + (s.entries || []).reduce((n, e) => n + (e.bullets?.length || 0), 0),
    0
  );
  return { roles, highlights };
}

function completeness({
  hasResume,
  summary,
  education,
  experiences,
  apply,
}: {
  hasResume: boolean;
  summary: string;
  education: Edu[];
  experiences: Exp[];
  apply: Record<string, unknown>;
}) {
  const checks = [
    hasResume,
    Boolean(summary.trim()),
    education.length > 0,
    experiences.length > 0,
    Boolean(apply.email || apply.phone || apply.location),
  ];
  const done = checks.filter(Boolean).length;
  return Math.round((done / checks.length) * 100);
}

export default function ProfilePanel({ userId, displayName, email }: ProfilePanelProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<EditSection>(null);

  const [activeTemplate, setActiveTemplate] = useState<ActiveTemplate | null>(null);
  const [templates, setTemplates] = useState<TemplateVersionItem[]>([]);

  const [candidateName, setCandidateName] = useState("");
  const [contactLine, setContactLine] = useState("");
  const [summary, setSummary] = useState("");
  const [skills, setSkills] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [education, setEducation] = useState<Edu[]>([]);
  const [experiences, setExperiences] = useState<Exp[]>([]);
  const [projects, setProjects] = useState<Proj[]>([]);
  const [apply, setApply] = useState<Record<string, unknown>>({});

  const hydrate = useCallback((lib: Awaited<ReturnType<typeof getCandidateLibrary>>) => {
    const inv = lib.inventory || {};
    setCandidateName(String(inv.candidate_name || ""));
    setContactLine(String(inv.contact_line || ""));
    setSummary(String(inv.summary || ""));
    setSkills(String(inv.skills_certifications || ""));
    setGithubUrl(String(inv.github_url || lib.apply?.github_url || ""));
    setEducation(Array.isArray(inv.education) ? (inv.education as Edu[]) : []);
    setExperiences(Array.isArray(inv.experiences) ? (inv.experiences as Exp[]) : []);
    setProjects(Array.isArray(inv.projects) ? (inv.projects as Proj[]) : []);
    setApply(lib.apply || {});
  }, []);

  const refreshTemplates = useCallback(async () => {
    const [active, listed] = await Promise.all([
      getActiveTemplate(userId),
      listTemplates(userId).catch(() => ({ templates: [] as TemplateVersionItem[] })),
    ]);
    setActiveTemplate(active);
    setTemplates(listed.templates || []);
  }, [userId]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([getCandidateLibrary(userId), refreshTemplates()])
      .then(([lib]) => {
        if (!alive) return;
        hydrate(lib);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "Failed to load profile");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [userId, hydrate, refreshTemplates]);

  const buildInventory = () => ({
    candidate_name: candidateName,
    contact_line: contactLine,
    summary,
    skills_certifications: skills,
    github_url: githubUrl,
    education,
    experiences,
    projects,
  });

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const lib = await updateCandidateLibrary(userId, {
        inventory: buildInventory(),
        apply,
      });
      hydrate(lib);
      setMessage("Saved");
      setEdit(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("Reset library to the seeded master inventory?")) return;
    setSaving(true);
    try {
      const lib = await resetCandidateLibrary(userId);
      hydrate(lib);
      setMessage("Reset to default inventory");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setSaving(false);
    }
  };

  const handleUpload = async (file: File | undefined) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".docx")) {
      setError("Only .docx resumes are supported for the master template.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await uploadTemplate(userId, file);
      await refreshTemplates();
      setMessage(`Uploaded ${file.name}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleActivate = async (templateId: string) => {
    setSaving(true);
    setError(null);
    try {
      await activateTemplate(templateId, userId);
      await refreshTemplates();
      setMessage("Active resume version updated");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not switch version");
    } finally {
      setSaving(false);
    }
  };

  const setApplyField = (key: string, value: unknown) => {
    setApply((prev) => ({ ...prev, [key]: value }));
  };

  const name = candidateName || displayName || "Your profile";
  const contactEmail = String(apply.email || email || "");
  const location = String(apply.location || "");
  const pct = useMemo(
    () =>
      completeness({
        hasResume: Boolean(activeTemplate),
        summary,
        education,
        experiences,
        apply,
      }),
    [activeTemplate, summary, education, experiences, apply]
  );

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center bg-[#f7f7f5]" data-testid="profile-panel">
        <p className="text-sm text-slate-500">Loading profile…</p>
      </div>
    );
  }

  return (
    <div className="min-h-0 min-w-0 flex-1 overflow-y-auto bg-[#f7f7f5]" data-testid="profile-panel">
      <div className="mx-auto max-w-5xl px-5 py-8 pb-16">
        {(message || error) && (
          <div
            className={`mb-4 rounded-lg px-3 py-2 text-xs font-medium ${
              error ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-800"
            }`}
          >
            {error || message}
          </div>
        )}

        {/* Identity & documents */}
        <section className="mb-8">
          <SectionLabel>Identity &amp; documents</SectionLabel>
          <div className="grid gap-3 md:grid-cols-2">
            <Card>
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-[#14352b] text-sm font-semibold text-white">
                    {initials(name)}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="truncate text-base font-semibold text-slate-900">{name}</h3>
                      <span className="rounded-full bg-[#e8f2ec] px-2 py-0.5 text-[10px] font-semibold text-[#14352b]">
                        Open to work
                      </span>
                      <span className="rounded-full bg-[#fff1e6] px-2 py-0.5 text-[10px] font-semibold text-[#b45309]">
                        {pct}% complete
                      </span>
                    </div>
                    <p className="mt-2 space-y-0.5 text-xs text-slate-500">
                      {location ? <span className="block">{location}</span> : null}
                      {contactEmail ? <span className="block">{contactEmail}</span> : null}
                      {contactLine && !contactEmail ? <span className="block">{contactLine}</span> : null}
                    </p>
                  </div>
                </div>
                <EditLink onClick={() => setEdit(edit === "identity" ? null : "identity")} />
              </div>
              {edit === "identity" ? (
                <div className="mt-4 grid gap-3 border-t border-[#f0f0ec] pt-4 sm:grid-cols-2">
                  <Field label="Full name" value={candidateName} onChange={setCandidateName} />
                  <Field label="Contact line" value={contactLine} onChange={setContactLine} />
                  <Field
                    label="GitHub"
                    value={githubUrl}
                    onChange={(v) => {
                      setGithubUrl(v);
                      setApplyField("github_url", v);
                    }}
                  />
                  <div className="flex items-end gap-2 sm:col-span-2">
                    <button
                      type="button"
                      onClick={() => void handleSave()}
                      disabled={saving}
                      className="rounded-lg bg-[#14352b] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      {saving ? "Saving…" : "Save"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setEdit(null)}
                      className="rounded-lg px-3 py-2 text-xs font-semibold text-slate-500"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}
            </Card>

            <Card className="flex flex-col justify-between">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#f3f4f1] text-[#14352b]">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                    <path
                      d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"
                      stroke="currentColor"
                      strokeWidth="1.6"
                    />
                    <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.6" />
                  </svg>
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-semibold text-slate-900">Resume</h3>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    {activeTemplate
                      ? `${activeTemplate.filename} · ${activeTemplate.block_count} blocks`
                      : "Upload a .docx master template to unlock tailor & apply."}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  disabled={uploading}
                  onClick={() => fileRef.current?.click()}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#14352b] hover:opacity-70 disabled:opacity-50"
                  data-testid="profile-replace-resume"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
                    <path
                      d="M12 16V4m0 0 3.5 3.5M12 4 8.5 7.5M4 16.5V18a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1.5"
                      stroke="currentColor"
                      strokeWidth="1.7"
                      strokeLinecap="round"
                    />
                  </svg>
                  {uploading ? "Uploading…" : "Replace"}
                </button>
                <a href="/?view=resume" className="text-xs font-semibold text-[#14352b] hover:opacity-70">
                  Edit →
                </a>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  className="hidden"
                  onChange={(e) => {
                    void handleUpload(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
              </div>
            </Card>
          </div>
        </section>

        {/* Resume versions */}
        <section className="mb-8">
          <SectionLabel>
            Resume versions{" "}
            <span className="font-normal normal-case tracking-normal text-slate-400">
              (each upload keeps history — switch anytime)
            </span>
          </SectionLabel>
          <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2">
            {templates.map((t, idx) => {
              const isActive = t.is_active;
              const label =
                t.filename.replace(/\.docx$/i, "") || (idx === 0 ? "Default" : `Version ${templates.length - idx}`);
              const { roles, highlights } = versionCounts(t);
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    if (!isActive) void handleActivate(t.id);
                  }}
                  className={`w-56 shrink-0 snap-start rounded-xl border bg-white p-4 text-left shadow-[0_1px_2px_rgba(15,23,42,0.03)] transition-colors ${
                    isActive
                      ? "border-[#14352b] ring-1 ring-[#14352b]"
                      : "border-[#e8e8e4] hover:border-[#14352b]/40"
                  }`}
                  data-testid={`template-version-${t.id}`}
                >
                  <div className="mb-3 flex flex-wrap gap-1.5">
                    {isActive ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-[#e8f2ec] px-2 py-0.5 text-[10px] font-semibold text-[#14352b]">
                        <span className="h-1.5 w-1.5 rounded-full bg-[#14352b]" />
                        Editing
                      </span>
                    ) : null}
                    {idx === 0 ? (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                        Latest
                      </span>
                    ) : null}
                  </div>
                  <p className="truncate text-sm font-semibold text-slate-900">{label}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {roles} role{roles === 1 ? "" : "s"} · {highlights} highlight{highlights === 1 ? "" : "s"}
                  </p>
                  <p className="mt-2 text-[10px] text-slate-400">
                    {t.created_at ? new Date(t.created_at).toLocaleDateString() : ""}
                  </p>
                </button>
              );
            })}

            <button
              type="button"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
              className="flex w-56 shrink-0 snap-start flex-col items-center justify-center rounded-xl border border-dashed border-[#cfcfc8] bg-white/60 p-4 text-center hover:border-[#14352b]/50 hover:bg-white"
              data-testid="profile-new-version"
            >
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#e8f2ec] text-lg font-semibold text-[#14352b]">
                +
              </span>
              <span className="mt-2 text-sm font-semibold text-slate-800">New version</span>
              <span className="mt-1 text-xs text-slate-400">Import another .docx resume</span>
            </button>
          </div>
        </section>

        {/* Profile details */}
        <section>
          <SectionLabel>Profile details</SectionLabel>
          <div className="grid gap-3 lg:grid-cols-[1.4fr_0.9fr]">
            <div className="space-y-3">
              <Card>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                      Professional summary
                    </p>
                    {edit === "summary" ? (
                      <div className="mt-3 space-y-3">
                        <Field label="Summary" value={summary} onChange={setSummary} multiline />
                        <Field label="Skills & certifications" value={skills} onChange={setSkills} multiline />
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => void handleSave()}
                            disabled={saving}
                            className="rounded-lg bg-[#14352b] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                          >
                            Save
                          </button>
                          <button type="button" onClick={() => setEdit(null)} className="text-xs font-semibold text-slate-500">
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <p className="mt-2 text-sm leading-6 text-slate-600">
                        {summary.trim() || "Add a professional summary — the first thing recruiters read."}
                      </p>
                    )}
                  </div>
                  {edit !== "summary" ? <EditLink onClick={() => setEdit("summary")} /> : null}
                </div>
              </Card>

              <Card>
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-[#14352b]" aria-hidden>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M12 3 3 8l9 5 9-5-9-5Zm-7 8.5V16c0 2 4 3.5 7 3.5s7-1.5 7-3.5v-4.5"
                          stroke="currentColor"
                          strokeWidth="1.6"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </span>
                    <h3 className="text-sm font-semibold text-slate-900">Education</h3>
                    <span className="text-xs text-slate-400">{education.length} entries</span>
                  </div>
                  <EditLink
                    label={edit === "education" ? "Done" : "Edit"}
                    onClick={() => setEdit(edit === "education" ? null : "education")}
                  />
                </div>
                {edit === "education" ? (
                  <div className="space-y-3">
                    {education.map((edu, idx) => (
                      <div key={idx} className="rounded-lg border border-[#f0f0ec] bg-[#fafaf8] p-3">
                        <div className="grid gap-2 sm:grid-cols-2">
                          <Field
                            label="Institution"
                            value={edu.institution || ""}
                            onChange={(v) => {
                              const next = [...education];
                              next[idx] = { ...edu, institution: v };
                              setEducation(next);
                            }}
                          />
                          <Field
                            label="Date range"
                            value={edu.date_range || ""}
                            onChange={(v) => {
                              const next = [...education];
                              next[idx] = { ...edu, date_range: v };
                              setEducation(next);
                            }}
                          />
                          <Field
                            label="Degree"
                            value={edu.degree || ""}
                            onChange={(v) => {
                              const next = [...education];
                              next[idx] = { ...edu, degree: v };
                              setEducation(next);
                            }}
                          />
                          <Field
                            label="Field"
                            value={edu.field || ""}
                            onChange={(v) => {
                              const next = [...education];
                              next[idx] = { ...edu, field: v };
                              setEducation(next);
                            }}
                          />
                        </div>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => void handleSave()}
                      disabled={saving}
                      className="rounded-lg bg-[#14352b] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      Save education
                    </button>
                  </div>
                ) : education.length ? (
                  <ul className="divide-y divide-[#f0f0ec]">
                    {education.map((edu, idx) => (
                      <li key={idx} className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0">
                        <div className="flex items-start gap-3">
                          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#f3f4f1] text-[10px] font-bold text-[#14352b]">
                            {(edu.institution || "?").slice(0, 2).toUpperCase()}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-slate-900">{edu.institution || "Institution"}</p>
                            <p className="text-xs text-slate-500">
                              {[edu.degree, edu.field].filter(Boolean).join(" · ") || "—"}
                            </p>
                          </div>
                        </div>
                        <span className="shrink-0 text-xs text-slate-400">{edu.date_range || ""}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-400">No education entries yet.</p>
                )}
              </Card>

              <Card>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-900">Experience</h3>
                  <EditLink
                    label={edit === "experience" ? "Done" : "Edit"}
                    onClick={() => setEdit(edit === "experience" ? null : "experience")}
                  />
                </div>
                {edit === "experience" ? (
                  <div className="space-y-3">
                    {experiences.map((exp, idx) => (
                      <div key={idx} className="rounded-lg border border-[#f0f0ec] bg-[#fafaf8] p-3">
                        <div className="grid gap-2 sm:grid-cols-2">
                          <Field
                            label="Title"
                            value={exp.title || ""}
                            onChange={(v) => {
                              const next = [...experiences];
                              next[idx] = { ...exp, title: v };
                              setExperiences(next);
                            }}
                          />
                          <Field
                            label="Company"
                            value={exp.company || ""}
                            onChange={(v) => {
                              const next = [...experiences];
                              next[idx] = { ...exp, company: v };
                              setExperiences(next);
                            }}
                          />
                          <Field
                            label="Date range"
                            value={exp.date_range || ""}
                            onChange={(v) => {
                              const next = [...experiences];
                              next[idx] = { ...exp, date_range: v };
                              setExperiences(next);
                            }}
                          />
                        </div>
                        <div className="mt-2">
                          <Field
                            label="Bullets (one per line)"
                            value={bulletsToText(exp.bullets)}
                            onChange={(v) => {
                              const next = [...experiences];
                              next[idx] = { ...exp, bullets: textToBullets(v, exp.bullets) };
                              setExperiences(next);
                            }}
                            multiline
                          />
                        </div>
                      </div>
                    ))}
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        className="text-xs font-semibold text-[#14352b]"
                        onClick={() =>
                          setExperiences((prev) => [
                            ...prev,
                            { company: "", title: "", location: "", date_range: "", tags: [], bullets: [] },
                          ])
                        }
                      >
                        + Add role
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleSave()}
                        disabled={saving}
                        className="rounded-lg bg-[#14352b] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                      >
                        Save experience
                      </button>
                    </div>
                  </div>
                ) : experiences.length ? (
                  <ul className="space-y-3">
                    {experiences.map((exp, idx) => (
                      <li key={idx}>
                        <p className="text-sm font-semibold text-slate-900">
                          {exp.title || "Role"}
                          {exp.company ? (
                            <span className="font-normal text-slate-500"> · {exp.company}</span>
                          ) : null}
                        </p>
                        <p className="text-xs text-slate-400">{exp.date_range || ""}</p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-400">No experience entries yet.</p>
                )}
              </Card>
            </div>

            <div className="space-y-3">
              <Card>
                <div className="mb-3 flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[#14352b]" aria-hidden>
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
                          <path
                            d="M8 4h8a2 2 0 0 1 2 2v14l-6-3-6 3V6a2 2 0 0 1 2-2Z"
                            stroke="currentColor"
                            strokeWidth="1.6"
                          />
                        </svg>
                      </span>
                      <h3 className="text-sm font-semibold text-slate-900">Application defaults</h3>
                    </div>
                    <p className="mt-1 text-xs text-slate-400">Auto-filled on ATS forms before submit pause.</p>
                  </div>
                  <EditLink
                    label={edit === "apply" ? "Done" : "Edit"}
                    onClick={() => setEdit(edit === "apply" ? null : "apply")}
                  />
                </div>

                {edit === "apply" ? (
                  <div className="space-y-3">
                    <div className="grid gap-2">
                      <Field
                        label="Email"
                        value={String(apply.email || "")}
                        onChange={(v) => setApplyField("email", v)}
                      />
                      <Field
                        label="Phone"
                        value={String(apply.phone || "")}
                        onChange={(v) => setApplyField("phone", v)}
                      />
                      <Field
                        label="Location"
                        value={String(apply.location || "")}
                        onChange={(v) => setApplyField("location", v)}
                      />
                      <Field
                        label="Preferred name"
                        value={String(apply.preferred_name || "")}
                        onChange={(v) => setApplyField("preferred_name", v)}
                        placeholder="Leave blank to use your legal name from the resume"
                      />
                      <Field
                        label="LinkedIn"
                        value={String(apply.linkedin_url || "")}
                        onChange={(v) => setApplyField("linkedin_url", v)}
                      />
                      <Field
                        label="Portfolio / website"
                        value={String(apply.portfolio_url || "")}
                        onChange={(v) => setApplyField("portfolio_url", v)}
                        placeholder="e.g. https://yourname.dev"
                      />
                      <Field
                        label="Twitter / X"
                        value={String(apply.twitter_url || "")}
                        onChange={(v) => setApplyField("twitter_url", v)}
                        placeholder="Optional — leave blank if you don't have one"
                      />
                      <Field
                        label="How did you hear about us? (default)"
                        value={String(apply.source || "")}
                        onChange={(v) => setApplyField("source", v)}
                        placeholder="e.g. LinkedIn, Referral, Handshake"
                      />
                    </div>
                    <div className="flex flex-col gap-2 text-sm">
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={Boolean(apply.work_authorized ?? true)}
                          onChange={(e) => setApplyField("work_authorized", e.target.checked)}
                        />
                        Work authorized
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={Boolean(apply.needs_sponsorship ?? true)}
                          onChange={(e) => setApplyField("needs_sponsorship", e.target.checked)}
                        />
                        Needs sponsorship
                      </label>
                      <label className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={Boolean(apply.willing_to_relocate ?? true)}
                          onChange={(e) => setApplyField("willing_to_relocate", e.target.checked)}
                        />
                        Willing to relocate
                      </label>
                    </div>
                    <div className="grid gap-2">
                      <Field
                        label="Visa / work permit type"
                        value={String(apply.visa_status || "")}
                        onChange={(v) => setApplyField("visa_status", v)}
                        placeholder="e.g. F-1 (Student), H-1B, Green Card"
                      />
                      <Field
                        label="Earliest start date"
                        value={String(apply.earliest_start || "")}
                        onChange={(v) => setApplyField("earliest_start", v)}
                        placeholder="e.g. Immediately, June 2027"
                      />
                      <Field
                        label="Salary expectation"
                        value={String(apply.salary_expectation || "")}
                        onChange={(v) => setApplyField("salary_expectation", v)}
                        placeholder="e.g. $90,000 - $110,000"
                      />
                    </div>
                    <div className="rounded-lg border border-[#f0f0ec] bg-[#fafaf8] p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                        Voluntary demographic info (EEO)
                      </p>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        Some ATS forms (e.g. Workday) ask these as optional self-identification
                        questions. Answers here are never auto-submitted — every EEO field always
                        pauses for your review before Submit.
                      </p>
                      <div className="mt-2 grid gap-2 sm:grid-cols-2">
                        <Field
                          label="Gender"
                          value={String(apply.gender || "")}
                          onChange={(v) => setApplyField("gender", v)}
                          placeholder="e.g. Female, Male, Prefer not to say"
                        />
                        <Field
                          label="Race / ethnicity"
                          value={String(apply.race_ethnicity || "")}
                          onChange={(v) => setApplyField("race_ethnicity", v)}
                          placeholder="e.g. Asian, Prefer not to say"
                        />
                        <Field
                          label="Veteran status"
                          value={String(apply.veteran_status || "")}
                          onChange={(v) => setApplyField("veteran_status", v)}
                          placeholder="e.g. Not a veteran, Prefer not to say"
                        />
                        <Field
                          label="Disability status"
                          value={String(apply.disability_status || "")}
                          onChange={(v) => setApplyField("disability_status", v)}
                          placeholder="e.g. No disability, Prefer not to say"
                        />
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleSave()}
                      disabled={saving}
                      className="rounded-lg bg-[#14352b] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      Save defaults
                    </button>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="rounded-lg border border-[#f0f0ec] bg-[#fafaf8] p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                        Work authorization
                      </p>
                      <p className="mt-1 text-sm font-medium text-slate-800">
                        {String(apply.location || "United States")}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                            apply.work_authorized !== false
                              ? "bg-[#e8f2ec] text-[#14352b]"
                              : "bg-slate-100 text-slate-400"
                          }`}
                        >
                          {apply.work_authorized !== false ? "✓ " : "× "}Authorized to work
                        </span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                            apply.needs_sponsorship
                              ? "bg-amber-50 text-amber-800"
                              : "bg-slate-100 text-slate-400"
                          }`}
                        >
                          {apply.needs_sponsorship ? "Needs sponsorship" : "× Needs sponsorship"}
                        </span>
                      </div>
                    </div>
                    <div className="rounded-lg border border-[#f0f0ec] bg-[#fafaf8] p-3">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                        Work preferences
                      </p>
                      <p className="mt-1 text-xs leading-5 text-slate-600">
                        {apply.willing_to_relocate !== false ? "Open to relocate" : "Local only"}
                        {apply.earliest_start ? ` · Start ${String(apply.earliest_start)}` : ""}
                      </p>
                    </div>
                  </div>
                )}
              </Card>

              <div className="flex flex-wrap gap-2 px-1">
                <button
                  type="button"
                  onClick={() => void handleSave()}
                  disabled={saving}
                  data-testid="profile-save"
                  className="rounded-lg bg-[#14352b] px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save all"}
                </button>
                <button
                  type="button"
                  onClick={() => void handleReset()}
                  disabled={saving}
                  className="rounded-lg border border-[#e8e8e4] bg-white px-3 py-2 text-xs font-semibold text-slate-600"
                >
                  Reset seed
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
