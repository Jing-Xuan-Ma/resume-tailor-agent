"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import { translateJdSegments } from "@/lib/api";

interface JdPanelProps {
  jdText: string;
  loading?: boolean;
  /** When true, grow with content (parent scrolls). Avoids tiny nested scroll areas. */
  expandContent?: boolean;
}

const BILINGUAL_KEY = "jd-panel-bilingual-zh";

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

function parseSections(jdText: string): {
  required: string[];
  preferred: string[];
  overview: string[];
} {
  const cleaned = stripJdHtml(jdText);
  const lines = cleaned.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  const required: string[] = [];
  const preferred: string[] = [];
  const overview: string[] = [];
  let mode: "required" | "preferred" | "overview" = "overview";

  for (const line of lines) {
    const lower = line.toLowerCase().replace(/:$/, "");
    if (/^(requirements?|required|qualifications?|must[\s-]have|what you.?ll need|hard[\s-]requirements?)/i.test(lower)) {
      mode = "required";
      continue;
    }
    if (/^(preferred|nice[\s-]to[\s-]have|bonus|plus|desired)/i.test(lower)) {
      mode = "preferred";
      continue;
    }
    if (/^(about|responsibilities|what you.?ll do|role|overview|job description)/i.test(lower)) {
      mode = "overview";
      continue;
    }
    const bullet = line.replace(/^[•\-\*]\s*/, "").trim();
    if (!bullet || bullet.length < 3) continue;
    if (mode === "required") required.push(bullet);
    else if (mode === "preferred") preferred.push(bullet);
    else overview.push(bullet);
  }

  // Unstructured JD: show full body under JD (no fake Required split).
  if (!required.length && !preferred.length && overview.length) {
    return { overview, required: [], preferred: [] };
  }
  return { required, preferred, overview };
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
    <li className="flex gap-2">
      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
      <div className="min-w-0 flex-1">
        <span className="block text-[13px] leading-5 text-slate-700">{text}</span>
        {showZh && zh ? (
          <span
            className="mt-0.5 block text-[12px] leading-snug text-slate-500"
            data-testid="jd-bullet-zh"
            style={{ letterSpacing: "0.01em" }}
          >
            {zh}
          </span>
        ) : null}
      </div>
    </li>
  );
}

export default function JdPanel({ jdText, loading, expandContent = false }: JdPanelProps) {
  const sections = useMemo(() => parseSections(jdText || ""), [jdText]);
  const [bilingual, setBilingual] = useState(false);
  const [zhMap, setZhMap] = useState<Record<string, string>>({});
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState<string | null>(null);
  const cacheRef = useRef<Record<string, string>>({});
  const reqIdRef = useRef(0);

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
    const all = [...sections.overview, ...sections.required, ...sections.preferred];
    const missing = all.filter((t) => t && !cacheRef.current[t]);
    if (!all.length) return;
    if (!missing.length) {
      const next: Record<string, string> = {};
      for (const t of all) next[t] = cacheRef.current[t];
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
        for (const t of all) next[t] = cacheRef.current[t] || "";
        setZhMap(next);
      })
      .catch((err: unknown) => {
        if (reqId !== reqIdRef.current) return;
        setTranslateError(err instanceof Error ? err.message : "Translation failed");
      })
      .finally(() => {
        if (reqId === reqIdRef.current) setTranslating(false);
      });
  }, [bilingual, sections.overview, sections.required, sections.preferred]);

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
    ? "px-5 py-4"
    : "min-h-0 flex-1 overflow-y-auto px-5 py-4";

  const hasStructured =
    sections.overview.length > 0 || sections.required.length > 0 || sections.preferred.length > 0;

  return (
    <div className={shellClass} data-testid="jd-panel">
      <div className="border-b border-slate-100 px-5 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
                <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor" aria-hidden>
                  <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
                  <circle cx="10" cy="10" r="3" />
                </svg>
              </span>
              <h3 className="text-base font-bold tracking-tight text-slate-950">Job Description</h3>
              {loading ? (
                <span className="text-[11px] font-medium text-slate-500">Analyzing…</span>
              ) : null}
            </div>
            <p className="mt-1 max-w-xl text-[12px] leading-4 text-slate-500">
              Role overview and hard requirements from the JD.
            </p>
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
      </div>

      <div className={bodyClass}>
        {bilingual && translating ? (
          <p className="mb-3 text-[11px] font-medium text-slate-500" data-testid="jd-translating">
            Translating…
          </p>
        ) : null}
        {bilingual && translateError ? (
          <p className="mb-3 text-[11px] font-medium text-amber-700" data-testid="jd-translate-error">
            {translateError}
          </p>
        ) : null}

        {sections.overview.length > 0 && (
          <section className="mb-5" data-testid="jd-overview">
            <h4 className="mb-2 text-sm font-bold text-slate-950">JD</h4>
            <ul className="space-y-2 text-[13px] leading-5 text-slate-700">
              {sections.overview.map((item, i) => (
                <BilingualBullet key={i} text={item} zh={zhMap[item]} showZh={bilingual} />
              ))}
            </ul>
          </section>
        )}

        {sections.required.length > 0 && (
          <section className="mb-5" data-testid="jd-required">
            <h4 className="mb-2 text-sm font-bold text-slate-950">Required（硬性要求）</h4>
            <ul className="space-y-2 text-[13px] leading-5 text-slate-700">
              {sections.required.map((item, i) => (
                <BilingualBullet key={i} text={item} zh={zhMap[item]} showZh={bilingual} />
              ))}
            </ul>
          </section>
        )}

        {sections.preferred.length > 0 && (
          <section className="mb-5" data-testid="jd-preferred">
            <h4 className="mb-2 text-sm font-bold text-slate-950">Preferred</h4>
            <ul className="space-y-2 text-[13px] leading-5 text-slate-700">
              {sections.preferred.map((item, i) => (
                <BilingualBullet key={i} text={item} zh={zhMap[item]} showZh={bilingual} />
              ))}
            </ul>
          </section>
        )}

        {!hasStructured && (
          <pre
            className="whitespace-pre-wrap font-sans text-[13px] leading-5 text-slate-700"
            data-testid="jd-plaintext"
          >
            {stripJdHtml(jdText)}
          </pre>
        )}
      </div>
    </div>
  );
}
