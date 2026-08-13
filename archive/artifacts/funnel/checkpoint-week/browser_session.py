from app.config import settings


class BrowserSession:
    """Dry-run browser session boundary.

    The first safe milestone is planning and field preparation. Real browser
    automation should be added behind this interface and remain submit-blocked
    until the user explicitly reviews the page.
    """

    mode = "dry_run"

    def open(self, url: str | None) -> dict:
        return {"mode": self.mode, "url": url, "opened": bool(url)}

    def submit(
        self,
        *,
        url: str | None,
        answers: list[dict],
        should_submit: bool,
        field_selectors: dict[str, list[str]] | None = None,
        submit_selectors: list[str] | None = None,
    ) -> dict:
        if not settings.ENABLE_BROWSER_AUTOMATION:
            return {
                "submitted": should_submit,
                "status": "browser_automation_disabled",
                "mode": "connector_submit_boundary",
                "message": (
                    "Browser automation is disabled. The application run was marked through the connector boundary."
                    if should_submit
                    else "Browser automation is disabled and submit was not requested."
                ),
            }
        if not url:
            return {"submitted": False, "status": "missing_url", "message": "Cannot submit without a source URL."}
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return {
                "submitted": False,
                "status": "playwright_unavailable",
                "message": f"Playwright is not installed or unavailable: {exc}",
            }

        filled: list[dict] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=settings.BROWSER_HEADLESS)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT_MS)
            for item in answers:
                answer = str(item.get("answer") or "").strip()
                question = str(item.get("question") or "").strip()
                field_name = str(item.get("field_name") or "").strip()
                field_type = str(item.get("field_type") or "").strip()
                aliases = [str(alias) for alias in item.get("aliases", []) or []]
                if not answer:
                    continue
                if field_type == "file":
                    filled_ok = self._upload_file(page, field_name, aliases, answer, field_selectors or {})
                else:
                    filled_ok = self._fill_field(page, field_name, question, aliases, answer, field_selectors or {})
                if filled_ok:
                    filled.append({"question": question, "status": "filled"})
                else:
                    filled.append({"question": question, "status": "not_found"})
            submitted = False
            if should_submit:
                submitted = self._click_submit(page, submit_selectors or [])
            browser.close()

        return {
            "submitted": submitted if should_submit else False,
            "status": "auto_submitted" if submitted else "filled_pending_manual_submit",
            "mode": "playwright",
            "filled": filled,
            "message": "Browser automation completed.",
        }

    def fill_and_pause(
        self,
        *,
        url: str,
        answers: list[dict],
        field_selectors: dict[str, list[str]] | None = None,
        screenshot_path: str | None = None,
    ) -> dict:
        """Fill supported fields and stop. Never clicks Submit."""
        from pathlib import Path

        from app.config import settings

        if not settings.ENABLE_BROWSER_FILL_PAUSE and not settings.ENABLE_BROWSER_AUTOMATION:
            return {
                "submitted": False,
                "status": "browser_fill_disabled",
                "mode": "dry_run",
                "filled": [],
                "message": "Browser fill-pause is disabled (set ENABLE_BROWSER_FILL_PAUSE=true).",
            }
        if not url:
            return {"submitted": False, "status": "missing_url", "filled": [], "message": "No URL"}

        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return {
                "submitted": False,
                "status": "playwright_unavailable",
                "filled": [],
                "message": str(exc),
            }

        filled: list[dict] = []
        shot = None
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=settings.BROWSER_HEADLESS, channel="chrome")
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT_MS)
            for item in answers:
                answer = str(item.get("answer") or item.get("value") or "").strip()
                question = str(item.get("question") or item.get("field") or "").strip()
                field_name = str(item.get("field_name") or item.get("field") or "").strip()
                field_type = str(item.get("field_type") or item.get("type") or "").strip()
                aliases = [str(a) for a in (item.get("aliases") or [])]
                if not answer or answer.startswith("("):
                    continue
                if field_type == "file" or field_name in {"resume", "resume_upload", "cover_letter"}:
                    # Skip missing local files in sandbox
                    if not Path(answer).exists():
                        filled.append({"field": field_name, "status": "skipped_missing_file"})
                        continue
                    ok = self._upload_file(page, field_name, aliases, answer, field_selectors or {})
                else:
                    ok = self._fill_field(page, field_name, question, aliases, answer, field_selectors or {})
                filled.append({"field": field_name or question, "status": "filled" if ok else "not_found"})
            # HARD STOP — never click submit
            if screenshot_path:
                Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                shot = screenshot_path
            browser.close()

        return {
            "submitted": False,
            "status": "filled_paused_before_submit",
            "mode": "playwright_fill_pause",
            "filled": filled,
            "screenshot_path": shot,
            "message": "Filled form fields and stopped before Submit.",
            "paused_before_submit": True,
        }

    def _fill_field(
        self,
        page,
        field_name: str,
        label_text: str,
        aliases: list[str],
        value: str,
        field_selectors: dict[str, list[str]],
    ) -> bool:
        for selector in field_selectors.get(field_name, []):
            if self._fill_selector(page, selector, value):
                return True
        for label in [label_text, *aliases]:
            if self._fill_by_label(page, label, value):
                return True
        return False

    def _fill_selector(self, page, selector: str, value: str) -> bool:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                tag = locator.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    locator.select_option(label=value, timeout=1500)
                else:
                    locator.fill(value, timeout=1500)
                return True
        except Exception:
            return False
        return False

    def _upload_file(self, page, field_name: str, aliases: list[str], file_path: str, field_selectors: dict[str, list[str]]) -> bool:
        selectors = [*field_selectors.get(field_name, []), "input[type='file']"]
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0:
                    locator.set_input_files(file_path, timeout=2500)
                    return True
            except Exception:
                continue
        for alias in aliases:
            try:
                page.get_by_label(alias, exact=False).set_input_files(file_path, timeout=2500)
                return True
            except Exception:
                continue
        return False

    def _fill_by_label(self, page, label_text: str, value: str) -> bool:
        candidates = [
            f"input[aria-label*='{label_text}' i]",
            f"textarea[aria-label*='{label_text}' i]",
            f"input[name*='{self._slug(label_text)}' i]",
            f"textarea[name*='{self._slug(label_text)}' i]",
        ]
        for selector in candidates:
            if self._fill_selector(page, selector, value):
                return True
        try:
            page.get_by_label(label_text, exact=False).fill(value, timeout=1500)
            return True
        except Exception:
            return False

    def _click_submit(self, page, submit_selectors: list[str]) -> bool:
        selectors = [
            *submit_selectors,
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit')",
            "button:has-text('Apply')",
            "button:has-text('Send')",
        ]
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0:
                    locator.click(timeout=2000)
                    return True
            except Exception:
                continue
        return False

    def _slug(self, value: str) -> str:
        return "_".join(part for part in value.lower().split() if part)
