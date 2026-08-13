"""Load editable scrape schedule / limits from config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "intern-list.toml"


@dataclass
class ScrapeConfig:
    categories: list[str] = field(
        default_factory=lambda: ["swe", "da", "aiml", "pm", "af", "ba"]
    )
    country: str = "us"
    max_jobs_per_category: int = 1000
    page_size: int = 20
    with_details: bool = True
    details_only_for_new: bool = True
    incremental: bool = True
    sleep_seconds: float = 0.35
    # How many times per day the scheduled job should run (1 or 2 typical).
    times_per_day: int = 1
    # Local hours (24h) when launchd/cron should fire. Length should match times_per_day.
    schedule_hours: list[int] = field(default_factory=lambda: [9])
    db_path: str | None = None


def load_config(path: Path | str | None = None) -> ScrapeConfig:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    data: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open("rb") as f:
            data = tomllib.load(f) or {}
    scrape = data.get("scrape") if isinstance(data.get("scrape"), dict) else data
    hours = scrape.get("schedule_hours")
    if isinstance(hours, list):
        schedule_hours = [int(h) for h in hours]
    else:
        schedule_hours = [9]
    times = int(scrape.get("times_per_day", len(schedule_hours) or 1))
    if times < 1:
        times = 1
    if len(schedule_hours) < times:
        # pad with evenly spaced hours if user only set times_per_day
        schedule_hours = list(schedule_hours) + [
            (9 + i * (12 // max(times, 1))) % 24 for i in range(len(schedule_hours), times)
        ]
    schedule_hours = schedule_hours[:times]
    return ScrapeConfig(
        categories=list(scrape.get("categories") or ["swe", "da", "aiml", "pm", "af", "ba"]),
        country=str(scrape.get("country") or "us"),
        max_jobs_per_category=int(scrape.get("max_jobs_per_category") or 1000),
        page_size=int(scrape.get("page_size") or 20),
        with_details=bool(scrape.get("with_details", True)),
        details_only_for_new=bool(scrape.get("details_only_for_new", True)),
        incremental=bool(scrape.get("incremental", True)),
        sleep_seconds=float(scrape.get("sleep_seconds") or 0.35),
        times_per_day=times,
        schedule_hours=schedule_hours,
        db_path=scrape.get("db_path"),
    )
