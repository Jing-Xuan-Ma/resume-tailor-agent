"""Mount the intern-list scrape viewer under the Resume Agent API.

The standalone viewer historically ran on :8101. Embedding it here means the
frontend only needs the main backend (:8000) — no separate process.
"""

from __future__ import annotations

import sys
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

logger = structlog.get_logger()

# resume-tailor-agent/backend/app/modules/intern_list_viewer/mount.py
# parents[4] = resume-tailor-agent → sibling intern-list-scraper
_AGENT_ROOT = Path(__file__).resolve().parents[4]
_SCRAPER_ROOT = _AGENT_ROOT.parent / "intern-list-scraper"
_SCRAPER_SRC = _SCRAPER_ROOT / "src"


def _ensure_scraper_on_path() -> None:
    for path in (_SCRAPER_SRC, _SCRAPER_ROOT):
        text = str(path)
        if path.is_dir() and text not in sys.path:
            sys.path.insert(0, text)


def load_intern_list_viewer_app() -> FastAPI | None:
    """Import the sibling intern-list-scraper viewer FastAPI app, or None."""
    if not _SCRAPER_ROOT.is_dir():
        logger.warning("intern-list-scraper not found; viewer not mounted", path=str(_SCRAPER_ROOT))
        return None
    _ensure_scraper_on_path()
    try:
        from viewer.app import app as viewer_app  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to import intern-list viewer", error=str(exc))
        return None
    return viewer_app


def mount_intern_list_viewer(app: FastAPI) -> bool:
    """Mount viewer at /intern-list. Returns True if mounted."""
    viewer_app = load_intern_list_viewer_app()
    if viewer_app is None:

        @app.get("/intern-list", response_class=HTMLResponse, include_in_schema=False)
        @app.get("/intern-list/", response_class=HTMLResponse, include_in_schema=False)
        async def intern_list_unavailable() -> str:
            return (
                "<!doctype html><html><body style='font-family:sans-serif;padding:2rem'>"
                "<h1>Intern-list viewer unavailable</h1>"
                "<p>Could not load <code>intern-list-scraper/viewer</code> from the project tree.</p>"
                "</body></html>"
            )

        return False

    app.mount("/intern-list", viewer_app)
    logger.info("mounted intern-list viewer", path="/intern-list", scraper=str(_SCRAPER_ROOT))
    return True
