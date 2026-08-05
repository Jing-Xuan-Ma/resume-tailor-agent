"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getCandidateLibrary,
  resetCandidateLibrary,
  updateCandidateLibrary,
} from "@/lib/api";

interface ProfilePanelProps {
  userId: string;
}

type TabId = "inventory" | "apply";

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
      <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</span>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          placeholder={placeholder}
          className="w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-emerald-400"
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-9 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none focus:border-emerald-400"
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

export default function ProfilePanel({ userId }: ProfilePanelProps) {
  const [tab, setTab] = useState<TabId>("inventory");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string>("");

  const [candidateName, setCandidateName] = useState("");
  const [contactLine, setContactLine] = useState("");
  const [summary, setSummary] = useState("");
  const [skills, setSkills] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [evidenceLinks, setEvidenceLinks] = useState<
    Array<{ label?: string; url?: string; maps_to_company?: string; note?: string; topics?: string[] }>
  >([]);
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
    setEvidenceLinks(Array.isArray(inv.evidence_links) ? (inv.evidence_links as typeof evidenceLinks) : []);
    setEducation(Array.isArray(inv.education) ? (inv.education as Edu[]) : []);
    setExperiences(Array.isArray(inv.experiences) ? (inv.experiences as Exp[]) : []);
    setProjects(Array.isArray(inv.projects) ? (inv.projects as Proj[]) : []);
    setApply(lib.apply || {});
    setUpdatedAt(lib.updated_at || "");
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    getCandidateLibrary(userId)
      .then((lib) => {
        if (!alive) return;
        hydrate(lib);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof Error ? err.message : "Failed to load library");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [userId, hydrate]);

  useEffect(() => {
    const onProfileUpdated = () => {
      getCandidateLibrary(userId)
        .then((lib) => {
          hydrate(lib);
          setMessage("Synced from Resume Agent chat.");
        })
        .catch(() => {
          /* ignore */
        });
    };
    window.addEventListener("ra-profile-updated", onProfileUpdated);
    return () => window.removeEventListener("ra-profile-updated", onProfileUpdated);
  }, [userId, hydrate]);

  const buildInventory = () => ({
    candidate_name: candidateName,
    contact_line: contactLine,
    summary,
    skills_certifications: skills,
    github_url: githubUrl,
    evidence_links: evidenceLinks,
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
      setMessage("Saved. Tailor and auto-apply will use this library.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "s") return;
      e.preventDefault();
      document.querySelector<HTMLButtonElement>("[data-testid=profile-save]")?.click();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const handleReset = async () => {
    if (!confirm("Reset library to the seeded master inventory? Your edits will be overwritten.")) return;
    setSaving(true);
    setError(null);
    try {
      const lib = await resetCandidateLibrary(userId);
      hydrate(lib);
      setMessage("Reset to default master inventory.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setSaving(false);
    }
  };

  const setApplyField = (key: string, value: unknown) => {
    setApply((prev) => ({ ...prev, [key]: value }));
  };

  if (loading) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8" data-testid="profile-panel">
        <div className="h-2 w-40 animate-pulse rounded bg-slate-200" />
        <div className="h-2 w-64 animate-pulse rounded bg-slate-100" />
        <p className="text-sm text-slate-500">Loading profile library…</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-[#f4f6f4]" data-testid="profile-panel">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-3">
        <div>
          <h2 className="text-base font-bold text-slate-950">Profile</h2>
          <p className="text-[12px] text-slate-500">
            Master Inventory + Apply Profile. Chat with Resume Agent to save personal facts here, or edit &amp; Save.
            Updated {updatedAt || "—"}.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-full bg-slate-100 p-1 ring-1 ring-slate-200">
            <button
              type="button"
              data-testid="profile-tab-inventory"
              onClick={() => setTab("inventory")}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                tab === "inventory" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"
              }`}
            >
              Inventory
            </button>
            <button
              type="button"
              data-testid="profile-tab-apply"
              onClick={() => setTab("apply")}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                tab === "apply" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500"
              }`}
            >
              Apply
            </button>
          </div>
          <button
            type="button"
            onClick={() => void handleReset()}
            disabled={saving}
            className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Reset seed
          </button>
          <button
            type="button"
            data-testid="profile-save"
            onClick={() => void handleSave()}
            disabled={saving}
            title="Save library (Ctrl+S)"
            className="rounded-full bg-emerald-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {(message || error) && (
        <div
          className={`shrink-0 px-5 py-2 text-[12px] font-semibold ${
            error ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-800"
          }`}
        >
          {error || message}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {tab === "inventory" ? (
          <div className="mx-auto flex max-w-4xl flex-col gap-4">
            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-bold text-slate-950">Basics</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Full name" value={candidateName} onChange={setCandidateName} />
                <Field label="Contact line" value={contactLine} onChange={setContactLine} />
              </div>
              <div className="mt-3">
                <Field
                  label="Primary GitHub (resume-tailor evidence)"
                  value={githubUrl}
                  onChange={(v) => {
                    setGithubUrl(v);
                    setApplyField("github_url", v);
                    setApplyField("resume_tailor_github", v);
                  }}
                  placeholder="https://github.com/Jing-Xuan-Ma/resume-tailor-agent"
                />
                {githubUrl ? (
                  <a
                    href={githubUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 inline-block text-[12px] font-semibold text-emerald-700 hover:underline"
                  >
                    Open repo →
                  </a>
                ) : null}
              </div>
              {evidenceLinks.length > 0 ? (
                <div className="mt-3 rounded-xl border border-emerald-100 bg-emerald-50/60 px-3 py-2 text-[12px] text-emerald-900">
                  <p className="font-semibold">Evidence links for JD agents</p>
                  <ul className="mt-1 space-y-1">
                    {evidenceLinks.map((link, i) => (
                      <li key={i}>
                        <a
                          href={String(link.url || "#")}
                          target="_blank"
                          rel="noreferrer"
                          className="font-semibold underline"
                        >
                          {link.label || link.url}
                        </a>
                        {link.maps_to_company ? (
                          <span className="text-emerald-800"> · maps to {link.maps_to_company}</span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div className="mt-3">
                <Field label="Summary" value={summary} onChange={setSummary} multiline />
              </div>
              <div className="mt-3">
                <Field
                  label="Skills & certifications (comma-separated)"
                  value={skills}
                  onChange={setSkills}
                  multiline
                />
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-bold text-slate-950">Education</h3>
              <div className="space-y-4">
                {education.map((edu, idx) => (
                  <div key={idx} className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
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
                        label="Location"
                        value={edu.location || ""}
                        onChange={(v) => {
                          const next = [...education];
                          next[idx] = { ...edu, location: v };
                          setEducation(next);
                        }}
                      />
                    </div>
                    <div className="mt-2">
                      <Field
                        label="Coursework ( | separated)"
                        value={(edu.coursework || []).join(" | ")}
                        onChange={(v) => {
                          const next = [...education];
                          next[idx] = {
                            ...edu,
                            coursework: v.split("|").map((s) => s.trim()).filter(Boolean),
                          };
                          setEducation(next);
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-950">Experience</h3>
                <button
                  type="button"
                  className="text-xs font-semibold text-emerald-700"
                  onClick={() =>
                    setExperiences((prev) => [
                      ...prev,
                      { company: "", title: "", location: "", date_range: "", tags: [], bullets: [] },
                    ])
                  }
                >
                  + Add
                </button>
              </div>
              <div className="space-y-4">
                {experiences.map((exp, idx) => (
                  <div key={idx} className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
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
                        label="Location"
                        value={exp.location || ""}
                        onChange={(v) => {
                          const next = [...experiences];
                          next[idx] = { ...exp, location: v };
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
                      <Field
                        label="GitHub / evidence URL"
                        value={exp.github_url || exp.evidence_url || ""}
                        onChange={(v) => {
                          const next = [...experiences];
                          next[idx] = { ...exp, github_url: v, evidence_url: v };
                          setExperiences(next);
                        }}
                        placeholder="https://github.com/..."
                      />
                    </div>
                    <div className="mt-2">
                      <Field
                        label="Tags (comma-separated)"
                        value={(exp.tags || []).join(", ")}
                        onChange={(v) => {
                          const next = [...experiences];
                          next[idx] = {
                            ...exp,
                            tags: v.split(",").map((s) => s.trim()).filter(Boolean),
                          };
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
                    <button
                      type="button"
                      className="mt-2 text-[11px] font-semibold text-rose-600"
                      onClick={() => setExperiences((prev) => prev.filter((_, i) => i !== idx))}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-950">Projects</h3>
                <button
                  type="button"
                  className="text-xs font-semibold text-emerald-700"
                  onClick={() =>
                    setProjects((prev) => [
                      ...prev,
                      { name: "", tools: [], context: "Independent Project", date_range: "", bullets: [] },
                    ])
                  }
                >
                  + Add
                </button>
              </div>
              <div className="space-y-4">
                {projects.map((proj, idx) => (
                  <div key={idx} className="rounded-xl border border-slate-100 bg-slate-50/70 p-3">
                    <div className="grid gap-2 sm:grid-cols-2">
                      <Field
                        label="Name"
                        value={proj.name || ""}
                        onChange={(v) => {
                          const next = [...projects];
                          next[idx] = { ...proj, name: v };
                          setProjects(next);
                        }}
                      />
                      <Field
                        label="Tools (comma-separated)"
                        value={(proj.tools || []).join(", ")}
                        onChange={(v) => {
                          const next = [...projects];
                          next[idx] = {
                            ...proj,
                            tools: v.split(",").map((s) => s.trim()).filter(Boolean),
                          };
                          setProjects(next);
                        }}
                      />
                    </div>
                    <div className="mt-2">
                      <Field
                        label="Bullets (one per line)"
                        value={bulletsToText(proj.bullets)}
                        onChange={(v) => {
                          const next = [...projects];
                          next[idx] = { ...proj, bullets: textToBullets(v, proj.bullets) };
                          setProjects(next);
                        }}
                        multiline
                      />
                    </div>
                    <button
                      type="button"
                      className="mt-2 text-[11px] font-semibold text-rose-600"
                      onClick={() => setProjects((prev) => prev.filter((_, i) => i !== idx))}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            </section>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="mb-3 text-sm font-bold text-slate-950">Apply autofill</h3>
            <p className="mb-4 text-[12px] text-slate-500" data-testid="profile-apply-hint">
              Used when auto-apply fills forms and pauses before Submit (never clicks Submit). Save with Ctrl+S.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field
                label="Full name"
                value={String(apply.full_name || "")}
                onChange={(v) => setApplyField("full_name", v)}
              />
              <Field
                label="Preferred name"
                value={String(apply.preferred_name || "")}
                onChange={(v) => setApplyField("preferred_name", v)}
              />
              <Field label="Email" value={String(apply.email || "")} onChange={(v) => setApplyField("email", v)} />
              <Field label="Phone" value={String(apply.phone || "")} onChange={(v) => setApplyField("phone", v)} />
              <Field
                label="Location"
                value={String(apply.location || "")}
                onChange={(v) => setApplyField("location", v)}
              />
              <Field
                label="LinkedIn URL"
                value={String(apply.linkedin_url || "")}
                onChange={(v) => setApplyField("linkedin_url", v)}
              />
              <Field
                label="Portfolio URL"
                value={String(apply.portfolio_url || "")}
                onChange={(v) => setApplyField("portfolio_url", v)}
              />
              <Field
                label="GitHub URL"
                value={String(apply.github_url || "")}
                onChange={(v) => setApplyField("github_url", v)}
              />
              <Field
                label="Visa status"
                value={String(apply.visa_status || "")}
                onChange={(v) => setApplyField("visa_status", v)}
              />
              <Field
                label="Earliest start"
                value={String(apply.earliest_start || "")}
                onChange={(v) => setApplyField("earliest_start", v)}
              />
            </div>
            <div className="mt-4 flex flex-wrap gap-4 text-sm">
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
            <div className="mt-5">
              <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Custom fields
              </h4>
              <p className="mb-2 text-[11px] text-slate-400">
                Extra facts the agent can add (JSON object). Used for Apply answers beyond the defaults.
              </p>
              <textarea
                value={JSON.stringify((apply.custom_fields as Record<string, unknown>) || {}, null, 2)}
                onChange={(e) => {
                  try {
                    const parsed = JSON.parse(e.target.value || "{}");
                    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                      setApplyField("custom_fields", parsed);
                    }
                  } catch {
                    /* keep typing */
                  }
                }}
                rows={4}
                className="w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 font-mono text-[12px] text-slate-800 outline-none focus:border-emerald-400"
                data-testid="profile-custom-fields"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
