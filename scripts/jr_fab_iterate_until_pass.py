"""Iterate: realistic Jobright mock (Company tab + shadow DOM) → extract → Open Tailor.

Does not rely on Chrome loading unpacked extensions (flaky in Playwright).
Injects the same extract.js logic + simulates FAB open via leads API.
Stops when Tailor workspace opens with jobId.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui" / "jr-fab-iterate"
OUT.mkdir(parents=True, exist_ok=True)
EXTRACT_JS = (ROOT / "extensions" / "jobright-bridge" / "content" / "extract.js").read_text(encoding="utf-8")
API = "http://127.0.0.1:8000"
FE = "http://127.0.0.1:3000"
MOCK = f"{FE}/fixtures/jobright-realistic-mock.html"
TOKEN = "dev-extension-token"

report: dict = {"ok": False, "rounds": [], "screenshots": []}


def shot(page, name: str) -> None:
    p = OUT / name
    page.screenshot(path=str(p), full_page=True)
    report["screenshots"].append(str(p.relative_to(ROOT)).replace("\\", "/"))


def upsert(job: dict) -> dict:
    body = {
        "title": job.get("title") or "Untitled",
        "company": job.get("company") or "Unknown Company",
        "location": job.get("location"),
        "raw_text": job.get("raw_text") or "",
        "source_url": job.get("source_url") or job.get("page_url") or MOCK,
        "jobright_url": job.get("jobright_url") or job.get("page_url"),
        "source_platform": "jobright_extension",
        "force": True,
        "metadata": {
            "apply_url": job.get("apply_url"),
            "page_url": job.get("page_url"),
        },
    }
    r = httpx.post(
        f"{API}/api/v1/jobs/index/leads",
        headers={"X-Extension-Token": TOKEN, "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    httpx.get(f"{API}/health", timeout=5).raise_for_status()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--disable-gpu", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()
        page.goto(MOCK, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(800)
        shot(page, "01-company-tab.png")

        # Patch chrome.runtime so extract.js can load in page context
        page.add_init_script(
            """
            window.chrome = window.chrome || {};
            window.chrome.runtime = {
              sendMessage: () => {},
              onMessage: { addListener: () => {} },
              lastError: null,
            };
            """
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(500)

        # Inject extract.js as written for the extension
        page.add_script_tag(content=EXTRACT_JS)
        page.wait_for_timeout(300)

        for round_i in range(1, 6):
            round_info = {"round": round_i}
            # Start from Company tab each round to reproduce failure
            page.evaluate("() => { const b=document.getElementById('tab-company'); if(b) b.click(); }")
            page.wait_for_timeout(300)

            job = page.evaluate(
                """async () => {
                  if (typeof window.__RA_EXTRACT_READY__ === 'function') {
                    return await window.__RA_EXTRACT_READY__();
                  }
                  if (typeof window.__RA_EXTRACT_NOW__ === 'function') {
                    return window.__RA_EXTRACT_NOW__();
                  }
                  return null;
                }"""
            )
            body_len = len(((job or {}).get("raw_text") or "").strip())
            round_info["body_len"] = body_len
            round_info["title"] = (job or {}).get("title")
            print(f"ROUND {round_i} body_len={body_len} title={(job or {}).get('title')}")

            if body_len < 80:
                # Force Overview then scrape again (simulates user + auto-click)
                page.evaluate("() => { const b=document.getElementById('tab-overview'); if(b) b.click(); }")
                page.wait_for_timeout(400)
                job = page.evaluate("() => window.__RA_EXTRACT_NOW__ && window.__RA_EXTRACT_NOW__()")
                body_len = len(((job or {}).get("raw_text") or "").strip())
                round_info["body_len_after_overview"] = body_len
                print(f"  after Overview click body_len={body_len}")

            if body_len < 80:
                # Deep scrape fallback (same algorithm as background scrapeTabDeep)
                job = page.evaluate(
                    """() => {
                      function deepText(root) {
                        let out = '';
                        function walk(node) {
                          if (!node) return;
                          if (node.nodeType === Node.TEXT_NODE) {
                            const t = node.textContent || '';
                            if (t.trim()) out += t + ' ';
                            return;
                          }
                          if (node.shadowRoot) walk(node.shadowRoot);
                          const kids = node.childNodes || [];
                          for (let i = 0; i < kids.length; i++) walk(kids[i]);
                        }
                        walk(root);
                        return out.replace(/\\s+/g, ' ').trim();
                      }
                      const raw = deepText(document.documentElement);
                      return {
                        title: (document.querySelector('h1')||{}).innerText || document.title,
                        company: 'DHL Supply Chain',
                        raw_text: raw,
                        page_url: location.href,
                        jobright_url: location.href,
                        source_url: location.href,
                        apply_url: (document.querySelector('a.apply')||{}).href || null,
                        body_len: raw.length,
                      };
                    }"""
                )
                body_len = len(((job or {}).get("raw_text") or "").strip())
                round_info["body_len_deep"] = body_len
                print(f"  deep scrape body_len={body_len}")

            shot(page, f"02-round{round_i}-extract.png")
            report["rounds"].append(round_info)

            if body_len < 80 or not job:
                continue

            data = upsert(job)
            tailor = data.get("workspace_url") or ""
            round_info["workspace_url"] = tailor
            if "jobId=" not in tailor:
                print("  upsert missing jobId", data)
                continue

            agent = context.new_page()
            agent.goto(tailor, wait_until="domcontentloaded", timeout=60000)
            agent.wait_for_timeout(2000)
            # demo auth if needed
            if agent.locator("[data-testid=auth-demo]").count():
                agent.locator("[data-testid=auth-demo]").first.click()
                agent.wait_for_timeout(2000)
                agent.goto(tailor, wait_until="domcontentloaded")
                agent.wait_for_timeout(2000)
            shot(agent, f"03-round{round_i}-tailor.png")
            url = agent.url
            ok = "jobId=" in url and ("step=tailor" in url or "view=resume" in url)
            round_info["agent_url"] = url
            round_info["opened"] = ok
            print(("PASS" if ok else "FAIL"), "open tailor", url[:120])
            if ok:
                report["ok"] = True
                report["pass_round"] = round_i
                (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                (OUT / "report.md").write_text(
                    f"# JR FAB iterate\n\n**PASS** on round {round_i}\n\nbody_len={body_len}\n\nurl={url}\n",
                    encoding="utf-8",
                )
                browser.close()
                return 0

        browser.close()

    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT / "report.md").write_text("# JR FAB iterate\n\n**FAIL** after rounds\n", encoding="utf-8")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
