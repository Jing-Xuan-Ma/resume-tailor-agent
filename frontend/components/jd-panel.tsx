"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import { translateJdSegments } from "@/lib/api";

interface JdPanelProps {
  jdText: string;
  loading?: boolean;
  /** When true, grow with content (parent scrolls). Avoids tiny nested scroll areas. */
  expandContent?: boolean;
  /** Optional "Company · Title" from the workspace chrome. */
  jobLabel?: string | null;
}

const BILINGUAL_KEY = "jd-panel-bilingual-zh";

const SKILL_LEXICON = [
  "Excel",
  "Google Sheets",
  "Google Suite",
  "Google Suites",
  "MS Office",
  "Microsoft Office",
  "PowerPoint",
  "Word",
  "Outlook",
  "SQL",
  "Python",
  "R",
  "Tableau",
  "Power BI",
  "Looker",
  "Snowflake",
  "dbt",
  "Airflow",
  "Spark",
  "AWS",
  "Azure",
  "GCP",
  "Java",
  "JavaScript",
  "TypeScript",
  "React",
  "Node.js",
  "Golang",
  "Rust",
  "C++",
  "C#",
  "Scala",
  "Kafka",
  "Redis",
  "PostgreSQL",
  "MySQL",
  "MongoDB",
  "Salesforce",
  "SAP",
  "Jira",
  "Confluence",
  "Git",
  "Docker",
  "Kubernetes",
  "ETL",
];

const SKILL_ALIASES: Record<string, string> = {
  "Google Suites": "Google Suite",
  "Microsoft Office": "MS Office",
  Go: "Golang",
};

const NOISE_LINE =
  /text\s+messaging|message\s+frequency|text\s+stop|message\s+and\s+data\s+rates|olivia\.paradox|equal\s+opportunity|classification\s+protected|background\s+screening|click\s+here\s+to\s+learn|apply\s+to\s+.+\s+today|requisition\s+id|we\s+make\s+applying\s+easy|diversity\s+of\s+thought|are\s+you\s+looking\s+for\s+a\s+job\s+with\s+competitive|member\s+of\s+compass\s+group|wage\s+transparency|paid\s+time\s+off\s+benefits\s+information|for\s+more\s+information\s+on\s+what\s+we\s+are\s+about|follow(ing)?\s+the\s+link\s+below|associates\s+of\s+.+\s+are\s+offered\s+many\s+fantastic/i;

type SectionId =
  | "summary"
  | "responsibilities"
  | "required"
  | "preferred"
  | "benefits"
  | "company"
  | "skip";

export type JdMeta = {
  title?: string;
  company?: string;
  location?: string;
  pay?: string;
  source?: string;
  url?: string;
};

export type JdParsed = {
  meta: JdMeta;
  skills: string[];
  summary: string[];
  responsibilities: string[];
  required: string[];
  preferred: string[];
  benefits: string[];
  company: string[];
};

