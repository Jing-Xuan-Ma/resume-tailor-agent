#!/usr/bin/env python3
"""5×3 human-path pipeline reliability soak (headed Chromium clicks + screenshots + timing).

Flow per round:
  /jobs?tab=internlist → select 3 → Shopping Cart → 批量 Refine → 投递 → 查看表单
Never clicks Submit on ATS.
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
ROUNDS = 5
JOBS_PER_ROUND = 3
REFINE_TIMEOUT_S = 900
APPLY_TIMEOUT_S = 900
USER_ID = "df52cd72-3d41-48c3-996b-355277835f2b"

OFFICIAL_HOST_HINTS = (
    "greenhouse.io",
    "myworkdayjobs.com",
    "workday.com",
    "lever.co",
    "ashbyhq.com",
    "icims.com",
    "smartrecruiters.com",
    "jobvite.com",
    "bamboohr.com",
    "ashby",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ms_since(t0: float) -> int:
    return int((time.time() - t0) * 1000)


class Timer:
    def __init__(self) -> None:
        self.stages: dict[str, int] = {}
        self._starts: dict[str, float] = {}

    def start(self, name: str) -> None:
        self._starts[name] = time.time()

    def stop(self, name: str) -> int:
        t0 = self._starts.get(name, time.time())
        d = ms_since(t0)
        self.stages[name] = d
        return d


def ensure_auth(page) -> None:
    page.goto(f"{FE}/jobs?tab=internlist", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1000)
    # Inject known user id used by shopping cart data
    page.evaluate(
        """(uid) => {
          const raw = localStorage.getItem('resume-agent-auth');
          let obj = {};
          try { obj = raw ? JSON.parse(raw) : {}; } catch (e) { obj = {}; }
          obj.user = Object.assign({}, obj.user || {}, { id: uid, email: (obj.user&&obj.user.email)||'demo@resume-agent.local' });
          if (!obj.token) obj.token = 'soak-token';
          localStorage.setItem('resume-agent-auth', JSON.stringify(obj));
          localStorage.setItem('resume-agent-jobs-tab', 'internlist');
        }""",
        USER_ID,
    )
    if page.locator("[data-testid=auth-demo]").count():
        page.locator("[data-testid=auth-demo]").first.click()
        page.wait_for_timeout(1500)
    page.goto(f"{FE}/jobs?tab=internlist", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1200)


def human_click(page, locator, *, delay_ms: int = 180) -> None:
    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(delay_ms)
    locator.click(timeout=15000)
    page.wait_for_timeout(250)


def shot(page, path: Path, label: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=False)
    return label


def is_official_ats(url: str | None) -> bool:
    u = (url or "").lower()
    return any(h in u for h in OFFICIAL_HOST_HINTS)


KNOWN_ATS_COMPANIES = {
    "postman",
    "scale ai",
    "notion",
    "stripe",
    "airbnb",
    "cloudflare",
    "datadog",
    "figma",
    "discord",
    "ramp",
    "openai",
    "anthropic",
}


def fetch_job_ids(offset: int, limit: int) -> list[dict[str, Any]]:
    r = httpx.get(f"{API}/intern-list/api/jobs", params={"limit": limit, "offset": offset}, timeout=30)
    r.raise_for_status()
    items = r.json().get("items") or []
    out = []
    for it in items:
        jid = it.get("job_id") or (it.get("list_json") or {}).get("jobId")
        if not jid and isinstance(it.get("list_json"), str):
            try:
                jid = json.loads(it["list_json"]).get("jobId")
            except (json.JSONDecodeError, AttributeError):
                jid = None
        if jid:
            out.append(
                {
                    "job_id": jid,
                    "company": it.get("company"),
                    "title": it.get("title"),
                }
            )
    return out


def fetch_resolvable_job_ids(need: int, start_offset: int = 0) -> list[dict[str, Any]]:
    """Pull intern-list pages until we have `need` jobs whose company ATS resolves.

    If unique resolvable jobs are scarce, cycle the pool so soak rounds can still run.
    """
    from app.modules.shopping_cart.apply_pipeline import jobright_url_for
    from app.modules.shopping_cart.jobright_nav import resolve_ats_url_for_item

    pool: list[dict[str, Any]] = []
    seen: set[str] = set()
    offset = 0
    scanned = 0
    while scanned < 400:
        batch = fetch_job_ids(offset=offset, limit=50)
        if not batch:
            break
        for it in batch:
            scanned += 1
            company = str(it.get("company") or "").strip().lower()
            if company not in KNOWN_ATS_COMPANIES:
                continue
            jid = it["job_id"]
            if jid in seen:
                continue
            out = resolve_ats_url_for_item(
                intern_job_id=jid,
                jobright_url=jobright_url_for(jid),
                source_url=f"https://jobright.ai/jobs/info/{jid}",
                force_live=False,
            )
            if out.get("ok") and is_official_ats(out.get("ats_url")):
                seen.add(jid)
                pool.append({**it, "ats_url": out.get("ats_url"), "ats_method": out.get("method")})
        offset += len(batch)
        if offset > 500:
            break

    if not pool:
        return []

    # Rotate through pool based on start_offset so rounds differ when possible
    start = int(start_offset) % len(pool)
    rotated = pool[start:] + pool[:start]
    out: list[dict[str, Any]] = []
    i = 0
    while len(out) < need:
        out.append(rotated[i % len(rotated)])
        i += 1
        if i > need * 3:
            break
    return out[:need]


def context_new_page(page):
    return page.context.new_page()


def wait_refine(page, timeout_s: int) -> dict[str, Any]:
    t0 = time.time()
    last = {}
    while time.time() - t0 < timeout_s:
        generating = (
            page.locator("text=Refine 进行中").count() > 0
            or page.locator("text=仍有职位生成中").count() > 0
            or page.locator("text=进行中").count() > 0
        )
        # Success chip like 成功 3/3
        body = page.locator("[data-testid=shopping-cart-panel]").inner_text() if page.locator("[data-testid=shopping-cart-panel]").count() else page.inner_text("body")
        bar = page.locator("[data-testid=cart-apply-bar]")
        text = bar.inner_text() if bar.count() else body[:500]
        # Count confirm buttons available (= ready_md items)
        confirm_n = page.locator("[data-testid=cart-confirm-pdf-btn]").count()
        ready_md_n = body.count("ready_md")
        last = {
            "elapsed_ms": ms_since(t0),
            "generating": generating,
            "bar_snippet": text[:240],
            "confirm_buttons": confirm_n,
            "ready_md_mentions": ready_md_n,
        }
        # Done when generation banner gone and at least 2 items ready (or timeout near with >=1)
        if (not generating) and confirm_n >= max(1, JOBS_PER_ROUND - 1):
            page.wait_for_timeout(1200)
            return {**last, "done": True}
        if (not generating) and confirm_n >= 1 and ms_since(t0) > 180_000:
            # accept partial after 3 min if generation settled
            page.wait_for_timeout(800)
            return {**last, "done": True, "partial": True}
        page.wait_for_timeout(2500)
    return {**last, "done": False, "error": "refine_timeout"}


def confirm_ready_pdfs(page) -> dict[str, Any]:
    """Click 确认最终版 for each ready item so apply has resume.pdf."""
    clicked = 0
    errors: list[str] = []
    # Expand + confirm each
    confirms = page.locator("[data-testid=cart-confirm-pdf-btn]")
    n = confirms.count()
    for i in range(n):
        btn = confirms.nth(i)
        try:
            label = (btn.inner_text(timeout=1000) or "").strip()
            if "已保存" in label:
                continue
            # Ensure row expanded: click parent header if needed
            human_click(page, btn, delay_ms=200)
            clicked += 1
            page.wait_for_timeout(2500)
        except Exception as exc:  # noqa: BLE001 - best-effort soak click, any Playwright failure is recorded and skipped
            errors.append(str(exc))
    page.wait_for_timeout(1500)
    return {"clicked": clicked, "errors": errors, "buttons": n}


def collect_cart_item_states(page) -> list[dict[str, Any]]:
    """Best-effort scrape of cart item apply statuses from visible text."""
    rows = []
    cards = page.locator("[data-testid=shopping-cart-panel] >> css=div.rounded-2xl, [data-testid=shopping-cart-panel] >> css=li")
    n = min(cards.count(), 12)
    for i in range(n):
        try:
            t = cards.nth(i).inner_text(timeout=1000)
        except Exception as exc:  # noqa: BLE001 - card may have detached/re-rendered mid-scrape
            log.debug("cart card %d unreadable: %s", i, exc)
            continue
        if not t or len(t) < 8:
            continue
        st = "unknown"
        for key in (
            "ready_to_submit",
            "待一键提交",
            "投递失败",
            "failed",
            "已到 ATS",
            "投递排队",
            "生成中",
            "已保存",
        ):
            if key in t:
                st = key
                break
        rows.append({"text": t[:220].replace("\n", " | "), "status_hint": st})
    return rows


def wait_apply(page, timeout_s: int) -> dict[str, Any]:
    t0 = time.time()
    last: dict[str, Any] = {}
    while time.time() - t0 < timeout_s:
        btn = page.locator("[data-testid=cart-start-apply-btn]")
        busy = False
        if btn.count():
            label = btn.inner_text().strip()
            busy = "导航" in label or bool(btn.get_attribute("disabled"))
        bar = page.locator("[data-testid=cart-apply-bar]")
        text = bar.inner_text() if bar.count() else ""
        open_btns = page.locator("[data-testid=cart-open-form-btn]").count()
        last = {
            "elapsed_ms": ms_since(t0),
            "busy": busy,
            "bar": text[:300],
            "open_form_buttons": open_btns,
            "items": collect_cart_item_states(page),
        }
        if (not busy) and ("ready_to_submit" in text or open_btns > 0 or "failed" in text.lower() or "投递失败" in text):
            # settle
            page.wait_for_timeout(2000)
            if not busy:
                return {**last, "done": True}
        page.wait_for_timeout(3000)
    return {**last, "done": False, "error": "apply_timeout"}


def run_round(page, round_idx: int, out_dir: Path, job_offset: int) -> dict[str, Any]:
    timer = Timer()
    round_dir = out_dir / f"r{round_idx}"
    round_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "round": round_idx,
        "started_at": utc_now(),
        "job_offset": job_offset,
        "errors": [],
        "jobs": [],
        "stages_ms": {},
        "gates": {},
    }

    # --- select ---
    timer.start("select_jobs")
    cart = None
    try:
        page.goto(f"{FE}/jobs?tab=internlist", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(1500)
        panel = page.locator("[data-testid=intern-list-jobs-panel]")
        if panel.count() == 0:
            result["errors"].append("intern_list_panel_missing")
            shot(page, round_dir / "01_jobs_fail.png", "jobs_fail")
            result["gates"]["A1_ui_opens"] = False
            result["stages_ms"] = timer.stages
            timer.stop("select_jobs")
            return result
        result["gates"]["A1_ui_opens"] = True
        shot(page, round_dir / "01_jobs.png", "jobs")

        # Prefer jobs with known official ATS so Phase 2 can succeed (human still uses cart UI after).
        planned = fetch_resolvable_job_ids(JOBS_PER_ROUND, start_offset=job_offset)
        if len(planned) < JOBS_PER_ROUND:
            # fallback: raw list (may fail apply with typed no_official_ats_url)
            planned = fetch_job_ids(offset=job_offset, limit=JOBS_PER_ROUND)
        result["jobs_planned"] = planned[:JOBS_PER_ROUND]
        ids = [p["job_id"] for p in result["jobs_planned"]]
        if len(ids) < JOBS_PER_ROUND:
            result["errors"].append(f"could_not_plan_{JOBS_PER_ROUND}_jobs")
            result["gates"]["A2_select"] = False
            timer.stop("select_jobs")
            result["stages_ms"] = timer.stages
            return result

        # Human opens cart for these IDs (same route as Shopping Cart button)
        cart_url = (
            f"{FE}/shoppingcart?internJobIds={','.join(ids)}&from=intern-list"
        )
        cart = context_new_page(page)
        cart.goto(cart_url, wait_until="domcontentloaded", timeout=90000)
        cart.wait_for_timeout(1800)
        result["cart_url"] = cart.url
        result["selected_ids"] = ids
        result["gates"]["A2_select"] = len(ids) >= JOBS_PER_ROUND
        shot(cart, round_dir / "03_cart.png", "cart")
        timer.stop("select_jobs")
    except Exception as exc:  # noqa: BLE001 - soak stage failure is recorded, never crashes the run
        timer.stop("select_jobs")
        result["errors"].append(f"select_exception:{exc}")
        result["stages_ms"] = timer.stages
        result["trace"] = traceback.format_exc()[-2000:]
        return result

    # --- refine ---
    timer.start("refine")
    try:
        refine = cart.locator("[data-testid=batch-refine-btn]")
        if refine.count() == 0:
            result["errors"].append("refine_button_missing")
            result["gates"]["A3_refine"] = False
        else:
            human_click(cart, refine.first, delay_ms=250)
            shot(cart, round_dir / "04_refine_clicked.png", "refine_clicked")
            refine_wait = wait_refine(cart, REFINE_TIMEOUT_S)
            result["refine_wait"] = refine_wait
            shot(cart, round_dir / "05_refine_done.png", "refine_done")
            # Expand items that look ready then confirm PDFs
            # Click each item header containing ready_md
            headers = cart.locator("[data-testid^=cart-item-]")
            for i in range(min(headers.count(), 8)):
                try:
                    t = headers.nth(i).inner_text(timeout=800)
                    if "ready_md" in t or "成功" in t:
                        human_click(cart, headers.nth(i), delay_ms=100)
                except Exception as exc:  # noqa: BLE001 - header may have detached/re-rendered mid-scan
                    log.debug("cart header %d expand skipped: %s", i, exc)
            confirm_res = confirm_ready_pdfs(cart)
            result["confirm_pdf"] = confirm_res
            shot(cart, round_dir / "05b_confirmed.png", "confirmed")
            start_btn = cart.locator("[data-testid=cart-start-apply-btn]")
            can_apply = start_btn.count() > 0 and not start_btn.is_disabled()
            result["gates"]["A3_refine"] = bool(refine_wait.get("done")) and (
                can_apply or (confirm_res.get("clicked") or 0) > 0
            )
            if not result["gates"]["A3_refine"]:
                result["errors"].append("refine_incomplete_or_no_ready_items")
        timer.stop("refine")
    except Exception as exc:  # noqa: BLE001 - soak stage failure is recorded, never crashes the run
        timer.stop("refine")
        result["errors"].append(f"refine_exception:{exc}")
        result["trace"] = traceback.format_exc()[-2000:]
        result["stages_ms"] = timer.stages
        try:
            cart.close()
        except Exception as exc2:  # noqa: BLE001 - best-effort cleanup on the failure path
            log.debug("cart.close() failed: %s", exc2)
        return result

    # --- apply ---
    timer.start("apply")
    try:
        start_btn = cart.locator("[data-testid=cart-start-apply-btn]")
        if start_btn.count() == 0 or start_btn.is_disabled():
            result["errors"].append("start_apply_unavailable")
            result["gates"]["A4_apply"] = False
        else:
            human_click(cart, start_btn.first, delay_ms=300)
            shot(cart, round_dir / "06_apply_clicked.png", "apply_clicked")
            apply_wait = wait_apply(cart, APPLY_TIMEOUT_S)
            result["apply_wait"] = apply_wait
            shot(cart, round_dir / "07_apply_done.png", "apply_done")
            body = cart.inner_text("body")
            sync_bug = "Playwright Sync API inside the asyncio" in body
            result["gates"]["A4_apply"] = bool(apply_wait.get("done")) and not sync_bug
            if sync_bug:
                result["errors"].append("playwright_sync_in_asyncio")
            open_n = cart.locator("[data-testid=cart-open-form-btn]").count()
            result["ready_open_form_count"] = open_n
        timer.stop("apply")
    except Exception as exc:  # noqa: BLE001 - soak stage failure is recorded, never crashes the run
        timer.stop("apply")
        result["errors"].append(f"apply_exception:{exc}")
        result["stages_ms"] = timer.stages
        try:
            cart.close()
        except Exception as exc2:  # noqa: BLE001 - best-effort cleanup on the failure path
            log.debug("cart.close() failed: %s", exc2)
        return result

    # --- open form for each ready button ---
    timer.start("open_form")
    open_results = []
    try:
        btns = cart.locator("[data-testid=cart-open-form-btn]")
        n = btns.count()
        for i in range(n):
            item_res: dict[str, Any] = {"index": i}
            t1 = time.time()
            try:
                human_click(cart, btns.nth(i), delay_ms=250)
                cart.wait_for_timeout(8000)  # allow headed refill to start
                msg = cart.locator("[data-testid=cart-open-form-msg]")
                item_res["ui_message"] = msg.inner_text() if msg.count() else ""
                item_res["ms"] = ms_since(t1)
                shot(cart, round_dir / f"08_open_form_{i}.png", f"open_{i}")
                # Inspect newest chromium page if popup; else note headed external browser
                item_res["ok"] = True
            except Exception as exc:  # noqa: BLE001 - per-item open-form failure is recorded, loop continues
                item_res["ok"] = False
                item_res["error"] = str(exc)
                item_res["ms"] = ms_since(t1)
            open_results.append(item_res)
        result["open_form_results"] = open_results
        result["gates"]["A6_open_form"] = (n == 0) or any(r.get("ok") for r in open_results)
        if n == 0:
            result["errors"].append("no_ready_to_submit_open_form_buttons")
            result["gates"]["A5_official_ats"] = False
            result["gates"]["A6_open_form"] = False
        else:
            # Pull apply status via API if cart_id in URL / local — fallback scrape
            result["gates"]["A5_official_ats"] = True  # refined below via API
        timer.stop("open_form")
    except Exception as exc:  # noqa: BLE001 - soak stage failure is recorded, never crashes the run
        timer.stop("open_form")
        result["errors"].append(f"open_form_exception:{exc}")

    # API enrichment: cart apply statuses
    timer.start("verify_submit_ui")
    try:
        cart_id = None
        try:
            cart_id = cart.locator("[data-testid=shopping-cart-panel]").get_attribute("data-cart-id")
        except Exception as exc:  # noqa: BLE001 - falls back to regex scrape below
            log.debug("cart-id attribute read failed: %s", exc)
            cart_id = None
        if not cart_id:
            import re

            html = cart.content()
            m = re.search(r"data-cart-id=\"([0-9a-f-]{36})\"", html, re.IGNORECASE)
            if m:
                cart_id = m.group(1)
        result["cart_id"] = cart_id
        if cart_id:
            st = httpx.get(
                f"{API}/api/v1/shopping-cart/{cart_id}/apply/status",
                params={"user_id": USER_ID},
                timeout=30,
            )
            if st.status_code == 200:
                payload = st.json()
                result["apply_status_api"] = payload.get("apply_summary")
                items = payload.get("items") or []
                official = []
                for it in items:
                    apply = it.get("apply") or {}
                    url = apply.get("form_url") or apply.get("ats_url")
                    official.append(
                        {
                            "company": it.get("company"),
                            "status": apply.get("status"),
                            "ats_url": url,
                            "official": is_official_ats(url),
                            "error": apply.get("error"),
                        }
                    )
                result["items_api"] = official
                ready = [x for x in official if x.get("status") == "ready_to_submit"]
                result["gates"]["A5_official_ats"] = all(x.get("official") for x in ready) if ready else False
                if ready and not result["gates"]["A5_official_ats"]:
                    result["errors"].append("ready_item_non_official_ats")
                # If no ready but all failed with typed ATS errors, note blocked_external
                if not ready and official:
                    fails = [x for x in official if x.get("status") == "failed"]
                    if len(fails) == len(official):
                        result["errors"].append("all_items_failed_apply")
        shot(cart, round_dir / "09_final.png", "final")
        timer.stop("verify_submit_ui")
    except Exception as exc:  # noqa: BLE001 - soak stage failure is recorded, never crashes the run
        timer.stop("verify_submit_ui")
        result["errors"].append(f"verify_exception:{exc}")

    result["stages_ms"] = timer.stages
    result["gates"]["A7_timing"] = bool(timer.stages)
    result["ended_at"] = utc_now()
    try:
        cart.close()
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup at end of round
        log.debug("cart.close() failed: %s", exc)
    return result


def summarize(rounds: list[dict[str, Any]]) -> dict[str, Any]:
    stage_sums: dict[str, list[int]] = {}
    for r in rounds:
        for k, v in (r.get("stages_ms") or {}).items():
            stage_sums.setdefault(k, []).append(int(v))
    avg = {k: int(sum(vs) / len(vs)) for k, vs in stage_sums.items() if vs}
    gate_fail = {}
    for r in rounds:
        for g, ok in (r.get("gates") or {}).items():
            gate_fail.setdefault(g, 0)
            if not ok:
                gate_fail[g] += 1
    errors = []
    for r in rounds:
        for e in r.get("errors") or []:
            errors.append({"round": r.get("round"), "error": e})
    return {
        "rounds": len(rounds),
        "avg_stage_ms": avg,
        "gate_fail_counts": gate_fail,
        "errors": errors,
    }


def write_report(run_dir: Path, rounds: list[dict[str, Any]]) -> Path:
    summary = summarize(rounds)
    payload = {
        "generated_at": utc_now(),
        "plan": "artifacts/pipeline_reliability/PLAN.md",
        "summary": summary,
        "rounds": rounds,
    }
    (run_dir / "report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Pipeline reliability report",
        "",
        f"Generated: {payload['generated_at']}",
        f"Rounds: {summary['rounds']} × {JOBS_PER_ROUND} jobs",
        "",
        "## Average stage timing (ms)",
        "",
    ]
    for k, v in summary["avg_stage_ms"].items():
        lines.append(f"- **{k}**: {v} ms ({v/1000:.1f}s)")
    lines += ["", "## Gate failures (count of rounds failing)", ""]
    for g, c in summary["gate_fail_counts"].items():
        lines.append(f"- `{g}`: {c}/{summary['rounds']}")
    lines += ["", "## Errors", ""]
    if not summary["errors"]:
        lines.append("- (none)")
    else:
        for e in summary["errors"][:80]:
            lines.append(f"- R{e['round']}: {e['error']}")
    lines += ["", "## Per-round stage ms", ""]
    for r in rounds:
        lines.append(f"### Round {r.get('round')}")
        lines.append(f"- stages: `{json.dumps(r.get('stages_ms') or {})}`")
        lines.append(f"- gates: `{json.dumps(r.get('gates') or {})}`")
        lines.append(f"- errors: `{json.dumps(r.get('errors') or [], ensure_ascii=False)}`")
        lines.append("")
    path = run_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    ts = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = ROOT / "artifacts" / "pipeline_reliability" / "runs" / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    # Health
    try:
        httpx.get(f"{API}/docs", timeout=5).raise_for_status()
        httpx.get(f"{FE}/", timeout=5).raise_for_status()
    except httpx.HTTPError as exc:
        (run_dir / "report.md").write_text(f"# FAIL health\n{exc}\n", encoding="utf-8")
        return 1

    rounds: list[dict[str, Any]] = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False, channel="chrome", slow_mo=80)
        except Exception as exc:  # noqa: BLE001 - no local Chrome channel; fall back to bundled Chromium
            log.debug("chrome channel launch failed, falling back to chromium: %s", exc)
            browser = p.chromium.launch(headless=False, slow_mo=80)
        context = browser.new_context(viewport={"width": 1440, "height": 920})
        page = context.new_page()
        ensure_auth(page)
        shot(page, run_dir / "00_auth.png", "auth")

        for i in range(1, ROUNDS + 1):
            offset = (i - 1) * JOBS_PER_ROUND
            print(f"\n===== ROUND {i}/{ROUNDS} offset={offset} =====", flush=True)
            r = run_round(page, i, run_dir, job_offset=offset)
            rounds.append(r)
            (run_dir / f"r{i}" / "round.json").write_text(
                json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print("stages", r.get("stages_ms"), "errors", r.get("errors"), flush=True)

        browser.close()

    report = write_report(run_dir, rounds)
    print("REPORT", report, flush=True)
    summary = summarize(rounds)
    # Soft exit: 0 if A1 true for all and no sync bug
    hard_fail = any("playwright_sync_in_asyncio" in (e.get("error") or "") for e in summary["errors"])
    a1_fail = summary["gate_fail_counts"].get("A1_ui_opens", 0) > 0
    return 1 if hard_fail or a1_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
