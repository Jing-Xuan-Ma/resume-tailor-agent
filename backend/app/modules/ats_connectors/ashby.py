from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class AshbyConnector(BaseATSConnector):
    ats_type = "ashby"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        return "ashbyhq.com" in value or "jobs.ashbyhq.com" in value

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "full_name": ["input[name='name']", "input[autocomplete='name']"],
            "email": ["input[name='email']", "input[type='email']"],
            "phone": ["input[name='phone']", "input[type='tel']"],
            "linkedin": ["input[name*='linkedin' i]"],
            "website": ["input[name*='website' i]", "input[name*='portfolio' i]"],
        })
        return selectors

    def submit_selectors(self) -> list[str]:
        return ["button:has-text('Submit Application')", "button:has-text('Submit')", *super().submit_selectors()]
