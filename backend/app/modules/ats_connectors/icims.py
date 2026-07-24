from app.modules.ats_connectors.generic_browser import BaseATSConnector, host


class ICIMSConnector(BaseATSConnector):
    ats_type = "icims"

    def supports(self, url: str | None) -> bool:
        value = host(url)
        return "icims.com" in value
