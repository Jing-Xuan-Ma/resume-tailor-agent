from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class GreenhouseConnector(BaseATSConnector):
    ats_type = "greenhouse"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        return "greenhouse.io" in value or "greenhouse" in (url or "").lower()

    def fields(self) -> list[dict]:
        fields = [field for field in super().fields() if field["name"] != "full_name"]
        fields.insert(0, {"name": "last_name", "type": "text", "required": True, "question": "Last name", "aliases": ["last name", "surname", "family name"]})
        fields.insert(0, {"name": "first_name", "type": "text", "required": True, "question": "First name", "aliases": ["first name", "given name"]})
        fields.extend([
            {"name": "linkedin", "type": "text", "required": False, "question": "LinkedIn Profile", "aliases": ["linkedin", "linkedin profile"]},
            {"name": "website", "type": "text", "required": False, "question": "Website", "aliases": ["website", "portfolio", "personal website"]},
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "first_name": ["#first_name", "input[name='job_application[first_name]']", "input[id*='first_name' i]"],
            "last_name": ["#last_name", "input[name='job_application[last_name]']", "input[id*='last_name' i]"],
            "email": ["#email", "input[name='job_application[email]']"],
            "phone": ["#phone", "input[name='job_application[phone]']"],
            "resume": ["#resume", "input[type='file'][name*='resume' i]", "input[type='file']"],
            "cover_letter": ["input[type='file'][name*='cover' i]"],
            "linkedin": ["input[name*='linkedin' i]", "input[id*='linkedin' i]"],
            "website": ["input[name*='website' i]", "input[id*='website' i]", "input[name*='portfolio' i]"],
        })
        return selectors

    def submit_selectors(self) -> list[str]:
        return ["#submit_app", "input[type='submit'][value*='Submit' i]", *super().submit_selectors()]
