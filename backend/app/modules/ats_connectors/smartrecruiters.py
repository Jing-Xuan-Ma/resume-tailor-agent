from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class SmartRecruitersConnector(BaseATSConnector):
    ats_type = "smartrecruiters"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        lower = (url or "").lower()
        return "smartrecruiters.com" in value or "fixture_smartrecruiters" in lower

    def fields(self) -> list[dict]:
        fields = [field for field in super().fields() if field["name"] != "full_name"]
        fields.insert(0, {"name": "last_name", "type": "text", "required": True, "question": "Last name", "aliases": ["last name", "surname"]})
        fields.insert(0, {"name": "first_name", "type": "text", "required": True, "question": "First name", "aliases": ["first name", "given name"]})
        fields.extend([
            {"name": "linkedin", "type": "text", "required": False, "question": "LinkedIn Profile", "aliases": ["linkedin", "linkedin profile"]},
            {"name": "website", "type": "text", "required": False, "question": "Portfolio or Website", "aliases": ["portfolio", "website"]},
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "first_name": [
                "input[name='firstName']",
                "input[id*='firstName' i]",
                "input[aria-label*='first name' i]",
            ],
            "last_name": [
                "input[name='lastName']",
                "input[id*='lastName' i]",
                "input[aria-label*='last name' i]",
            ],
            "email": [
                "input[name='email']",
                "input[type='email']",
                "input[id*='email' i]",
            ],
            "phone": [
                "input[name='mobile']",
                "input[name='phone']",
                "input[type='tel']",
                "input[id*='phone' i]",
            ],
            "linkedin": [
                "input[name*='linkedin' i]",
                "input[id*='linkedin' i]",
                "input[placeholder*='linkedin' i]",
            ],
            "website": [
                "input[name*='website' i]",
                "input[id*='website' i]",
                "input[placeholder*='portfolio' i]",
            ],
            "resume": [
                "input[type='file'][name*='resume' i]",
                "input[type='file']",
                "div[class*='dropzone' i] input[type='file']",
            ],
            "cover_letter": [
                "input[type='file'][name*='cover' i]",
            ],
            "work_authorization": [
                "select[name*='authoriz' i]",
                "div[role='radiogroup'] label:has-text('Yes')",
            ],
        })
        return selectors

    def apply_selectors(self) -> list[str]:
        return [
            "button:has-text('I\\'m interested')",
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
