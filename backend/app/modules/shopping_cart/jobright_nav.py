"""Phase 2: open Jobright job page → click Original Job Post / APPLY NOW → land on ATS URL."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
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

_PROJECT_ROOT = Path(__file__).resolve().parents[4]

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
    "a[href*='lifeattiktok.com']",
    "a[href*='careers.tiktok.com']",
]

_APPLY_NOW_RE = re.compile(r"APPLY\s*NOW", re.I)
_SIGNUP_WALL_RE = re.compile(r"Sign\s*Up\s*to\s*Apply", re.I)


def detect_ats_type(url: str | None) -> str:
    host = _host(url or "")
    if "lifeattiktok.com" in host or host.startswith("careers.tiktok."):
        return "lifeattiktok"
    connector = connector_for(url)
    return str(getattr(connector, "ats_type", None) or "") or "generic"


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _resolve_data_path(configured: str, *defaults: str) -> Path | None:
    raw = (configured or "").strip()
    candidates: list[Path] = []
    if raw:
        p = Path(raw)
        candidates.append(p if p.is_absolute() else (_PROJECT_ROOT / p))
        # backend/.env often uses paths relative to backend/
        candidates.append(Path(__file__).resolve().parents[3] / p)
    for rel in defaults:
        candidates.append(_PROJECT_ROOT / rel)
    for path in candidates:
        try:
            if path.is_file():
                return path.resolve()
        except Exception:
            continue
    return None


def cookie_editor_to_playwright(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Cookie-Editor JSON export → Playwright add_cookies() shape."""
    out: list[dict[str, Any]] = []
    for c in raw or []:
        if not isinstance(c, dict) or not c.get("name") or c.get("value") is None:
            continue
        same = c.get("sameSite")
        same_l = str(same or "").lower()
        if same in (None, "", "unspecified") or same_l in ("unspecified", "null"):
            same_site = "Lax"
        elif same_l in ("no_restriction", "none"):
            same_site = "None"
        elif same_l == "lax":
            same_site = "Lax"
        elif same_l == "strict":
            same_site = "Strict"
        else:
            same_site = "Lax"
        item: dict[str, Any] = {
            "name": str(c["name"]),
            "value": str(c["value"]),
            "domain": str(c.get("domain") or ".jobright.ai"),
            "path": str(c.get("path") or "/"),
            "httpOnly": bool(c.get("httpOnly")),
            "secure": bool(c.get("secure")),
            "sameSite": same_site,
        }
        exp = c.get("expirationDate")
        if exp is not None:
            try:
                item["expires"] = float(exp)
            except (TypeError, ValueError):
                pass
        out.append(item)
    return out


