"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  draftOutreach,
  findOutreachEmail,
  getOutreachCrmExportUrl,
  ingestOutreachJd,
  listOutreachContacts,
  markOutreachSent,
  rankOutreachCandidates,
  upsertOutreachContact,
  type OutreachContact,
  type OutreachEmailCandidate,
  type OutreachMessage,
  type OutreachRankedCandidate,
} from "@/lib/api";

const COFFEE_SLOT_PRESETS = [
  "Tue/Thu mornings PT",
  "Wed afternoons ET",
  "Mon–Fri 12–1pm local",
  "Flexible evenings this week",
];

const REPLY_STATUSES = [
  { id: "none", label: "No reply yet" },
  { id: "awaiting", label: "Awaiting reply" },
  { id: "replied", label: "Replied" },
  { id: "scheduled", label: "Coffee scheduled" },
  { id: "declined", label: "Declined" },
];

const STEPS = [
  { id: 1, label: "搜索候选人", short: "搜索" },
  { id: 2, label: "排序与选择", short: "排序" },
  { id: 3, label: "补全联系方式", short: "联系方式" },
  { id: 4, label: "选模板起草", short: "起草" },
] as const;

type ChannelPref = "email" | "linkedin" | "unknown";

type LocalCandidate = {
  localId: string;
  name: string;
  title: string;
  snippet: string;
  recent_activity: string;
  linkedin_url: string;
};

type SelectedPerson = {
  localId: string;
  name: string;
  title: string;
  linkedin_url: string;
  score: number;
  match_reason: string;
  email: string;
  channel: ChannelPref;
  emailCandidates: OutreachEmailCandidate[];
  emailLookupNote: string | null;
};

const TEMPLATES = [
  {
    id: "linkedin_connect",
    label: "LinkedIn connection request",
    channel: "linkedin" as const,
    roleHint: "Hiring Manager / Team Lead",
    preview:
      "Hi {name} — I applied for {role} at {company}. Background in … Would value connecting.",
    requiresEmail: false,
  },
  {
    id: "coffee_chat",
    label: "Coffee chat",
    channel: "linkedin" as const,
    roleHint: "Hiring Manager / Team Lead",
    preview: "Quick 15-min coffee chat about the open role — warm tone, slot line included.",
    requiresEmail: false,
  },
  {
    id: "post_apply_thanks",
    label: "Post-apply thank-you",
    channel: "email" as const,
    roleHint: "Recruiter",
    preview: "Thank you for reviewing my application — email only.",
    requiresEmail: true,
  },
  {
    id: "recruiter_ping",
    label: "Recruiter ping",
    channel: "email" as const,
    roleHint: "Talent Acquisition",
    preview: "Following up — any extra materials needed? Email only.",
    requiresEmail: true,
  },
];

function starsLabel(n: number) {
  return "★".repeat(Math.max(1, Math.min(5, n))) + "☆".repeat(Math.max(0, 5 - Math.min(5, n)));
}

