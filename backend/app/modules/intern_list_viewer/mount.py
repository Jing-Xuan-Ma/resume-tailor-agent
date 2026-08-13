"""Mount the intern-list scrape viewer under the Resume Agent API."""

from __future__ import annotations

import structlog
from fastapi import FastAPI

logger = structlog.get_logger()


def mount_intern_list_viewer(app: FastAPI) -> bool:
    """Mount viewer at /intern-list. Returns True if mounted."""
    from app.modules.intern_list_viewer.app import app as viewer_app

    app.mount("/intern-list", viewer_app)
    logger.info("mounted intern-list viewer", path="/intern-list")
    return True
