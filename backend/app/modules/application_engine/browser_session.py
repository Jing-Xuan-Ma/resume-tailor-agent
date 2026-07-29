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

    def _click_apply(self, page) -> bool:
        apply_selectors = [
            "button:has-text('Apply for this Job')",
            "button:has-text('Apply')",
            "button:has-text('Start Application')",
            "a:has-text('Apply for this Job')",
            "a:has-text('Apply')",
            "[role=button]:has-text('Apply')",
        ]
        for selector in apply_selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0 and locator.is_visible():
                    locator.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    return True
            except Exception:
                continue
        return False

    def submit(
        self,
        *,
        url: str | None,
        answers: list[dict],
        should_submit: bool,
        field_selectors: dict[str, list[str]] | None = None,
        submit_selectors: list[str] | None = None,
        apply_selectors: list[str] | None = None,
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
            page.wait_for_timeout(2000)
            if apply_selectors:
                for selector in apply_selectors:
                    try:
                        locator = page.locator(selector).first
                        if locator.count() > 0 and locator.is_visible():
                            locator.click(timeout=3000)
                            page.wait_for_timeout(2000)
                            break
                    except Exception:
                        continue
            else:
                self._click_apply(page)
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
