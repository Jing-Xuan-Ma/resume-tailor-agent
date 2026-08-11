"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
/** Same-origin Next proxy → backend /intern-list/api (avoids CORS + hard-coded host issues). */
const IL_API = "/intern-list-viewer/api";

type JobItem = {
  job_id: string;
  title?: string;
  company?: string;
  location?: string;
  work_model?: string;
  salary?: string;
  posted_at?: number;
  has_detail?: number;
  slug?: string;
};

type Stats = {
  list_total?: number;
  unique_jobs?: number;
  detail_total?: number;
  by_slug?: Record<string, number>;
  db?: string;
};

type DetailPayload = {
  job_id: string;
  detail?: Record<string, unknown> | null;
  sections?: {
    title?: string;
    company?: string;
    location?: string;
    work_model?: string;
    summary?: string;
    responsibilities?: string[];
    qualification?: string[];
    required?: string[];
    preferred?: string[];
  } | null;
  list_rows?: JobItem[];
};

const TARGETS = [
  { slug: "swe", label: "Software Engineering" },
  { slug: "data_analysis", label: "Data Analysis" },
  { slug: "ml_ai", label: "Machine Learning and AI" },
  { slug: "product_management", label: "Product Management" },
  { slug: "accounting_finance", label: "Accounting and Finance" },
  { slug: "business_analyst", label: "Business Analyst" },
];

function relativeDate(postedAt?: number) {
  const n = Number(postedAt);
  if (!Number.isFinite(n) || n <= 0) return "—";
  const ms = n < 1e12 ? n * 1000 : n;
  const diff = Date.now() - ms;
  if (diff < 0) return "just now";
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} minutes ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  const months = Math.floor(days / 30);
  return `${months} month${months === 1 ? "" : "s"} ago`;
}

function workModelClass(model?: string) {
  const key = String(model || "")
    .toLowerCase()
    .replace(/\s+/g, "");
  if (key.includes("remote")) return "bg-cyan-50 text-cyan-800 ring-cyan-200";
  if (key.includes("hybrid")) return "bg-emerald-50 text-emerald-800 ring-emerald-200";
  if (key.includes("onsite") || key.includes("on-site")) return "bg-violet-50 text-violet-800 ring-violet-200";
  return "bg-slate-100 text-slate-600 ring-slate-200";
}

