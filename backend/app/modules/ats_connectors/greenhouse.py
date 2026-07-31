from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class GreenhouseConnector(BaseATSConnector):
    """Greenhouse board connector tuned for core application fields.

    Validated against real Greenhouse pages (SpaceX / AppDirect, 2026-07-29):
    first_name, last_name, email, phone, resume, cover_letter via #id selectors;
    LinkedIn via label "LinkedIn Profile". Workday/iCIMS remain thinner overlays.
    """

    ats_type = "greenhouse"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        text = (url or "").lower()
        return (
            "greenhouse.io" in value
            or "boards.greenhouse.io" in text
            or "job-boards.greenhouse.io" in text
        )

    def fields(self) -> list[dict]:
        fields = [field for field in super().fields() if field["name"] != "full_name"]
        fields.insert(0, {
            "name": "last_name",
            "type": "text",
            "required": True,
            "question": "Last name",
            "aliases": ["last name", "surname", "family name"],
        })
        fields.insert(0, {
            "name": "first_name",
            "type": "text",
            "required": True,
            "question": "First name",
            "aliases": ["first name", "given name"],
        })
        fields.extend([
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
                "question": "Website",
                "aliases": ["website", "portfolio", "personal website"],
            },
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "first_name": [
                "#first_name",
                "input[name='job_application[first_name]']",
                "input[id*='first_name' i]",
                "input[autocomplete='given-name']",
            ],
            "last_name": [
                "#last_name",
                "input[name='job_application[last_name]']",
                "input[id*='last_name' i]",
                "input[autocomplete='family-name']",
            ],
            "email": [
                "#email",
                "input[name='job_application[email]']",
                "input[type='email']",
                "input[autocomplete='email']",
            ],
            "phone": [
                "#phone",
                "input[name='job_application[phone]']",
                "input[type='tel']",
                "input[autocomplete='tel']",
            ],
            "resume": [
                "#resume",
                "input[type='file'][name*='resume' i]",
                "input[type='file'][id*='resume' i]",
                "#resume_fieldset input[type='file']",
            ],
            "cover_letter": [
                "#cover_letter",
                "textarea#cover_letter",
                "textarea[name*='cover_letter' i]",
                "input[type='file'][name*='cover' i]",
                "input[type='file'][id*='cover' i]",
            ],
            # Custom GH questions often use question_<id>; label fallback still helps.
            "linkedin": [
                "input[name*='linkedin' i]",
                "input[id*='linkedin' i]",
                "input[aria-label*='linkedin' i]",
                "label:has-text('LinkedIn') + input",
                "label:has-text('LinkedIn Profile') + input",
            ],
            "website": [
                "input[name*='website' i]",
                "input[id*='website' i]",
                "input[name*='portfolio' i]",
                "input[aria-label*='website' i]",
                "input[aria-label*='portfolio' i]",
            ],
        })
        return selectors

    def apply_selectors(self) -> list[str]:
        return [
            "a:has-text('Apply')",
            "button:has-text('Apply')",
            "a:has-text('Apply for this job')",
            "button:has-text('Apply for this job')",
            "[data-qa='btn-apply']",
        ]

    def submit_selectors(self) -> list[str]:
        return [
            "#submit_app",
            "input#submit_app",
            "input[type='submit'][value*='Submit' i]",
            "button:has-text('Submit Application')",
            *super().submit_selectors(),
        ]

    def plan_steps(self, url: str | None) -> list[dict]:
        steps = super().plan_steps(url)
        steps.insert(1, {"action": "click_apply_button", "target": self.ats_type, "mode": "automated"})
        return steps
