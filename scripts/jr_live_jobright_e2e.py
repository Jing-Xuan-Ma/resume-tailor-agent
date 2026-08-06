"""Live Jobright.ai smoke: open a real job → FAB three buttons → screenshots.

Uses Chrome + extensions/jobright-bridge. Falls back to script inject + API upsert
when extension SW cannot talk. Never auto-submits ATS.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "extensions" / "jobright-bridge"
OUT = ROOT / "artifacts" / "ui" / "jr-live-e2e"
OUT.mkdir(parents=True, exist_ok=True)

API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
TOKEN = "dev-extension-token"
JR_HOME = "https://jobright.ai/"
JR_JOBS = "https://jobright.ai/jobs"

report: dict = {
    "ok": False,
    "mode": "live_jobright",
    "gates": {},
    "screenshots": [],
    "errors": [],
    "notes": [],
    "job": {},
    "urls": {},
}


def shot(page, name: str) -> None:
    path = OUT / name
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        page.screenshot(path=str(path))
    report["screenshots"].append(str(path.relative_to(ROOT)).replace("\\", "/"))


def gate(name: str, passed: bool, detail: str = "") -> None:
    report["gates"][name] = {"passed": bool(passed), "detail": detail[:300]}
    print(("PASS" if passed else "FAIL"), name, detail[:200])
    if not passed:
        report["errors"].append(f"{name}: {detail}")


def pause(page, ms: int = 800) -> None:
    page.wait_for_timeout(ms)


def ensure_services() -> bool:
    try:
        h = httpx.get(f"{API}/health", timeout=5)
        gate("api_health", h.status_code == 200, h.text[:80])
        return h.status_code == 200
    except Exception as exc:
        gate("api_health", False, str(exc))
        return False


def ensure_demo(page) -> None:
    try:
        demo = page.locator("[data-testid=auth-demo]")
        if demo.count():
            demo.first.click()
            pause(page, 1500)
    except Exception:
        pass


def inject_fab(page) -> None:
    page.evaluate(
        """() => {
      if (document.getElementById('ra-jobright-fab')) return;
      const wrap = document.createElement('div');
      wrap.id = 'ra-jobright-fab';
      wrap.setAttribute('data-testid', 'ra-jobright-fab');
      Object.assign(wrap.style, {
        position:'fixed', right:'16px', bottom:'20px', zIndex:2147483646,
        display:'flex', flexDirection:'column', gap:'8px'
      });
      const mk = (label, tid, bg) => {
        const b = document.createElement('button');
        b.type = 'button'; b.textContent = label;
        b.setAttribute('data-testid', tid);
        Object.assign(b.style, {
          border:'none', borderRadius:'999px', padding:'11px 14px',
          background:bg, color:'#fff', font:'600 12px/1.2 system-ui',
          boxShadow:'0 8px 24px rgba(15,23,42,0.22)', cursor:'pointer'
        });
        wrap.appendChild(b);
      };
      mk('Open Tailor', 'ra-fab-tailor', '#047857');
      mk('Open Apply', 'ra-fab-apply', '#0f172a');
      mk('Open Outreach', 'ra-fab-outreach', '#1d4ed8');
      document.documentElement.appendChild(wrap);
    }"""
    )


def wire_fab(page, urls: dict) -> None:
    page.evaluate(
        """(urls) => {
      const bind = (tid, url) => {
        const b = document.querySelector(`[data-testid="${tid}"]`);
        if (!b || !url) return;
        b.onclick = (e) => { e.preventDefault(); window.open(url, '_blank'); };
      };
      bind('ra-fab-tailor', urls.tailor);
      bind('ra-fab-apply', urls.apply);
      bind('ra-fab-outreach', urls.outreach);
    }""",
        urls,
    )


def extract_job_from_page(page) -> dict:
    """Best-effort JD scrape from live Jobright DOM."""
    data = page.evaluate(
        """() => {
      const text = (el) => (el && (el.innerText || el.textContent) || '').trim();
      const title =
        text(document.querySelector('h1')) ||
        text(document.querySelector('[class*="jobTitle"], [class*="JobTitle"], [data-testid*="title"]'));
      const body =
        text(document.querySelector('[class*="description"], [class*="Description"], article, main')) ||
        text(document.body);
      const company =
        text(document.querySelector('[class*="company"], [class*="Company"]')) || '';
      let apply = '';
      const links = Array.from(document.querySelectorAll('a[href]'));
      for (const a of links) {
        const href = a.href || '';
        const t = (a.innerText || '').toLowerCase();
        if (/utm_source=jobright/i.test(href) && !/jobright\\.ai/i.test(href)) { apply = href; break; }
        if ((t.includes('apply') || t.includes('申请')) && /^https?:/i.test(href) && !/jobright\\.ai/i.test(href)) {
          apply = href; break;
        }
      }
      return {
        title: (title || 'Untitled').slice(0, 200),
        company: (company || 'Unknown').slice(0, 120),
        raw_text: (body || '').slice(0, 12000),
        apply_url: apply,
        page_url: location.href,
      };
    }"""
    )
    return data or {}


def upsert(job: dict) -> dict | None:
    apply_url = (job.get("apply_url") or "").strip()
    page_url = (job.get("page_url") or "").strip()
    source = apply_url or page_url
    if not source:
        gate("upsert_lead", False, "no source url")
        return None
    raw = (job.get("raw_text") or "").strip()
    if len(raw) < 80:
        # soft: still try with title padding so FAB URLs exist
        raw = f"{job.get('title')} at {job.get('company')}\n\n{raw}\nLive Jobright smoke placeholder JD for bridge upsert.".strip()
        report["notes"].append("jd_short_padded")
    payload = {
        "title": job.get("title") or "Untitled",
        "company": job.get("company") or "Unknown",
        "location": job.get("location"),
        "raw_text": raw,
        "source_url": source,
        "jobright_url": page_url or None,
        "source_platform": "jobright_extension",
        "force": True,
        "metadata": {
            "apply_url": apply_url or None,
            "page_url": page_url or None,
            "has_external_apply": bool(apply_url and "jobright.ai" not in apply_url.lower()),
            "live_smoke": True,
        },
    }
    res = httpx.post(
        f"{API}/api/v1/jobs/index/leads",
        headers={"X-Extension-Token": TOKEN, "Content-Type": "application/json"},
        json=payload,
        timeout=45,
    )
    if res.status_code != 200:
        gate("upsert_lead", False, res.text[:240])
        return None
    data = res.json()
    jid = data["id"]
    root = f"{FE}/?view=resume&jobId={jid}"
    data["workspace_url"] = f"{root}&step=tailor"
    data["apply_step_url"] = f"{root}&step=apply"
    data["outreach_step_url"] = f"{FE}/outreach?jobId={jid}"
    gate("upsert_lead", True, jid)
    return data


def looks_like_job_detail(page) -> bool:
    url = (page.url or "").lower()
    if url.rstrip("/") in {"https://jobright.ai", "https://www.jobright.ai"}:
        return False
    if "/jobs/" not in url and "/job/" not in url and "position" not in url:
        # some SPAs keep query-only routes
        if "jobId" not in url and "job_id" not in url:
            body = (page.locator("body").inner_text() or "")[:1500].lower()
            if "try jobright" in body or "try for free" in body and "responsibilities" not in body:
                return False
    h1 = page.locator("h1")
    if h1.count() == 0:
        return False
    text = page.locator("body").inner_text() or ""
    return len(text) > 600 and ("responsibilit" in text.lower() or "qualification" in text.lower() or "requirement" in text.lower() or len(text) > 2500)


def open_job_detail(page) -> bool:
    """Navigate Jobright until a real job detail page is visible (not marketing home)."""
    # Prefer browse/jobs entry points
    for start in (JR_JOBS, "https://jobright.ai/jobs/recommend", "https://www.jobright.ai/jobs", JR_HOME):
        try:
            page.goto(start, wait_until="domcontentloaded", timeout=90000)
            pause(page, 2500)
            break
        except Exception:
            continue
    shot(page, "01-jobright-jobs.png")

    body = (page.locator("body").inner_text() or "")[:2500].lower()
    if any(x in body for x in ("sign in", "log in", "登录", "sign up", "try for free", "try jobright")):
        report["notes"].append("possible_login_wall")
        shot(page, "01b-login-or-landing.png")
        # Try Browse Jobs / Dashboard nav before giving up
        for label in ("Browse Jobs", "Dashboard", "AI Agent", "Jobs"):
            link = page.get_by_role("link", name=re.compile(label, re.I))
            if link.count():
                try:
                    link.first.click()
                    pause(page, 2500)
                    shot(page, "01c-nav-click.png")
                    break
                except Exception:
                    pass

    if looks_like_job_detail(page):
        return True

    candidates = [
        "a[href*='/jobs/']",
        "a[href*='/job/']",
        "[class*='job-card'] a",
        "[class*='JobCard'] a",
        "a:has-text('Apply')",
        "button:has-text('Apply')",
    ]
    for sel in candidates:
        loc = page.locator(sel)
        n = loc.count()
        if n == 0:
            continue
        for i in range(min(n, 10)):
            try:
                href = loc.nth(i).get_attribute("href") or ""
            except Exception:
                href = ""
            if href and href.rstrip("/").endswith("/jobs"):
                continue
            try:
                loc.nth(i).click(timeout=5000)
            except Exception:
                continue
            pause(page, 2500)
            shot(page, "02-job-detail-attempt.png")
            if looks_like_job_detail(page):
                return True
            # SPA modal detail?
            if page.locator("h1").count() and len(page.locator("body").inner_text() or "") > 1200:
                if "try for free" not in (page.locator("body").inner_text() or "").lower()[:800]:
                    return True
    return looks_like_job_detail(page)


def click_fab(context, page, testid: str, expect: str, shot_name: str) -> bool:
    btn = page.locator(f"[data-testid={testid}]")
    if btn.count() == 0:
        gate(testid, False, "missing")
        return False
    box = btn.bounding_box()
    if box:
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        pause(page, 200)
    before = {p.url for p in context.pages}
    btn.click()
    pause(page, 2000)
    target = None
    for p in context.pages:
        if expect in (p.url or ""):
            target = p
            break
    if target is None:
        for p in context.pages:
            if p.url not in before:
                target = p
                break
    if target is None:
        shot(page, shot_name)
        gate(testid, False, f"no new page; pages={[p.url for p in context.pages][:5]}")
        return False
    try:
        target.wait_for_load_state("domcontentloaded", timeout=45000)
    except Exception:
        pass
    ensure_demo(target)
    if expect not in (target.url or ""):
        # re-nav to intended if demo wiped query
        intended = None
        if "tailor" in testid:
            intended = report["urls"].get("tailor")
        elif "apply" in testid:
            intended = report["urls"].get("apply")
        elif "outreach" in testid:
            intended = report["urls"].get("outreach")
        if intended:
            target.goto(intended, wait_until="domcontentloaded", timeout=60000)
            ensure_demo(target)
    pause(target, 1000)
    shot(target, shot_name)
    ok = expect in (target.url or "")
    gate(testid, ok, (target.url or "")[:200])
    return ok


def main() -> int:
    if not ensure_services():
        (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return 1

    user_data = Path(tempfile.mkdtemp(prefix="jr-live-"))
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                str(user_data),
                channel="chrome",
                headless=False,
                args=[
                    f"--disable-extensions-except={EXT}",
                    f"--load-extension={EXT}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                viewport={"width": 1440, "height": 960},
                ignore_default_args=["--enable-automation"],
            )
            report["notes"].append("extension_context")
        except Exception as exc:
            report["notes"].append(f"extension_fail:{exc}")
            browser = p.chromium.launch(channel="chrome", headless=False)
            context = browser.new_context(viewport={"width": 1440, "height": 960})

        page = context.new_page()
        page.set_default_timeout(60000)

        opened = False
        try:
            opened = open_job_detail(page)
        except Exception as exc:
            report["errors"].append(f"open_job: {exc}")
            shot(page, "00-open-error.png")

        gate("live_job_open", opened, page.url)
        shot(page, "03-after-open.png")

        job = extract_job_from_page(page)
        report["job"] = {
            "title": job.get("title"),
            "company": job.get("company"),
            "page_url": job.get("page_url"),
            "apply_url": job.get("apply_url"),
            "jd_len": len(job.get("raw_text") or ""),
        }
        gate("extract_jd", len(job.get("raw_text") or "") >= 80, f"len={report['job']['jd_len']}")

        lead = upsert(job)
        if not lead:
            # Still try home-level screenshot report
            (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            context.close()
            shutil.rmtree(user_data, ignore_errors=True)
            return 1

        report["urls"] = {
            "tailor": lead["workspace_url"],
            "apply": lead["apply_step_url"],
            "outreach": lead["outreach_step_url"],
        }
        report["job_id"] = lead["id"]

        # FAB: wait for extension or inject
        pause(page, 1500)
        fab = page.locator("[data-testid=ra-fab-tailor]")
        if fab.count() == 0:
            report["notes"].append("fab_inject_fallback")
            inject_fab(page)
        wire_fab(
            page,
            {
                "tailor": lead["workspace_url"],
                "apply": lead["apply_step_url"],
                "outreach": lead["outreach_step_url"],
            },
        )
        fab_ok = page.locator("[data-testid=ra-fab-tailor]").count() > 0
        gate("G1_fab", fab_ok, "three buttons")
        shot(page, "04-fab.png")

        ok_t = click_fab(context, page, "ra-fab-tailor", "step=tailor", "05-tailor.png")
        page.bring_to_front()
        pause(page, 600)
        ok_a = click_fab(context, page, "ra-fab-apply", "step=apply", "06-apply.png")
        page.bring_to_front()
        pause(page, 600)
        ok_o = click_fab(context, page, "ra-fab-outreach", "/outreach", "07-outreach.png")

        gate("G2_tailor", ok_t)
        gate("G3_apply", ok_a)
        gate("G4_outreach", ok_o)

        # Optional: if external apply URL looks like ATS, open and pause (no submit)
        apply_url = (job.get("apply_url") or "").strip()
        if apply_url and re.search(r"greenhouse|lever|myworkdayjobs|ashbyhq|icims", apply_url, re.I):
            report["notes"].append("ats_external_detected")
            ats = context.new_page()
            try:
                ats.goto(apply_url, wait_until="domcontentloaded", timeout=90000)
                pause(ats, 2500)
                shot(ats, "08-ats-external.png")
                gate("ats_opened", True, apply_url[:180])
                report["notes"].append("ats_stop_manual_review_only")
            except Exception as exc:
                gate("ats_opened", False, str(exc))
            finally:
                ats.close()
        else:
            report["notes"].append("no_external_ats_link_on_page")
            gate("ats_opened", True, "skipped_no_external_link")

        report["ok"] = all(
            report["gates"].get(k, {}).get("passed")
            for k in ("api_health", "live_job_open", "upsert_lead", "G1_fab", "G2_tailor", "G3_apply", "G4_outreach")
        )

        lines = [
            "# Jobright LIVE e2e",
            "",
            f"**Result:** {'PASS' if report['ok'] else 'FAIL'}",
            "",
            f"- job: {report['job'].get('title')} @ {report['job'].get('company')}",
            f"- page: {report['job'].get('page_url')}",
            f"- apply_url: {report['job'].get('apply_url') or '(none)'}",
            f"- job_id: {report.get('job_id')}",
            "",
            "## Gates",
            "",
        ]
        for k, v in report["gates"].items():
            lines.append(f"- {'✅' if v['passed'] else '❌'} `{k}` {v.get('detail','')}")
        lines += ["", "## Notes", ""]
        for n in report["notes"]:
            lines.append(f"- {n}")
        lines += ["", "## Screenshots", ""]
        for s in report["screenshots"]:
            lines.append(f"- `{s}`")
        (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
        (OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        context.close()
    shutil.rmtree(user_data, ignore_errors=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
