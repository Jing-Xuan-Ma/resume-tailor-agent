#!/usr/bin/env python3
"""
Export all data from SQLite to JSON for migration to PostgreSQL.

Usage:
    python scripts/export_sqlite.py [--db PATH] [--output PATH]

    # Default: exports data/app.db to data/export.json
    python scripts/export_sqlite.py

    # To PostgreSQL:
    # 1. python scripts/export_sqlite.py
    # 2. alembic upgrade head  (creates PG schema)
    # 3. python scripts/import_pg.py data/export.json
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


SKIP_TABLES = {"alembic_version"}

TABLE_ORDER = [
    "users",
    "resumes",
    "tailored_resumes",
    "drafts",
    "conversation_turns",
    "user_profiles",
    "events",
    "jobs",
    "job_bookmarks",
    "application_runs",
    "cover_letters",
    "application_audit_logs",
    "outreach_messages",
    "growth_plans",
    "job_history",
    "jd_sessions",
    "resume_versions",
    "resume_templates",
]


def export_sqlite(db_path: str) -> dict[str, list[dict]]:
    data: dict[str, list[dict]] = {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        for row in tables:
            table = row["name"]
            if table in SKIP_TABLES:
                continue
            rows = conn.execute(f"SELECT * FROM [{table}]").fetchall()
            data[table] = [dict(r) for r in rows]
            print(f"  {table}: {len(data[table])} rows", file=sys.stderr)
    finally:
        conn.close()
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Export SQLite data to JSON")
    parser.add_argument("--db", default=str(Path(__file__).resolve().parents[1] / ".." / "data" / "app.db"))
    parser.add_argument("--output", default=str(Path(__file__).resolve().parents[1] / ".." / "data" / "export.json"))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Exporting from: {db_path}", file=sys.stderr)
    data = export_sqlite(str(db_path))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    total = sum(len(rows) for rows in data.values())
    print(f"\nExported {total} rows across {len(data)} tables to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
