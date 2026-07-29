from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class LeverConnector(BaseATSConnector):
    ats_type = "lever"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        return "lever.co" in value

    def fields(self) -> list[dict]:
        fields = super().fields()
        fields.extend([
            {"name": "linkedin", "type": "text", "required": False, "question": "LinkedIn Profile", "aliases": ["linkedin", "linkedin profile", "linkedin url"]},
            {"name": "website", "type": "text", "required": False, "question": "Portfolio or Website", "aliases": ["portfolio", "website", "personal website", "portfolio url"]},
            {"name": "github", "type": "text", "required": False, "question": "GitHub Profile", "aliases": ["github", "github url"]},
            {"name": "twitter", "type": "text", "required": False, "question": "Twitter Profile", "aliases": ["twitter", "x profile"]},
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "full_name": [
                "input[name='name']",
                "input[aria-label*='name' i]",
                "input#name",
                "input[data-testid='name-input']",
            ],
            "email": [
                "input[name='email']",
                "input[type='email']",
                "input#email",
            ],
            "phone": [
                "input[name='phone']",
                "input[type='tel']",
                "input#phone",
            ],
            "linkedin": [
                "input[name*='linkedin' i]",
                "input[id*='linkedin' i]",
                "input[placeholder*='linkedin' i]",
            ],
            "website": [
                "input[name*='urls' i]",
                "input[name*='portfolio' i]",
                "input[name*='website' i]",
                "input[placeholder*='portfolio' i]",
            ],
            "github": [
                "input[name*='github' i]",
                "input[id*='github' i]",
                "input[placeholder*='github' i]",
            ],
            "twitter": [
                "input[name*='twitter' i]",
                "input[id*='twitter' i]",
                "input[name*='x.com' i]",
            ],
            "resume": [
                "input[type='file'][name*='resume' i]",
                "input[type='file']#resume",
                "input[type='file']",
            ],
            "cover_letter": [
                "input[type='file'][name*='cover' i]",
                "input[type='file'][id*='cover' i]",
            ],
            "work_authorization": [
                "select[name*='authoriz' i]",
                "select[id*='authoriz' i]",
                "select[aria-label*='authoriz' i]",
                "input[aria-label*='authoriz' i]",
                "div[role='radiogroup'][aria-label*='authoriz' i] label",
            ],
        })
        return selectors

    def apply_selectors(self) -> list[str]:
        return [
            "a:has-text('Apply for this Job')",
            "button:has-text('Apply for this Job')",
            "button:has-text('Apply Now')",
            "button:has-text('Apply')",
            "a:has-text('Apply Now')",
            "a:has-text('Apply')",
        ]

    def submit_selectors(self) -> list[str]:
        return [
            "button:has-text('Submit application')",
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
            "button[type='submit']",
            *super().submit_selectors(),
        ]

    def plan_steps(self, url: str | None) -> list[dict]:
        steps = super().plan_steps(url)
        steps.insert(1, {"action": "click_apply_button", "target": self.ats_type, "mode": "automated"})
        return steps
