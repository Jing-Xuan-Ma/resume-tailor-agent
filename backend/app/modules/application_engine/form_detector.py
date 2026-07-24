from app.modules.ats_connectors.registry import connector_for


def detect_form(source_url: str | None) -> dict:
    connector = connector_for(source_url)
    return {"ats_type": connector.ats_type, "fields": connector.fields()}
