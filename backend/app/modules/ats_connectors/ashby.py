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
        fields.extend(
            [
                {
                    "name": "linkedin",
                    "type": "text",
                    "required": False,
                    "question": "LinkedIn Profile",
                    "aliases": ["linkedin", "linkedin profile"],
                },
                {
                    "name": "website",
                    "type": "text",
                    "required": False,
                    "question": "Website",
                    "aliases": ["website", "portfolio", "personal website"],
                },
            ]
        )
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update(
            {
                "full_name": ["#name", "input[name='name']", "input[autocomplete='name']"],
                "email": ["#email", "input[name='email']", "input[type='email']"],
                "phone": ["#phone", "input[name='phone']", "input[type='tel']"],
                "linkedin": ["#linkedin", "input[name*='linkedin' i]", "input[id*='linkedin' i]"],
                "website": [
                    "#website",
                    "input[name*='website' i]",
                    "input[name*='portfolio' i]",
                    "input[id*='website' i]",
                ],
            }
        )
        return selectors

    def submit_selectors(self) -> list[str]:
        return [
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
            *super().submit_selectors(),
        ]
