#!/usr/bin/env python3
"""
Import exported JSON data into PostgreSQL.

Usage:
    DATABASE_URL=postgresql://user:pass@host/dbname python scripts/import_pg.py data/export.json
"""

import argparse
import json
import os
import sys

import psycopg2


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


def import_data(pg_url: str, data: dict[str, list[dict]]) -> None:
    conn = psycopg2.connect(pg_url)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        for table in TABLE_ORDER:
            rows = data.get(table, [])
            if not rows:
                continue
            columns = list(rows[0].keys())
            placeholders = ", ".join(["%s"] * len(columns))
            col_names = ", ".join(f'"{c}"' for c in columns)
            insert_sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})'

            for row in rows:
                values = [row.get(c) for c in columns]
                try:
                    cur.execute(insert_sql, values)
                except Exception as e:
                    print(f"  ERROR inserting into {table}: {e}", file=sys.stderr)
                    print(f"  Values: {values[:3]}...", file=sys.stderr)
                    conn.rollback()
                    raise

            print(f"  {table}: {len(rows)} rows imported", file=sys.stderr)

        conn.commit()
        print("\nAll data imported successfully!", file=sys.stderr)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import JSON into PostgreSQL")
    parser.add_argument("input", help="Path to JSON file (from export_sqlite.py)")
    parser.add_argument("--pg-url", default=os.getenv("DATABASE_URL"), help="PostgreSQL connection URL")
    args = parser.parse_args()

    pg_url = args.pg_url
    if not pg_url:
        print("Error: set DATABASE_URL env var or pass --pg-url", file=sys.stderr)
        sys.exit(1)

    with open(args.input) as f:
        data = json.load(f)

    total = sum(len(rows) for rows in data.values())
    print(f"Importing {total} rows across {len(data)} tables to PostgreSQL...", file=sys.stderr)
    import_data(pg_url, data)


if __name__ == "__main__":
    main()
