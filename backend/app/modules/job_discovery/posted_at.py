"""Extract employer-facing post time from provider metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_DATE_KEYS = (
    "date_posted",
    "DATE_POSTED",
    "publication_date",
    "pubDate",
    "pub_date",
    "created",
    "created_at",
    "date",
    "posted_at",
)


def _parse_one(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # RemoteOK epoch seconds / ms
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    # Numeric string epoch
    if text.isdigit():
        return _parse_one(int(text))
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return None


def extract_posted_at(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    for key in _DATE_KEYS:
        if key in metadata:
            parsed = _parse_one(metadata.get(key))
            if parsed:
                return parsed
    return None


def display_age_iso(*, scraped_at: str | None, metadata: dict[str, Any] | None) -> str:
    """Prefer real post time; fall back to ingest time."""
    posted = extract_posted_at(metadata)
    if posted:
        return posted
    return scraped_at or ""
