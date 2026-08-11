from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class WorkableConnector(BaseATSConnector):
    ats_type = "workable"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        lower = (url or "").lower()
        return "workable.com" in value or "fixture_workable" in lower

    def fields(self) -> list[dict]:
        fields = super().fields()
        fields.extend([
            {"name": "linkedin", "type": "text", "required": False, "question": "LinkedIn Profile", "aliases": ["linkedin", "linkedin profile"]},
            {"name": "website", "type": "text", "required": False, "question": "Portfolio or Website", "aliases": ["portfolio", "website"]},
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "full_name": [
                "input[name='name']",
                "input[id*='candidate_name' i]",
                "input[aria-label*='full name' i]",
            ],
            "email": [
                "input[name='email']",
                "input[type='email']",
            ],
            "phone": [
                "input[name='phone']",
                "input[type='tel']",
            ],
            "linkedin": [
                "input[name*='linkedin' i]",
                "input[id*='linkedin' i]",
                "input[placeholder*='linkedin' i]",
            ],
            "website": [
                "input[name*='website' i]",
                "input[name*='portfolio' i]",
                "input[placeholder*='website' i]",
            ],
            "resume": [
                "input[type='file'][name*='resume' i]",
                "input[type='file']",
                "div[data-ui='resume'] input[type='file']",
            ],
            "cover_letter": [
                "input[type='file'][name*='cover' i]",
                "div[data-ui='cover_letter'] input[type='file']",
            ],
            "work_authorization": [
                "select[name*='authoriz' i]",
                "fieldset:has-text('authorized') input[type='radio']",
            ],
        })
        return selectors

    def apply_selectors(self) -> list[str]:
        return [
            "a:has-text('Apply for this job')",
            "button:has-text('Apply for this job')",
            "button:has-text('Apply')",
            "a:has-text('Apply')",
        ]

    def submit_selectors(self) -> list[str]:
        return [
            "button:has-text('Submit application')",
            "button:has-text('Submit')",
            "button[type='submit']",
            *super().submit_selectors(),
        ]
