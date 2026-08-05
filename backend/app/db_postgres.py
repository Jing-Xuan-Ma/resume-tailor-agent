"""Postgres connectivity probe + schema bootstrap for cloud deployments.

Local MVP keeps SQLite (`app.db`). When STORAGE_BACKEND=postgres, callers can
use `get_pg_dsn()` / `ensure_postgres_schema()` against DATABASE_URL.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, unquote

from app.config import settings


def storage_backend() -> str:
    raw = (getattr(settings, "STORAGE_BACKEND", None) or "sqlite").strip().lower()
    return raw if raw in {"sqlite", "postgres"} else "sqlite"


def get_pg_dsn() -> str | None:
    """Return a libpq/psycopg DSN from DATABASE_URL, or None if not postgres."""
    if storage_backend() != "postgres":
        return None
    url = (settings.DATABASE_URL or "").strip()
    if not url:
        return None
    # Accept SQLAlchemy-style postgresql+asyncpg:// → postgresql://
    if url.startswith("postgresql+"):
        url = "postgresql://" + url.split("://", 1)[1]
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def probe_postgres() -> dict[str, Any]:
    dsn = get_pg_dsn()
    if not dsn:
        return {
            "ok": False,
            "backend": storage_backend(),
            "message": "Postgres not selected (STORAGE_BACKEND!=postgres) or DATABASE_URL empty.",
        }
    try:
        import psycopg  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "backend": "postgres",
            "message": f"psycopg not installed: {exc}",
        }
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        parsed = urlparse(dsn)
        return {
            "ok": True,
            "backend": "postgres",
            "host": parsed.hostname,
            "db": (parsed.path or "/").lstrip("/") or None,
            "user": unquote(parsed.username or "") or None,
        }
    except Exception as exc:
        return {"ok": False, "backend": "postgres", "message": str(exc)}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS application_queue (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_id TEXT,
    version_id TEXT,
    source_url TEXT,
    company TEXT,
    position TEXT,
    fill_status TEXT NOT NULL DEFAULT 'queued',
    awaiting_confirm INTEGER NOT NULL DEFAULT 0,
    apply_id TEXT,
    submitted_at TEXT,
    skipped_at TEXT,
    error TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_application_queue_user ON application_queue(user_id, updated_at);
"""


def ensure_postgres_schema() -> dict[str, Any]:
    probe = probe_postgres()
    if not probe.get("ok"):
        return probe
    dsn = get_pg_dsn()
    assert dsn
    import psycopg  # type: ignore

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
    probe["schema"] = "ensured"
    return probe
