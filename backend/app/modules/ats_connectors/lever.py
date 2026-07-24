from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class LeverConnector(BaseATSConnector):
    ats_type = "lever"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        return "lever.co" in value or "jobs.lever.co" in value

    def fields(self) -> list[dict]:
        fields = super().fields()
        fields.extend([
            {"name": "linkedin", "type": "text", "required": False, "question": "LinkedIn Profile", "aliases": ["linkedin"]},
            {"name": "website", "type": "text", "required": False, "question": "Portfolio or Website", "aliases": ["portfolio", "website"]},
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "full_name": ["input[name='name']", "input[aria-label*='name' i]"],
            "email": ["input[name='email']", "input[type='email']"],
            "phone": ["input[name='phone']", "input[type='tel']"],
            "linkedin": ["input[name*='linkedin' i]"],
            "website": ["input[name*='urls' i]", "input[name*='portfolio' i]", "input[name*='website' i]"],
        })
        return selectors

    def submit_selectors(self) -> list[str]:
        return ["button:has-text('Submit application')", "button:has-text('Submit')", *super().submit_selectors()]
