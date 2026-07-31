from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class LeverConnector(BaseATSConnector):
    """Lever postings connector for core single-page application fields.

    Lever uses a single ``name`` field (not first/last). URL fields commonly
    appear as ``urls[LinkedIn]``, ``urls[GitHub]``, ``urls[Portfolio]``. Cover
    letters are often a textarea (``comments`` / custom) rather than a file.
    Workday/iCIMS stay on thinner fallback overlays — depth over breadth.
    """

    ats_type = "lever"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        return "lever.co" in value

    def fields(self) -> list[dict]:
        fields = super().fields()
        # Prefer text cover letter for Lever; browser will also try file upload.
        for field in fields:
            if field["name"] == "cover_letter":
                field["type"] = "text"
                field["question"] = "Cover letter / additional information"
                field["aliases"] = [
                    "cover letter",
                    "additional information",
                    "comments",
                    "additional info",
                ]
        fields.extend([
            {
                "name": "org",
                "type": "text",
                "required": False,
                "question": "Current company",
                "aliases": ["company", "current company", "organization", "employer"],
            },
            {
                "name": "linkedin",
                "type": "text",
                "required": False,
                "question": "LinkedIn Profile",
                "aliases": ["linkedin", "linkedin profile", "linkedin url"],
            },
            {
                "name": "website",
                "type": "text",
                "required": False,
                "question": "Portfolio or Website",
                "aliases": ["portfolio", "website", "personal website", "portfolio url"],
            },
            {
                "name": "github",
                "type": "text",
                "required": False,
                "question": "GitHub Profile",
                "aliases": ["github", "github url"],
            },
            {
                "name": "twitter",
                "type": "text",
                "required": False,
                "question": "Twitter / X Profile",
                "aliases": ["twitter", "x profile", "x.com"],
            },
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "full_name": [
                "input[name='name']",
                "input#name",
                "input[data-qa='name-input']",
                "input[data-testid='name-input']",
                "input[aria-label*='full name' i]",
                "input[aria-label*='name' i]",
            ],
            "email": [
                "input[name='email']",
                "input[type='email']",
                "input#email",
                "input[data-qa='email-input']",
            ],
            "phone": [
                "input[name='phone']",
                "input[type='tel']",
                "input#phone",
                "input[data-qa='phone-input']",
            ],
            "org": [
                "input[name='org']",
                "input[name*='company' i]",
                "input[id*='company' i]",
                "input[placeholder*='company' i]",
            ],
            "linkedin": [
                "input[name='urls[LinkedIn]']",
                "input[name='urls[Linkedin]']",
                "input[name*='linkedin' i]",
                "input[id*='linkedin' i]",
                "input[placeholder*='linkedin' i]",
            ],
            "website": [
                "input[name='urls[Portfolio]']",
                "input[name='urls[Other]']",
                "input[name*='portfolio' i]",
                "input[name*='website' i]",
                "input[placeholder*='portfolio' i]",
            ],
            "github": [
                "input[name='urls[GitHub]']",
                "input[name='urls[Github]']",
                "input[name*='github' i]",
                "input[id*='github' i]",
                "input[placeholder*='github' i]",
            ],
            "twitter": [
                "input[name='urls[Twitter]']",
                "input[name*='twitter' i]",
                "input[id*='twitter' i]",
                "input[name*='x.com' i]",
            ],
            "resume": [
                "input[name='resume']",
                "input[type='file'][name*='resume' i]",
                "input[type='file']#resume",
                "input[type='file'][data-qa*='resume' i]",
            ],
            "cover_letter": [
                "textarea[name='comments']",
                "textarea[name*='cover' i]",
                "textarea[id*='cover' i]",
                "textarea[aria-label*='cover' i]",
                "textarea[placeholder*='cover' i]",
                "textarea[name*='additional' i]",
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
            "a.postings-btn:has-text('Apply')",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
            "button:has-text('Apply')",
            "a:has-text('Apply')",
        ]

    def submit_selectors(self) -> list[str]:
        return [
            "button.template-btn-submit",
            "button:has-text('Submit application')",
            "button:has-text('Submit Application')",
            "button[type='submit']:has-text('Submit')",
            "button:has-text('Submit')",
            "button[type='submit']",
            *super().submit_selectors(),
        ]

    def plan_steps(self, url: str | None) -> list[dict]:
        steps = super().plan_steps(url)
        steps.insert(1, {"action": "click_apply_button", "target": self.ats_type, "mode": "automated"})
        return steps
