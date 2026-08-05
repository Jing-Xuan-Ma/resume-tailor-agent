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
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                        locator.click(timeout=5000)
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
                            with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                                locator.click(timeout=5000)
                            break
                    except Exception:
                        continue
            else:
                self._click_apply(page)
            page.wait_for_timeout(2000)
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
            # HARD STOP — never click Submit even if caller asked.
            # Real auto-submit stays frozen until product policy + ENABLE_AUTO_SUBMIT
            # are explicitly re-opened by the main agent (config is out of this module).
            _ = should_submit
            _ = submit_selectors
            browser.close()

        return {
            "submitted": False,
            "status": "filled_paused_before_submit",
            "mode": "playwright_fill_pause",
            "filled": filled,
            "message": "Browser automation filled fields and stopped before Submit.",
            "paused_before_submit": True,
        }

    def scan_fields(
        self,
        *,
        url: str,
        click_apply_first: bool = True,
    ) -> dict:
        """Open URL, optional Apply click, return DOM field scan. Never submits."""
        from app.config import settings

        if not settings.ENABLE_BROWSER_FILL_PAUSE and not settings.ENABLE_BROWSER_AUTOMATION:
            return {"fields": [], "status": "browser_fill_disabled", "url": url}
        if not url:
            return {"fields": [], "status": "missing_url", "url": url}
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return {"fields": [], "status": "playwright_unavailable", "message": str(exc), "url": url}

        from app.modules.ats_connectors.dom_scan import scan_page_fields

        fields: list = []
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=settings.BROWSER_HEADLESS, channel="chrome"
                )
            except Exception:
                browser = playwright.chromium.launch(headless=settings.BROWSER_HEADLESS)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT_MS)
            if click_apply_first:
                self._maybe_click_apply_entry(page)
            try:
                fields = scan_page_fields(page)
            except Exception:
                fields = []
            browser.close()
        return {"fields": fields, "status": "scanned", "url": url, "count": len(fields)}

    def fill_and_pause(
        self,
        *,
        url: str,
        answers: list[dict],
        field_selectors: dict[str, list[str]] | None = None,
        screenshot_path: str | None = None,
        ats_type: str | None = None,
        sandbox: bool = False,
        fill_plan: list[dict] | None = None,
        click_apply_first: bool = True,
    ) -> dict:
        """Fill supported fields and stop. Never clicks Submit.

        Prefer fill_plan (DOM-scan mappings with selectors). Falls back to answers+selectors.
        """
        from pathlib import Path

        from app.config import settings

        if not settings.ENABLE_BROWSER_FILL_PAUSE and not settings.ENABLE_BROWSER_AUTOMATION:
            return {
                "submitted": False,
                "status": "browser_fill_disabled",
                "mode": "dry_run",
                "filled": [],
                "message": "Browser fill-pause is disabled (set ENABLE_BROWSER_FILL_PAUSE=true).",
                "paused_before_submit": True,
                "ats_type": ats_type,
                "sandbox": sandbox,
            }
        if not url:
            return {
                "submitted": False,
                "status": "missing_url",
                "filled": [],
                "message": "No URL",
                "paused_before_submit": True,
                "ats_type": ats_type,
                "sandbox": sandbox,
            }

        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            return {
                "submitted": False,
                "status": "playwright_unavailable",
                "filled": [],
                "message": str(exc),
                "paused_before_submit": True,
                "ats_type": ats_type,
                "sandbox": sandbox,
            }

        filled: list[dict] = []
        scanned_fields: list[dict] = []
        shot = None
        submit_marker = ""
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=settings.BROWSER_HEADLESS, channel="chrome"
                )
            except Exception:
                browser = playwright.chromium.launch(headless=settings.BROWSER_HEADLESS)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT_MS)
            if click_apply_first:
                self._maybe_click_apply_entry(page)

            plan = list(fill_plan or [])
            if not plan:
                # Legacy path
                for item in answers:
                    answer = str(item.get("answer") or item.get("value") or "").strip()
                    question = str(item.get("question") or item.get("field") or "").strip()
                    field_name = str(item.get("field_name") or item.get("field") or "").strip()
                    field_type = str(item.get("field_type") or item.get("type") or "").strip()
                    aliases = [str(a) for a in (item.get("aliases") or [])]
                    if not answer or answer.startswith("("):
                        continue
                    if field_type == "file" or field_name in {"resume", "resume_upload", "cover_letter"}:
                        if not Path(answer).exists():
                            filled.append({"field": field_name, "status": "skipped_missing_file"})
                            continue
                        ok = self._upload_file(page, field_name, aliases, answer, field_selectors or {})
                    else:
                        ok = self._fill_field(
                            page, field_name, question, aliases, answer, field_selectors or {}
                        )
                    filled.append({"field": field_name or question, "status": "filled" if ok else "not_found"})
            else:
                from app.modules.ats_connectors.dom_scan import scan_page_fields

                try:
                    scanned_fields = scan_page_fields(page)
                except Exception:
                    scanned_fields = []
                for item in plan:
                    action = str(item.get("action") or "leave_empty")
                    value = str(item.get("value") or "").strip()
                    label = str(item.get("label") or item.get("profile_key") or item.get("field_id") or "")
                    tier = str(item.get("tier") or "")
                    if action == "leave_empty" or not value:
                        filled.append(
                            {
                                "field": label,
                                "field_id": item.get("field_id"),
                                "status": "left_empty",
                                "tier": tier or "empty",
                                "confidence": item.get("confidence"),
                                "needs_review": True,
                            }
                        )
                        continue
                    if action == "upload":
                        if not Path(value).exists():
                            filled.append(
                                {
                                    "field": label,
                                    "field_id": item.get("field_id"),
                                    "status": "skipped_missing_file",
                                    "tier": "empty",
                                    "needs_review": True,
                                }
                            )
                            continue
                        ok = self._fill_plan_item(page, item, value, upload=True)
                    else:
                        ok = self._fill_plan_item(page, item, value, upload=False)
                    filled.append(
                        {
                            "field": label,
                            "field_id": item.get("field_id"),
                            "status": "filled" if ok else "not_found",
                            "tier": tier,
                            "confidence": item.get("confidence"),
                            "needs_review": bool(item.get("needs_review")),
                            "profile_key": item.get("profile_key"),
                            "value": value if ok and action != "upload" else (value if ok else ""),
                        }
                    )

            # HARD STOP — never click submit / never invoke form.submit()
            try:
                submit_marker = (page.locator("#msg").first.inner_text(timeout=500) or "").strip()
            except Exception:
                submit_marker = ""
            if screenshot_path:
                Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                shot = screenshot_path
            browser.close()

        leaked_submit = "SUBMITTED" in submit_marker.upper()
        return {
            "submitted": False,
            "status": "filled_paused_before_submit",
            "mode": "playwright_fill_pause",
            "filled": filled,
            "fill_plan": fill_plan or [],
            "scanned_field_count": len(scanned_fields),
            "screenshot_path": shot,
            "message": "Filled form fields and stopped before Submit.",
            "paused_before_submit": True,
            "submit_marker": submit_marker,
            "submit_leaked": leaked_submit,
            "ats_type": ats_type,
            "sandbox": sandbox,
        }

    def _maybe_click_apply_entry(self, page) -> bool:
        """Greenhouse JD pages often need an Apply click before the form appears."""
        selectors = [
            "a:has-text('Apply')",
            "button:has-text('Apply')",
            "#apply_button",
            "a[href*='application']",
            "[data-testid='apply-button']",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() == 0:
                    continue
                text = (loc.inner_text(timeout=500) or "").lower()
                if "submit" in text:
                    continue
                loc.click(timeout=2000)
                page.wait_for_timeout(800)
                return True
            except Exception:
                continue
        return False

    def _frame_for_index(self, page, frame_index: int):
        frames = list(page.frames)
        if 0 <= int(frame_index) < len(frames):
            return frames[int(frame_index)]
        return page.main_frame

    def _fill_plan_item(self, page, item: dict, value: str, *, upload: bool) -> bool:
        frame = self._frame_for_index(page, int(item.get("frame_index") or 0))
        selector = str(item.get("selector") or "").strip()
        if selector:
            try:
                loc = frame.locator(selector).first
                if loc.count() > 0:
                    if upload:
                        loc.set_input_files(value, timeout=2500)
                    else:
                        tag = loc.evaluate("el => el.tagName.toLowerCase()")
                        if tag == "select":
                            try:
                                loc.select_option(label=value, timeout=1500)
                            except Exception:
                                loc.select_option(value=value, timeout=1500)
                        else:
                            loc.fill(value, timeout=1500)
                    return True
            except Exception:
                pass
        # Fallbacks
        label = str(item.get("label") or "")
        if upload:
            return self._upload_file(page, "resume", [label, "resume", "cv"], value, {})
        return self._fill_by_label(page, label, value) if label else False

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
