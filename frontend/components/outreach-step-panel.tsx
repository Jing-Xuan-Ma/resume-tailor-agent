"use client";

import { useCallback, useEffect, useState } from "react";
import {
  draftOutreach,
  getOutreachCrmExportUrl,
  listOutreachContacts,
  markOutreachSent,
  upsertOutreachContact,
  type OutreachContact,
  type OutreachMessage,
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

const TEMPLATES = [
  {
    id: "coffee_chat",
    label: "Coffee chat",
    channel: "linkedin" as const,
    roleHint: "Hiring Manager / Team Lead",
  },
  {
    id: "post_apply_thanks",
    label: "Post-apply thank-you",
    channel: "email" as const,
    roleHint: "Recruiter",
  },
  {
    id: "recruiter_ping",
    label: "Recruiter ping",
    channel: "email" as const,
    roleHint: "Talent Acquisition",
  },
];

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
  company,
  position,
}: OutreachStepPanelProps) {
  const [contactName, setContactName] = useState("");
  const [contactRole, setContactRole] = useState("Hiring Manager");
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [coffeeAvailability, setCoffeeAvailability] = useState("");
  const [replyStatus, setReplyStatus] = useState("none");
  const [templateId, setTemplateId] = useState("coffee_chat");
  const [busy, setBusy] = useState(false);
  const [crmBusy, setCrmBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crmNote, setCrmNote] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<OutreachMessage[]>([]);
  const [contacts, setContacts] = useState<OutreachContact[]>([]);
  const [crmFilter, setCrmFilter] = useState<string>("all");

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

  if (!show) return null;

  const selected = TEMPLATES.find((t) => t.id === templateId) || TEMPLATES[0];

  const handleDraft = async () => {
    setBusy(true);
    setError(null);
    setCrmNote(null);
    try {
      const msg = await draftOutreach({
        user_id: userId,
        job_id: jobId || undefined,
        contact_name: contactName || undefined,
        contact_role: contactRole || selected.roleHint,
        company: company || undefined,
        channel: selected.channel,
        tone: templateId === "recruiter_ping" ? "concise" : "warm",
        template_type: templateId,
        linkedin_url: linkedinUrl || undefined,
        contact_email: contactEmail || undefined,
        coffee_availability: coffeeAvailability || undefined,
        save_to_crm: !!(contactName || linkedinUrl || contactEmail),
      });
      setDrafts((prev) => [msg, ...prev].slice(0, 6));
      if (contactName || linkedinUrl || contactEmail) {
        await refreshContacts();
        setCrmNote("Contact saved to CRM with this draft.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Draft failed");
    } finally {
      setBusy(false);
    }
  };

  const handleSaveContact = async () => {
    if (!contactName && !linkedinUrl && !contactEmail) {
      setError("Enter a name, LinkedIn URL, or email before saving.");
      return;
    }
    setCrmBusy(true);
    setError(null);
    setCrmNote(null);
    try {
      await upsertOutreachContact({
        user_id: userId,
        name: contactName || undefined,
        role: contactRole || undefined,
        company: company || undefined,
        job_id: jobId || undefined,
        linkedin_url: linkedinUrl || undefined,
        email: contactEmail || undefined,
        coffee_availability: coffeeAvailability || undefined,
        coffee_slots: coffeeAvailability ? [coffeeAvailability] : [],
        status: "identified",
        reply_status: replyStatus,
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
    setContactName(c.name || "");
    setContactRole(c.role || "Hiring Manager");
    setLinkedinUrl(c.linkedin_url || "");
    setContactEmail(c.email || "");
    setCoffeeAvailability(c.coffee_availability || "");
    setReplyStatus(c.reply_status || "none");
    setCrmNote(`Loaded ${c.name || "contact"} from CRM.`);
  };

  const handleMarkSent = async (id: string) => {
    try {
      const updated = await markOutreachSent(id, userId);
      setDrafts((prev) => prev.map((d) => (d.id === id ? updated : d)));
      // Track outreach as awaiting reply in CRM when we have a contact name
      if (contactName || linkedinUrl || contactEmail) {
        await upsertOutreachContact({
          user_id: userId,
          name: contactName || undefined,
          role: contactRole || undefined,
          company: company || undefined,
          job_id: jobId || undefined,
          linkedin_url: linkedinUrl || undefined,
          email: contactEmail || undefined,
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

  const searchQueries = [
    `${company || "Company"} "Hiring Manager" ${position ? `"${position.split(" ")[0]}"` : "Data"}`,
    `${company || "Company"} Recruiter OR "Talent Acquisition"`,
    `${company || "Company"} "Head of Data" OR "Analytics Manager" OR "Data Lead"`,
  ];

  const linkedInSearchUrl = (q: string) =>
    `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(q)}`;

  return (
    <div
      className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
      data-testid="outreach-step-panel"
    >
      <h3 className="text-sm font-bold text-slate-950">Step 6 · Find people / Cold outreach</h3>
      <p className="mt-1 text-xs text-slate-500">
        Semi-auto playbook: open LinkedIn searches, save contacts to CRM, then draft. You always send —
        no mass mail.
      </p>
      <p
        className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-amber-800"
        data-testid="outreach-no-auto-send"
      >
        Safety: drafts only — never auto-sends email or LinkedIn
      </p>

      <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-3" data-testid="hm-playbook">
        <div className="text-[11px] font-bold uppercase tracking-wide text-slate-600">
          Hiring-manager search playbook
        </div>
        <ul className="mt-2 space-y-1.5">
          {searchQueries.map((q) => (
            <li key={q} className="flex items-start justify-between gap-2 text-[11px] text-slate-700">
              <span className="min-w-0 flex-1 truncate" title={q}>
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
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[10px] text-slate-500">
          Prefer: Hiring Manager → Team Lead / Head of Data → Recruiter. Skip mass InMails.
        </p>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {TEMPLATES.map((t) => (
          <button
            key={t.id}
            type="button"
            data-testid={`outreach-template-${t.id}`}
            onClick={() => {
              setTemplateId(t.id);
              if (!contactRole || TEMPLATES.some((x) => x.roleHint === contactRole)) {
                setContactRole(t.roleHint);
              }
            }}
            className={`rounded-xl border px-3 py-2 text-left text-xs ${
              templateId === t.id
                ? "border-emerald-500 bg-emerald-50 font-semibold text-emerald-900"
                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            {t.label}
            <div className="mt-0.5 text-[10px] font-normal text-slate-500">{t.channel}</div>
          </button>
        ))}
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <label className="text-[11px] text-slate-600">
          Contact name
          <input
            data-testid="outreach-contact-name"
            value={contactName}
            onChange={(e) => setContactName(e.target.value)}
            placeholder="Optional — e.g. Alex Chen"
            className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
          />
        </label>
        <label className="text-[11px] text-slate-600">
          Role
          <input
            data-testid="outreach-contact-role"
            value={contactRole}
            onChange={(e) => setContactRole(e.target.value)}
            className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
          />
        </label>
        <label className="text-[11px] text-slate-600">
          LinkedIn URL
          <input
            data-testid="outreach-linkedin"
            value={linkedinUrl}
            onChange={(e) => setLinkedinUrl(e.target.value)}
            placeholder="Paste after you find them"
            className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
          />
        </label>
        <label className="text-[11px] text-slate-600">
          Email (if known)
          <input
            data-testid="outreach-email"
            value={contactEmail}
            onChange={(e) => setContactEmail(e.target.value)}
            placeholder="optional"
            className="mt-1 h-8 w-full rounded-lg border border-slate-200 px-2 text-xs"
          />
        </label>
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
                data-testid={`outreach-coffee-slot-${slot.slice(0, 8)}`}
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
            onChange={(e) => {
              const next = e.target.value;
              setReplyStatus(next);
              if (
                (next === "replied" || next === "scheduled") &&
                (contactName || linkedinUrl || contactEmail)
              ) {
                void upsertOutreachContact({
                  user_id: userId,
                  name: contactName || undefined,
                  role: contactRole || undefined,
                  company: company || undefined,
                  job_id: jobId || undefined,
                  linkedin_url: linkedinUrl || undefined,
                  email: contactEmail || undefined,
                  coffee_availability: coffeeAvailability || undefined,
                  status: next === "scheduled" ? "scheduled" : "replied",
                  reply_status: next,
                })
                  .then(() => {
                    setCrmNote(`Reply status saved: ${next}`);
                    return refreshContacts();
                  })
                  .catch((err) =>
                    setError(err instanceof Error ? err.message : "Reply status save failed")
                  );
              }
            }}
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

      <div className="mt-3 flex flex-wrap gap-2">
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

      {crmNote ? (
        <p className="mt-2 text-xs text-emerald-700" data-testid="outreach-crm-note">
          {crmNote}
        </p>
      ) : null}

      {error ? (
        <p className="mt-2 text-xs text-rose-600" data-testid="outreach-error">
          {error}
        </p>
      ) : null}

      {contacts.length > 0 ? (
        <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-3" data-testid="outreach-crm-list">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[11px] font-bold uppercase tracking-wide text-slate-600">
              CRM contacts ({contacts.length})
            </div>
            <div className="flex flex-wrap gap-1" data-testid="outreach-crm-filters">
              {[
                { id: "all", label: "All" },
                { id: "awaiting", label: "Awaiting" },
                { id: "replied", label: "Replied" },
                { id: "scheduled", label: "Scheduled" },
              ].map((f) => (
                <button
                  key={f.id}
                  type="button"
                  data-testid={`outreach-crm-filter-${f.id}`}
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
          <ul className="mt-2 max-h-40 space-y-1.5 overflow-y-auto">
            {(() => {
              const visible =
                crmFilter === "all"
                  ? contacts
                  : contacts.filter((c) => (c.reply_status || "none") === crmFilter);
              if (!visible.length) {
                return (
                  <li className="text-[10px] text-slate-500" data-testid="outreach-crm-filter-empty">
                    No contacts for this reply filter.
                  </li>
                );
              }
              return visible.map((c) => (
              <li
                key={c.id}
                className="flex items-start justify-between gap-2 text-[11px] text-slate-700"
                data-testid={`outreach-crm-contact-${c.id}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold text-slate-900">
                    {c.name || "(unnamed)"}
                    {c.role ? ` · ${c.role}` : ""}
                  </div>
                  <div className="truncate text-[10px] text-slate-500">
                    {[
                      c.company,
                      c.email,
                      c.coffee_availability,
                      c.last_reply_at ? `at:${c.last_reply_at.slice(0, 10)}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ") ||
                      c.linkedin_url ||
                      c.status}
                  </div>
                  {c.reply_status && c.reply_status !== "none" ? (
                    <span
                      data-testid="outreach-reply-badge"
                      className={`mt-0.5 inline-block rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
                        c.reply_status === "replied"
                          ? "bg-emerald-100 text-emerald-800"
                          : c.reply_status === "scheduled"
                            ? "bg-sky-100 text-sky-800"
                            : c.reply_status === "awaiting"
                              ? "bg-amber-100 text-amber-900"
                              : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {c.reply_status}
                    </span>
                  ) : null}
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
            ));
            })()}
          </ul>
        </div>
      ) : null}

      {drafts.length === 0 ? (
        <div
          className="mt-3 rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-3 py-3 text-center"
          data-testid="outreach-drafts-empty"
        >
          <p className="text-[11px] font-semibold text-slate-800">No drafts yet</p>
          <p className="mt-0.5 text-[10px] text-slate-500">
            Fill a contact (optional), pick a template, then Draft. You send — we never mass-mail.
          </p>
          <button
            type="button"
            data-testid="outreach-draft-hint-btn"
            disabled={busy}
            onClick={() => void handleDraft()}
            className="mt-2 h-8 rounded-lg bg-slate-900 px-3 text-[11px] font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {busy ? "Drafting…" : "Draft coffee chat now"}
          </button>
        </div>
      ) : null}

      {drafts.length > 0 ? (
        <div className="mt-3 space-y-2" data-testid="outreach-drafts">
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
                    {d.metadata?.safety ? ` · ${String(d.metadata.safety)}` : ""}
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
                  {contactEmail || d.channel === "email" ? (
                    <a
                      href={`mailto:${encodeURIComponent(contactEmail || "")}?subject=${encodeURIComponent(d.subject || "")}&body=${encodeURIComponent(d.body || "")}`}
                      className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-900"
                      data-testid="outreach-mailto"
                      onClick={() => {
                        setCrmNote("Opened mail client (mailto). Mark sent after you hit Send.");
                      }}
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
      ) : null}
    </div>
  );
}
