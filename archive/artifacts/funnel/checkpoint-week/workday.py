from app.modules.ats_connectors.generic_browser import BaseATSConnector


class WorkdayConnector(BaseATSConnector):
    ats_type = "workday"

    def supports(self, url: str | None) -> bool:
        value = (url or "").lower()
        return "myworkdayjobs.com" in value or "workdayjobs.com" in value or "wd1." in value or "wd5." in value

    def fields(self) -> list[dict]:
        fields = [field for field in super().fields() if field["name"] != "full_name"]
        fields.insert(0, {"name": "last_name", "type": "text", "required": True, "question": "Last name", "aliases": ["last name", "surname", "family name"]})
        fields.insert(0, {"name": "first_name", "type": "text", "required": True, "question": "First name", "aliases": ["first name", "given name"]})
        fields.append({"name": "source", "type": "select", "required": False, "question": "How did you hear about us?", "options": ["LinkedIn", "Company Website", "Referral", "Other"], "aliases": ["source", "hear about us"]})
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "first_name": ["input[data-automation-id*='firstName' i]", "input[aria-label*='first name' i]"],
            "last_name": ["input[data-automation-id*='lastName' i]", "input[aria-label*='last name' i]"],
            "email": ["input[data-automation-id*='email' i]", "input[type='email']"],
            "phone": ["input[data-automation-id*='phone' i]", "input[type='tel']"],
            "resume": ["input[type='file'][data-automation-id*='resume' i]", "input[type='file']"],
            "cover_letter": ["input[type='file'][data-automation-id*='cover' i]"],
            "source": ["select[data-automation-id*='source' i]", "button[data-automation-id*='source' i]"],
        })
        return selectors

    def submit_selectors(self) -> list[str]:
        return ["button[data-automation-id='bottom-navigation-next-button']", "button:has-text('Submit')", *super().submit_selectors()]
