"""Adapter registry."""

from __future__ import annotations

from app.modules.job_discovery.apply_resolver.adapters.base import AtsSearchAdapter
from app.modules.job_discovery.apply_resolver.adapters.greenhouse import GreenhouseAdapter
from app.modules.job_discovery.apply_resolver.adapters.lever import LeverAdapter
from app.modules.job_discovery.apply_resolver.adapters.lifeattiktok import LifeAtTikTokAdapter
from app.modules.job_discovery.apply_resolver.adapters.workday import WorkdayAdapter

ADAPTERS: list[AtsSearchAdapter] = [
    WorkdayAdapter(),
    GreenhouseAdapter(),
    LeverAdapter(),
    LifeAtTikTokAdapter(),
]


def adapters_for_hints(hints: dict) -> list[tuple[AtsSearchAdapter, dict]]:
    found: list[tuple[AtsSearchAdapter, dict]] = []
    seen: set[str] = set()
    for adapter in ADAPTERS:
        conn = adapter.detect_hints(hints)
        if not conn:
            continue
        key = f"{adapter.name}:{conn.get('tenant')}:{conn.get('site')}"
        if key in seen:
            continue
        seen.add(key)
        found.append((adapter, conn))
    return found
