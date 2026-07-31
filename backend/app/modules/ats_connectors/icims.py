"""iCIMS connector — thin overlay / fallback.

Login walls and iframe-heavy career sites are common; core-field automation is
not deeply validated here. Prefer Greenhouse + Lever for demoable fills.
"""

from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class ICIMSConnector(BaseATSConnector):
    ats_type = "icims"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        return "icims.com" in value

    def fields(self) -> list[dict]:
        fields = [field for field in super().fields() if field["name"] != "full_name"]
        fields.insert(0, {"name": "last_name", "type": "text", "required": True, "question": "Last name", "aliases": ["last name", "surname", "family name"]})
        fields.insert(0, {"name": "first_name", "type": "text", "required": True, "question": "First name", "aliases": ["first name", "given name"]})
        fields.extend([
            {"name": "linkedin", "type": "text", "required": False, "question": "LinkedIn Profile", "aliases": ["linkedin", "linkedin profile"]},
            {"name": "source", "type": "select", "required": False, "question": "How did you hear about us?", "options": ["LinkedIn", "Company Website", "Referral", "Other"], "aliases": ["source", "referral"]},
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "first_name": [
                "input[name*='firstName' i]",
                "input[id*='firstName' i]",
                "input[name='fname']",
                "input[aria-label*='first name' i]",
            ],
            "last_name": [
                "input[name*='lastName' i]",
                "input[id*='lastName' i]",
                "input[name='lname']",
                "input[aria-label*='last name' i]",
            ],
            "email": [
                "input[name*='email' i]",
                "input[type='email']",
                "input[name='email']",
            ],
            "phone": [
                "input[name*='phone' i]",
                "input[type='tel']",
                "input[name='phone']",
            ],
            "linkedin": [
                "input[name*='linkedin' i]",
                "input[id*='linkedin' i]",
                "input[placeholder*='linkedin' i]",
            ],
            "resume": [
                "input[type='file'][name*='resume' i]",
                "input[type='file'][id*='resume' i]",
                "input[type='file']",
            ],
            "source": [
                "select[name*='source' i]",
                "select[id*='source' i]",
                "select[aria-label*='source' i]",
            ],
            "work_authorization": [
                "select[name*='authoriz' i]",
                "select[id*='authoriz' i]",
                "div[class*='radio'] label:has(input[type='radio'])",
            ],
        })
        return selectors

    def submit_selectors(self) -> list[str]:
        return [
            "input[type='submit'][value*='Submit' i]",
            "button:has-text('Submit')",
            "button:has-text('Next')",
            "button[type='submit']",
            *super().submit_selectors(),
        ]