def load_jobright_auth() -> dict[str, Any]:
    """Load storage_state and/or Cookie-Editor cookies for authenticated Jobright nav."""
    storage_path = _resolve_data_path(
        getattr(settings, "JOBRIGHT_STORAGE_STATE_PATH", "") or "",
        "data/jobright_storage_state.json",
    )
    cookies_path = _resolve_data_path(
        getattr(settings, "JOBRIGHT_COOKIES_PATH", "") or "",
        "data/jobright_cookies.json",
    )
    info: dict[str, Any] = {
        "storage_state": str(storage_path) if storage_path else None,
        "cookies_path": str(cookies_path) if cookies_path else None,
        "cookies": [],
        "source": None,
    }
    if storage_path:
        info["source"] = "storage_state"
    if cookies_path:
        try:
            raw = json.loads(cookies_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                info["cookies"] = cookie_editor_to_playwright(raw)
                info["source"] = info["source"] or "cookies"
            elif isinstance(raw, dict) and isinstance(raw.get("cookies"), list):
                # Playwright storage_state-shaped file used as cookies path
                info["cookies"] = raw["cookies"]
                info["source"] = info["source"] or "cookies"
        except Exception as exc:  # noqa: BLE001
            log.warning("jobright cookies load failed path=%s err=%s", cookies_path, exc)
    return info


def _dismiss_jobright_overlays(page: Any) -> None:
    """Close Orion / promo modals that can block Original Job Post clicks."""
    for sel in (
        "[role=dialog] button:has-text('EXIT')",
        "[role=dialog] button:has-text('Exit')",
        "button:has-text('EXIT')",
        "[role=dialog] button:has-text('Not now')",
        "[aria-label='Close']",
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=1500)
                page.wait_for_timeout(400)
        except Exception:
            continue


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


def _page_has_signup_wall(page: Any) -> bool:
    try:
        if page.get_by_text(_SIGNUP_WALL_RE).count() > 0:
            return True
    except Exception:
        pass
    try:
        body = (page.inner_text("body") or "")[:4000]
        return bool(_SIGNUP_WALL_RE.search(body))
    except Exception:
        return False


def _try_click_open_external(context: Any, page: Any, loc: Any, timeout_ms: int) -> str | None:
    """Click a locator; return popup / navigated URL if it leaves Jobright."""
    try:
        with context.expect_page(timeout=8000) as new_page_info:
            loc.click(timeout=5000)
        new_page = new_page_info.value
        new_page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        return new_page.url
    except Exception:
        pass
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
            loc.click(timeout=5000)
        return page.url
    except Exception:
        try:
            loc.click(timeout=5000)
            page.wait_for_timeout(1500)
            return page.url
        except Exception:
            return None


def navigate_jobright_to_ats(
    *,
    jobright_url: str,
    timeout_ms: int | None = None,
    headless: bool | None = None,
) -> dict[str, Any]:
    """Live Playwright: Jobright detail → Original Job Post / APPLY NOW → final ATS URL."""
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

    auth = load_jobright_auth()
    screenshot_note = None
    final_url = None
    clicked = False
    employer_site_mode = False
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=headless, channel="chrome")
            except Exception:
                browser = playwright.chromium.launch(headless=headless)

            context_kwargs: dict[str, Any] = {}
            if auth.get("storage_state"):
                context_kwargs["storage_state"] = auth["storage_state"]
            context = browser.new_context(**context_kwargs)
            if auth.get("cookies") and not auth.get("storage_state"):
                try:
                    context.add_cookies(auth["cookies"])
                except Exception as exc:  # noqa: BLE001
                    log.warning("jobright add_cookies failed: %s", exc)

            page = context.new_page()
            page.goto(jr, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(1500)
            _dismiss_jobright_overlays(page)

            try:
                employer_site_mode = page.get_by_text(
                    re.compile(r"Apply on Employer Site", re.I)
                ).count() > 0
            except Exception:
                employer_site_mode = False

            # Prefer popup / new-tab open for Original Job Post / ATS anchors
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

                    opened = _try_click_open_external(context, page, loc, timeout_ms)
                    if opened and "jobright.ai" not in _host(opened):
                        final_url = opened
                        clicked = True
                        break
                    if _page_has_signup_wall(page):
                        screenshot_note = "jobright_login_required_for_employer_site"
                        break
                except Exception:
                    continue

            # Employer-site jobs often only expose a green APPLY NOW button (no Original Post link).
            if not final_url and screenshot_note != "jobright_login_required_for_employer_site":
                try:
                    btn = page.get_by_role("button", name=_APPLY_NOW_RE)
                    if btn.count() == 0:
                        btn = page.get_by_text(_APPLY_NOW_RE)
                    if btn.count() > 0 and btn.first.is_visible():
                        opened = _try_click_open_external(context, page, btn.first, timeout_ms)
                        clicked = True
                        if opened and "jobright.ai" not in _host(opened):
                            final_url = opened
                        elif _page_has_signup_wall(page):
                            screenshot_note = "jobright_login_required_for_employer_site"
                except Exception:
                    pass

            if not final_url and screenshot_note != "jobright_login_required_for_employer_site":
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

            if not final_url and not screenshot_note:
                screenshot_note = (
                    "jobright_login_required_for_employer_site"
                    if employer_site_mode and _page_has_signup_wall(page)
                    else "original_job_post_not_found"
                )
                if not auth.get("source"):
                    screenshot_note = "jobright_login_required_missing_session"

            browser.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("jobright navigate failed url=%s err=%s", jr, exc)
        return {
            "ok": False,
            "error": str(exc),
            "method": "jobright_original_post_click",
            "jobright_url": jr,
            "auth_source": auth.get("source"),
        }

    final_url = normalize_apply_url(final_url) or final_url
    if not final_url or is_aggregator_url(final_url) or "jobright.ai" in _host(final_url or ""):
        return {
            "ok": False,
            "error": screenshot_note or "original_job_post_not_found",
            "method": "jobright_original_post_click",
            "jobright_url": jr,
            "clicked": clicked,
            "employer_site_mode": employer_site_mode,
            "auth_source": auth.get("source"),
        }

    return {
        "ok": True,
        "ats_url": final_url,
        "ats_type": detect_ats_type(final_url),
        "method": "jobright_original_post_click",
        "jobright_url": jr,
        "clicked": clicked,
        "employer_site_mode": employer_site_mode,
        "auth_source": auth.get("source"),
    }


def resolve_ats_from_company_resolver(
    *,
    intern_job_id: str,
    source_url: str | None = None,
) -> dict[str, Any] | None:
    """Fallback: company ATS cache + Greenhouse/Workday/LifeAtTikTok board search by title."""
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
        "company": company,
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
        "adapter": getattr(result, "adapter", None),
    }


