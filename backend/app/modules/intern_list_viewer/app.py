"""Standalone FastAPI acceptance UI for intern-list scrape results."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.modules.intern_list_scraper.categories import CATEGORY_LABELS, TARGET_LINKS, TARGET_SLUGS

AGENT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = AGENT_ROOT / "backend"
DEFAULT_DB = AGENT_ROOT / "data" / "app.db"

app = FastAPI(title="Intern-list Scrape Viewer", version="0.2.0")
_scrape_lock = threading.Lock()
_scrape_status: dict[str, Any] = {"running": False, "last": None, "log": ""}


@app.middleware("http")
async def allow_embed_from_resume_agent(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Allow Resume Agent (/jobs Intern-list tab) to iframe this viewer."""
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'self' http://127.0.0.1:3000 http://localhost:3000"
    )
    # Drop legacy header if any reverse-proxy set it.
    if "x-frame-options" in response.headers:
        del response.headers["x-frame-options"]
    return response


def db_path() -> Path:
    import os

    return Path(os.environ.get("INTERN_LIST_DB", DEFAULT_DB))


def connect() -> sqlite3.Connection:
    path = db_path()
    if not path.exists():
        raise HTTPException(404, f"DB not found: {path}")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


@app.get("/api/health")
def health() -> dict[str, Any]:
    path = db_path()
    return {"ok": True, "db": str(path), "exists": path.exists()}


@app.get("/api/targets")
def api_targets() -> dict[str, Any]:
    return {
        "targets": [
            {
                "slug": slug,
                "label": CATEGORY_LABELS.get(slug, slug),
                "url": TARGET_LINKS.get(slug, ""),
            }
            for slug in TARGET_SLUGS
        ]
    }


@app.get("/api/stats")
def api_stats() -> dict[str, Any]:
    conn = connect()
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "intern_list_jobs" not in tables:
            return {
                "list_total": 0,
                "detail_total": 0,
                "by_slug": {},
                "targets": TARGET_SLUGS,
                "note": "intern_list tables not created yet — run scrape first",
            }
        list_total = conn.execute(
            "SELECT COUNT(*) AS n FROM intern_list_jobs"
        ).fetchone()["n"]
        unique_jobs = conn.execute(
            "SELECT COUNT(DISTINCT job_id) AS n FROM intern_list_jobs"
        ).fetchone()["n"]
        detail_total = conn.execute(
            "SELECT COUNT(*) AS n FROM intern_list_job_details"
        ).fetchone()["n"]
        by_slug = {
            r["slug"]: r["n"]
            for r in conn.execute(
                "SELECT slug, COUNT(*) AS n FROM intern_list_jobs GROUP BY slug ORDER BY n DESC"
            )
        }
        # ensure target slugs appear even if 0
        for slug in TARGET_SLUGS:
            by_slug.setdefault(slug, 0)
        states = []
        if "intern_list_scrape_state" in tables:
            states = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM intern_list_scrape_state ORDER BY slug"
                )
            ]
        return {
            "list_total": list_total,
            "unique_jobs": unique_jobs,
            "detail_total": detail_total,
            "by_slug": by_slug,
            "targets": TARGET_SLUGS,
            "scrape_state": states,
            "db": str(db_path()),
            "scrape_status": _scrape_status,
        }
    finally:
        conn.close()


