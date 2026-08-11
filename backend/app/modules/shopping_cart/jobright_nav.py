"""Phase 2: open Jobright job page → click Original Job Post → land on ATS URL."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.modules.ats_connectors.registry import connector_for
from app.modules.job_discovery.apply_url import (
    is_aggregator_url,
    is_usable_job_apply_url,
    normalize_apply_url,
)

log = logging.getLogger(__name__)

_ORIGINAL_POST_SELECTORS = [
    "a:has-text('Original Job Post')",
    "button:has-text('Original Job Post')",
    "[role=link]:has-text('Original Job Post')",
    "a:has-text('Original job post')",
    "a:has-text('Apply on Employer Site')",
    "a:has-text('Apply on employer site')",
    "a[href*='myworkdayjobs.com']",
    "a[href*='greenhouse.io']",
    "a[href*='lever.co']",
    "a[href*='ashbyhq.com']",
]


def detect_ats_type(url: str | None) -> str:
    connector = connector_for(url)
    return str(getattr(connector, "ats_type", None) or "generic")


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def resolve_ats_from_scraped(
    *, intern_job_id: str, source_url: str | None
) -> dict[str, Any] | None:
    """Fast path when DB/scrape already has a company ATS URL."""
    from app.modules.shopping_cart.store import resolve_intern_job

    candidates: list[str | None] = [source_url]
    try:
        resolved = resolve_intern_job(intern_job_id)
        candidates.append(resolved.get("source_url"))
        candidates.append(resolved.get("apply_url") if isinstance(resolved, dict) else None)
    except Exception:
        pass

    for raw in candidates:
        url = normalize_apply_url(raw)
        if not url:
            continue
        if is_aggregator_url(url):
            continue
        if not is_usable_job_apply_url(url):
            continue
        return {
            "ats_url": url,
            "ats_type": detect_ats_type(url),
            "method": "scraped_apply_url",
            "ok": True,
        }
    return None


def navigate_jobright_to_ats(
    *,
    jobright_url: str,
    timeout_ms: int | None = None,
    headless: bool | None = None,
) -> dict[str, Any]:
    """Live Playwright: Jobright detail → Original Job Post → final ATS URL."""
    timeout_ms = int(timeout_ms or settings.BROWSER_TIMEOUT_MS or 30000)
    headless = settings.BROWSER_HEADLESS if headless is None else bool(headless)
    jr = normalize_apply_url(jobright_url) or (jobright_url or "").strip()
    if not jr:
        return {
            "ok": False,
            "error": "missing_jobright_url",
            "method": "jobright_original_post_click",
        }

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"playwright_unavailable: {exc}",
            "method": "jobright_original_post_click",
        }

    screenshot_note = None
    final_url = None
    clicked = False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()
            page.goto(jr, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)

            # Prefer popup / new-tab open for Original Job Post
            for selector in _ORIGINAL_POST_SELECTORS:
                try:
                    matches = page.locator(selector)
                    if matches.count() == 0:
                        continue
                    loc = matches.first
                    if not loc.is_visible():
                        continue
                    href = None
                    try:
                        href = loc.get_attribute("href")
                    except Exception:
                        href = None
                    href = normalize_apply_url(href)
                    if href and not is_aggregator_url(href) and is_usable_job_apply_url(href):
                        final_url = href
                        clicked = True
                        break

                    try:
                        with context.expect_page(timeout=8000) as new_page_info:
                            loc.click(timeout=5000)
                        new_page = new_page_info.value
                        new_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                        final_url = new_page.url
                        clicked = True
                        break
                    except Exception:
                        try:
                            with page.expect_navigation(
                                wait_until="domcontentloaded", timeout=timeout_ms
                            ):
                                loc.click(timeout=5000)
                            final_url = page.url
                            clicked = True
                            break
                        except Exception:
                            continue
                except Exception:
                    continue

            if not final_url:
                # Scan all external links as last resort
                try:
                    hrefs = page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => e.href)",
                    )
                except Exception:
                    hrefs = []
                for href in hrefs or []:
                    u = normalize_apply_url(href)
                    if not u or is_aggregator_url(u):
                        continue
                    if "jobright.ai" in _host(u):
                        continue
                    if is_usable_job_apply_url(u):
                        final_url = u
                        clicked = True
                        break

            if not final_url:
                try:
                    screenshot_note = "original_job_post_not_found"
                except Exception:
                    pass

            browser.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("jobright navigate failed url=%s err=%s", jr, exc)
        return {
            "ok": False,
            "error": str(exc),
            "method": "jobright_original_post_click",
            "jobright_url": jr,
        }

    final_url = normalize_apply_url(final_url) or final_url
    if not final_url or is_aggregator_url(final_url) or "jobright.ai" in _host(final_url or ""):
        return {
            "ok": False,
            "error": screenshot_note or "original_job_post_not_found",
            "method": "jobright_original_post_click",
            "jobright_url": jr,
            "clicked": clicked,
        }

    return {
        "ok": True,
        "ats_url": final_url,
        "ats_type": detect_ats_type(final_url),
        "method": "jobright_original_post_click",
        "jobright_url": jr,
        "clicked": clicked,
    }


def resolve_ats_from_company_resolver(
    *,
    intern_job_id: str,
    source_url: str | None = None,
) -> dict[str, Any] | None:
    """Fallback: company ATS cache + Greenhouse/Workday board search by title."""
    try:
        from app.modules.job_discovery.apply_resolver import resolve_apply_url
        from app.modules.job_discovery.apply_url import (
            is_ats_or_company_apply_url,
            is_usable_job_apply_url,
            normalize_apply_url,
        )
        from app.modules.shopping_cart.store import resolve_intern_job
    except Exception:
        return None

    try:
        job = resolve_intern_job(intern_job_id) or {}
    except Exception:
        job = {}
    company = str(job.get("company") or "").strip()
    title = str(job.get("title") or job.get("position") or "").strip()
    if not title:
        return None
    hints: dict[str, Any] = {
        "source_url": source_url or job.get("source_url"),
        "raw_text": job.get("jd_text") or "",
    }
    try:
        result = resolve_apply_url(
            company=company,
            title=title,
            location=str(job.get("location") or "") or None,
            raw_text=str(job.get("jd_text") or "") or None,
            hints=hints,
            verify=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"company_resolver_error:{exc}",
            "method": "company_ats_resolver",
        }
    url = normalize_apply_url(getattr(result, "url", None))
    status = str(getattr(getattr(result, "status", None), "value", getattr(result, "status", "")) or "")
    if not url or not is_usable_job_apply_url(url) or not is_ats_or_company_apply_url(url):
        return None
    if status in {"not_found", "error"}:
        return None
    return {
        "ok": True,
        "ats_url": url,
        "ats_type": detect_ats_type(url),
        "method": "company_ats_resolver",
        "resolver_status": status,
        "resolver_message": getattr(result, "message", None),
        "company": company,
        "title": title,
    }


def resolve_ats_url_for_item(
    *,
    intern_job_id: str,
    jobright_url: str,
    source_url: str | None = None,
    force_live: bool | None = None,
) -> dict[str, Any]:
    """Phase 2 resolver: scraped → company ATS resolver → live Jobright click."""
    live = (
        bool(force_live)
        if force_live is not None
        else bool(getattr(settings, "CART_APPLY_LIVE_NAV", False))
    )

    scraped = resolve_ats_from_scraped(intern_job_id=intern_job_id, source_url=source_url)
    if scraped:
        return scraped

    resolved = resolve_ats_from_company_resolver(
        intern_job_id=intern_job_id, source_url=source_url
    )
    if resolved and resolved.get("ok"):
        return resolved

    # Live Jobright is slow and often returns non-ATS links; only when explicitly enabled.
    if live:
        nav = navigate_jobright_to_ats(jobright_url=jobright_url)
        if nav.get("ok"):
            from app.modules.job_discovery.apply_url import is_usable_job_apply_url

            if is_usable_job_apply_url(nav.get("ats_url")):
                return nav
            return {
                "ok": False,
                "error": "jobright_url_not_official_ats",
                "rejected_url": nav.get("ats_url"),
                "method": nav.get("method") or "jobright_original_post_click",
                "jobright_url": jobright_url,
            }
        return {
            "ok": False,
            "error": nav.get("error") or "no_official_ats_url",
            "method": nav.get("method") or "none",
            "jobright_url": jobright_url,
            "resolver_message": (resolved or {}).get("resolver_message") if resolved else None,
        }

    return {
        "ok": False,
        "error": "no_official_ats_url",
        "method": "none",
        "jobright_url": jobright_url,
        "resolver_message": (resolved or {}).get("resolver_message") if resolved else None,
        "note": "Set CART_APPLY_LIVE_NAV=true to try Jobright Original Job Post click",
    }