function newLocalId() {
  return `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

interface OutreachStepPanelProps {
  visible: boolean;
  userId: string;
  jobId?: string | null;
  company?: string | null;
  position?: string | null;
}

export default function OutreachStepPanel({
  visible,
  userId,
  jobId,
  company: companyProp,
  position: positionProp,
}: OutreachStepPanelProps) {
  const [step, setStep] = useState(1);
  const [company, setCompany] = useState(companyProp || "");
  const [position, setPosition] = useState(positionProp || "");
  const [jdUrl, setJdUrl] = useState("");
  const [jdText, setJdText] = useState("");
  const [companySize, setCompanySize] = useState<"unknown" | "small" | "medium" | "large">("unknown");
  const [jdBusy, setJdBusy] = useState(false);

  const [draftCandidate, setDraftCandidate] = useState<LocalCandidate>({
    localId: "",
    name: "",
    title: "",
    snippet: "",
    recent_activity: "",
    linkedin_url: "",
  });
  const [pool, setPool] = useState<LocalCandidate[]>([]);
  const [ranked, setRanked] = useState<OutreachRankedCandidate[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [rankBusy, setRankBusy] = useState(false);

  const [people, setPeople] = useState<SelectedPerson[]>([]);
  const [activePersonId, setActivePersonId] = useState<string | null>(null);
  const [lookupBusy, setLookupBusy] = useState(false);

  const [coffeeAvailability, setCoffeeAvailability] = useState("");
  const [replyStatus, setReplyStatus] = useState("none");
  const [templateId, setTemplateId] = useState("linkedin_connect");
  const [busy, setBusy] = useState(false);
  const [crmBusy, setCrmBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crmNote, setCrmNote] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<OutreachMessage[]>([]);
  const [contacts, setContacts] = useState<OutreachContact[]>([]);
  const [crmFilter, setCrmFilter] = useState<string>("all");

  useEffect(() => {
    if (companyProp) setCompany(companyProp);
  }, [companyProp]);
  useEffect(() => {
    if (positionProp) setPosition(positionProp);
  }, [positionProp]);

  const refreshContacts = useCallback(async () => {
    if (!userId) return;
    try {
      const res = await listOutreachContacts(userId);
      setContacts(res.contacts || []);
    } catch {
      /* CRM list is best-effort */
    }
  }, [userId]);

  const [forceOutreach, setForceOutreach] = useState(false);
  useEffect(() => {
    try {
      setForceOutreach(new URLSearchParams(window.location.search).get("forceOutreach") === "1");
    } catch {
      setForceOutreach(false);
    }
  }, []);

  const show = visible || forceOutreach;

  useEffect(() => {
    if (show) void refreshContacts();
  }, [show, refreshContacts]);

  const activePerson = useMemo(
    () => people.find((p) => p.localId === activePersonId) || people[0] || null,
    [people, activePersonId]
  );

  const channelPref: ChannelPref = activePerson?.channel || "unknown";
  const hasEmail = !!(activePerson?.email || "").trim();

  const availableTemplates = useMemo(() => {
    return TEMPLATES.filter((t) => {
      if (channelPref === "linkedin") return !t.requiresEmail;
      if (channelPref === "email") return t.requiresEmail || t.id === "coffee_chat";
      // unknown: show all but mark email-only
      return true;
    });
  }, [channelPref]);

  useEffect(() => {
    if (!availableTemplates.some((t) => t.id === templateId)) {
      setTemplateId(availableTemplates[0]?.id || "linkedin_connect");
    }
  }, [availableTemplates, templateId]);

  const selected = availableTemplates.find((t) => t.id === templateId) || availableTemplates[0] || TEMPLATES[0];

  const searchQueries = [
    `${company || "Company"} "Hiring Manager" ${position ? `"${position.split(" ")[0]}"` : "Data"}`,
    `${company || "Company"} Recruiter OR "Talent Acquisition"`,
    `${company || "Company"} "Head of Data" OR "Analytics Manager" OR "Data Lead"`,
  ];

  const linkedInSearchUrl = (q: string) =>
    `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(q)}`;

  const handleIngestJd = async () => {
    if (!jdUrl.trim()) {
      setError("Paste a Greenhouse / Lever / LinkedIn Jobs URL first.");
      return;
    }
    setJdBusy(true);
    setError(null);
    try {
      const res = await ingestOutreachJd({
        user_id: userId,
        url: jdUrl.trim(),
        jd_text_override: jdText || undefined,
      });
      if (res.company) setCompany(res.company);
      if (res.position) setPosition(res.position);
      if (res.jd_text) setJdText(res.jd_text);
      setCrmNote(
        res.ok
          ? `JD ingested (${res.platform}): ${res.company || "?"} · ${res.position || "?"}`
          : res.error || "Could not extract — fill company/position manually."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "JD ingest failed");
    } finally {
      setJdBusy(false);
    }
  };

  const handleAddToPool = () => {
    if (!draftCandidate.name.trim() && !draftCandidate.title.trim()) {
      setError("Enter at least a name or title from LinkedIn.");
      return;
    }
    const row: LocalCandidate = {
      ...draftCandidate,
      localId: newLocalId(),
      name: draftCandidate.name.trim(),
      title: draftCandidate.title.trim(),
    };
    setPool((prev) => [...prev, row]);
    setDraftCandidate({
      localId: "",
      name: "",
      title: "",
      snippet: "",
      recent_activity: "",
      linkedin_url: "",
    });
    setError(null);
    setCrmNote(`Added ${row.name || row.title} to candidate pool.`);
  };

  const handleRank = async () => {
    if (!pool.length) {
      setError("Add at least one candidate from LinkedIn search results.");
      return;
    }
    setRankBusy(true);
    setError(null);
    try {
      const res = await rankOutreachCandidates({
        user_id: userId,
        candidates: pool.map((p) => ({
          id: p.localId,
          name: p.name,
          title: p.title,
          snippet: p.snippet,
          recent_activity: p.recent_activity,
          linkedin_url: p.linkedin_url,
          company_size: companySize === "unknown" ? undefined : companySize,
        })),
        jd_text: jdText,
        position,
        company,
        company_size: companySize,
      });
      setRanked(res.candidates || []);
      setCrmNote(`Ranked ${res.candidates?.length || 0} candidates by predicted outreach fit.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ranking failed");
    } finally {
      setRankBusy(false);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 3) {
        setError("Select at most 3 people for this outreach batch.");
        return prev;
      }
      setError(null);
      return [...prev, id];
    });
  };

  const commitSelectionToStep3 = () => {
    const source = ranked.length ? ranked : [];
    const picked = source.filter((r) => selectedIds.includes(r.id || ""));
    if (!picked.length) {
      setError("Select 1–3 people to add to this outreach.");
      return;
    }
    const next: SelectedPerson[] = picked.map((r) => ({
      localId: r.id || newLocalId(),
      name: r.name,
      title: r.title,
      linkedin_url: r.linkedin_url || "",
      score: r.score,
      match_reason: r.match_reason,
      email: "",
      channel: "unknown" as ChannelPref,
      emailCandidates: [],
      emailLookupNote: null,
    }));
    setPeople(next);
    setActivePersonId(next[0]?.localId || null);
    setStep(3);
    setError(null);
    setCrmNote(`Selected ${next.length} for contact enrichment. You choose the channel.`);
  };

  const updateActive = (patch: Partial<SelectedPerson>) => {
    if (!activePerson) return;
    setPeople((prev) =>
      prev.map((p) => (p.localId === activePerson.localId ? { ...p, ...patch } : p))
    );
  };

  const handleFindEmail = async () => {
    if (!activePerson?.name) {
      setError("Need a name to look up email.");
      return;
    }
    setLookupBusy(true);
    setError(null);
    try {
      const res = await findOutreachEmail({
        user_id: userId,
        name: activePerson.name,
        company,
      });
      updateActive({
        emailCandidates: res.candidates || [],
        emailLookupNote: res.expectancy_note,
        channel: (res.candidates || []).length ? activePerson.channel : "linkedin",
      });
      setCrmNote(
        (res.candidates || []).length
          ? `Found ${res.candidates.length} email candidate(s) — pick one or use LinkedIn.`
          : res.empty_reason || "No email candidates — use LinkedIn connection request."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Email lookup failed");
    } finally {
      setLookupBusy(false);
    }
  };

  const handleDraft = async () => {
    if (!activePerson) {
      setError("Select a person in step 3 first.");
      return;
    }
    if (selected.requiresEmail && !activePerson.email) {
      setError("This template needs an email — pick one in step 3, or switch to a LinkedIn template.");
      return;
    }
    setBusy(true);
    setError(null);
    setCrmNote(null);
    try {
      const channel =
        selected.channel === "email" || activePerson.channel === "email" ? selected.channel : "linkedin";
      const msg = await draftOutreach({
        user_id: userId,
        job_id: jobId || undefined,
        contact_name: activePerson.name || undefined,
        contact_role: activePerson.title || selected.roleHint,
        company: company || undefined,
        channel,
        tone: templateId === "recruiter_ping" ? "concise" : "warm",
        template_type: templateId as
          | "coffee_chat"
          | "post_apply_thanks"
          | "recruiter_ping"
          | "linkedin_connect"
          | "general",
        linkedin_url: activePerson.linkedin_url || undefined,
        contact_email: activePerson.email || undefined,
        coffee_availability: coffeeAvailability || undefined,
        save_to_crm: !!(activePerson.name || activePerson.linkedin_url || activePerson.email),
      });
      setDrafts((prev) => [msg, ...prev].slice(0, 6));
      await refreshContacts();
      setCrmNote("Draft ready — you send (mailto / LinkedIn). We never auto-send.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Draft failed");
    } finally {
      setBusy(false);
    }
  };

  const handleSaveContact = async () => {
    if (!activePerson) {
      setError("No person selected.");
      return;
    }
    if (!activePerson.name && !activePerson.linkedin_url && !activePerson.email) {
      setError("Enter a name, LinkedIn URL, or email before saving.");
      return;
    }
    setCrmBusy(true);
    setError(null);
    try {
      await upsertOutreachContact({
        user_id: userId,
        name: activePerson.name || undefined,
        role: activePerson.title || undefined,
        company: company || undefined,
        job_id: jobId || undefined,
        linkedin_url: activePerson.linkedin_url || undefined,
        email: activePerson.email || undefined,
        coffee_availability: coffeeAvailability || undefined,
        coffee_slots: coffeeAvailability ? [coffeeAvailability] : [],
        status: "identified",
        reply_status: replyStatus,
        notes: activePerson.match_reason || undefined,
      });
      await refreshContacts();
      setCrmNote("Contact saved to CRM.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "CRM save failed");
    } finally {
      setCrmBusy(false);
    }
  };

  const handleLoadContact = (c: OutreachContact) => {
    const person: SelectedPerson = {
      localId: c.id || newLocalId(),
      name: c.name || "",
      title: c.role || "",
      linkedin_url: c.linkedin_url || "",
      score: 0,
      match_reason: "Loaded from CRM",
      email: c.email || "",
      channel: c.email ? "email" : c.linkedin_url ? "linkedin" : "unknown",
      emailCandidates: [],
      emailLookupNote: null,
    };
    setPeople([person]);
    setActivePersonId(person.localId);
    setCoffeeAvailability(c.coffee_availability || "");
    setReplyStatus(c.reply_status || "none");
    setStep(3);
    setCrmNote(`Loaded ${c.name || "contact"} from CRM → step 3.`);
  };

  const handleMarkSent = async (id: string) => {
    try {
      const updated = await markOutreachSent(id, userId);
      setDrafts((prev) => prev.map((d) => (d.id === id ? updated : d)));
      if (activePerson && (activePerson.name || activePerson.linkedin_url || activePerson.email)) {
        await upsertOutreachContact({
          user_id: userId,
          name: activePerson.name || undefined,
          role: activePerson.title || undefined,
          company: company || undefined,
          job_id: jobId || undefined,
          linkedin_url: activePerson.linkedin_url || undefined,
          email: activePerson.email || undefined,
          coffee_availability: coffeeAvailability || undefined,
          status: "contacted",
          reply_status: replyStatus === "none" ? "awaiting" : replyStatus,
        });
        setReplyStatus((prev) => (prev === "none" ? "awaiting" : prev));
        await refreshContacts();
        setCrmNote("Marked sent — CRM reply status set to awaiting.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Mark sent failed");
    }
  };

  if (!show) return null;

  const canGo = (n: number) => {
    if (n <= step) return true;
    if (n === 2) return true;
    if (n === 3) return people.length > 0 || selectedIds.length > 0;
    if (n === 4) return people.length > 0;
    return false;
  };

  return (
    <div
      className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="outreach-step-panel"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-slate-950">Step 6 · Cold outreach pipeline</h3>
          <p className="mt-1 text-xs text-slate-500">
            找人 → 排序选择 → 补全联系方式 → 起草。决策权在你；找不到邮箱时用 LinkedIn。
          </p>
        </div>
        <p
          className="text-[10px] font-semibold uppercase tracking-wide text-amber-800"
          data-testid="outreach-no-auto-send"
        >
          Safety: drafts only — never auto-sends
        </p>
      </div>

      <div className="mt-4 flex flex-col gap-4 md:flex-row">
        {/* Left vertical stepper */}
        <nav
          className="flex shrink-0 gap-2 overflow-x-auto md:w-44 md:flex-col md:overflow-visible"
          data-testid="outreach-pipeline-stepper"
          aria-label="Outreach steps"
        >
          {STEPS.map((s) => {
            const active = step === s.id;
            const done = step > s.id;
            return (
              <button
                key={s.id}
                type="button"
                data-testid={`outreach-step-${s.id}`}
                disabled={!canGo(s.id)}
                onClick={() => canGo(s.id) && setStep(s.id)}
                className={`flex min-w-[7.5rem] items-center gap-2 rounded-xl border px-2.5 py-2 text-left text-[11px] transition md:min-w-0 ${
                  active
                    ? "border-emerald-500 bg-emerald-50 font-semibold text-emerald-950"
                    : done
                      ? "border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100"
                      : "border-slate-100 bg-white text-slate-400"
                } disabled:cursor-not-allowed disabled:opacity-50`}
              >
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                    active
                      ? "bg-emerald-600 text-white"
                      : done
                        ? "bg-slate-800 text-white"
                        : "bg-slate-200 text-slate-600"
                  }`}
                >
                  {s.id}
                </span>
                <span className="leading-tight">
                  <span className="block md:hidden">{s.short}</span>
                  <span className="hidden md:block">{s.label}</span>
                </span>
              </button>
            );
          })}
        </nav>

        <div className="min-w-0 flex-1">
          {/* ─── Step 1 ─── */}
          {step === 1 ? (
            <div className="space-y-3" data-testid="outreach-step1">
              <div className="rounded-xl border border-slate-100 bg-slate-50 p-3" data-testid="hm-playbook">
                <div className="text-[11px] font-bold uppercase tracking-wide text-slate-600">
                  ① LinkedIn search presets
                </div>
                <ul className="mt-2 space-y-2">
                  {searchQueries.map((q) => (
                    <li key={q} className="text-[11px] text-slate-700">
                      <div className="flex items-start justify-between gap-2">
                        <span className="min-w-0 flex-1 truncate font-medium" title={q}>
                          {q}
                        </span>
                        <a
                          href={linkedInSearchUrl(q)}
                          target="_blank"
                          rel="noreferrer"
                          className="shrink-0 font-semibold text-emerald-700 underline"
                          data-testid="hm-linkedin-search"
                        >
                          Open LinkedIn
                        </a>
                      </div>
                      <p className="mt-0.5 text-[10px] text-slate-500">
                        预计能找到 2–5 人，逐个复制 LinkedIn URL / 姓名+Title 粘贴到下一步
                      </p>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-xl border border-slate-200 p-3" data-testid="outreach-jd-ingest">
                <div className="text-[11px] font-bold uppercase tracking-wide text-slate-600">
                  手动粘贴职位链接（打分数据源）
                </div>
                <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                  <input
                    data-testid="outreach-jd-url"
                    value={jdUrl}
                    onChange={(e) => setJdUrl(e.target.value)}
                    placeholder="Greenhouse / Lever / LinkedIn Jobs URL"
                    className="h-8 flex-1 rounded-lg border border-slate-200 px-2 text-xs"
                  />
                  <button
                    type="button"
                    data-testid="outreach-jd-ingest-btn"
                    disabled={jdBusy}
                    onClick={() => void handleIngestJd()}
                    className="h-8 rounded-lg bg-slate-900 px-3 text-[11px] font-semibold text-white disabled:opacity-50"
                  >
                    {jdBusy ? "Fetching…" : "抓取公司/职位"}
                  </button>
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <label className="text-[11px] text-slate-600">
                    Company
                    <input
                      data-testid="outreach-company"
                      value={company}
                      onChange={(e) => setCompany(e.target.value)}
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                    />
                  </label>
                  <label className="text-[11px] text-slate-600">
                    Position
                    <input
                      data-testid="outreach-position"
                      value={position}
                      onChange={(e) => setPosition(e.target.value)}
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                    />
                  </label>
                  <label className="text-[11px] text-slate-600 sm:col-span-2">
                    JD text (optional — improves team-affinity scoring)
                    <textarea
                      data-testid="outreach-jd-text"
                      value={jdText}
                      onChange={(e) => setJdText(e.target.value)}
                      rows={3}
                      placeholder="Paste JD snippet or let URL ingest fill this"
                      className="mt-1 w-full rounded-lg border border-slate-200 px-2 py-1.5 text-xs"
                    />
                  </label>
                  <label className="text-[11px] text-slate-600">
                    Company size (adjusts Recruiter vs HM weight)
                    <select
                      data-testid="outreach-company-size"
                      value={companySize}
                      onChange={(e) => setCompanySize(e.target.value as typeof companySize)}
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                    >
                      <option value="unknown">Unknown</option>
                      <option value="small">Small (&lt;200)</option>
                      <option value="medium">Medium</option>
                      <option value="large">Large / enterprise</option>
                    </select>
                  </label>
                </div>
              </div>

              <div className="flex justify-end">
                <button
                  type="button"
                  data-testid="outreach-to-step2"
                  onClick={() => setStep(2)}
                  className="h-9 rounded-xl bg-emerald-700 px-4 text-xs font-semibold text-white hover:bg-emerald-800"
                >
                  下一步：粘贴候选人 →
                </button>
              </div>
            </div>
          ) : null}

          {/* ─── Step 2 ─── */}
          {step === 2 ? (
            <div className="space-y-3" data-testid="outreach-step2">
              <div className="rounded-xl border border-slate-200 p-3">
                <div className="text-[11px] font-bold uppercase tracking-wide text-slate-600">
                  粘贴候选人（姓名 + Title 即可，无需邮箱）
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <label className="text-[11px] text-slate-600">
                    Name
                    <input
                      data-testid="outreach-cand-name"
                      value={draftCandidate.name}
                      onChange={(e) => setDraftCandidate((p) => ({ ...p, name: e.target.value }))}
                      placeholder="Alex Chen"
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                    />
                  </label>
                  <label className="text-[11px] text-slate-600">
                    Title
                    <input
                      data-testid="outreach-cand-title"
                      value={draftCandidate.title}
                      onChange={(e) => setDraftCandidate((p) => ({ ...p, title: e.target.value }))}
                      placeholder="Data Team Hiring Manager"
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                    />
                  </label>
                  <label className="text-[11px] text-slate-600 sm:col-span-2">
                    LinkedIn URL
                    <input
                      data-testid="outreach-cand-linkedin"
                      value={draftCandidate.linkedin_url}
                      onChange={(e) =>
                        setDraftCandidate((p) => ({ ...p, linkedin_url: e.target.value }))
                      }
                      placeholder="https://www.linkedin.com/in/…"
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                    />
                  </label>
                  <label className="text-[11px] text-slate-600">
                    Snippet / headline
                    <input
                      data-testid="outreach-cand-snippet"
                      value={draftCandidate.snippet}
                      onChange={(e) => setDraftCandidate((p) => ({ ...p, snippet: e.target.value }))}
                      placeholder="Optional — about / headline text"
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                    />
                  </label>
                  <label className="text-[11px] text-slate-600">
                    Recent activity note
                    <input
                      data-testid="outreach-cand-activity"
                      value={draftCandidate.recent_activity}
                      onChange={(e) =>
                        setDraftCandidate((p) => ({ ...p, recent_activity: e.target.value }))
                      }
                      placeholder='e.g. "posted we are hiring DA"'
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                    />
                  </label>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    data-testid="outreach-add-candidate"
                    onClick={handleAddToPool}
                    className="h-8 rounded-lg border border-slate-300 bg-white px-3 text-[11px] font-semibold text-slate-800"
                  >
                    + Add to list
                  </button>
                  <button
                    type="button"
                    data-testid="outreach-rank-btn"
                    disabled={rankBusy || pool.length === 0}
                    onClick={() => void handleRank()}
                    className="h-8 rounded-lg bg-slate-900 px-3 text-[11px] font-semibold text-white disabled:opacity-50"
                  >
                    {rankBusy ? "Scoring…" : `Score & sort (${pool.length})`}
                  </button>
                </div>
                {pool.length > 0 && ranked.length === 0 ? (
                  <ul className="mt-2 space-y-1 text-[11px] text-slate-600" data-testid="outreach-pool">
                    {pool.map((p) => (
                      <li key={p.localId}>
                        {p.name || "(unnamed)"} · {p.title || "—"}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>

              {ranked.length > 0 ? (
                <div className="overflow-x-auto rounded-xl border border-slate-200" data-testid="outreach-ranked-table">
                  <table className="min-w-full text-left text-[11px]">
                    <thead className="bg-slate-50 text-[10px] uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="px-2 py-2">选</th>
                        <th className="px-2 py-2">姓名</th>
                        <th className="px-2 py-2">Title</th>
                        <th className="px-2 py-2">匹配度</th>
                        <th className="px-2 py-2">匹配理由</th>
                        <th className="px-2 py-2">状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ranked.map((r) => {
                        const id = r.id || "";
                        const checked = selectedIds.includes(id);
                        return (
                          <tr
                            key={id}
                            className={`border-t border-slate-100 ${checked ? "bg-emerald-50/60" : ""}`}
                            data-testid={`outreach-ranked-row-${id}`}
                          >
                            <td className="px-2 py-2">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => toggleSelect(id)}
                                data-testid="outreach-select-candidate"
                                aria-label={`Select ${r.name}`}
                              />
                            </td>
                            <td className="px-2 py-2 font-semibold text-slate-900">{r.name || "—"}</td>
                            <td className="px-2 py-2 text-slate-700">{r.title || "—"}</td>
                            <td className="px-2 py-2 whitespace-nowrap font-semibold text-amber-800">
                              <span title={`${r.score}/100`}>
                                {starsLabel(r.stars)} {r.score}
                              </span>
                            </td>
                            <td className="max-w-[220px] px-2 py-2 text-slate-600">{r.match_reason}</td>
                            <td className="px-2 py-2 text-slate-500">未联系</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <p className="border-t border-slate-100 px-3 py-2 text-[10px] text-slate-500">
                    点选 1–3 人加入本次 outreach — 系统不替你决定发给谁。
                  </p>
                </div>
              ) : null}

              <div className="flex flex-wrap justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="h-9 rounded-xl border border-slate-200 px-3 text-xs font-semibold text-slate-700"
                >
                  ← 上一步
                </button>
                <button
                  type="button"
                  data-testid="outreach-to-step3"
                  disabled={selectedIds.length === 0}
                  onClick={commitSelectionToStep3}
                  className="h-9 rounded-xl bg-emerald-700 px-4 text-xs font-semibold text-white disabled:opacity-50"
                >
                  加入本次 outreach（{selectedIds.length}）→
                </button>
              </div>
            </div>
          ) : null}

          {/* ─── Step 3 ─── */}
          {step === 3 ? (
            <div className="space-y-3" data-testid="outreach-step3">
              <p
                className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-950"
                data-testid="outreach-email-expectancy"
              >
                70% 以上情况找不到公开邮箱是正常的。这时候优先用 LinkedIn 连接请求，效果并不比
                email 差。
              </p>

              {people.length > 1 ? (
                <div className="flex flex-wrap gap-1" data-testid="outreach-people-tabs">
                  {people.map((p) => (
                    <button
                      key={p.localId}
                      type="button"
                      onClick={() => setActivePersonId(p.localId)}
                      className={`rounded-full px-2.5 py-1 text-[10px] font-semibold ${
                        activePerson?.localId === p.localId
                          ? "bg-slate-900 text-white"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {p.name || "Person"} · {p.score}
                    </button>
                  ))}
                </div>
              ) : null}

              {activePerson ? (
                <div className="rounded-xl border border-slate-200 p-3">
                  <div className="text-xs font-bold text-slate-900">
                    {activePerson.name || "(unnamed)"}
                    <span className="ml-2 font-normal text-slate-500">{activePerson.title}</span>
                  </div>
                  <p className="mt-0.5 text-[10px] text-slate-500">{activePerson.match_reason}</p>

                  <div className="mt-3 grid gap-2 sm:grid-cols-3">
                    <button
                      type="button"
                      data-testid="outreach-find-email-btn"
                      disabled={lookupBusy}
                      onClick={() => void handleFindEmail()}
                      className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-[11px] font-semibold hover:bg-slate-50 disabled:opacity-50"
                    >
                      查邮箱
                      <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                        Hunter（如已配置）+ 格式推断 · 单次点击
                      </div>
                    </button>
                    <button
                      type="button"
                      data-testid="outreach-linkedin-channel-btn"
                      onClick={() => {
                        updateActive({ channel: "linkedin" });
                        setTemplateId("linkedin_connect");
                        setCrmNote("Channel → LinkedIn connection request (default fallback).");
                      }}
                      className={`rounded-xl border px-3 py-2 text-left text-[11px] font-semibold ${
                        activePerson.channel === "linkedin"
                          ? "border-emerald-500 bg-emerald-50 text-emerald-950"
                          : "border-slate-200 bg-white hover:bg-slate-50"
                      }`}
                    >
                      LinkedIn 连接请求
                      <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                        默认兜底路径 · 下一步生成短文案
                      </div>
                    </button>
                    <div className="rounded-xl border border-slate-200 px-3 py-2">
                      <div className="text-[11px] font-semibold text-slate-800">手动填</div>
                      <input
                        data-testid="outreach-email"
                        value={activePerson.email}
                        onChange={(e) =>
                          updateActive({
                            email: e.target.value,
                            channel: e.target.value.trim() ? "email" : activePerson.channel,
                          })
                        }
                        placeholder="you@company.com"
                        className="mt-1 h-7 w-full rounded-lg border border-slate-200 px-2 text-xs"
                      />
                    </div>
                  </div>

                  <label className="mt-2 block text-[11px] text-slate-600">
                    LinkedIn URL
                    <input
                      data-testid="outreach-linkedin"
                      value={activePerson.linkedin_url}
                      onChange={(e) => updateActive({ linkedin_url: e.target.value })}
                      className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                    />
                  </label>

                  {activePerson.emailCandidates.length > 0 ? (
                    <ul className="mt-3 space-y-2" data-testid="outreach-email-candidates">
                      {activePerson.emailCandidates.map((c) => (
                        <li
                          key={c.email}
                          className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-[11px]"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <code className="font-semibold text-slate-900">{c.email}</code>
                            <button
                              type="button"
                              data-testid="outreach-pick-email"
                              onClick={() =>
                                updateActive({ email: c.email, channel: "email" })
                              }
                              className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-900"
                            >
                              选用
                            </button>
                          </div>
                          <div className="mt-1 text-[10px] text-slate-600">
                            来源：{c.source_detail || c.source} · 置信度：
                            <span className="font-semibold">
                              {c.confidence_label} ({Math.round(c.confidence * 100)}%)
                            </span>
                            {c.smtp_status ? ` · SMTP：${c.smtp_status}` : ""}
                          </div>
                          <div className="text-[10px] text-slate-500">{c.recommendation}</div>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {activePerson.emailLookupNote ? (
                    <p className="mt-2 text-[10px] text-slate-500">{activePerson.emailLookupNote}</p>
                  ) : null}
                </div>
              ) : (
                <p className="text-xs text-slate-500">还没有选中的人 — 请回到步骤 ②。</p>
              )}

              <div className="flex flex-wrap justify-between gap-2">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="h-9 rounded-xl border border-slate-200 px-3 text-xs font-semibold text-slate-700"
                >
                  ← 上一步
                </button>
                <button
                  type="button"
                  data-testid="outreach-to-step4"
                  disabled={!activePerson}
                  onClick={() => setStep(4)}
                  className="h-9 rounded-xl bg-emerald-700 px-4 text-xs font-semibold text-white disabled:opacity-50"
                >
                  下一步：选模板起草 →
                </button>
              </div>
            </div>
          ) : null}

          {/* ─── Step 4 ─── */}
          {step === 4 ? (
            <div className="space-y-3" data-testid="outreach-step4">
              {activePerson ? (
                <div className="rounded-lg bg-slate-50 px-3 py-2 text-[11px] text-slate-700">
                  Drafting for{" "}
                  <span className="font-semibold">{activePerson.name || "contact"}</span>
                  {activePerson.email ? ` · ${activePerson.email}` : ""}
                  {` · channel: ${activePerson.channel === "unknown" ? selected.channel : activePerson.channel}`}
                  {!hasEmail && channelPref !== "email" ? (
                    <span className="ml-1 text-amber-800">(email templates hidden until you pick an email)</span>
                  ) : null}
                </div>
              ) : null}

              <div className="grid gap-2 sm:grid-cols-2">
                {availableTemplates.map((t) => {
                  const previewChars = t.preview.length;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      data-testid={`outreach-template-${t.id}`}
                      onClick={() => setTemplateId(t.id)}
                      className={`rounded-xl border px-3 py-2 text-left text-xs ${
                        templateId === t.id
                          ? "border-emerald-500 bg-emerald-50 font-semibold text-emerald-900"
                          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      {t.label}
                      <div className="mt-0.5 text-[10px] font-normal text-slate-500">
                        {t.channel} · ~{previewChars} chars preview
                      </div>
                      <div className="mt-1 line-clamp-2 text-[10px] font-normal text-slate-600">
                        {t.preview}
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="grid gap-2 sm:grid-cols-2">
                <label className="text-[11px] text-slate-600 sm:col-span-2">
                  Coffee availability
                  <input
                    data-testid="outreach-coffee-availability"
                    value={coffeeAvailability}
                    onChange={(e) => setCoffeeAvailability(e.target.value)}
                    placeholder="e.g. Tue/Thu mornings PT"
                    className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                  />
                  <div className="mt-1.5 flex flex-wrap gap-1" data-testid="outreach-coffee-slots">
                    {COFFEE_SLOT_PRESETS.map((slot) => (
                      <button
                        key={slot}
                        type="button"
                        onClick={() => setCoffeeAvailability(slot)}
                        className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-700 hover:border-emerald-300 hover:bg-emerald-50"
                      >
                        {slot}
                      </button>
                    ))}
                  </div>
                </label>
                <label className="text-[11px] text-slate-600 sm:col-span-2">
                  Reply tracking
                  <select
                    data-testid="outreach-reply-status"
                    value={replyStatus}
                    onChange={(e) => setReplyStatus(e.target.value)}
                    className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
                  >
                    {REPLY_STATUSES.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setStep(3)}
                  className="h-9 rounded-xl border border-slate-200 px-3 text-xs font-semibold text-slate-700"
                >
                  ← 上一步
                </button>
                <button
                  type="button"
                  data-testid="outreach-crm-save-btn"
                  disabled={crmBusy}
                  onClick={() => void handleSaveContact()}
                  className="h-9 rounded-xl border border-slate-300 bg-white px-4 text-xs font-semibold text-slate-800 hover:bg-slate-50 disabled:opacity-50"
                >
                  {crmBusy ? "Saving…" : "Save contact to CRM"}
                </button>
                <button
                  type="button"
                  data-testid="outreach-draft-btn"
                  disabled={busy}
                  onClick={() => void handleDraft()}
                  className="h-9 rounded-xl bg-slate-900 px-4 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                >
                  {busy ? "Drafting…" : `Draft ${selected.label}`}
                </button>
                <a
                  data-testid="outreach-crm-export"
                  href={getOutreachCrmExportUrl(userId)}
                  className="inline-flex h-9 items-center rounded-xl border border-slate-300 bg-white px-4 text-xs font-semibold text-slate-800 hover:bg-slate-50"
                >
                  Export CRM CSV
                </a>
              </div>

              {contacts.length > 0 ? (
                <div
                  className="rounded-xl border border-slate-100 bg-slate-50 p-3"
                  data-testid="outreach-crm-list"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-[11px] font-bold uppercase tracking-wide text-slate-600">
                      CRM contacts ({contacts.length})
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {[
                        { id: "all", label: "All" },
                        { id: "awaiting", label: "Awaiting" },
                        { id: "replied", label: "Replied" },
                        { id: "scheduled", label: "Scheduled" },
                      ].map((f) => (
                        <button
                          key={f.id}
                          type="button"
                          onClick={() => setCrmFilter(f.id)}
                          className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ring-1 ${
                            crmFilter === f.id
                              ? "bg-slate-900 text-white ring-slate-900"
                              : "bg-white text-slate-600 ring-slate-200"
                          }`}
                        >
                          {f.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <ul className="mt-2 max-h-36 space-y-1.5 overflow-y-auto">
                    {(crmFilter === "all"
                      ? contacts
                      : contacts.filter((c) => (c.reply_status || "none") === crmFilter)
                    ).map((c) => (
                      <li
                        key={c.id}
                        className="flex items-start justify-between gap-2 text-[11px] text-slate-700"
                      >
                        <div className="min-w-0 flex-1 truncate font-semibold">
                          {c.name || "(unnamed)"}
                          {c.role ? ` · ${c.role}` : ""}
                        </div>
                        <button
                          type="button"
                          className="shrink-0 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold"
                          onClick={() => handleLoadContact(c)}
                          data-testid="outreach-crm-load"
                        >
                          Load
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {drafts.length > 0 ? (
                <div className="space-y-2" data-testid="outreach-drafts">
                  {drafts.map((d) => (
                    <div
                      key={d.id}
                      className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs"
                      data-testid={`outreach-draft-${d.id}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="font-bold text-slate-900">{d.subject}</div>
                          <div className="text-[10px] text-slate-500">
                            {d.channel} · {d.status}
                            {d.metadata?.template_type ? ` · ${String(d.metadata.template_type)}` : ""}
                          </div>
                        </div>
                        <div className="flex shrink-0 gap-1">
                          <button
                            type="button"
                            className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold"
                            data-testid="outreach-copy-draft"
                            onClick={() => {
                              const text = `${d.subject}\n\n${d.body}`;
                              void navigator.clipboard.writeText(text).then(
                                () => setCrmNote("Draft copied to clipboard."),
                                () => setError("Clipboard copy failed")
                              );
                            }}
                          >
                            Copy
                          </button>
                          {activePerson?.email || d.channel === "email" ? (
                            <a
                              href={`mailto:${encodeURIComponent(activePerson?.email || "")}?subject=${encodeURIComponent(d.subject || "")}&body=${encodeURIComponent(d.body || "")}`}
                              className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-900"
                              data-testid="outreach-mailto"
                            >
                              Open in email
                            </a>
                          ) : null}
                          {d.status === "draft" ? (
                            <button
                              type="button"
                              className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold"
                              data-testid="outreach-mark-sent"
                              onClick={() => void handleMarkSent(d.id)}
                            >
                              Mark sent by me
                            </button>
                          ) : null}
                        </div>
                      </div>
                      <pre className="mt-2 max-h-36 overflow-y-auto whitespace-pre-wrap font-sans text-[11px] text-slate-700">
                        {d.body}
                      </pre>
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  className="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-3 py-3 text-center"
                  data-testid="outreach-drafts-empty"
                >
                  <p className="text-[11px] font-semibold text-slate-800">No drafts yet</p>
                  <p className="mt-0.5 text-[10px] text-slate-500">
                    Pick a template filtered by your channel, then Draft. You send.
                  </p>
                </div>
              )}
            </div>
          ) : null}

          {crmNote ? (
            <p className="mt-3 text-xs text-emerald-700" data-testid="outreach-crm-note">
              {crmNote}
            </p>
          ) : null}
          {error ? (
            <p className="mt-2 text-xs text-rose-600" data-testid="outreach-error">
              {error}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