@app.get("/api/jobs")
def api_jobs(
    slug: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List jobs. Always dedupe by job_id so cross-category tags don't double-show."""
    conn = connect()
    try:
        clauses = ["1=1"]
        params: list[Any] = []
        if slug:
            clauses.append("j.slug = ?")
            params.append(slug)
        if q:
            clauses.append(
                "(j.title LIKE ? OR j.company LIKE ? OR j.location LIKE ?)"
            )
            like = f"%{q}%"
            params.extend([like, like, like])
        where = " AND ".join(clauses)

        # One row per job_id (Jobright tags the same posting into multiple categories).
        total = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM (
              SELECT j.job_id
              FROM intern_list_jobs j
              WHERE {where}
              GROUP BY j.job_id
            )
            """,
            params,
        ).fetchone()["n"]

        rows = conn.execute(
            f"""
            WITH filtered AS (
              SELECT j.*
              FROM intern_list_jobs j
              WHERE {where}
            ),
            ranked AS (
              SELECT
                f.*,
                ROW_NUMBER() OVER (
                  PARTITION BY f.job_id
                  ORDER BY COALESCE(f.posted_at, 0) DESC, f.updated_at DESC
                ) AS rn
              FROM filtered f
            ),
            slug_agg AS (
              SELECT job_id, GROUP_CONCAT(DISTINCT slug) AS slugs
              FROM filtered
              GROUP BY job_id
            )
            SELECT
              r.*,
              s.slugs,
              CASE WHEN d.job_id IS NULL THEN 0 ELSE 1 END AS has_detail
            FROM ranked r
            JOIN slug_agg s ON s.job_id = r.job_id
            LEFT JOIN intern_list_job_details d ON d.job_id = r.job_id
            WHERE r.rn = 1
            ORDER BY COALESCE(r.posted_at, 0) DESC, r.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [row_to_dict(r) for r in rows],
        }
    finally:
        conn.close()


