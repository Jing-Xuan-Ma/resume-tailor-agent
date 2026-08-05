"""
Alembic env — supports both SQLite (default) and PostgreSQL.

Usage:
    # Preview SQL (offline, recommended for review):
    alembic upgrade head --sql

    # Apply to SQLite (local default):
    alembic upgrade head

    # Apply to PostgreSQL:
    DATABASE_URL=postgresql://user:pass@host/db alembic upgrade head
"""

import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, event
from sqlalchemy import pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Resolve database URL ─────────────────────────────────────
# Priority: env var > alembic.ini > fallback
DB_URL = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url", "sqlite:///../data/app.db"))


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _render_item(type_, obj, autogen_context):
    """Custom renderer to handle SQLite vs PostgreSQL differences."""
    return False  # fallback to default


# ── Offline (--sql) ──────────────────────────────────────────
def run_migrations_offline() -> None:
    scripts = []
    context.configure(
        url=DB_URL,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        output_buffer=scripts if not hasattr(context, "output_buffer") else None,
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online ───────────────────────────────────────────────────
def run_migrations_online() -> None:
    connectable = create_engine(DB_URL, poolclass=pool.NullPool)

    if _is_sqlite(DB_URL):
        @event.listens_for(connectable, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,
            render_item=_render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
