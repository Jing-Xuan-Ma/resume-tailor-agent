"""Local ATS sandbox fixtures — preferred over live boards for fill-pause dry-runs."""

from __future__ import annotations

from pathlib import Path

from app.modules.ats_connectors.registry import connector_for

_REPO = Path(__file__).resolve().parents[4]

SANDBOX_FIXTURES: dict[str, Path] = {
    "greenhouse": _REPO / "artifacts" / "funnel" / "sprint-i" / "fixture_greenhouse.html",
    "lever": _REPO / "artifacts" / "funnel" / "sprint-i" / "fixture_lever.html",
    "ashby": _REPO / "artifacts" / "funnel" / "agent3" / "fixture_ashby.html",
    "workday": _REPO / "artifacts" / "funnel" / "sprint-j" / "fixture_workday.html",
}


def sandbox_path_for(ats_type: str) -> Path | None:
    path = SANDBOX_FIXTURES.get(ats_type)
    if path and path.exists():
        return path.resolve()
    return None


def sandbox_uri_for(ats_type: str) -> str | None:
    path = sandbox_path_for(ats_type)
    return path.as_uri() if path else None


def resolve_browser_fill_url(
    source_url: str | None,
    *,
    prefer_sandbox: bool = True,
    allow_live: bool | None = None,
) -> dict:
    """Map a posting URL to a fill target.

    Default: sandbox fixtures win. Live URLs only when prefer_sandbox=False and
    allow_live is True (settings.ALLOW_LIVE_BROWSER_FILL). Never submits.
    """
    from app.config import settings

    if allow_live is None:
        allow_live = bool(settings.ALLOW_LIVE_BROWSER_FILL)
    connector = connector_for(source_url)
    ats_type = getattr(connector, "ats_type", None) or "generic"
    use_sandbox = prefer_sandbox or not allow_live
    sandbox = sandbox_uri_for(ats_type) if use_sandbox else None
    if sandbox:
        return {
            "url": sandbox,
            "ats_type": ats_type,
            "sandbox": True,
            "original_url": source_url,
            "fixture_path": str(sandbox_path_for(ats_type)),
            "live_gated": not allow_live,
        }
    if not allow_live:
        return {
            "url": "",
            "ats_type": ats_type,
            "sandbox": False,
            "original_url": source_url,
            "fixture_path": None,
            "live_gated": True,
            "message": "Live URL fill blocked (ALLOW_LIVE_BROWSER_FILL=false).",
        }
    return {
        "url": source_url or "",
        "ats_type": ats_type,
        "sandbox": False,
        "original_url": source_url,
        "fixture_path": None,
        "live_gated": False,
    }