@app.get("/api/jobs/{job_id}")
def api_job_detail(job_id: str) -> dict[str, Any]:
    from app.modules.intern_list_scraper.jd_sections import parse_jd_sections

    conn = connect()
    try:
        lists = conn.execute(
            "SELECT * FROM intern_list_jobs WHERE job_id = ? ORDER BY category",
            (job_id,),
        ).fetchall()
        detail = conn.execute(
            "SELECT * FROM intern_list_job_details WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if not lists and not detail:
            raise HTTPException(404, f"job not found: {job_id}")
        out: dict[str, Any] = {
            "job_id": job_id,
            "list_rows": [row_to_dict(r) for r in lists],
            "detail": None,
            "sections": None,
        }
        if detail:
            d = row_to_dict(detail)
            sections = {}
            try:
                sections = json.loads(d.get("sections_json") or "{}")
            except json.JSONDecodeError:
                sections = {}
            if not sections:
                try:
                    ds = json.loads(d.get("data_source_json") or "{}")
                    sections = parse_jd_sections(ds)
                except Exception:  # noqa: BLE001
                    sections = {}
            d.pop("data_source_json", None)
            d.pop("sections_json", None)
            out["detail"] = d
            out["sections"] = sections
        return out
    finally:
        conn.close()


def _run_scrape_cmd(
    categories: list[str],
    limit: int,
    with_details: bool,
    *,
    backfill_details: bool = False,
) -> None:
    global _scrape_status
    py = BACKEND_ROOT / ".venv" / "bin" / "python"
    python = str(py) if py.exists() else sys.executable
    prefix = [python, "-m", "app.modules.intern_list_scraper", "--config", str(AGENT_ROOT / "config" / "intern-list.toml")]
    if backfill_details:
        if categories and categories != list(TARGET_SLUGS):
            cmd = [*prefix, "--categories", *categories, "--backfill-details", "--refresh-details"]
        else:
            cmd = [*prefix, "--targets", "--backfill-details", "--refresh-details"]
    else:
        cmd = [
            *prefix,
            "--categories",
            *categories,
            "--limit",
            str(limit),
            "--full",
            "--with-details" if with_details else "--no-details",
        ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BACKEND_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        _scrape_status["last"] = {
            "returncode": proc.returncode,
            "categories": categories,
            "limit": limit,
            "cmd": cmd,
        }
        _scrape_status["log"] = ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-8000:]
    except Exception as e:  # noqa: BLE001
        _scrape_status["last"] = {"error": str(e)}
        _scrape_status["log"] = str(e)
    finally:
        _scrape_status["running"] = False


@app.post("/api/scrape")
def api_scrape(
    slug: str | None = None,
    limit: int = Query(30, ge=1, le=1000),
    with_details: bool = True,
    backfill_details: bool = False,
) -> dict[str, Any]:
    if not _scrape_lock.acquire(blocking=False):
        raise HTTPException(409, "scrape already running")
    categories = [slug] if slug else list(TARGET_SLUGS)
    _scrape_status["running"] = True
    _scrape_status["log"] = "starting…"

    def runner() -> None:
        try:
            _run_scrape_cmd(
                categories, limit, with_details, backfill_details=backfill_details
            )
        finally:
            _scrape_lock.release()

    threading.Thread(target=runner, daemon=True).start()
    return {
        "started": True,
        "categories": categories,
        "limit": limit,
        "with_details": with_details,
        "backfill_details": backfill_details,
    }


@app.get("/api/scrape/status")
def api_scrape_status() -> dict[str, Any]:
    return _scrape_status


@app.get("/", response_class=HTMLResponse)
def index(_: Request) -> str:
    return INDEX_HTML


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Intern-list 抓取验收</title>
  <style>
    :root {
      --bg: #f4f7f5;
      --card: #ffffff;
      --ink: #14231c;
      --muted: #5c7266;
      --line: #d7e3db;
      --accent: #00a86b;
      --accent-soft: #e6f7ef;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(1200px 500px at 10% -10%, #d9f5e7 0%, transparent 55%),
        var(--bg);
      color: var(--ink);
    }
    header { padding: 28px 28px 8px; max-width: 1200px; margin: 0 auto; }
    h1 { margin: 0 0 6px; font-size: 28px; letter-spacing: -0.02em; }
    .sub { color: var(--muted); margin: 0; }
    .stats, .cats, .toolbar {
      display: flex; gap: 10px; flex-wrap: wrap;
      max-width: 1200px; margin: 14px auto 0; padding: 0 28px;
    }
    .pill, .chip {
      background: var(--card); border: 1px solid var(--line);
      border-radius: 999px; padding: 8px 14px; font-size: 13px; cursor: pointer;
    }
    .pill strong { color: var(--accent); }
    /* button{} above forces white text — chips must override explicitly */
    button.chip {
      background: #fff !important;
      color: var(--ink) !important;
      border: 1px solid var(--line) !important;
      font-weight: 500;
      box-shadow: none;
    }
    button.chip .count {
      color: var(--accent) !important;
      font-weight: 700;
      margin-left: 6px;
    }
    button.chip.active {
      background: var(--accent) !important;
      color: #fff !important;
      border-color: var(--accent) !important;
    }
    button.chip.active .count { color: #fff !important; }
    input, select, button {
      font: inherit; padding: 10px 12px; border-radius: 10px;
      border: 1px solid var(--line); background: var(--card); color: var(--ink);
    }
    button { background: var(--accent); color: white; border: none; cursor: pointer; font-weight: 600; }
    button.secondary { background: var(--accent-soft); color: var(--accent); }
    main {
      max-width: 1400px; margin: 0 auto 40px; padding: 0 28px;
      display: flex; align-items: stretch; gap: 0;
    }
    #listPane {
      width: 61%;
      min-width: 280px;
      flex-shrink: 0;
    }
    #detailPane {
      flex: 1 1 0;
      min-width: 240px;
    }
    .resizer {
      width: 10px;
      flex: 0 0 10px;
      margin: 0 3px;
      cursor: col-resize;
      position: relative;
      touch-action: none;
      user-select: none;
    }
    .resizer::before {
      content: "";
      position: absolute;
      left: 50%;
      top: 12px;
      bottom: 12px;
      width: 2px;
      transform: translateX(-50%);
      border-radius: 1px;
      background: var(--line);
      transition: background 0.15s ease, width 0.15s ease;
    }
    .resizer:hover::before,
    .resizer.dragging::before {
      width: 3px;
      background: var(--accent);
    }
    body.resizing { cursor: col-resize; user-select: none; }
    body.resizing iframe { pointer-events: none; }
    @media (max-width: 960px) {
      main { flex-direction: column; }
      .resizer { display: none; }
      #listPane { width: 100% !important; min-width: 0; }
      #detailPane { min-width: 0; }
    }
    body.has-batch-bar { padding-bottom: 88px; }
    .card {
      background: var(--card); border: 1px solid var(--line);
      border-radius: 16px; overflow: hidden; min-height: 420px;
    }
    .card h2 {
      margin: 0; padding: 14px 16px; font-size: 15px;
      border-bottom: 1px solid var(--line); background: #fbfdfc;
    }
    table.job-table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 720px; }
    table.job-table th, table.job-table td {
      padding: 12px 10px; border-bottom: 1px solid #e6e6e6; border-right: 1px solid #eee;
      text-align: left; vertical-align: middle; color: #1a1a1a;
    }
    table.job-table th:last-child, table.job-table td:last-child { border-right: none; }
    table.job-table th {
      color: #111; font-weight: 700; position: sticky; top: 0; background: #fff; z-index: 1;
      border-bottom: 1px solid #ddd;
    }
    table.job-table th.col-check, table.job-table td.col-check {
      width: 36px; padding-left: 12px; padding-right: 4px; text-align: center;
    }
    table.job-table th.col-idx, table.job-table td.col-idx {
      width: 36px; color: #888; text-align: center; padding-left: 4px; padding-right: 4px;
    }
    table.job-table td.col-title { font-weight: 700; min-width: 180px; max-width: 260px; }
    table.job-table td.col-date { color: #8a8a8a; white-space: nowrap; min-width: 88px; }
    table.job-table td.col-salary { white-space: nowrap; }
    .wm {
      display: inline-block; padding: 2px 10px; border-radius: 8px; font-size: 12px; font-weight: 600;
      border: 1px solid transparent;
    }
    .wm-onsite { color: #7b4db8; background: #f4edfa; border-color: #d9c4ef; }
    .wm-hybrid { color: #2f6fed; background: #eef3ff; border-color: #c9d8ff; }
    .wm-remote { color: #0a9b5c; background: #e8f8f0; border-color: #b6e8cf; }
    .wm-other { color: #666; background: #f3f3f3; border-color: #ddd; }
    td.col-check { cursor: default; }
    tr:hover td { background: #f7fbf8; cursor: pointer; }
    tr:hover td.col-check { cursor: default; }
    tr.active td { background: var(--accent-soft); }
    tr.selected td { background: #eef8f2; }
    .row-check {
      width: 16px; height: 16px; margin: 0; accent-color: var(--accent); cursor: pointer;
    }
    .muted { color: var(--muted); }
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      background: var(--accent-soft); color: var(--accent); font-size: 12px;
    }
    #detail { padding: 16px 18px; font-size: 13px; line-height: 1.5; }
    #detail h3 {
      margin: 16px 0 8px; font-size: 13px; letter-spacing: 0.02em;
      color: var(--ink); border-bottom: 1px solid var(--line); padding-bottom: 4px;
    }
    #detail h3:first-of-type { margin-top: 12px; }
    #detail ul { margin: 0; padding-left: 18px; }
    #detail li { margin: 4px 0; }
    .tags { display: flex; flex-wrap: wrap; gap: 6px; }
    .tag {
      background: var(--accent-soft); color: var(--accent);
      border-radius: 999px; padding: 3px 10px; font-size: 12px;
    }
    .meta-line { color: var(--muted); margin-top: 4px; }
    .empty-section { color: var(--muted); font-style: italic; }
    .scroll { max-height: 70vh; overflow: auto; }
    a { color: var(--accent); }
    #scrapeLog {
      max-width: 1200px; margin: 8px auto 0; padding: 0 28px;
      font-size: 12px; color: var(--muted); white-space: pre-wrap;
    }
    #batchBar {
      display: none;
      position: fixed; left: 0; right: 0; bottom: 0; z-index: 40;
      border-top: 1px solid var(--line);
      background: rgba(255,255,255,0.96);
      backdrop-filter: blur(10px);
      box-shadow: 0 -8px 24px rgba(20, 35, 28, 0.06);
    }
    #batchBar.visible { display: block; }
    .batch-inner {
      max-width: 1200px; margin: 0 auto;
      padding: 14px 28px;
      display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
    }
    .batch-meta { font-size: 14px; color: var(--ink); }
    .batch-meta strong { color: var(--accent); font-size: 16px; }
    .batch-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    button.ghost {
      background: #fff; color: var(--muted); border: 1px solid var(--line);
    }
  </style>
</head>
<body>
  <header>
    <h1>Intern-list 抓取验收</h1>
    <p class="sub">六个目标分类可选 · 数据写入 resume-tailor-agent SQLite</p>
  </header>
  <div class="stats" id="stats"></div>
  <div class="cats" id="cats"></div>
  <div class="toolbar">
    <input id="q" placeholder="搜索 title / company / location" style="min-width:240px" />
    <button onclick="loadJobs()">刷新列表</button>
    <button class="secondary" onclick="scrapeCurrent()">抓取当前分类(含详情)</button>
    <button class="secondary" onclick="scrapeAll()">抓取六类各30条(含详情)</button>
    <button class="secondary" onclick="backfillDetails()">补抓全部详情</button>
  </div>
  <pre id="scrapeLog"></pre>
  <main>
    <section class="card" id="listPane">
      <h2 id="listTitle">职位列表</h2>
      <div class="scroll">
        <table class="job-table">
          <thead>
            <tr>
              <th class="col-check">
                <input type="checkbox" class="row-check" id="selectAll" title="全选当前列表" aria-label="全选" />
              </th>
              <th class="col-idx">#</th>
              <th>Position Title</th>
              <th>Date</th>
              <th>Work Model</th>
              <th>Location</th>
              <th>Company</th>
              <th>Salary</th>
            </tr>
          </thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
    </section>
    <div
      class="resizer"
      id="paneResizer"
      role="separator"
      aria-orientation="vertical"
      aria-label="拖拽调整左右宽度"
      title="拖拽调整左右宽度"
    ></div>
    <section class="card" id="detailPane">
      <h2>详情 / JD</h2>
      <div id="detail" class="muted">点击左侧一行查看详情</div>
    </section>
  </main>
  <div id="batchBar" aria-live="polite">
    <div class="batch-inner">
      <div class="batch-meta">已选 <strong id="selectedCount">0</strong> 个职位</div>
      <div class="batch-actions">
        <button type="button" class="ghost" onclick="clearSelection()">清空选择</button>
        <button type="button" id="batchRefineBtn" onclick="openBatchRefine()">Shopping Cart</button>
      </div>
    </div>
  </div>
  <script>
    let currentId = null;
    let currentSlug = '';
    /** @type {Map<string, {job_id:string,title:string,company:string,has_detail:number}>} */
    const selected = new Map();
    let visibleJobIds = [];
    const REFINE_BASE = (window.RESUME_AGENT_FRONTEND || 'http://127.0.0.1:3000').replace(/\\/$/, '');
    /** API prefix when embedded under Resume Agent (/intern-list or /intern-list-viewer). */
    function internListApiBase() {
      if (window.INTERN_LIST_API_BASE != null) {
        return String(window.INTERN_LIST_API_BASE).replace(/\\/$/, '');
      }
      const p = location.pathname || '';
      if (p.startsWith('/intern-list-viewer')) return '/intern-list-viewer';
      if (p.startsWith('/intern-list')) return '/intern-list';
      return '';
    }
    const API = internListApiBase();
    function apiUrl(path) {
      const p = path.startsWith('/') ? path : '/' + path;
      return API + p;
    }
    const TARGETS = [
      {slug:'swe', label:'Software Engineering', k:'swe'},
      {slug:'data_analysis', label:'Data Analysis', k:'da'},
      {slug:'ml_ai', label:'Machine Learning and AI', k:'aiml'},
      {slug:'product_management', label:'Product Management', k:'pm'},
      {slug:'accounting_finance', label:'Accounting and Finance', k:'af'},
      {slug:'business_analyst', label:'Business Analyst', k:'ba'},
    ];

    function renderCats(bySlug={}) {
      const el = document.getElementById('cats');
      el.innerHTML = '';
      const all = document.createElement('button');
      all.type = 'button';
      all.className = 'chip' + (currentSlug === '' ? ' active' : '');
      all.textContent = '全部';
      all.onclick = () => { currentSlug=''; renderCats(bySlug); loadJobs(); };
      el.appendChild(all);
      TARGETS.forEach(t => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'chip' + (currentSlug === t.slug ? ' active' : '');
        b.innerHTML = `${esc(t.label)} <span class="count">${bySlug[t.slug]||0}</span>`;
        b.title = 'https://www.intern-list.com/?k=' + t.k;
        b.onclick = () => { currentSlug=t.slug; renderCats(bySlug); loadJobs(); };
        el.appendChild(b);
      });
    }

    function syncBatchBar() {
      const n = selected.size;
      document.getElementById('selectedCount').textContent = String(n);
      document.getElementById('batchBar').classList.toggle('visible', n > 0);
      document.body.classList.toggle('has-batch-bar', n > 0);
      document.getElementById('batchRefineBtn').disabled = n === 0;
      const all = document.getElementById('selectAll');
      if (!visibleJobIds.length) {
        all.checked = false;
        all.indeterminate = false;
      } else {
        const selectedVisible = visibleJobIds.filter(id => selected.has(id)).length;
        all.checked = selectedVisible === visibleJobIds.length;
        all.indeterminate = selectedVisible > 0 && selectedVisible < visibleJobIds.length;
      }
    }

    function setRowSelected(tr, jobId, on) {
      if (on) {
        selected.set(jobId, {
          job_id: jobId,
          title: tr.dataset.title || '',
          company: tr.dataset.company || '',
          has_detail: Number(tr.dataset.hasDetail || 0),
        });
        tr.classList.add('selected');
      } else {
        selected.delete(jobId);
        tr.classList.remove('selected');
      }
      const cb = tr.querySelector('.row-check');
      if (cb) cb.checked = on;
      syncBatchBar();
    }

    function clearSelection() {
      selected.clear();
      document.querySelectorAll('#rows tr.selected').forEach(tr => tr.classList.remove('selected'));
      document.querySelectorAll('#rows .row-check').forEach(cb => { cb.checked = false; });
      syncBatchBar();
    }

    function openBatchRefine() {
      const ids = [...selected.keys()];
      if (!ids.length) return;
      const url = new URL(REFINE_BASE + '/shoppingcart');
      url.searchParams.set('internJobIds', ids.join(','));
      url.searchParams.set('from', 'intern-list');
      window.open(url.toString(), '_blank', 'noopener');
    }

    async function loadStats() {
      const s = await fetch(apiUrl('/api/stats')).then(r => r.json());
      document.getElementById('stats').innerHTML = `
        <div class="pill">唯一职位 <strong>${s.unique_jobs ?? s.list_total ?? 0}</strong></div>
        <div class="pill">分类行 <strong>${s.list_total ?? 0}</strong></div>
        <div class="pill">详情 <strong>${s.detail_total ?? 0}</strong></div>
        <div class="pill muted">${s.db || ''}</div>
      `;
      renderCats(s.by_slug || {});
      if (s.scrape_status?.running) {
        document.getElementById('scrapeLog').textContent = '抓取进行中…\\n' + (s.scrape_status.log || '');
      }
      return s;
    }

    function relativeDate(postedAt) {
      const n = Number(postedAt);
      if (!Number.isFinite(n) || n <= 0) return '—';
      const ms = n < 1e12 ? n * 1000 : n; // allow seconds or ms
      const diff = Date.now() - ms;
      if (diff < 0) return 'just now';
      const mins = Math.floor(diff / 60000);
      if (mins < 1) return 'just now';
      if (mins < 60) return mins + ' minutes ago';
      const hours = Math.floor(mins / 60);
      if (hours < 24) return hours + (hours === 1 ? ' hour ago' : ' hours ago');
      const days = Math.floor(hours / 24);
      if (days < 30) return days + (days === 1 ? ' day ago' : ' days ago');
      const months = Math.floor(days / 30);
      return months + (months === 1 ? ' month ago' : ' months ago');
    }
    function workModelBadge(model) {
      const raw = String(model || '').trim();
      if (!raw) return '<span class="wm wm-other">—</span>';
      const key = raw.toLowerCase().replace(/\\s+/g, '');
      let cls = 'wm-other';
      if (key.includes('remote')) cls = 'wm-remote';
      else if (key.includes('hybrid')) cls = 'wm-hybrid';
      else if (key.includes('onsite') || key.includes('on-site') || key === 'onsite') cls = 'wm-onsite';
      // normalize display like intern-list
      let label = raw;
      if (key === 'onsite' || key === 'on-site') label = 'On Site';
      else if (key === 'hybrid') label = 'Hybrid';
      else if (key === 'remote') label = 'Remote';
      return `<span class="wm ${cls}">${esc(label)}</span>`;
    }

    async function loadJobs() {
      const q = document.getElementById('q').value.trim();
      const params = new URLSearchParams({ limit: '100' });
      if (currentSlug) params.set('slug', currentSlug);
      if (q) params.set('q', q);
      const data = await fetch(apiUrl('/api/jobs?' + params)).then(r => r.json());
      document.getElementById('listTitle').textContent =
        `职位列表 (${data.total || 0})` + (currentSlug ? ` · ${currentSlug}` : '');
      const tbody = document.getElementById('rows');
      tbody.innerHTML = '';
      visibleJobIds = [];
      (data.items || []).forEach((item, idx) => {
        const tr = document.createElement('tr');
        const jobId = item.job_id;
        visibleJobIds.push(jobId);
        tr.dataset.jobId = jobId;
        tr.dataset.title = item.title || '';
        tr.dataset.company = item.company || '';
        tr.dataset.hasDetail = item.has_detail ? '1' : '0';
        if (jobId === currentId) tr.classList.add('active');
        if (selected.has(jobId)) tr.classList.add('selected');
        tr.innerHTML = `
          <td class="col-check">
            <input type="checkbox" class="row-check" ${selected.has(jobId) ? 'checked' : ''}
              aria-label="选择 ${esc(item.title || jobId)}" />
          </td>
          <td class="col-idx">${idx + 1}</td>
          <td class="col-title">${esc(item.title || '')}</td>
          <td class="col-date">${esc(relativeDate(item.posted_at))}</td>
          <td>${workModelBadge(item.work_model)}</td>
          <td>${esc(item.location || '—')}</td>
          <td>${esc(item.company || '—')}</td>
          <td class="col-salary">${esc(item.salary || 'N/A')}</td>
        `;
        const cb = tr.querySelector('.row-check');
        cb.addEventListener('click', (e) => e.stopPropagation());
        cb.addEventListener('change', (e) => {
          e.stopPropagation();
          setRowSelected(tr, jobId, cb.checked);
        });
        tr.onclick = (e) => {
          if (e.target.closest('.col-check')) return;
          showDetail(jobId, tr);
        };
        tbody.appendChild(tr);
      });
      syncBatchBar();
    }

    async function showDetail(jobId, tr) {
      currentId = jobId;
      document.querySelectorAll('tr.active').forEach(x => x.classList.remove('active'));
      if (tr) tr.classList.add('active');
      const data = await fetch(apiUrl('/api/jobs/' + encodeURIComponent(jobId))).then(r => r.json());
      const d = data.detail || {};
      const s = data.sections || {};
      const list = (data.list_rows || [])[0] || {};
      const title = s.title || d.title || list.title || jobId;
      const company = s.company || d.company || list.company || '';
      const location = s.location || d.location || list.location || '';
      const work = s.work_model || d.work_model || list.work_model || '';
      let html = '';
      html += `<div><strong style="font-size:15px">${esc(title)}</strong></div>`;
      html += `<div class="meta-line">${esc(company)}${location ? ' · ' + esc(location) : ''}${work ? ' · ' + esc(work) : ''}</div>`;
      if (d.detail_url) html += `<div style="margin:8px 0"><a href="${esc(d.detail_url)}" target="_blank" rel="noopener">Jobright 页</a></div>`;
      if (s.summary) html += `<p style="margin:10px 0 0">${esc(s.summary)}</p>`;

      html += sectionList('Responsibilities', s.responsibilities);
      html += sectionTags('Qualification', s.qualification);
      html += sectionList('Required', s.required);
      html += sectionList('Preferred', s.preferred);

      if (!data.detail) {
        html += `<p class="muted" style="margin-top:12px">尚无详情，请点「补抓全部详情」</p>`;
      }
      document.getElementById('detail').innerHTML = html;
    }
    function sectionList(title, items) {
      const arr = items || [];
      let html = `<h3>${esc(title)}</h3>`;
      if (!arr.length) return html + `<div class="empty-section">—</div>`;
      html += '<ul>';
      arr.forEach(x => { html += `<li>${esc(x)}</li>`; });
      html += '</ul>';
      return html;
    }
    function sectionTags(title, items) {
      const arr = items || [];
      let html = `<h3>${esc(title)}</h3>`;
      if (!arr.length) return html + `<div class="empty-section">—</div>`;
      html += '<div class="tags">';
      arr.forEach(x => { html += `<span class="tag">${esc(x)}</span>`; });
      html += '</div>';
      return html;
    }

    async function scrapeCurrent() {
      const params = new URLSearchParams({ limit: '30', with_details: 'true' });
      if (currentSlug) params.set('slug', currentSlug);
      await fetch(apiUrl('/api/scrape?' + params), { method: 'POST' });
      pollScrape();
    }
    async function scrapeAll() {
      await fetch(apiUrl('/api/scrape?limit=30&with_details=true'), { method: 'POST' });
      pollScrape();
    }
    async function backfillDetails() {
      const params = new URLSearchParams({ backfill_details: 'true', with_details: 'true' });
      if (currentSlug) params.set('slug', currentSlug);
      await fetch(apiUrl('/api/scrape?' + params), { method: 'POST' });
      pollScrape();
    }
    async function pollScrape() {
      const st = await fetch(apiUrl('/api/scrape/status')).then(r => r.json());
      document.getElementById('scrapeLog').textContent =
        (st.running ? '抓取进行中…\\n' : '抓取结束\\n') + (st.log || '');
      if (st.running) setTimeout(pollScrape, 2000);
      else { loadStats().then(loadJobs); }
    }

    function esc(s) {
      return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    document.getElementById('selectAll').addEventListener('change', (e) => {
      const on = e.target.checked;
      document.querySelectorAll('#rows tr').forEach(tr => {
        const jobId = tr.dataset.jobId;
        if (!jobId) return;
        setRowSelected(tr, jobId, on);
      });
    });

    (function initPaneResizer() {
      const main = document.querySelector('main');
      const listPane = document.getElementById('listPane');
      const resizer = document.getElementById('paneResizer');
      const STORAGE_KEY = 'intern-list-viewer-list-width';
      const MIN_LEFT = 280;
      const MIN_RIGHT = 240;
      const GAP = 16;

      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) listPane.style.width = saved;

      function applyWidth(clientX) {
        const rect = main.getBoundingClientRect();
        const maxLeft = rect.width - MIN_RIGHT - GAP;
        const next = Math.max(MIN_LEFT, Math.min(maxLeft, clientX - rect.left));
        listPane.style.width = next + 'px';
      }

      function onPointerMove(e) {
        if (e.pointerType === 'mouse' && e.buttons === 0) return;
        applyWidth(e.clientX);
      }

      function onPointerUp(e) {
        resizer.releasePointerCapture(e.pointerId);
        resizer.classList.remove('dragging');
        document.body.classList.remove('resizing');
        resizer.removeEventListener('pointermove', onPointerMove);
        resizer.removeEventListener('pointerup', onPointerUp);
        resizer.removeEventListener('pointercancel', onPointerUp);
        localStorage.setItem(STORAGE_KEY, listPane.style.width);
      }

      resizer.addEventListener('pointerdown', (e) => {
        if (window.matchMedia('(max-width: 960px)').matches) return;
        e.preventDefault();
        resizer.setPointerCapture(e.pointerId);
        resizer.classList.add('dragging');
        document.body.classList.add('resizing');
        resizer.addEventListener('pointermove', onPointerMove);
        resizer.addEventListener('pointerup', onPointerUp);
        resizer.addEventListener('pointercancel', onPointerUp);
      });

      resizer.addEventListener('dblclick', () => {
        listPane.style.width = '61%';
        localStorage.removeItem(STORAGE_KEY);
      });
    })();

    loadStats().then(loadJobs);
    document.getElementById('q').addEventListener('keydown', e => { if (e.key === 'Enter') loadJobs(); });
  </script>
</body>
</html>
"""


def main() -> None:
    import os

    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8101"))
    uvicorn.run("viewer.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