export default function InternListJobsPanel() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [total, setTotal] = useState(0);
  const [slug, setSlug] = useState("");
  const [q, setQ] = useState("");
  const [qLive, setQLive] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, JobItem>>({});
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DetailPayload | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [scrapeLog, setScrapeLog] = useState("");
  const [leftWidth, setLeftWidth] = useState(62);

  const selectedIds = useMemo(() => Object.keys(selected), [selected]);

  const loadStats = useCallback(async () => {
    const res = await fetch(`${IL_API}/stats`, { cache: "no-store" });
    if (!res.ok) throw new Error(`stats ${res.status}`);
    const data = (await res.json()) as Stats;
    setStats(data);
    return data;
  }, []);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (slug) params.set("slug", slug);
      if (q.trim()) params.set("q", q.trim());
      const res = await fetch(`${IL_API}/jobs?${params}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`jobs ${res.status}`);
      const data = await res.json();
      setJobs(data.items || []);
      setTotal(data.total || 0);
    } catch (err) {
      setJobs([]);
      setError(
        err instanceof Error
          ? `${err.message}. 请确认后端已启动：${API_BASE}（Intern-list 挂在 /intern-list）`
          : `无法连接 Intern-list API（经前端代理）。请启动后端 ${API_BASE}`
      );
    } finally {
      setLoading(false);
    }
  }, [slug, q]);

  useEffect(() => {
    const t = window.setTimeout(() => setQ(qLive), 280);
    return () => window.clearTimeout(t);
  }, [qLive]);

  useEffect(() => {
    loadStats().catch(() => {
      setError(`无法连接 Intern-list API。请先启动后端 ${API_BASE}`);
    });
  }, [loadStats]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  const openDetail = useCallback(async (jobId: string) => {
    setActiveId(jobId);
    setDetailLoading(true);
    try {
      const res = await fetch(`${IL_API}/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`detail ${res.status}`);
      setDetail((await res.json()) as DetailPayload);
    } catch (err) {
      setDetail(null);
      setError(err instanceof Error ? err.message : "加载详情失败");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const toggleSelect = (job: JobItem, on: boolean) => {
    setSelected((prev) => {
      const next = { ...prev };
      if (on) next[job.job_id] = job;
      else delete next[job.job_id];
      return next;
    });
  };

  const selectAllVisible = (on: boolean) => {
    setSelected((prev) => {
      const next = { ...prev };
      for (const job of jobs) {
        if (on) next[job.job_id] = job;
        else delete next[job.job_id];
      }
      return next;
    });
  };

  const openShoppingCart = () => {
    if (!selectedIds.length) return;
    const url = new URL("/shoppingcart", window.location.origin);
    url.searchParams.set("internJobIds", selectedIds.join(","));
    url.searchParams.set("from", "intern-list");
    window.open(url.toString(), "_blank", "noopener");
  };

  const pollScrape = useCallback(async () => {
    const res = await fetch(`${IL_API}/scrape/status`, { cache: "no-store" });
    const st = await res.json();
    setScrapeLog(`${st.running ? "抓取进行中…\n" : "抓取结束\n"}${st.log || ""}`);
    if (st.running) {
      window.setTimeout(() => {
        void pollScrape();
      }, 2000);
    } else {
      await loadStats();
      await loadJobs();
    }
  }, [loadJobs, loadStats]);

  const startScrape = async (mode: "current" | "all" | "backfill") => {
    const params = new URLSearchParams({ with_details: "true" });
    if (mode === "current") {
      params.set("limit", "30");
      if (slug) params.set("slug", slug);
    } else if (mode === "all") {
      params.set("limit", "30");
    } else {
      params.set("backfill_details", "true");
      if (slug) params.set("slug", slug);
    }
    await fetch(`${IL_API}/scrape?${params}`, { method: "POST" });
    void pollScrape();
  };

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!(window as unknown as { __ilResizing?: boolean }).__ilResizing) return;
      const root = document.getElementById("il-split");
      if (!root) return;
      const rect = root.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftWidth(Math.max(32, Math.min(75, pct)));
    };
    const onUp = () => {
      (window as unknown as { __ilResizing?: boolean }).__ilResizing = false;
      document.body.classList.remove("select-none");
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  const sections = detail?.sections;
  const list0 = detail?.list_rows?.[0];
  const d = detail?.detail || {};

  return (
    <div className="flex flex-col gap-3" data-testid="intern-list-jobs-panel">
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-950">
        <p className="font-semibold">Intern-list 职位源（原生页面）</p>
        <p className="mt-1 text-xs text-emerald-900/80">
          数据来自 intern-list.com，经本项目后端 <code className="font-mono">{IL_API}</code> 读取。无需 8101，也无需 iframe。
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs">
          唯一职位 <strong className="text-emerald-700">{stats?.unique_jobs ?? "—"}</strong>
        </div>
        <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs">
          分类行 <strong className="text-emerald-700">{stats?.list_total ?? "—"}</strong>
        </div>
        <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs">
          详情 <strong className="text-emerald-700">{stats?.detail_total ?? "—"}</strong>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setSlug("")}
          className={`rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ${
            slug === "" ? "bg-emerald-600 text-white ring-emerald-600" : "bg-white text-slate-700 ring-slate-200"
          }`}
        >
          全部
        </button>
        {TARGETS.map((t) => (
          <button
            key={t.slug}
            type="button"
            onClick={() => setSlug(t.slug)}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ${
              slug === t.slug ? "bg-emerald-600 text-white ring-emerald-600" : "bg-white text-slate-700 ring-slate-200"
            }`}
          >
            {t.label}
            <span className="ml-1 opacity-80">{stats?.by_slug?.[t.slug] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white p-3">
        <input
          value={qLive}
          onChange={(e) => setQLive(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") setQ(qLive);
          }}
          placeholder="搜索 title / company / location"
          className="h-9 min-w-[220px] flex-1 rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-emerald-500"
        />
        <button
          type="button"
          onClick={() => void loadJobs()}
          className="h-9 rounded-xl bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-700"
        >
          {loading ? "加载中…" : "刷新列表"}
        </button>
        <button
          type="button"
          onClick={() => void startScrape("current")}
          className="h-9 rounded-xl bg-emerald-50 px-3 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-200"
        >
          抓取当前分类
        </button>
        <button
          type="button"
          onClick={() => void startScrape("all")}
          className="h-9 rounded-xl bg-emerald-50 px-3 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-200"
        >
          抓取六类各30条
        </button>
        <button
          type="button"
          onClick={() => void startScrape("backfill")}
          className="h-9 rounded-xl bg-emerald-50 px-3 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-200"
        >
          补抓全部详情
        </button>
      </div>

      {scrapeLog ? (
        <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-white p-3 text-[11px] text-slate-500">
          {scrapeLog}
        </pre>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</div>
      ) : null}

      <div id="il-split" className="flex min-h-[70vh] items-stretch gap-0">
        <section
          className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
          style={{ width: `${leftWidth}%`, minWidth: 280 }}
        >
          <div className="flex items-center justify-between border-b border-slate-100 bg-[#fbfdfc] px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">
              职位列表 ({total}){slug ? ` · ${slug}` : ""}
            </h2>
          </div>
          <div className="max-h-[70vh] overflow-auto">
            <table className="w-full min-w-[720px] border-collapse text-left text-[13px]">
              <thead className="sticky top-0 bg-white text-[11px] uppercase tracking-wide text-slate-500">
                <tr className="border-b border-slate-100">
                  <th className="w-10 px-3 py-2">
                    <input
                      type="checkbox"
                      checked={jobs.length > 0 && jobs.every((j) => selected[j.job_id])}
                      onChange={(e) => selectAllVisible(e.target.checked)}
                      className="accent-emerald-600"
                      aria-label="全选"
                    />
                  </th>
                  <th className="w-10 px-2 py-2">#</th>
                  <th className="px-2 py-2">Position</th>
                  <th className="px-2 py-2">Date</th>
                  <th className="px-2 py-2">Work</th>
                  <th className="px-2 py-2">Location</th>
                  <th className="px-2 py-2">Company</th>
                  <th className="px-2 py-2">Salary</th>
                </tr>
              </thead>
              <tbody>
                {jobs.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-16 text-center text-sm text-slate-500">
                      {loading ? "加载中…" : "暂无职位"}
                    </td>
                  </tr>
                ) : (
                  jobs.map((job, idx) => (
                    <tr
                      key={job.job_id}
                      onClick={() => void openDetail(job.job_id)}
                      className={`cursor-pointer border-b border-slate-50 hover:bg-emerald-50/60 ${
                        activeId === job.job_id ? "bg-emerald-50" : ""
                      } ${selected[job.job_id] ? "bg-[#eef8f2]" : ""}`}
                    >
                      <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={Boolean(selected[job.job_id])}
                          onChange={(e) => toggleSelect(job, e.target.checked)}
                          className="accent-emerald-600"
                        />
                      </td>
                      <td className="px-2 py-2 text-slate-400">{idx + 1}</td>
                      <td className="max-w-[240px] truncate px-2 py-2 font-semibold text-slate-950">{job.title || "—"}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-slate-500">{relativeDate(job.posted_at)}</td>
                      <td className="px-2 py-2">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ${workModelClass(job.work_model)}`}>
                          {job.work_model || "—"}
                        </span>
                      </td>
                      <td className="max-w-[120px] truncate px-2 py-2 text-slate-600">{job.location || "—"}</td>
                      <td className="max-w-[140px] truncate px-2 py-2 text-slate-800">{job.company || "—"}</td>
                      <td className="whitespace-nowrap px-2 py-2 text-slate-600">{job.salary || "N/A"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        <div
          role="separator"
          aria-orientation="vertical"
          title="拖拽调整宽度"
          className="mx-1 w-2 cursor-col-resize rounded bg-transparent hover:bg-emerald-100"
          onMouseDown={() => {
            (window as unknown as { __ilResizing?: boolean }).__ilResizing = true;
            document.body.classList.add("select-none");
          }}
        />

        <section className="min-w-[240px] flex-1 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 bg-[#fbfdfc] px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">详情 / JD</h2>
          </div>
          <div className="max-h-[70vh] overflow-auto px-4 py-4 text-[13px] leading-relaxed text-slate-800">
            {detailLoading ? (
              <p className="text-slate-500">加载详情…</p>
            ) : !detail ? (
              <p className="text-slate-500">点击左侧一行查看详情</p>
            ) : (
              <>
                <div className="text-[15px] font-bold text-slate-950">
                  {sections?.title || String(d.title || list0?.title || detail.job_id)}
                </div>
                <div className="mt-1 text-slate-500">
                  {[sections?.company || d.company || list0?.company, sections?.location || d.location || list0?.location, sections?.work_model || d.work_model || list0?.work_model]
                    .filter(Boolean)
                    .map(String)
                    .join(" · ")}
                </div>
                {d.detail_url ? (
                  <a
                    href={String(d.detail_url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-emerald-700 underline"
                  >
                    Jobright 页
                  </a>
                ) : null}
                {sections?.summary ? <p className="mt-3">{sections.summary}</p> : null}
                {(
                  [
                    ["Responsibilities", sections?.responsibilities],
                    ["Required", sections?.required],
                    ["Preferred", sections?.preferred],
                  ] as const
                ).map(([title, items]) => (
                  <div key={title} className="mt-4">
                    <h3 className="mb-2 border-b border-slate-100 pb-1 text-[13px] font-semibold">{title}</h3>
                    {items?.length ? (
                      <ul className="list-disc space-y-1 pl-5">
                        {items.map((x) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    ) : (
                      <div className="italic text-slate-400">—</div>
                    )}
                  </div>
                ))}
                <div className="mt-4">
                  <h3 className="mb-2 border-b border-slate-100 pb-1 text-[13px] font-semibold">Qualification</h3>
                  {sections?.qualification?.length ? (
                    <div className="flex flex-wrap gap-1.5">
                      {sections.qualification.map((x) => (
                        <span key={x} className="rounded-full bg-emerald-50 px-2.5 py-1 text-[12px] text-emerald-800">
                          {x}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="italic text-slate-400">—</div>
                  )}
                </div>
                {!detail.detail ? (
                  <p className="mt-4 text-slate-500">尚无详情，请点「补抓全部详情」</p>
                ) : null}
              </>
            )}
          </div>
        </section>
      </div>

      {selectedIds.length > 0 ? (
        <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-slate-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-6 py-3">
            <div className="text-sm">
              已选 <strong className="text-emerald-700">{selectedIds.length}</strong> 个职位
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setSelected({})}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600"
              >
                清空选择
              </button>
              <button
                type="button"
                onClick={openShoppingCart}
                className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
              >
                Shopping Cart
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