function unescapeMd(s: string): string {
  return s
    .replace(/\\([.\\_*`#\-\[\]()])/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function stripJdHtml(raw: string): string {
  let text = raw || "";
  text = text.replace(/<(br|\/p|\/li|\/div|\/h\d)[^>]*>/gi, "\n");
  text = text.replace(/<li[^>]*>/gi, "\n- ");
  text = text.replace(/<[^>]+>/g, " ");
  text = text
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">");
  const cssNoise =
    /^(?:tw-|sm:|md:|lg:|xl:|hover:|focus:|ring-|border-|shadow-|bg-|text-|flex|grid|rounded|px-|py-|mt-|mb-|w-|h-|font-|leading-|tracking-|opacity-|transition|absolute|relative|inset-|overflow-|items-|justify-|gap-|prose)/i;
  return text
    .split(/\r?\n/)
    .map((l) => l.replace(/[ \t]+/g, " ").trim())
    .filter((l) => {
      if (!l) return true;
      const tokens = l.split(/\s+/);
      const noisy = tokens.filter((t) => cssNoise.test(t) || t.startsWith("tw-")).length;
      return noisy < Math.max(2, Math.ceil(tokens.length / 2));
    })
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function classifyHeading(raw: string): SectionId | null {
  const t = unescapeMd(raw)
    .replace(/[:：]\s*$/, "")
    .replace(/^\d+[\).\s]+/, "")
    .trim()
    .toLowerCase();
  if (!t || t.length > 80) return null;
  if (/^-+$/.test(t) || /^={2,}$/.test(t)) return "skip";
  if (/^(job\s+summary|summary|about\s+the\s+role|role\s+overview|overview|about\s+this\s+role)$/.test(t)) {
    return "summary";
  }
  if (
    /^(key\s+responsibilities|responsibilities|what\s+you.?ll\s+do|what\s+you\s+will\s+do|duties|day\s+to\s+day)$/.test(
      t
    )
  ) {
    return "responsibilities";
  }
  if (
    /^(preferred(\s+qualifications?)?|nice[\s-]to[\s-]have|bonus|plus|desired|good\s+to\s+have)$/.test(t)
  ) {
    return "preferred";
  }
  if (
    /^(requirements?|required(\s+qualifications?)?|qualifications?|must[\s-]have|minimum\s+qualifications?|what\s+you.?ll\s+need|hard[\s-]requirements?|basic\s+qualifications?)$/.test(
      t
    )
  ) {
    return "required";
  }
  if (/^(benefits?|perks?|what\s+we\s+offer|compensation\s+&\s+benefits)$/.test(t)) {
    return "benefits";
  }
  if (/^(about\s+(us|the\s+company|levy|company)|company|who\s+we\s+are)$/.test(t)) {
    return "company";
  }
  return null;
}

function looksLikeHeading(line: string): boolean {
  const raw = line.trim();
  if (/^\*\*[^*].*[^*]\*\*:?\s*$/.test(raw)) return true;
  if (/^#{1,3}\s+\S/.test(raw)) return true;
  const plain = unescapeMd(raw);
  if (plain.length < 4 || plain.length > 70) return false;
  if (/[.?!]$/.test(plain)) return false;
  return classifyHeading(plain) !== null;
}

function extractMeta(lines: string[]): { meta: JdMeta; bodyStart: number } {
  const meta: JdMeta = {};
  let i = 0;
  let seenHeaderBlock = 0;

  while (i < lines.length) {
    const line = lines[i];
    const plain = unescapeMd(line);
    if (!plain) {
      i += 1;
      continue;
    }

    const mCompany = plain.match(/^Company\s*:\s*(.*)$/i);
    const mLoc = plain.match(/^Location\s*:\s*(.*)$/i);
    const mSource = plain.match(/^Source\s*:\s*(.*)$/i);
    const mUrl = plain.match(/^URL\s*:\s*(.*)$/i);
    const mPay = plain.match(/^(?:Pay\s*Range|Salary|Compensation|Pay)\s*:\s*(.+)$/i);

    if (mCompany || mLoc || mSource || mUrl) {
      if (mCompany && mCompany[1] && !meta.company) meta.company = mCompany[1].trim();
      if (mLoc && mLoc[1] && !meta.location) meta.location = mLoc[1].trim();
      if (mSource && mSource[1] && !meta.source) meta.source = mSource[1].trim();
      if (mUrl && mUrl[1] && !meta.url) meta.url = mUrl[1].trim();
      seenHeaderBlock = 1;
      i += 1;
      continue;
    }

    if (mPay) {
      meta.pay = mPay[1].trim();
      i += 1;
      continue;
    }

    // Title-only first lines before structured sections
    if (
      !meta.title &&
      seenHeaderBlock === 0 &&
      plain.length < 100 &&
      !/^https?:\/\//i.test(plain) &&
      !NOISE_LINE.test(plain)
    ) {
      meta.title = plain;
      i += 1;
      continue;
    }

    // Skip duplicate title/company header block
    if (
      meta.title &&
      (plain === meta.title ||
        (meta.company && plain.toLowerCase() === meta.company.toLowerCase()))
    ) {
      i += 1;
      continue;
    }

    break;
  }

  return { meta, bodyStart: i };
}

function extractSkills(texts: string[]): string[] {
  const found: string[] = [];
  const blob = texts.join(" \n ");
  for (const skill of SKILL_LEXICON) {
    // Avoid matching lone "R" inside words
    const escaped = skill.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re =
      skill.length <= 2
        ? new RegExp(`(?:^|[^A-Za-z0-9+#])${escaped}(?:[^A-Za-z0-9+#]|$)`, "i")
        : new RegExp(`(?:^|[^A-Za-z0-9+#])${escaped}(?:[^A-Za-z0-9+#]|$)`, "i");
    if (re.test(blob)) {
      const label = SKILL_ALIASES[skill] || skill;
      if (!found.some((x) => x.toLowerCase() === label.toLowerCase())) found.push(label);
    }
  }
  return found.slice(0, 12);
}

function isNoiseLine(plain: string): boolean {
  if (!plain) return true;
  if (/^-+$/.test(plain) || /^={2,}$/.test(plain)) return true;
  if (NOISE_LINE.test(plain)) return true;
  if (/^https?:\/\/\S+$/i.test(plain)) return true;
  if (plain.length > 420 && /employer|applicants|associates|without regard/i.test(plain)) return true;
  return false;
}

/** Exported for unit-style selftests. */
export function parseJdStructured(jdText: string): JdParsed {
  const cleaned = stripJdHtml(jdText);
  const lines = cleaned.split(/\r?\n/).map((l) => l.trim());
  const { meta, bodyStart } = extractMeta(lines);

  const summary: string[] = [];
  const responsibilities: string[] = [];
  const required: string[] = [];
  const preferred: string[] = [];
  const benefits: string[] = [];
  const company: string[] = [];

  let mode: SectionId = "summary";
  let started = false;

  for (let i = bodyStart; i < lines.length; i++) {
    const raw = lines[i];
    if (!raw) continue;
    const plain = unescapeMd(raw.replace(/^#{1,3}\s+/, ""));

    // Soft section cues buried in marketing sentences
    if (/fantastic benefits|employee benefits|what we offer|perks like/i.test(plain) && plain.length < 160) {
      mode = "benefits";
      started = true;
      continue;
    }

    if (looksLikeHeading(raw) || looksLikeHeading(plain)) {
      const next = classifyHeading(plain) || classifyHeading(raw);
      if (next === "skip") continue;
      if (next) {
        mode = next;
        started = true;
        const inline = plain.replace(/^[^:]+:\s*/i, "").trim();
        if (
          inline &&
          inline.toLowerCase() !== plain.toLowerCase() &&
          inline.length > 20 &&
          mode === "summary"
        ) {
          summary.push(inline);
        }
        continue;
      }
    }

    const summaryInline = plain.match(/^Summary\s*:\s*(.+)$/i);
    if (summaryInline) {
      summary.push(summaryInline[1].trim());
      mode = "summary";
      started = true;
      continue;
    }

    // Pay range can appear mid-body
    const mPay = plain.match(/^(?:Pay\s*Range|Salary|Compensation|Pay)\s*:\s*(.+)$/i);
    if (mPay) {
      if (!meta.pay) meta.pay = mPay[1].trim();
      continue;
    }

    if (isNoiseLine(plain)) continue;
    if (/^(Company|Location|Source|URL)\s*:/i.test(plain)) continue;

    let bullet = plain.replace(/^[•\-\*]\s+/, "").trim();
    if (/^\*\s+/.test(raw)) bullet = unescapeMd(raw.replace(/^\*\s+/, ""));
    if (!bullet || bullet.length < 3) continue;

    if (!started && mode === "summary") {
      if (bullet.length > 180 && /founded|venues|restaurant|industry|headquarter/i.test(bullet)) {
        company.push(bullet);
        continue;
      }
    }

    const bucket =
      mode === "responsibilities"
        ? responsibilities
        : mode === "required"
          ? required
          : mode === "preferred"
            ? preferred
            : mode === "benefits"
              ? benefits
              : mode === "company"
                ? company
                : summary;

    if (!bucket.includes(bullet)) bucket.push(bullet);
  }

  if (
    !responsibilities.length &&
    !required.length &&
    !preferred.length &&
    !benefits.length &&
    summary.length === 0
  ) {
    for (const line of lines) {
      const plain = unescapeMd(line);
      if (isNoiseLine(plain)) continue;
      if (/^(Company|Location|Source|URL|Pay)\s*:/i.test(plain)) continue;
      if (plain.length >= 40) summary.push(plain);
      if (summary.length >= 6) break;
    }
  }

  const skills = extractSkills([...required, ...preferred, ...responsibilities, ...summary]);

  return {
    meta,
    skills,
    summary: summary.slice(0, 8),
    responsibilities: responsibilities.slice(0, 12),
    required: required.slice(0, 12),
    preferred: preferred.slice(0, 12),
    benefits: benefits.slice(0, 16),
    company: company.slice(0, 4),
  };
}

function BilingualBullet({
  text,
  zh,
  showZh,
}: {
  text: string;
  zh?: string;
  showZh: boolean;
}) {
  return (
    <li className="flex gap-2.5">
      <span className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500/80" />
      <div className="min-w-0 flex-1">
        <span className="block text-[14px] leading-6 text-slate-700">{text}</span>
        {showZh && zh ? (
          <span
            className="mt-0.5 block text-[12px] leading-snug text-slate-500"
            data-testid="jd-bullet-zh"
          >
            {zh}
          </span>
        ) : null}
      </div>
    </li>
  );
}

function SectionIcon({ kind }: { kind: "summary" | "responsibilities" | "qualification" | "benefits" | "company" }) {
  const common = "h-4 w-4";
  if (kind === "responsibilities") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <rect x="3" y="7" width="18" height="13" rx="2" />
        <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      </svg>
    );
  }
  if (kind === "qualification") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <circle cx="12" cy="12" r="8" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    );
  }
  if (kind === "benefits") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <path d="M12 7v13M12 7c0-2 1.5-4 4-4 0 3-2 4-4 4zm0 0c0-2-1.5-4-4-4 0 3 2 4 4 4z" />
        <path d="M5 11h14v3a6 6 0 0 1-6 6h-2a6 6 0 0 1-6-6v-3z" />
      </svg>
    );
  }
  if (kind === "company") {
    return (
      <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
        <path d="M3 21h18M5 21V8l7-4 7 4v13M9 21v-6h6v6" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className={common} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M4 19V5M4 19h16M8 15V9m4 6V7m4 8v-4" />
    </svg>
  );
}

function SectionHeader({
  kind,
  title,
  testId,
}: {
  kind: "summary" | "responsibilities" | "qualification" | "benefits" | "company";
  title: string;
  testId: string;
}) {
  return (
    <div className="mb-3 flex items-center gap-2" data-testid={testId}>
      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
        <SectionIcon kind={kind} />
      </span>
      <h4 className="text-[15px] font-bold tracking-tight text-slate-950">{title}</h4>
    </div>
  );
}

function MetaChip({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="min-w-0 rounded-xl bg-slate-50 px-3 py-2 ring-1 ring-slate-200/80"
      data-testid={`jd-meta-${label.toLowerCase()}`}
    >
      <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 truncate text-[13px] font-semibold text-slate-800" title={value}>
        {value}
      </div>
    </div>
  );
}

export default function JdPanel({
  jdText,
  loading,
  expandContent = false,
  jobLabel = null,
}: JdPanelProps) {
  const parsed = useMemo(() => parseJdStructured(jdText || ""), [jdText]);
  const [bilingual, setBilingual] = useState(false);
  const [zhMap, setZhMap] = useState<Record<string, string>>({});
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);
  const [qualExpanded, setQualExpanded] = useState(false);
  const cacheRef = useRef<Record<string, string>>({});
  const reqIdRef = useRef(0);

  const labelCompany = jobLabel?.split("·")[0]?.trim() || "";
  const labelTitle = jobLabel?.split("·").slice(1).join("·").trim() || "";
  const title = parsed.meta.title || labelTitle || "";
  const company = parsed.meta.company || labelCompany || "";
  const location = parsed.meta.location || "";
  const pay = parsed.meta.pay || "";

  const allBullets = useMemo(
    () => [
      ...parsed.summary,
      ...parsed.responsibilities,
      ...parsed.required,
      ...parsed.preferred,
      ...parsed.benefits,
      ...parsed.company,
    ],
    [parsed]
  );

  useEffect(() => {
    try {
      setBilingual(window.localStorage.getItem(BILINGUAL_KEY) === "1");
    } catch {
      setBilingual(false);
    }
  }, []);

  useEffect(() => {
    if (!bilingual) {
      setTranslating(false);
      setTranslateError(null);
      return;
    }
    const missing = allBullets.filter((t) => t && !cacheRef.current[t]);
    if (!allBullets.length) return;
    if (!missing.length) {
      const next: Record<string, string> = {};
      for (const t of allBullets) next[t] = cacheRef.current[t];
      setZhMap(next);
      return;
    }

    const reqId = ++reqIdRef.current;
    setTranslating(true);
    setTranslateError(null);
    void translateJdSegments(missing)
      .then((res) => {
        if (reqId !== reqIdRef.current) return;
        for (const row of res.translations || []) {
          if (row.source) cacheRef.current[row.source] = row.translated || row.source;
        }
        const next: Record<string, string> = {};
        for (const t of allBullets) next[t] = cacheRef.current[t] || "";
        setZhMap(next);
      })
      .catch((err: unknown) => {
        if (reqId !== reqIdRef.current) return;
        setTranslateError(err instanceof Error ? err.message : "Translation failed");
      })
      .finally(() => {
        if (reqId === reqIdRef.current) setTranslating(false);
      });
  }, [bilingual, allBullets]);

  const toggleBilingual = () => {
    setBilingual((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(BILINGUAL_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  if (!jdText) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="jd-panel">
        <h3 className="text-base font-bold text-slate-900">Job Description</h3>
        <p className="mt-2 text-sm text-slate-500">Paste a job description or open a ranked job.</p>
      </div>
    );
  }

  const shellClass = expandContent
    ? "shrink-0 rounded-2xl border border-slate-200 bg-white shadow-sm"
    : "flex h-full min-h-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm";
  const bodyClass = expandContent
    ? "space-y-7 px-5 py-5"
    : "min-h-0 flex-1 space-y-7 overflow-y-auto px-5 py-5";

  const hasBody =
    parsed.summary.length > 0 ||
    parsed.responsibilities.length > 0 ||
    parsed.required.length > 0 ||
    parsed.preferred.length > 0 ||
    parsed.benefits.length > 0 ||
    parsed.company.length > 0;

  const qualItems = [...parsed.required, ...parsed.preferred];

  return (
    <div className={shellClass} data-testid="jd-panel">
      <div className="border-b border-slate-100 px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-lg font-bold tracking-tight text-slate-950" data-testid="jd-title">
                {title || "Job Description"}
              </h3>
              {loading ? (
                <span className="text-[11px] font-medium text-slate-500">Analyzing…</span>
              ) : null}
            </div>
            {(company || location) && (
              <p className="mt-1 text-[13px] text-slate-500" data-testid="jd-subtitle">
                {[company, location].filter(Boolean).join(" · ")}
              </p>
            )}
          </div>
          <label
            className="inline-flex shrink-0 cursor-pointer items-center gap-2 rounded-full bg-slate-50 px-2.5 py-1 ring-1 ring-slate-200"
            data-testid="jd-bilingual-toggle"
            title="Show Chinese under each bullet"
          >
            <span className="text-[11px] font-semibold text-slate-600">中文对照</span>
            <button
              type="button"
              role="switch"
              aria-checked={bilingual}
              onClick={toggleBilingual}
              className={`relative h-5 w-9 rounded-full transition ${
                bilingual ? "bg-emerald-600" : "bg-slate-300"
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
                  bilingual ? "left-4" : "left-0.5"
                }`}
              />
            </button>
          </label>
        </div>

        {(pay || location || company) && (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3" data-testid="jd-meta-row">
            {pay ? <MetaChip label="Pay" value={pay} /> : null}
            {location ? <MetaChip label="Location" value={location} /> : null}
            {company ? <MetaChip label="Company" value={company} /> : null}
          </div>
        )}
      </div>

      <div className={bodyClass}>
        {bilingual && translating ? (
          <p className="text-[11px] font-medium text-slate-500" data-testid="jd-translating">
            Translating…
          </p>
        ) : null}
        {bilingual && translateError ? (
          <p className="text-[11px] font-medium text-amber-700" data-testid="jd-translate-error">
            {translateError}
          </p>
        ) : null}

        {parsed.summary.length > 0 ? (
          <section data-testid="jd-overview">
            <SectionHeader kind="summary" title="Summary" testId="jd-section-summary" />
            <div className="space-y-2">
              {parsed.summary.map((item, i) => (
                <p key={i} className="text-[14px] leading-6 text-slate-700">
                  {item}
                  {bilingual && zhMap[item] ? (
                    <span className="mt-0.5 block text-[12px] text-slate-500">{zhMap[item]}</span>
                  ) : null}
                </p>
              ))}
            </div>
          </section>
        ) : null}

        {parsed.responsibilities.length > 0 ? (
          <section data-testid="jd-responsibilities">
            <SectionHeader
              kind="responsibilities"
              title="Responsibilities"
              testId="jd-section-responsibilities"
            />
            <ul className="space-y-2.5">
              {parsed.responsibilities.map((item, i) => (
                <BilingualBullet key={i} text={item} zh={zhMap[item]} showZh={bilingual} />
              ))}
            </ul>
          </section>
        ) : null}

        {qualItems.length > 0 || parsed.skills.length > 0 ? (
          <section data-testid="jd-required">
            <SectionHeader
              kind="qualification"
              title="Qualification"
              testId="jd-section-qualification"
            />
            {parsed.skills.length > 0 ? (
              <div className="mb-3 flex flex-wrap gap-2" data-testid="jd-skill-tags">
                {parsed.skills.map((skill) => (
                  <span
                    key={skill}
                    className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2.5 py-1 text-[12px] font-semibold text-emerald-800 ring-1 ring-emerald-100"
                    data-testid="jd-skill-tag"
                  >
                    <svg viewBox="0 0 16 16" className="h-3 w-3 text-emerald-600" fill="currentColor" aria-hidden>
                      <path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5v-9zM4 5v1.5h8V5H4zm0 3v1.5h5V8H4z" />
                    </svg>
                    {skill}
                  </span>
                ))}
              </div>
            ) : null}
            {parsed.required.length > 0 ? (
              <>
                <p className="mb-2 text-[13px] font-bold text-slate-900">Required</p>
                <ul className="mb-4 space-y-2.5">
                  {(qualExpanded ? parsed.required : parsed.required.slice(0, 5)).map((item, i) => (
                    <BilingualBullet key={i} text={item} zh={zhMap[item]} showZh={bilingual} />
                  ))}
                </ul>
              </>
            ) : null}
            {parsed.preferred.length > 0 ? (
              <>
                <p className="mb-2 text-[13px] font-bold text-slate-900">
                  {parsed.required.length ? "Preferred" : "Required"}
                </p>
                <ul className="space-y-2.5" data-testid="jd-preferred">
                  {(qualExpanded
                    ? parsed.preferred
                    : parsed.preferred.slice(0, parsed.required.length ? 4 : 5)
                  ).map((item, i) => (
                    <BilingualBullet key={i} text={item} zh={zhMap[item]} showZh={bilingual} />
                  ))}
                </ul>
              </>
            ) : null}
            {qualItems.length > 5 ? (
              <button
                type="button"
                className="mt-3 text-[12px] font-semibold text-emerald-700 hover:text-emerald-800"
                data-testid="jd-qual-expand"
                onClick={() => setQualExpanded((v) => !v)}
              >
                {qualExpanded ? "Show less" : `Show all ${qualItems.length} qualifications`}
              </button>
            ) : null}
          </section>
        ) : null}

        {parsed.benefits.length > 0 ? (
          <section data-testid="jd-benefits">
            <SectionHeader kind="benefits" title="Benefits" testId="jd-section-benefits" />
            <ul className="grid grid-cols-1 gap-x-6 gap-y-2.5 sm:grid-cols-2">
              {parsed.benefits.map((item, i) => (
                <BilingualBullet key={i} text={item} zh={zhMap[item]} showZh={bilingual} />
              ))}
            </ul>
          </section>
        ) : null}

        {parsed.company.length > 0 ? (
          <section data-testid="jd-company">
            <SectionHeader kind="company" title="Company" testId="jd-section-company" />
            <div className="space-y-2">
              {parsed.company.map((item, i) => (
                <p key={i} className="text-[14px] leading-6 text-slate-700">
                  {item}
                  {bilingual && zhMap[item] ? (
                    <span className="mt-0.5 block text-[12px] text-slate-500">{zhMap[item]}</span>
                  ) : null}
                </p>
              ))}
            </div>
          </section>
        ) : null}

        {!hasBody ? (
          <pre
            className="whitespace-pre-wrap font-sans text-[13px] leading-5 text-slate-700"
            data-testid="jd-plaintext"
          >
            {stripJdHtml(jdText)}
          </pre>
        ) : null}
      </div>
    </div>
  );
}
