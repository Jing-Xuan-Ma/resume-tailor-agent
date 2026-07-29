from app.modules.ats_connectors.generic_browser import BaseATSConnector


WORKDAY_SUBDOMAINS = ["wd1.", "wd2.", "wd3.", "wd5.", "wd.myday.cloud"]
REVIEW_BUTTON_SELECTORS = [
    "button[data-automation-id='bottom-navigation-next-button']",
    "button[data-automation-id='bottom-navigation-continue-button']",
    "button[aria-label*='Next' i]",
    "button:has-text('Next')",
    "button:has-text('Continue')",
    "button:has-text('Review')",
]


class WorkdayConnector(BaseATSConnector):
    ats_type = "workday"

    def supports(self, url: str | None) -> bool:
        value = (url or "").lower()
        if "myworkdayjobs.com" in value or "workdayjobs.com" in value:
            return True
        for subdomain in WORKDAY_SUBDOMAINS:
            if subdomain in value:
                return True
        return False

    def fields(self) -> list[dict]:
        fields = [field for field in super().fields() if field["name"] != "full_name"]
        fields.insert(0, {"name": "last_name", "type": "text", "required": True, "question": "Last name", "aliases": ["last name", "surname", "family name"]})
        fields.insert(0, {"name": "first_name", "type": "text", "required": True, "question": "First name", "aliases": ["first name", "given name"]})
        fields.extend([
            {"name": "linkedin", "type": "text", "required": False, "question": "LinkedIn Profile", "aliases": ["linkedin", "linkedin profile"]},
            {"name": "source", "type": "select", "required": False, "question": "How did you hear about us?", "options": ["LinkedIn", "Company Website", "Referral", "Other"], "aliases": ["source", "hear about us", "referred by"]},
            {"name": "gender", "type": "select", "required": False, "question": "Gender", "options": ["Male", "Female", "Non-binary", "Prefer not to say"], "aliases": ["gender", "sex"]},
            {"name": "race_ethnicity", "type": "select", "required": False, "question": "Race/Ethnicity", "options": ["Asian", "Black", "Hispanic", "White", "Two or more", "Prefer not to say"], "aliases": ["race", "ethnicity"]},
            {"name": "veteran_status", "type": "select", "required": False, "question": "Veteran Status", "options": ["Yes", "No", "Prefer not to say"], "aliases": ["veteran", "protected veteran"]},
            {"name": "disability_status", "type": "select", "required": False, "question": "Disability Status", "options": ["Yes", "No", "Prefer not to say"], "aliases": ["disability"]},
        ])
        return fields

    def field_selectors(self) -> dict[str, list[str]]:
        selectors = super().field_selectors()
        selectors.update({
            "first_name": [
                "input[data-automation-id*='firstName' i]",
                "input[aria-label*='first name' i]",
                "input[name*='firstName' i]",
                "input[id*='firstName' i]",
            ],
            "last_name": [
                "input[data-automation-id*='lastName' i]",
                "input[aria-label*='last name' i]",
                "input[name*='lastName' i]",
                "input[id*='lastName' i]",
            ],
            "email": [
                "input[data-automation-id*='email' i]",
                "input[type='email']",
                "input[name*='email' i]",
                "input[autocomplete='email']",
            ],
            "phone": [
                "input[data-automation-id*='phone' i]",
                "input[type='tel']",
                "input[aria-label*='phone' i]",
            ],
            "linkedin": [
                "input[data-automation-id*='linkedin' i]",
                "input[aria-label*='linkedin' i]",
                "input[name*='linkedin' i]",
            ],
            "resume": [
                "input[type='file'][data-automation-id*='resume' i]",
                "button[data-automation-id*='resume' i]",
                "input[type='file']",
            ],
            "cover_letter": [
                "input[type='file'][data-automation-id*='cover' i]",
                "button[data-automation-id*='cover' i]",
            ],
            "source": [
                "select[data-automation-id*='source' i]",
                "button[data-automation-id*='source' i]",
                "div[data-automation-id*='source' i]",
                "input[data-automation-id*='source' i]",
            ],
            "gender": [
                "select[data-automation-id*='gender' i]",
                "div[data-automation-id*='gender' i]",
                "fieldset[data-automation-id*='gender' i] label",
            ],
            "race_ethnicity": [
                "select[data-automation-id*='race' i]",
                "select[data-automation-id*='ethnicity' i]",
                "div[data-automation-id*='race' i]",
                "fieldset[data-automation-id*='race' i] label",
            ],
            "veteran_status": [
                "select[data-automation-id*='veteran' i]",
                "div[data-automation-id*='veteran' i]",
                "fieldset[data-automation-id*='veteran' i] label",
            ],
            "disability_status": [
                "select[data-automation-id*='disability' i]",
                "div[data-automation-id*='disability' i]",
                "fieldset[data-automation-id*='disability' i] label",
            ],
            "work_authorization": [
                "select[data-automation-id*='authoriz' i]",
                "div[data-automation-id*='authoriz' i]",
                "fieldset[data-automation-id*='authoriz' i] label",
            ],
        })
        return selectors

    def submit_selectors(self) -> list[str]:
        return [
            *REVIEW_BUTTON_SELECTORS,
            "button[data-automation-id='bottom-navigation-submit-button']",
            "button:has-text('Submit Application')",
            "button:has-text('Submit')",
            *super().submit_selectors(),
        ]

    def plan_steps(self, url: str | None) -> list[dict]:
        return [
            {"action": "open_url", "target": url, "mode": "manual_review"},
            {"action": "detect_form", "target": self.ats_type, "mode": "dry_run"},
            {"action": "fill_supported_fields", "target": "application_form", "mode": "automated"},
            {"action": "navigate_multi_step_form", "target": "next_button", "mode": "automated"},
            {"action": "handle_eeo_questions", "target": "eeo_section", "mode": "automated"},
            {"action": "submit_or_wait_for_confirmation", "target": "submit_button", "mode": "policy_controlled"},
        ]