def resolve_ats_url_for_item(
    *,
    intern_job_id: str,
    jobright_url: str,
    source_url: str | None = None,
    force_live: bool | None = None,
) -> dict[str, Any]:
    """Phase 2 resolver: scraped / company resolver / live Jobright Original Job Post.

    - CART_APPLY_LIVE_NAV=true → try live Jobright click first (uses saved login session).
    - else scraped → company resolver → live once if CART_APPLY_LIVE_NAV_FALLBACK.
    """
    prefer_live = (
        bool(force_live)
        if force_live is not None
        else bool(getattr(settings, "CART_APPLY_LIVE_NAV", False))
    )
    allow_fallback = bool(getattr(settings, "CART_APPLY_LIVE_NAV_FALLBACK", True))

    def _run_live() -> dict[str, Any]:
        nav = navigate_jobright_to_ats(jobright_url=jobright_url)
        if nav.get("ok"):
            if is_usable_job_apply_url(nav.get("ats_url")):
                return nav
            return {
                "ok": False,
                "error": "jobright_url_not_official_ats",
                "rejected_url": nav.get("ats_url"),
                "method": nav.get("method") or "jobright_original_post_click",
                "jobright_url": jobright_url,
                "auth_source": nav.get("auth_source"),
            }
        return {
            "ok": False,
            "error": nav.get("error") or "no_official_ats_url",
            "method": nav.get("method") or "none",
            "jobright_url": jobright_url,
            "employer_site_mode": nav.get("employer_site_mode"),
            "auth_source": nav.get("auth_source"),
        }

    if prefer_live:
        live_out = _run_live()
        if live_out.get("ok"):
            return live_out
        scraped = resolve_ats_from_scraped(intern_job_id=intern_job_id, source_url=source_url)
        if scraped:
            scraped = {**scraped, "live_error": live_out.get("error")}
            return scraped
        resolved = resolve_ats_from_company_resolver(
            intern_job_id=intern_job_id, source_url=source_url
        )
        if resolved and resolved.get("ok"):
            return {**resolved, "live_error": live_out.get("error")}
        return live_out

    scraped = resolve_ats_from_scraped(intern_job_id=intern_job_id, source_url=source_url)
    if scraped:
        return scraped

    resolved = resolve_ats_from_company_resolver(
        intern_job_id=intern_job_id, source_url=source_url
    )
    if resolved and resolved.get("ok"):
        return resolved

    if allow_fallback or force_live:
        live_out = _run_live()
        if live_out.get("ok"):
            return live_out
        return {
            **live_out,
            "resolver_message": (resolved or {}).get("resolver_message") if resolved else None,
        }

    return {
        "ok": False,
        "error": "no_official_ats_url",
        "method": "none",
        "jobright_url": jobright_url,
        "resolver_message": (resolved or {}).get("resolver_message") if resolved else None,
        "note": "Set CART_APPLY_LIVE_NAV=true or provide Jobright session cookies",
    }
