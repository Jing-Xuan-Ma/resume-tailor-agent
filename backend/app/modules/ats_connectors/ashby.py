from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class AshbyConnector(BaseATSConnector):
    ats_type = "ashby"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        lower = (url or "").lower()
        return (
            "ashbyhq.com" in value
            or "jobs.ashbyhq.com" in value
            or "fixture_ashby" in lower
        )

    def fields(self) -> list[dict]:
        fields = super().fields()
        fields.extend([
            {"name": "linkedin", "type": "text", "required": False, "question": "LinkedIn Profile", "aliases": ["linkedin", "linkedin profile", "linkedin url"]},
            {"name": "website", "type": "text", "required": False, "question": "Portfolio or Website", "aliases": ["portfolio", "website", "personal website"]},
            {"name": "github", "type": "text", "required": False, "question": "GitHub Profile", "aliases": ["github", "github url"]},
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "full_name": [
                "#_systemfield_name",
                "#name",
                "input[name='name']",
                "input[autocomplete='name']",
                "input[id$='_name']",
                "input[aria-label*='full name' i]",
            ],
            "email": [
                "#_systemfield_email",
                "#email",
                "input[name='email']",
                "input[type='email']",
                "input[autocomplete='email']",
                "input[id$='_email']",
            ],
            "phone": [
                "#_systemfield_phone",
                "#phone",
                "input[name='phone']",
                "input[type='tel']",
                "input[autocomplete='tel']",
                "input[id$='_phone']",
            ],
            "resume": [
                "#_systemfield_resume",
                "input[type='file']",
                "input[type='file'][accept*='.pdf' i]",
                "div[data-testid='resume-upload'] input[type='file']",
            ],
            "cover_letter": [
                "input[type='file'][accept*='.pdf' i]",
                "input[type='file'][name*='cover' i]",
                "div[data-testid='cover-letter-upload'] input[type='file']",
            ],
            "linkedin": [
                "#linkedin",
                "input[name*='linkedin' i]",
                "input[id*='linkedin' i]",
                "input[placeholder*='linkedin' i]",
                "input[aria-label*='linkedin' i]",
            ],
            "website": [
                "#website",
                "input[name*='website' i]",
                "input[name*='portfolio' i]",
                "input[id*='website' i]",
                "input[placeholder*='portfolio' i]",
                "input[placeholder*='website' i]",
            ],
            "github": [
                "input[name*='github' i]",
                "input[id*='github' i]",
                "input[placeholder*='github' i]",
            ],
            "work_authorization": [
                "select[name*='authoriz' i]",
                "select[id*='authoriz' i]",
                "div[role='radiogroup'] label:has-text('Yes')",
                "div[role='radiogroup'] label:has-text('No')",
                "label:has(input[type='radio'])",
            ],
        })
        return selectors

    def apply_selectors(self) -> list[str]:
        return [
            "button:has-text('Apply for this Job')",
            "a:has-text('Apply for this Job')",
            "button:has-text('Apply')",
            "a:has-text('Apply')",
            "button:has-text('Start your application')",
            "a:has-text('Start your application')",
        ]

    def submit_selectors(self) -> list[str]:
        return [
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
            "button[type='submit']",
            "button:has-text('Next')",
            *super().submit_selectors(),
        ]

    def plan_steps(self, url: str | None) -> list[dict]:
        steps = super().plan_steps(url)
        steps.insert(1, {"action": "click_apply_button", "target": self.ats_type, "mode": "automated"})
        return steps
