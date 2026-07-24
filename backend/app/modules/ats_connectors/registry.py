from app.modules.ats_connectors.ashby import AshbyConnector
from app.modules.ats_connectors.generic_browser import BaseATSConnector
from app.modules.ats_connectors.greenhouse import GreenhouseConnector
from app.modules.ats_connectors.icims import ICIMSConnector
from app.modules.ats_connectors.lever import LeverConnector
from app.modules.ats_connectors.workday import WorkdayConnector


CONNECTORS = [GreenhouseConnector(), LeverConnector(), AshbyConnector(), WorkdayConnector(), ICIMSConnector()]


def connector_for(url: str | None) -> BaseATSConnector:
    for connector in CONNECTORS:
        if connector.supports(url):
            return connector
    return BaseATSConnector()
