"""JR-1: ingest providers into the local job_listings catalog."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import db
from app.modules.job_discovery import job_index


async def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest jobs into local job_listings index")
    parser.add_argument("--query", action="append", default=[], help="Search query (repeatable)")
    parser.add_argument("--location", default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--hours-old", type=int, default=None)
    args = parser.parse_args()

    db.init_db()
    result = await job_index.ingest_queries(
        queries=args.query or None,
        location=args.location,
        limit_per_query=args.limit,
        hours_old=args.hours_old,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
